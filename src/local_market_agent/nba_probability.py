"""Fixed NBA Elo with chronological retrospective validation, not price fitting."""

import hashlib
import heapq
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean

MODEL_SPEC = {
    "model": "nba_fixed_elo_v1",
    "initial_rating": 1500,
    "k": 20,
    "scale": 400,
    "home_advantage": 65,
    "season_retention": 0.75,
    "result_update_lag_utc_days": 2,
    "warmup_seasons": [2024, 2025],
    "holdout_season": 2026,
    "forward_season": 2027,
    "minimum_warmup_games": 2300,
    "minimum_holdout_games": 1100,
    "ece_bins": 10,
    "maximum_ece": 0.05,
    "minimum_current_bin_games": 50,
    "bootstrap_iterations": 1000,
    "bootstrap_seed": 20261109,
}
TEAM_IDS = {str(i) for i in range(1, 31)}


def parse_time(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone required")
    return result.astimezone(UTC)


@dataclass(frozen=True)
class Game:
    game_id: str
    season: int
    start: datetime
    home: str
    away: str
    neutral: bool
    home_score: int
    away_score: int

    @property
    def outcome(self):
        return int(self.home_score > self.away_score)

    @property
    def available_after(self):
        # Conservative lag for retrospective reconstruction. This is not a
        # claimed historical publication timestamp or a point-in-time archive.
        return self.start.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2)


def parse_final(event, requested_season, requested_team, cutoff):
    if int(event["season"]["year"]) != requested_season:
        raise ValueError("Event season mismatch; top-level schedule season is not authoritative")
    if int(event["seasonType"]["type"]) != 2:
        return None, "non_regular_season"
    if len(event["competitions"]) != 1:
        raise ValueError("Ambiguous competition")
    c = event["competitions"][0]
    if c["type"]["id"] != "1":
        return None, "non_standard_game_including_cup_final"
    state = c["status"]["type"]
    if state.get("completed") is not True or state.get("state") != "post":
        return None, "not_final"
    start = parse_time(event["date"])
    if (
        not datetime(requested_season - 1, 10, 1, tzinfo=UTC)
        <= start
        < datetime(requested_season, 7, 1, tzinfo=UTC)
    ):
        raise ValueError("Game date outside the requested NBA season")
    if start >= cutoff:
        raise ValueError("Completed game cannot start in the future")
    if len(c["competitors"]) != 2 or not isinstance(c.get("neutralSite"), bool):
        raise ValueError("Two competitors and explicit neutral-site flag required")
    home = next(t for t in c["competitors"] if t["homeAway"] == "home")
    away = next(t for t in c["competitors"] if t["homeAway"] == "away")
    ids = {home["id"], away["id"]}
    if len(ids) != 2 or not ids <= TEAM_IDS or requested_team not in ids:
        raise ValueError("Team identity mismatch")
    scores = [float(t["score"]["value"]) for t in (home, away)]
    if (
        any(not math.isfinite(s) or s <= 0 or not s.is_integer() for s in scores)
        or scores[0] == scores[1]
    ):
        raise ValueError("Final NBA scores must be positive distinct integers")
    if home.get("winner") != (scores[0] > scores[1]) or away.get("winner") != (
        scores[1] > scores[0]
    ):
        raise ValueError("Winner disagrees with final score")
    return Game(
        str(event["id"]),
        requested_season,
        start,
        home["id"],
        away["id"],
        c["neutralSite"],
        int(scores[0]),
        int(scores[1]),
    ), None


def load_history(directory, *, now=None):
    directory = Path(directory).resolve()
    now = now or datetime.now(UTC)
    protocol = json.loads((directory / "protocol.json").read_text())
    if any(protocol.get(k) != v for k, v in MODEL_SPEC.items()):
        raise ValueError("History protocol does not match the frozen model specification")
    frozen = parse_time(protocol["frozen_at"])
    receipts = json.loads((directory / "receipts.json").read_text())
    expected = {(s, t) for s in (2024, 2025, 2026, 2027) for t in TEAM_IDS}
    if (
        len(receipts) != len(expected)
        or {(r["season"], r["team_id"]) for r in receipts} != expected
    ):
        raise ValueError("All 120 season/team source receipts are required")
    games, appearances, excluded, verified = {}, Counter(), Counter(), []
    for receipt in receipts:
        season, team = receipt["season"], receipt["team_id"]
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team}/schedule?season={season}&seasontype=2"
        path = (directory / receipt["path"]).resolve()
        if (
            not path.is_relative_to(directory)
            or not path.is_file()
            or path.stat().st_size > 5_000_000
        ):
            raise ValueError("History source path/size invalid")
        raw = path.read_bytes()
        retrieved = parse_time(receipt["retrieved_at"])
        if (
            receipt["url"] != url
            or not frozen <= retrieved <= now
            or hashlib.sha256(raw).hexdigest() != receipt["sha256"]
        ):
            raise ValueError("History source receipt hash, URL or time mismatch")
        payload = json.loads(raw)
        if payload["team"]["id"] != team:
            raise ValueError("Schedule team mismatch")
        per_page_ids = set()
        for event in payload["events"]:
            if event["id"] in per_page_ids:
                raise ValueError("Duplicate game within one team schedule")
            per_page_ids.add(event["id"])
            game, reason = parse_final(event, season, team, now)
            if game is None:
                excluded[f"{season}:{reason}"] += 1
                continue
            if game.game_id in games and games[game.game_id] != game:
                raise ValueError("Conflicting duplicate final game")
            games[game.game_id] = game
            appearances[game.game_id] += 1
        verified.append(receipt)
    if any(n != 2 for n in appearances.values()):
        raise ValueError("Every final game must appear consistently in both team schedules")
    counts = {}
    for season in (2024, 2025, 2026, 2027):
        selected = [g for g in games.values() if g.season == season]
        team_counts = Counter(t for g in selected for t in (g.home, g.away))
        counts[str(season)] = {
            "unique_games": len(selected),
            "team_games": {t: team_counts[t] for t in sorted(TEAM_IDS, key=int)},
        }
    complete = all(
        counts[str(s)]["unique_games"] == 1230
        and all(n == 82 for n in counts[str(s)]["team_games"].values())
        for s in (2024, 2025, 2026)
    )
    audit = {
        "source_count": len(verified),
        "seasons": counts,
        "excluded_source_rows": dict(excluded),
        "complete_historical_seasons": complete,
        "retrospective_not_point_in_time": True,
        "latest_retrieval": max(parse_time(r["retrieved_at"]) for r in verified).isoformat(),
        "current_history_oldest_retrieval": min(
            parse_time(r["retrieved_at"]) for r in verified if r["season"] == 2027
        ).isoformat(),
        "source_manifest_sha256": hashlib.sha256(
            (directory / "receipts.json").read_bytes()
        ).hexdigest(),
        "protocol_sha256": hashlib.sha256((directory / "protocol.json").read_bytes()).hexdigest(),
    }
    return sorted(games.values(), key=lambda g: (g.start, g.game_id)), audit


def home_probability(ratings, home, away, neutral=False):
    if home not in ratings or away not in ratings or home == away:
        raise ValueError("Known distinct teams required")
    difference = ratings[home] - ratings[away] + (0 if neutral else MODEL_SPEC["home_advantage"])
    return 1 / (1 + 10 ** (-difference / MODEL_SPEC["scale"]))


def chronological_predictions(games, *, cutoff):
    if cutoff.tzinfo is None:
        raise ValueError("Timezone required for model cutoff")
    ratings = dict.fromkeys(TEAM_IDS, float(MODEL_SPEC["initial_rating"]))
    pending, predictions = [], []
    season = None
    seen = set()

    def apply_ready(at):
        while pending and pending[0][0] <= at:
            _, _, game, probability = heapq.heappop(pending)
            delta = MODEL_SPEC["k"] * (game.outcome - probability)
            ratings[game.home] += delta
            ratings[game.away] -= delta

    for game in sorted(games, key=lambda g: (g.start, g.game_id)):
        if game.game_id in seen or game.start >= cutoff:
            raise ValueError("Duplicate/future game in chronological inputs")
        seen.add(game.game_id)
        apply_ready(game.start)
        if season != game.season:
            if season is not None:
                if pending or game.season != season + 1:
                    raise ValueError(
                        "Nonconsecutive season or unresolved update across season boundary"
                    )
                ratings = {
                    t: 1500 + MODEL_SPEC["season_retention"] * (r - 1500)
                    for t, r in ratings.items()
                }
            season = game.season
        probability = home_probability(ratings, game.home, game.away, game.neutral)
        predictions.append(
            {
                "game_id": game.game_id,
                "season": game.season,
                "start": game.start.isoformat(),
                "day": game.start.date().isoformat(),
                "home": game.home,
                "away": game.away,
                "probability_home": probability,
                "outcome_home": game.outcome,
            }
        )
        heapq.heappush(pending, (game.available_after, game.game_id, game, probability))
    apply_ready(cutoff)
    return (
        predictions,
        ratings,
        {
            "last_season": season,
            "pending_lagged_updates": len(pending),
            "as_of": cutoff.isoformat(),
        },
    )


def wilson(successes, n):
    if not n:
        return [0.0, 1.0]
    z = 1.959963984540054
    p = successes / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [max(0, center - half), min(1, center + half)]


def quantile(values, q):
    values = sorted(values)
    if not values:
        raise ValueError("Nonempty quantile input required")
    i = (len(values) - 1) * q
    lo = int(i)
    return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (i - lo)


def _logloss(p, y):
    p = min(1 - 1e-12, max(1e-12, p))
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def _daily_blocks(rows):
    days = defaultdict(list)
    for row in rows:
        days[row["day"]].append(row)
    return [days[k] for k in sorted(days)]


def validate_predictions(predictions, audit):
    training = [r for r in predictions if r["season"] in MODEL_SPEC["warmup_seasons"]]
    heldout = [r for r in predictions if r["season"] == MODEL_SPEC["holdout_season"]]
    if not training or not heldout:
        raise ValueError("Warmup and holdout predictions required")
    baseline = mean(r["outcome_home"] for r in training)
    brier = mean((r["probability_home"] - r["outcome_home"]) ** 2 for r in heldout)
    baseline_brier = mean((baseline - r["outcome_home"]) ** 2 for r in heldout)
    logloss = mean(_logloss(r["probability_home"], r["outcome_home"]) for r in heldout)
    baseline_logloss = mean(_logloss(baseline, r["outcome_home"]) for r in heldout)
    bins = []
    for i in range(10):
        rows = [r for r in heldout if min(9, int(r["probability_home"] * 10)) == i]
        n = len(rows)
        bins.append(
            {
                "index": i,
                "n": n,
                "mean_probability": mean(r["probability_home"] for r in rows) if n else None,
                "observed_frequency": mean(r["outcome_home"] for r in rows) if n else None,
                "frequency_wilson_95": wilson(sum(r["outcome_home"] for r in rows), n),
            }
        )
    ece = sum(
        b["n"] * abs(b["mean_probability"] - b["observed_frequency"]) for b in bins if b["n"]
    ) / len(heldout)
    blocks = _daily_blocks(heldout)
    deltas = [
        (
            sum(
                (r["probability_home"] - r["outcome_home"]) ** 2
                - (baseline - r["outcome_home"]) ** 2
                for r in block
            ),
            len(block),
        )
        for block in blocks
    ]
    rng = random.Random(MODEL_SPEC["bootstrap_seed"])
    boot = []
    for _ in range(MODEL_SPEC["bootstrap_iterations"]):
        sampled = rng.choices(deltas, k=len(deltas))
        boot.append(sum(x[0] for x in sampled) / sum(x[1] for x in sampled))
    interval = [quantile(boot, 0.025), quantile(boot, 0.975)]
    checks = {
        "complete_historical_seasons": audit["complete_historical_seasons"],
        "warmup_size": len(training) >= MODEL_SPEC["minimum_warmup_games"],
        "holdout_size": len(heldout) >= MODEL_SPEC["minimum_holdout_games"],
        "brier_beats_baseline": brier < baseline_brier,
        "logloss_beats_baseline": logloss < baseline_logloss,
        "paired_brier_upper_below_zero": interval[1] < 0,
        "ece_within_limit": ece <= MODEL_SPEC["maximum_ece"],
    }
    return {
        "model_spec": MODEL_SPEC,
        "warmup_n": len(training),
        "holdout_n": len(heldout),
        "baseline_home_probability": baseline,
        "brier": brier,
        "baseline_brier": baseline_brier,
        "logloss": logloss,
        "baseline_logloss": baseline_logloss,
        "ece": ece,
        "bins": bins,
        "paired_delta_brier_bootstrap_95": interval,
        "checks": checks,
        "passed": all(checks.values()),
        "limitations": [
            "Historical scores were retrieved now; validation is retrospective, not a point-in-time trading backtest.",
            "Raw fixed Elo only; no injury, lineup or roster information and no demonstrated market profit.",
            "Calibration bins/intervals describe groups, not the true probability interval of a single game.",
        ],
    }


def candidate_support(predictions, raw_home_probability, yes_is_home, snapshot, risk):
    """Holdout residual stress check; does not refit the point probability."""
    if not math.isfinite(raw_home_probability) or not 0 <= raw_home_probability <= 1:
        raise ValueError("Finite home probability in [0,1] required")
    heldout = [r for r in predictions if r["season"] == MODEL_SPEC["holdout_season"]]
    if not heldout:
        raise ValueError("Heldout predictions required")
    index = min(9, int(raw_home_probability * 10))
    bucket = [r for r in heldout if min(9, int(r["probability_home"] * 10)) == index]
    raw_yes = raw_home_probability if yes_is_home else 1 - raw_home_probability
    market_p = snapshot.market_implied_probability
    if market_p is None or snapshot.best_bid is None or snapshot.best_ask is None:
        raise ValueError("Complete quote required for support analysis")
    buy_yes = raw_yes >= market_p
    price = snapshot.best_ask if buy_yes else 1 - snapshot.best_bid
    fill = min(1.0, round(price + risk.paper_slippage_bps / 10000, 4))
    cost = fill * (1 + risk.paper_fee_rate)
    threshold = max(risk.min_edge, 2 * snapshot.spread)
    # Resample full UTC days; empty-bin replicates count as no support.
    blocks = _daily_blocks(heldout)
    summaries = []
    for block in blocks:
        selected = [r for r in block if min(9, int(r["probability_home"] * 10)) == index]
        summaries.append(
            (sum(r["outcome_home"] - r["probability_home"] for r in selected), len(selected))
        )
    rng = random.Random(MODEL_SPEC["bootstrap_seed"])
    edges = []
    for _ in range(MODEL_SPEC["bootstrap_iterations"]):
        sampled = rng.choices(summaries, k=len(summaries))
        n = sum(x[1] for x in sampled)
        if not n:
            edges.append(-1.0)
            continue
        stressed_home = min(1.0, max(0.0, raw_home_probability + sum(x[0] for x in sampled) / n))
        stressed_yes = stressed_home if yes_is_home else 1 - stressed_home
        edges.append((stressed_yes if buy_yes else 1 - stressed_yes) - cost)
    interval = [quantile(edges, 0.025), quantile(edges, 0.975)]
    enough = len(bucket) >= MODEL_SPEC["minimum_current_bin_games"]
    return {
        "raw_probability_home": raw_home_probability,
        "raw_probability_yes": raw_yes,
        "side": "BUY_YES" if buy_yes else "BUY_NO",
        "home_bin": index,
        "bin_n": len(bucket),
        "fill_price": fill,
        "cost_per_contract": cost,
        "required_edge": threshold,
        "raw_net_edge": (raw_yes if buy_yes else 1 - raw_yes) - cost,
        "stress_net_edge_bootstrap_95": interval,
        "edge_support_fraction": sum(e >= threshold for e in edges) / len(edges),
        "enough_bin_data": enough,
        "conservative_edge_passed": enough and interval[0] >= threshold,
        "interpretation": "Residual-transfer stress diagnostic, not a single-game probability confidence interval; raw Elo remains the point estimate.",
    }
