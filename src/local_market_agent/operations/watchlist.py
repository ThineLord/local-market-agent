"""Bounded, read-only market screening. No database, LLM calls, or order execution."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from local_market_agent.adapters import KalshiAdapter, PolymarketAdapter
from local_market_agent.config import Settings
from local_market_agent.schemas import MarketSnapshot, ResearchBrief
from local_market_agent.schemas.models import StrictBaseModel, deterministic_model_context
from local_market_agent.strategy import PredictionMarketEdgeStrategy

ScreenStatus = Literal["research_candidate", "needs_research", "observe", "blocked", "error"]


class WatchlistEntry(StrictBaseModel):
    source: Literal["file", "kalshi", "polymarket"]
    market_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")
    snapshot_file: Path | None = None
    brief_file: Path | None = None

    @model_validator(mode="after")
    def validate_source(self):
        if (self.source == "file") != (self.snapshot_file is not None):
            raise ValueError("Only file sources require snapshot_file")
        if self.source != "file" and self.brief_file is not None:
            raise ValueError("Save a snapshot and use file mode to evaluate its matching brief")
        return self


class Watchlist(StrictBaseModel):
    name: str = Field(min_length=1, max_length=120)
    entries: list[WatchlistEntry] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_markets(self):
        keys = [(entry.source, entry.market_id) for entry in self.entries]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate source/market_id in watchlist")
        return self


class ScreenCheck(StrictBaseModel):
    code: str
    passed: bool
    message: str


class ScreenRow(StrictBaseModel):
    source: str
    market_id: str
    title: str = ""
    status: ScreenStatus = "blocked"
    checked_at: datetime
    timestamp_basis: Literal["file_observation", "retrieval_only"]
    snapshot: MarketSnapshot | None = None
    checks: list[ScreenCheck] = Field(default_factory=list)
    input_sha256: dict[str, str] = Field(default_factory=dict)
    brief_id: str | None = None
    signal_action: str | None = None
    edge: float | None = None
    strategy_reason: str | None = None
    error_type: str | None = None


class ScreenReport(StrictBaseModel):
    schema_version: Literal[1] = 1
    name: str
    as_of: datetime
    historical_review: bool
    watchlist_sha256: str
    network_enabled: bool
    thresholds: dict[str, float | int]
    rows: list[ScreenRow]
    counts: dict[str, int]
    orders_created: Literal[0] = 0
    execution_authorized: Literal[False] = False
    limitations: list[str] = Field(default_factory=lambda: [
        "Research triage only; candidates still require portfolio risk checks and human approval.",
        "File observations and supplied briefs are not independently verified evidence.",
        "Public metadata adapters record retrieval time, not an exchange quote timestamp.",
        "Screening does not establish profitability, source terms clearance, or acceptance readiness.",
    ])


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An explicit timezone is required")
    return value.astimezone(UTC)


def _read_json(path: Path) -> tuple[object, str]:
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _relative(base: Path, path: Path) -> Path:
    return path if path.is_absolute() else base / path


def screen_watchlist(
    path: Path,
    *,
    settings: Settings | None = None,
    as_of: datetime | None = None,
    allow_network: bool = False,
) -> ScreenReport:
    settings = settings or Settings()
    payload, digest = _read_json(path)
    watchlist = Watchlist.model_validate(payload)
    now = _aware(as_of or datetime.now(UTC))
    if as_of is not None and any(entry.source != "file" for entry in watchlist.entries):
        raise ValueError("--as-of is only valid for all-file watchlists; current quotes cannot be backdated")
    rows = []
    for entry in watchlist.entries:
        row = ScreenRow(
            source=entry.source, market_id=entry.market_id,
            checked_at=now if as_of else datetime.now(UTC),
            timestamp_basis="file_observation" if entry.source == "file" else "retrieval_only",
        )
        rows.append(row)
        if entry.source != "file" and not allow_network:
            row.checks.append(ScreenCheck(
                code="network_disabled", passed=False,
                message="Public requests are disabled. Use --allow-network to fetch this entry.",
            ))
            continue
        try:
            if entry.source == "file":
                raw, checksum = _read_json(_relative(path.parent, entry.snapshot_file))
                row.input_sha256["snapshot"] = checksum
                # Accept both the existing fixture envelope and a saved MarketSnapshot.
                if "snapshot" in raw:
                    raw = {**raw["snapshot"], "market": raw["market"]}
                if "as_of" not in raw or "snapshot_id" not in raw:
                    raise ValueError("Saved snapshots must supply as_of and snapshot_id")
                snapshot = MarketSnapshot.model_validate(raw)
            else:
                adapter_type = KalshiAdapter if entry.source == "kalshi" else PolymarketAdapter
                snapshot = adapter_type(settings.raw_cache_dir).fetch_snapshot(entry.market_id)
                row.checked_at = datetime.now(UTC)
                row.input_sha256["normalized_snapshot"] = hashlib.sha256(
                    snapshot.model_dump_json().encode()
                ).hexdigest()
            # Pydantic's shared snapshot schema permits infinite nonnegative liquidity.
            # Reject nonfinite data before it can pass thresholds or serialize as null.
            json.dumps(snapshot.model_dump(mode="json"), allow_nan=False)
            row.snapshot = snapshot
            row.title = snapshot.market.title
            _screen_snapshot(row, entry, settings)
            if not all(check.passed for check in row.checks):
                continue
            if entry.brief_file is None:
                row.status = "needs_research"
                row.checks.append(ScreenCheck(
                    code="research_missing", passed=False,
                    message="No matching research brief supplied; no probability edge is inferred.",
                ))
                continue
            raw, checksum = _read_json(_relative(path.parent, entry.brief_file))
            row.input_sha256["brief"] = checksum
            if "created_at" not in raw:
                raise ValueError("Saved briefs must supply created_at")
            brief = ResearchBrief.model_validate(raw)
            _screen_brief(row, brief, settings)
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            row.status = "error"
            row.error_type = type(exc).__name__
            # Validation exceptions can contain source payloads; do not echo them into reports.
            row.checks.append(ScreenCheck(
                code="input_error", passed=False,
                message="Unable to load or validate this entry. Check its files, source, and market ID.",
            ))
    return ScreenReport(
        name=watchlist.name, as_of=now, historical_review=as_of is not None,
        watchlist_sha256=digest, network_enabled=allow_network,
        thresholds={
            "max_age_seconds": settings.risk_gates.max_market_data_age_seconds,
            "max_spread": settings.risk.max_spread,
            "min_liquidity": settings.risk.min_liquidity_depth,
            "min_confidence": settings.risk.min_confidence,
            "min_edge": settings.risk.min_edge,
            "min_evidence_quality": 0.65,
        },
        rows=rows, counts=dict(Counter(row.status for row in rows)),
    )


def _check(row: ScreenRow, code: str, passed: bool, message: str) -> None:
    row.checks.append(ScreenCheck(code=code, passed=passed, message=message))


def _screen_snapshot(row: ScreenRow, entry: WatchlistEntry, settings: Settings) -> None:
    snapshot = row.snapshot
    market = snapshot.market
    _check(row, "market_identity", market.market_id == entry.market_id,
           "The returned market must match the requested market ID.")
    _check(row, "binary_market", market.market_type == "prediction" and
           [outcome.lower() for outcome in market.outcomes] == ["yes", "no"],
           "Only binary YES/NO prediction snapshots in YES-first order can be screened.")
    _check(row, "market_open", market.status == "open",
           "The market must be explicitly open.")
    _check(row, "before_close", market.close_time is None or
           _aware(market.close_time) > row.checked_at, "The market close time must not have passed.")
    age = (row.checked_at - _aware(snapshot.as_of)).total_seconds()
    _check(row, "snapshot_age", 0 <= age <= settings.risk_gates.max_market_data_age_seconds,
           f"Observation age is {age:.0f}s; allowed range is 0–{settings.risk_gates.max_market_data_age_seconds}s.")
    _check(row, "two_sided_quote", snapshot.spread is not None,
           "Both bid and ask are required; last price is not a substitute.")
    _check(row, "spread", snapshot.spread is not None and snapshot.spread <= settings.risk.max_spread,
           f"Spread must be at most {settings.risk.max_spread:.2f}.")
    _check(row, "liquidity", snapshot.liquidity is not None and
           snapshot.liquidity >= settings.risk.min_liquidity_depth,
           f"Reported liquidity must be at least {settings.risk.min_liquidity_depth:g}; unknown is not sufficient.")
    _check(row, "market_probability", snapshot.market_implied_probability is not None,
           "A market probability is required.")
    if snapshot.best_bid is not None and snapshot.best_ask is not None:
        probability = snapshot.market_implied_probability
        _check(row, "probability_consistent", probability is not None and
               snapshot.best_bid <= probability <= snapshot.best_ask,
               "Market probability must lie within the observed bid/ask interval.")


def _screen_brief(row: ScreenRow, brief: ResearchBrief, settings: Settings) -> None:
    row.brief_id = brief.brief_id
    snapshot = row.snapshot
    _check(row, "brief_identity", brief.market_id == row.market_id and
           brief.snapshot_id == snapshot.snapshot_id, "The brief must reference this exact market and snapshot.")
    _check(row, "brief_time", _aware(snapshot.as_of) <= _aware(brief.created_at) <= row.checked_at,
           "The brief must have been created between the snapshot and the review time.")
    evidence = brief.evidence + brief.counter_evidence
    _check(row, "evidence_count", len({item.evidence_id for item in evidence}) >= 2,
           "At least two distinct evidence references are required.")
    _check(row, "evidence_time", bool(evidence) and all(
        item.published_at is not None and _aware(item.published_at) <= _aware(snapshot.as_of)
        for item in evidence
    ), "All evidence needs an explicit publication timezone and must predate the snapshot.")
    _check(row, "brief_veto", not brief.must_not_trade_reasons,
           "Any must-not-trade reason in the brief blocks a research candidate.")
    _check(row, "resolution", bool(brief.resolution_source) and not brief.resolution_ambiguity,
           "The brief must identify an unambiguous resolution source.")
    if not all(check.passed for check in row.checks):
        return
    with deterministic_model_context(f"watchlist:{row.market_id}", row.checked_at):
        signal = PredictionMarketEdgeStrategy(settings.risk).generate_signal(brief, snapshot)
    row.signal_action = signal.action.value
    row.edge = signal.edge
    row.strategy_reason = signal.rationale
    row.status = "research_candidate" if signal.action in {"paper_buy_yes", "paper_buy_no"} else "observe"


def report_markdown(report: ScreenReport) -> str:
    lines = [f"# Watchlist: {report.name}", "", f"Review time: {report.as_of.isoformat()}",
             f"Historical review: {report.historical_review}",
             f"Results: {json.dumps(report.counts, sort_keys=True)}", "",
             "Research triage only. No orders or execution approvals are created.", ""]
    for row in report.rows:
        lines.extend([f"## {row.market_id} — {row.status}", "", row.title,
                      f"Timestamp basis: {row.timestamp_basis}", ""])
        for check in row.checks:
            lines.append(f"- {'PASS' if check.passed else 'CHECK'} `{check.code}`: {check.message}")
        if row.strategy_reason:
            lines.append(f"- Strategy: {row.signal_action}; edge={row.edge}. {row.strategy_reason}")
        lines.append("")
    lines.extend(["## Limits", "", *[f"- {item}" for item in report.limitations], ""])
    return "\n".join(lines)


def write_screen_report(report: ScreenReport, output_dir: Path) -> Path:
    """Keep each run, then atomically publish a dashboard copy of the latest complete report."""
    run_dir = output_dir / f"screen-{uuid4().hex}"
    run_dir.mkdir(parents=True, exist_ok=False)
    content = report.model_dump_json(indent=2) + "\n"
    report_path = run_dir / "report.json"
    report_path.write_text(content, encoding="utf-8")
    (run_dir / "report.md").write_text(report_markdown(report), encoding="utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output_dir, delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
        os.replace(temporary, output_dir / "latest.json")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return report_path
