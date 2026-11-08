"""Shared, fail-closed checks for research screening and paper execution."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from local_market_agent.config import Settings
from local_market_agent.nba_guard import forecast_gate
from local_market_agent.schemas import MarketSnapshot, ResearchBrief


@dataclass(frozen=True)
class PreflightCheck:
    code: str
    passed: bool
    message: str


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Preflight timestamps require a timezone")
    return value.astimezone(UTC)


def snapshot_checks(
    snapshot: MarketSnapshot, market_id: str, settings: Settings, now: datetime
) -> list[PreflightCheck]:
    now = _aware(now)
    checks = []

    def check(code, passed, message):
        checks.append(PreflightCheck(code, bool(passed), message))

    check(
        "finite_values",
        all(
            math.isfinite(v)
            for v in (
                snapshot.best_bid,
                snapshot.best_ask,
                snapshot.last_price,
                snapshot.market_implied_probability,
                snapshot.volume,
                snapshot.liquidity,
            )
            if v is not None
        ),
        "Snapshot numeric values must be finite.",
    )
    market = snapshot.market
    check(
        "market_identity",
        market.market_id == market_id,
        "The returned market must match the requested market ID.",
    )
    check(
        "binary_market",
        market.market_type == "prediction"
        and [outcome.lower() for outcome in market.outcomes] == ["yes", "no"],
        "Only binary YES/NO prediction snapshots in YES-first order can be screened.",
    )
    check("market_open", market.status == "open", "The market must be explicitly open.")
    check(
        "before_close",
        market.close_time is None or _aware(market.close_time) > now,
        "The market close time must not have passed.",
    )
    age = (now - _aware(snapshot.as_of)).total_seconds()
    check(
        "snapshot_age",
        0 <= age <= settings.risk_gates.max_market_data_age_seconds,
        f"Observation age is {age:.0f}s; allowed range is 0–{settings.risk_gates.max_market_data_age_seconds}s; stale or future observations are blocked.",
    )
    check(
        "two_sided_quote",
        snapshot.spread is not None,
        "Both bid and ask are required; last price is not a substitute.",
    )
    check(
        "spread",
        snapshot.spread is not None and snapshot.spread <= settings.risk.max_spread,
        f"Spread must be at most {settings.risk.max_spread:.2f}.",
    )
    check(
        "liquidity",
        snapshot.liquidity is not None and snapshot.liquidity >= settings.risk.min_liquidity_depth,
        f"Liquidity is {snapshot.liquidity if snapshot.liquidity is not None else 'unknown'}; required minimum is {settings.risk.min_liquidity_depth:g}. Unknown or insufficient depth blocks execution.",
    )
    check(
        "market_probability",
        snapshot.market_implied_probability is not None,
        "A market probability is required.",
    )
    if snapshot.best_bid is not None and snapshot.best_ask is not None:
        probability = snapshot.market_implied_probability
        check(
            "probability_consistent",
            probability is not None and snapshot.best_bid <= probability <= snapshot.best_ask,
            "Market probability must lie within the observed bid/ask interval.",
        )

    return checks


def brief_checks(
    snapshot: MarketSnapshot, brief: ResearchBrief, settings: Settings, now: datetime
) -> list[PreflightCheck]:
    now = _aware(now)
    checks = []

    def check(code, passed, message):
        checks.append(PreflightCheck(code, bool(passed), message))

    check(
        "brief_identity",
        brief.market_id == snapshot.market.market_id and brief.snapshot_id == snapshot.snapshot_id,
        "The brief must reference this exact market and snapshot.",
    )
    check(
        "brief_time",
        _aware(snapshot.as_of) <= _aware(brief.created_at) <= now,
        "The brief must have been created between the snapshot and the review time.",
    )
    evidence = brief.evidence + brief.counter_evidence
    check(
        "evidence_count",
        len({item.evidence_id for item in evidence}) >= 2,
        "At least two distinct evidence references are required.",
    )
    check(
        "evidence_time",
        bool(evidence)
        and all(
            item.published_at is not None and _aware(item.published_at) <= _aware(snapshot.as_of)
            for item in evidence
        ),
        "All evidence needs an explicit publication timezone and must predate the snapshot.",
    )
    check(
        "brief_veto",
        not brief.must_not_trade_reasons,
        "Brief veto: " + "; ".join(brief.must_not_trade_reasons) if brief.must_not_trade_reasons else "No brief veto.",
    )
    check(
        "resolution",
        bool(brief.resolution_source) and not brief.resolution_ambiguity,
        "The brief must identify an unambiguous resolution source.",
    )

    model_check = forecast_gate(snapshot, brief, settings, now)
    if model_check is not None:
        passed, reasons = model_check
        check("nba_model_gate", passed, "; ".join(reasons) or "Frozen NBA probability, conservative edge and pregame/source-age requirements passed.")
    return checks


def preflight(
    snapshot: MarketSnapshot, brief: ResearchBrief, settings: Settings, now: datetime
) -> list[PreflightCheck]:
    return snapshot_checks(snapshot, brief.market_id, settings, now) + brief_checks(
        snapshot, brief, settings, now
    )


def portfolio_marks(repository, snapshot, settings, now):
    """Refuse cost-basis estimates when a held market has no fresh trusted quote."""
    marks = {snapshot.market.market_id: snapshot.market_implied_probability}
    for position in repository.list_positions():
        if not position.is_open or position.market_id in marks:
            continue
        candidates = repository.list_market_snapshots(position.market_id, limit=1)
        if not candidates or any(not c.passed for c in snapshot_checks(candidates[0], position.market_id, settings, now)):
            raise ValueError(f"Fresh valid mark required for held market: {position.market_id}")
        marks[position.market_id] = candidates[0].market_implied_probability
    return marks
