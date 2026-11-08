"""Execution-time checks for the explicitly labelled NBA Elo packet workflow."""

import math

from local_market_agent.nba_probability import MODEL_SPEC, home_probability, parse_time

VALIDATION_KEYS = {
    "complete_historical_seasons",
    "warmup_size",
    "holdout_size",
    "brier_beats_baseline",
    "logloss_beats_baseline",
    "paired_brier_upper_below_zero",
    "ece_within_limit",
}
MAX_HISTORY_AGE_SECONDS = 6 * 60 * 60


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Finite numeric model proof required")
    return value


def forecast_gate(snapshot, brief, settings, now):
    markers = [
        item
        for item in brief.evidence + brief.counter_evidence
        if item.metadata.get("model") == MODEL_SPEC["model"]
    ]
    if not markers:
        return None
    reasons = []
    try:
        if len(markers) != 1:
            raise ValueError("One unambiguous NBA forecast proof required")
        guard = markers[0].metadata["nba_forecast"]
        if guard["model_spec"] != MODEL_SPEC:
            raise ValueError("Frozen model specification mismatch")
        if (
            guard["market_id"] != snapshot.market.market_id
            or guard["snapshot_id"] != snapshot.snapshot_id
        ):
            raise ValueError("Forecast market/snapshot identity mismatch")
        if guard["last_season"] != MODEL_SPEC["forward_season"]:
            raise ValueError("Current-season rating state required")
        start = parse_time(guard["event_start"])
        observed = parse_time(guard["event_observed_at"])
        history_at = parse_time(guard["current_history_oldest_retrieval"])
        if guard["event_state"] != "pre" or not observed <= snapshot.as_of <= now < start:
            reasons.append(
                "NBA Elo is pregame only; current event must be observed before the quote and not started"
            )
        if (
            not 0
            <= (now - observed).total_seconds()
            <= settings.risk_gates.max_market_data_age_seconds
        ):
            reasons.append("NBA event-status observation is stale or future-dated")
        if not 0 <= (now - history_at).total_seconds() <= MAX_HISTORY_AGE_SECONDS:
            reasons.append(
                "Current-season history is stale; refresh sources, not just the analysis clock"
            )
        validation = guard["validation"]
        checks = validation["checks"]
        if (
            not checks.keys() >= VALIDATION_KEYS
            or not all(v is True for v in checks.values())
            or validation["passed"] is not True
        ):
            reasons.append("Frozen holdout validation requirements failed")
        if not (
            validation["warmup_n"] >= MODEL_SPEC["minimum_warmup_games"]
            and validation["holdout_n"] >= MODEL_SPEC["minimum_holdout_games"]
            and _number(validation["brier"]) < _number(validation["baseline_brier"])
            and _number(validation["logloss"]) < _number(validation["baseline_logloss"])
            and 0 <= _number(validation["ece"]) <= MODEL_SPEC["maximum_ece"]
            and _number(validation["paired_delta_brier_bootstrap_95"][1]) < 0
        ):
            reasons.append("Holdout numeric results do not satisfy the frozen gates")
        match = guard["match"]
        home, away = match["home_id"], match["away_id"]
        if match["yes_team_id"] not in {home, away} or not isinstance(match["neutral"], bool):
            raise ValueError("Invalid NBA team/neutral identity")
        p_home = home_probability(
            {home: _number(guard["home_rating"]), away: _number(guard["away_rating"])},
            home,
            away,
            match["neutral"],
        )
        p_yes = p_home if match["yes_team_id"] == home else 1 - p_home
        support = guard["support"]
        if not math.isclose(
            _number(support["raw_probability_home"]), p_home, abs_tol=1e-12
        ) or not math.isclose(_number(brief.estimated_probability), p_yes, abs_tol=1e-12):
            raise ValueError("Brief probability is not reproducible from the frozen ratings")
        side = "BUY_YES" if p_yes >= snapshot.market_implied_probability else "BUY_NO"
        price = snapshot.best_ask if side == "BUY_YES" else 1 - snapshot.best_bid
        fill = min(1.0, round(price + settings.risk.paper_slippage_bps / 10000, 4))
        cost = fill * (1 + settings.risk.paper_fee_rate)
        threshold = max(settings.risk.min_edge, 2 * snapshot.spread)
        if (
            support["side"] != side
            or not math.isclose(_number(support["cost_per_contract"]), cost, abs_tol=1e-12)
            or not math.isclose(_number(support["required_edge"]), threshold, abs_tol=1e-12)
        ):
            raise ValueError(
                "Support calculation does not match current side/quote/cost configuration"
            )
        index = min(9, int(p_home * 10))
        if support["home_bin"] != index or support["bin_n"] != validation["bins"][index]["n"]:
            raise ValueError("Support bucket does not match the validated probability bin")
        raw_edge = (p_yes if side == "BUY_YES" else 1 - p_yes) - cost
        if (
            not math.isclose(_number(support["raw_net_edge"]), raw_edge, abs_tol=1e-12)
            or raw_edge < threshold
        ):
            reasons.append("Raw net edge after costs is below the unchanged threshold")
        lower, upper = map(_number, support["stress_net_edge_bootstrap_95"])
        if not (
            support["bin_n"] >= MODEL_SPEC["minimum_current_bin_games"]
            and support["enough_bin_data"] is True
            and support["conservative_edge_passed"] is True
            and threshold <= lower <= upper <= 1
        ):
            reasons.append("Insufficient bin support or conservative net edge")
        if not 0 <= _number(support["edge_support_fraction"]) <= 1 or not math.isclose(
            brief.confidence, support["edge_support_fraction"], abs_tol=1e-12
        ):
            raise ValueError("Brief confidence must equal the computed edge-support fraction")
        prerequisites = guard["input_checks"]
        expected = {
            "source_hashes",
            "complete_history",
            "pregame_identity",
            "unit_dollar_rules",
            "current_history",
            "holdout_validation",
            "bin_support",
            "conservative_edge",
        }
        if set(prerequisites) != expected or not all(
            isinstance(v, bool) for v in prerequisites.values()
        ):
            raise ValueError("Explicit input-quality checklist required")
        quality = sum(prerequisites.values()) / len(prerequisites)
        if not math.isclose(brief.evidence_quality, quality, abs_tol=1e-12) or not all(
            prerequisites.values()
        ):
            reasons.append(
                "Evidence prerequisites failed; a high quality number cannot override missing inputs"
            )
    except (KeyError, ValueError, TypeError, IndexError, OverflowError) as exc:
        reasons.append("Invalid NBA model proof: " + str(exc))
    return not reasons, reasons
