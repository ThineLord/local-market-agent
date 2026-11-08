"""Offline synthetic checks for model gates and exact event mapping."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from local_market_agent.adapters.kalshi import KalshiAdapter
from local_market_agent.config import Settings
from local_market_agent.nba_guard import VALIDATION_KEYS, forecast_gate
from local_market_agent.nba_probability import MODEL_SPEC, home_probability
from local_market_agent.nba_workflow import SECONDARY_RULE, build_nba_packet, match_event
from local_market_agent.paper.execution import PaperExecutionService
from local_market_agent.risk import RiskEngine
from local_market_agent.risk.preflight import preflight
from local_market_agent.schemas.models import EvidenceItem, ResearchBrief
from local_market_agent.strategy import PredictionMarketEdgeStrategy

NOW = datetime(2026, 11, 8, 19, tzinfo=UTC)


def example():
    market = {
        "ticker": "KXNBAGAME-26NOV08NOPLAC-LAC",
        "event_ticker": "KXNBAGAME-26NOV08NOPLAC",
        "yes_sub_title": "Los Angeles C",
        "rules_secondary": SECONDARY_RULE,
        "title": "Los Angeles C wins",
        "rules_primary": "If Los Angeles C wins the New Orleans vs Los Angeles C Pro Basketball game originally scheduled for Nov 8, 2026, then the market resolves to Yes.",
        "status": "active",
        "market_type": "binary",
        "yes_bid_dollars": "0.44",
        "yes_ask_dollars": "0.46",
        "yes_bid_size_fp": "1000",
        "yes_ask_size_fp": "1000",
        "notional_value_dollars": "1.0000",
    }
    event = {
        "id": "synthetic-game",
        "date": (NOW + timedelta(seconds=60)).isoformat(),
        "season": {"year": 2027, "type": 2},
        "competitions": [
            {
                "id": "synthetic-game",
                "type": {"id": "1"},
                "timeValid": True,
                "neutralSite": False,
                "status": {"type": {"state": "pre", "completed": False}},
                "competitors": [{"id": "12", "homeAway": "home"}, {"id": "3", "homeAway": "away"}],
            }
        ],
    }
    return market, event


def model_example():
    market, event = example()
    snapshot = KalshiAdapter().normalize_market(market).model_copy(update={"as_of": NOW})
    match = match_event(market, [(event, NOW)], now=NOW)
    p = home_probability({"12": 1550.0, "3": 1500.0}, "12", "3")
    validation = {
        "checks": dict.fromkeys(VALIDATION_KEYS, True),
        "passed": True,
        "warmup_n": 2460,
        "holdout_n": 1230,
        "brier": 0.21,
        "baseline_brier": 0.25,
        "logloss": 0.61,
        "baseline_logloss": 0.69,
        "ece": 0.03,
        "paired_delta_brier_bootstrap_95": [-0.04, -0.02],
        "bins": [{"n": 100} for _ in range(10)],
    }
    support = {
        "raw_probability_home": p,
        "side": "BUY_YES",
        "cost_per_contract": 0.461461,
        "required_edge": 0.08,
        "raw_net_edge": p - 0.461461,
        "home_bin": int(p * 10),
        "bin_n": 100,
        "stress_net_edge_bootstrap_95": [0.10, 0.20],
        "enough_bin_data": True,
        "conservative_edge_passed": True,
        "edge_support_fraction": 0.999,
    }
    proof = {
        "model_spec": deepcopy(MODEL_SPEC),
        "market_id": snapshot.market.market_id,
        "snapshot_id": snapshot.snapshot_id,
        "last_season": 2027,
        "event_start": match["event_start"],
        "event_observed_at": NOW.isoformat(),
        "event_state": "pre",
        "current_history_oldest_retrieval": NOW.isoformat(),
        "validation": validation,
        "match": match,
        "home_rating": 1550.0,
        "away_rating": 1500.0,
        "support": support,
        "input_checks": dict.fromkeys(
            [
                "source_hashes",
                "complete_history",
                "pregame_identity",
                "unit_dollar_rules",
                "current_history",
                "holdout_validation",
                "bin_support",
                "conservative_edge",
            ],
            True,
        ),
    }
    evidence = [
        EvidenceItem(
            source="Synthetic model gate test",
            title="Fixture validation",
            url="synthetic://validation",
            published_at=NOW,
            retrieved_at=NOW,
            summary="Synthetic test only",
            relevance_score=1,
            credibility_score=1,
            metadata={"model": MODEL_SPEC["model"], "nba_forecast": proof},
        ),
        EvidenceItem(
            source="Synthetic event test",
            title="Fixture event",
            url="synthetic://event",
            published_at=NOW,
            retrieved_at=NOW,
            summary="Synthetic test only",
            relevance_score=1,
            credibility_score=1,
        ),
    ]
    brief = ResearchBrief(
        market_id=snapshot.market.market_id,
        snapshot_id=snapshot.snapshot_id,
        created_at=NOW,
        thesis="Synthetic",
        uncertainty_notes=["Synthetic fixture only"],
        rationale="Synthetic",
        evidence=evidence,
        confidence=0.999,
        evidence_quality=1,
        estimated_probability=p,
        market_implied_probability=snapshot.market_implied_probability,
        recommended_action="paper_buy_yes",
        resolution_source="synthetic://resolution",
    )
    return snapshot, brief, brief.evidence[0].metadata["nba_forecast"]


def test_exact_pregame_mapping_and_no_network_without_opt_in(tmp_path):
    market, event = example()
    match = match_event(market, [(event, NOW)], now=NOW)
    assert match["yes_team_id"] == "12" and match["away_id"] == "3"
    with pytest.raises(ValueError, match="allow-network"):
        build_nba_packet(tmp_path / "out", tmp_path / "history")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "mutation", ["wrong_team", "wording", "season", "live", "time_unknown", "duplicate", "stale"]
)
def test_mapping_fails_closed(mutation):
    market, event = example()
    observed = NOW
    if mutation == "wrong_team":
        market["ticker"] += "-BAD"
    if mutation == "wording":
        market["rules_primary"] += " Different cancellation policy."
    if mutation == "season":
        event["season"]["year"] = 2026
    if mutation == "live":
        event["competitions"][0]["status"]["type"]["state"] = "in"
    if mutation == "time_unknown":
        event["competitions"][0]["timeValid"] = False
    if mutation == "stale":
        observed -= timedelta(seconds=301)
    events = [(event, observed)] * (2 if mutation == "duplicate" else 1)
    with pytest.raises(ValueError):
        match_event(market, events, now=NOW)


@pytest.mark.parametrize(
    "mutation",
    [
        "lower_edge",
        "holdout",
        "bin",
        "history",
        "event",
        "probability",
        "cost",
        "nan",
        "quality",
        "missing",
    ],
)
def test_model_proof_blocks_failed_or_inconsistent_inputs(mutation):
    snapshot, brief, proof = model_example()
    assert forecast_gate(snapshot, brief, Settings(), NOW) == (True, [])
    if mutation == "lower_edge":
        proof["support"]["stress_net_edge_bootstrap_95"][0] = 0.079
    if mutation == "holdout":
        proof["validation"]["brier"] = 0.26
    if mutation == "bin":
        proof["support"]["bin_n"] = 101
    if mutation == "history":
        proof["current_history_oldest_retrieval"] = (NOW - timedelta(hours=7)).isoformat()
    if mutation == "event":
        proof["event_start"] = NOW.isoformat()
    if mutation == "probability":
        brief.estimated_probability = 0.99
    if mutation == "cost":
        proof["support"]["cost_per_contract"] -= 0.01
    if mutation == "nan":
        proof["home_rating"] = float("nan")
    if mutation == "quality":
        proof["input_checks"]["source_hashes"] = False
    if mutation == "missing":
        del proof["validation"]
    assert forecast_gate(snapshot, brief, Settings(), NOW)[0] is False
    assert any(
        c.code == "nba_model_gate" and not c.passed
        for c in preflight(snapshot, brief, Settings(), NOW)
    )


def test_game_start_blocks_approval_and_execution_even_with_fresh_quote(repo):
    snapshot, brief, _ = model_example()
    settings = Settings(db_path=repo.db_path)
    signal = PredictionMarketEdgeStrategy(settings.risk).generate_signal(brief, snapshot)
    risk = RiskEngine(settings.risk).evaluate_signal(signal, open_positions=0)
    service = PaperExecutionService(repo, settings)
    intent = service.prepare(signal, risk, snapshot, brief, now=NOW)
    with pytest.raises(ValueError, match="pregame"):
        service.approve(
            intent.intent_id,
            actor="synthetic-reviewer",
            reason="test",
            now=NOW + timedelta(seconds=60),
        )
    service.approve(intent.intent_id, actor="synthetic-reviewer", reason="test", now=NOW)
    result = service.execute(intent.intent_id, now=NOW + timedelta(seconds=60))
    assert result["status"] == "rejected"
    assert repo.count("paper_orders") == repo.count("paper_fills") == 0


@pytest.mark.parametrize(
    "mutation", ["rating", "payout", "payout_bool", "series", "prerequisite", "secondary"]
)
def test_source_bound_packet_recomputes_and_rejects_forged_probability(
    tmp_path, monkeypatch, mutation
):
    import hashlib
    import json

    from test_nba_history import history_files
    from test_nba_probability import final_event

    from local_market_agent.evidence_packet import load_packet, packet_status

    history = tmp_path / "history"
    receipts = history_files(history)
    for record in receipts:
        if record["team_id"] in {"1", "2"}:
            event = final_event()
            season = record["season"]
            event["id"] = "fixture-" + str(season)
            event["season"]["year"] = season
            event["date"] = f"{season - 1}-10-20T18:00:00Z"
            raw = json.dumps({"team": {"id": record["team_id"]}, "events": [event]}).encode()
            (history / record["path"]).write_bytes(raw)
            record["sha256"] = hashlib.sha256(raw).hexdigest()
    (history / "receipts.json").write_text(json.dumps(receipts))
    market, event = example()

    def get(url):
        if "scoreboard?dates=20261108" in url:
            return {"events": [event]}
        if "scoreboard?" in url:
            return {"events": []}
        if "/series/" in url:
            return {
                "series": {
                    "ticker": "KXNBAGAME",
                    "settlement_sources": [
                        {"name": "the Governing League", "url": "https://www.nba.com"}
                    ],
                }
            }
        if "/markets?" in url:
            return {"markets": [market]}
        if url.endswith("/orderbook"):
            return {"orderbook": {}}
        return {"market": market}

    monkeypatch.setattr("local_market_agent.nba_workflow.safe_get_json", get)
    monkeypatch.setattr("local_market_agent.public_screen.safe_get_json", get)
    monkeypatch.setattr("local_market_agent.nba_workflow.utc_now", lambda: NOW)
    monkeypatch.setattr("local_market_agent.public_screen.utc_now", lambda: NOW)
    path = build_nba_packet(tmp_path / "out", history, allow_network=True)
    status = packet_status(path)
    assert status["source_count"] == 130
    assert not status["preflight_ready"]  # tiny history must stay blocked
    packet = load_packet(path)
    if mutation == "rating":
        packet.evidence[0].metadata["nba_forecast"]["home_rating"] += 100
        packet.brief.evidence[0].metadata["nba_forecast"]["home_rating"] += 100
    elif mutation == "prerequisite":
        packet.evidence[0].metadata["nba_forecast"]["input_checks"]["complete_history"] = True
        packet.brief.evidence[0].metadata["nba_forecast"]["input_checks"]["complete_history"] = True
    else:
        sid = "series" if mutation == "series" else "market"
        receipt = next(s for s in packet.sources if s.source_id == sid)
        source_path = path.parent / receipt.path
        payload = json.loads(source_path.read_text())
        if mutation == "series":
            payload["series"]["settlement_sources"] = []
        elif mutation == "secondary":
            payload["market"]["rules_secondary"] = "Different cancellation rules"
        else:
            payload["market"]["notional_value_dollars"] = (
                True if mutation == "payout_bool" else "2.0000"
            )
        source_path.write_text(json.dumps(payload))
        receipt.sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    path.write_text(packet.model_dump_json())
    with pytest.raises(ValueError):
        load_packet(path)
