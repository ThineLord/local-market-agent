from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from local_market_agent.adapters import FixtureAdapter
from local_market_agent.config import RiskConfig
from local_market_agent.nba_probability import (
    TEAM_IDS,
    Game,
    candidate_support,
    chronological_predictions,
    home_probability,
    parse_final,
    validate_predictions,
    wilson,
)

NOW = datetime(2026, 11, 8, 19, tzinfo=UTC)


def game(i, *, days=0, season=2026):
    return Game(str(i), season, NOW - timedelta(days=days), "1", "2", False, 110, 100)


def test_current_outcomes_do_not_change_holdout_and_no_self_leakage():
    games = [
        game(1, days=500, season=2025),
        game(2, days=300),
        game(3, days=299),
        game(4, days=1, season=2027),
    ]
    rows, _, _ = chronological_predictions(games, cutoff=NOW)
    altered = [replace(g, home_score=90) if g.season == 2027 else g for g in games]
    other, _, _ = chronological_predictions(altered, cutoff=NOW)
    assert rows[:-1] == other[:-1]
    altered = [replace(g, home_score=90) if g.game_id == "2" else g for g in games]
    other, _, _ = chronological_predictions(altered, cutoff=NOW)
    assert rows[1]["probability_home"] == other[1]["probability_home"]
    # The next UTC day's prediction still cannot use that game's outcome.
    assert rows[2]["probability_home"] == other[2]["probability_home"]


def test_two_day_lag_and_season_reversion():
    g = game(1, days=1)
    _, early, state = chronological_predictions([g], cutoff=NOW)
    assert state["pending_lagged_updates"] == 1 and early["1"] == 1500
    _, late, state = chronological_predictions([g], cutoff=NOW + timedelta(days=2))
    assert state["pending_lagged_updates"] == 0 and late["1"] > 1500
    future = replace(game(2), start=NOW + timedelta(days=40), season=2027)
    rows, _, _ = chronological_predictions([g, future], cutoff=future.start + timedelta(hours=1))
    expected = {t: 1500 + 0.75 * (r - 1500) for t, r in late.items()}
    assert rows[-1]["probability_home"] == home_probability(expected, "1", "2")


def test_prediction_inputs_fail_closed():
    with pytest.raises(ValueError, match="Duplicate"):
        chronological_predictions([game(1, days=3)] * 2, cutoff=NOW)
    with pytest.raises(ValueError, match="future"):
        chronological_predictions([game(1)], cutoff=NOW)
    with pytest.raises(ValueError, match="Timezone"):
        chronological_predictions([], cutoff=NOW.replace(tzinfo=None))


def predictions():
    return [
        {
            "game_id": str(i),
            "season": 2026,
            "day": str(i // 5),
            "probability_home": 0.35,
            "outcome_home": int(i % 20 < 7),
        }
        for i in range(200)
    ]


def test_support_uses_actual_side_cost_and_is_symmetric():
    snap = (
        FixtureAdapter()
        .fetch_snapshot()
        .model_copy(update={"best_bid": 0.09, "best_ask": 0.11, "market_implied_probability": 0.1})
    )
    yes = candidate_support(predictions(), 0.35, True, snap, RiskConfig())
    inverted = snap.model_copy(
        update={"best_bid": 0.89, "best_ask": 0.91, "market_implied_probability": 0.9}
    )
    no = candidate_support(predictions(), 0.35, False, inverted, RiskConfig())
    assert yes["side"] == "BUY_YES" and no["side"] == "BUY_NO"
    assert yes["cost_per_contract"] == pytest.approx(0.111 * 1.001)
    assert yes["edge_support_fraction"] == no["edge_support_fraction"]
    assert yes["stress_net_edge_bootstrap_95"] == pytest.approx(no["stress_net_edge_bootstrap_95"])
    assert yes["conservative_edge_passed"]
    assert candidate_support(predictions(), 0.35, True, snap, RiskConfig()) == yes
    assert not candidate_support(predictions()[:20], 0.35, True, snap, RiskConfig())[
        "conservative_edge_passed"
    ]


@pytest.mark.parametrize("p", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_probability_rejected(p):
    with pytest.raises(ValueError, match="Finite"):
        candidate_support(predictions(), p, True, FixtureAdapter().fetch_snapshot(), RiskConfig())


def test_validation_failure_is_explicit_not_rescored():
    rows = predictions() + [{**r, "season": 2025} for r in predictions()]
    v = validate_predictions(rows, {"complete_historical_seasons": False})
    assert not v["passed"] and not v["checks"]["holdout_size"]
    assert sum(b["n"] for b in v["bins"]) == 200
    assert len(TEAM_IDS) == 30 and wilson(0, 0) == [0, 1]


def final_event():
    return {
        "id": "game",
        "date": "2026-11-01T01:00Z",
        "season": {"year": 2027},
        "seasonType": {"type": 2},
        "competitions": [
            {
                "type": {"id": "1"},
                "status": {"type": {"completed": True, "state": "post"}},
                "neutralSite": False,
                "competitors": [
                    {"id": "1", "homeAway": "home", "score": {"value": 110}, "winner": True},
                    {"id": "2", "homeAway": "away", "score": {"value": 100}, "winner": False},
                ],
            }
        ],
    }


def test_history_parser_filters_cup_and_validates_final_scores():
    event = final_event()
    result, reason = parse_final(event, 2027, "1", NOW)
    assert result.outcome == 1 and reason is None
    event["competitions"][0]["type"]["id"] = "39"
    assert parse_final(event, 2027, "1", NOW)[1] == "non_standard_game_including_cup_final"
    event = final_event()
    event["competitions"][0]["competitors"][0]["winner"] = False
    with pytest.raises(ValueError, match="Winner"):
        parse_final(event, 2027, "1", NOW)
    with pytest.raises(ValueError, match="season"):
        parse_final(final_event(), 2026, "1", NOW)
