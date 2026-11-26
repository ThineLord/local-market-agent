from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from local_market_agent.adapters import (
    FixtureAdapter,
    KalshiAdapter,
    PolymarketAdapter,
    YFinanceAdapter,
)
from local_market_agent.operations.phase7_historical_dataset import (
    HistoricalMarketRecord,
    input_record_at,
    load_historical_dataset,
    qualify_historical_records,
    record_known_at,
    record_with_visible_settlement,
    records_known_at,
)
from local_market_agent.schemas import EvidenceItem, Market, MarketSnapshot
from local_market_agent.schemas.models import MarketStatus, MarketType, new_id

MARKET_SOURCE_FIXTURE = "fixture"
MARKET_SOURCE_POLYMARKET = "polymarket"
MARKET_SOURCE_KALSHI = "kalshi"
MARKET_SOURCE_YFINANCE = "yfinance"
MARKET_SOURCE_HISTORICAL_FILE = "historical-file"
SUPPORTED_MARKET_SOURCES = {
    MARKET_SOURCE_FIXTURE,
    MARKET_SOURCE_POLYMARKET,
    MARKET_SOURCE_KALSHI,
    MARKET_SOURCE_YFINANCE,
    MARKET_SOURCE_HISTORICAL_FILE,
}

DATA_MODE_FIXTURE = "fixture"
DATA_MODE_CURRENT_SNAPSHOT = "current_snapshot"
DATA_MODE_HISTORICAL_LOCAL = "historical_local_dataset"


@dataclass(frozen=True)
class Phase7MarketDataAudit:
    market_source: str
    market_id: str | None
    data_mode: str
    network_calls_enabled: bool
    is_fixture: bool
    is_historical: bool
    is_snapshot_only: bool
    read_only: bool
    can_create_orders: bool
    profitability_claims_meaningful: bool
    requires_market_id: bool
    evidence_source: str
    historical_file: str | None = None
    historical_record_count: int | None = None
    historical_start_date: str | None = None
    historical_end_date: str | None = None
    historical_record_date: str | None = None
    historical_dataset_warnings: tuple[str, ...] = ()
    evidence_count: int = 0
    has_settlement: bool = False
    settlement_coverage: str = "not_applicable"
    settlement_outcome: str | None = None
    closed_position_evaluation_supported: bool = False
    configuration_error: str | None = None
    settlement_label_present: bool = False
    settlement_ambiguous: bool | None = None
    settlement_status: str | None = None
    credible_settlement: bool = False
    paper_pnl_allowed: bool | None = None
    acceptance_candidate: bool | None = None
    historical_profile: str | None = None
    paper_profit_block_reason: str | None = None
    paper_profit_label: str | None = None
    paper_profit_note: str | None = None
    eligible_historical_row_count: int = 0
    ineligible_historical_row_count: int = 0
    historical_record_qualifications: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "market_source": self.market_source,
            "market_id": self.market_id,
            "data_mode": self.data_mode,
            "network_calls_enabled": self.network_calls_enabled,
            "is_fixture": self.is_fixture,
            "is_historical": self.is_historical,
            "is_snapshot_only": self.is_snapshot_only,
            "read_only": self.read_only,
            "can_create_orders": self.can_create_orders,
            "profitability_claims_meaningful": self.profitability_claims_meaningful,
            "requires_market_id": self.requires_market_id,
            "evidence_source": self.evidence_source,
            "historical_file": self.historical_file,
            "historical_record_count": self.historical_record_count,
            "historical_start_date": self.historical_start_date,
            "historical_end_date": self.historical_end_date,
            "historical_record_date": self.historical_record_date,
            "historical_dataset_warnings": list(self.historical_dataset_warnings),
            "evidence_count": self.evidence_count,
            "has_settlement": self.has_settlement,
            "settlement_coverage": self.settlement_coverage,
            "settlement_outcome": self.settlement_outcome,
            "closed_position_evaluation_supported": self.closed_position_evaluation_supported,
            "configuration_error": self.configuration_error,
            "settlement_label_present": self.settlement_label_present,
            "settlement_ambiguous": self.settlement_ambiguous,
            "settlement_status": self.settlement_status,
            "credible_settlement": self.credible_settlement,
            "paper_pnl_allowed": self.paper_pnl_allowed,
            "acceptance_candidate": self.acceptance_candidate,
            "historical_profile": self.historical_profile,
            "paper_profit_block_reason": self.paper_profit_block_reason,
            "paper_profit_label": self.paper_profit_label,
            "paper_profit_note": self.paper_profit_note,
            "eligible_historical_row_count": self.eligible_historical_row_count,
            "ineligible_historical_row_count": self.ineligible_historical_row_count,
            "historical_record_qualifications": [
                dict(row) for row in self.historical_record_qualifications
            ],
        }


@dataclass(frozen=True)
class Phase7MarketInputs:
    snapshot: MarketSnapshot
    evidence: list[EvidenceItem]
    audit: Phase7MarketDataAudit


def normalize_market_source(market_source: str | None) -> str:
    source = (market_source or MARKET_SOURCE_FIXTURE).strip().lower()
    if source not in SUPPORTED_MARKET_SOURCES:
        choices = ", ".join(sorted(SUPPORTED_MARKET_SOURCES))
        msg = f"unsupported market source '{market_source}'. Supported sources: {choices}"
        raise ValueError(msg)
    return source


def phase7_market_data_audit(
    market_source: str | None,
    *,
    market_id: str | None = None,
    historical_file: str | Path | None = None,
    as_of: datetime | None = None,
) -> Phase7MarketDataAudit:
    source = normalize_market_source(market_source)
    market_id = _optional_text(market_id)
    is_fixture = source == MARKET_SOURCE_FIXTURE
    is_historical_file = source == MARKET_SOURCE_HISTORICAL_FILE
    if is_historical_file:
        return _historical_file_audit(
            market_id=market_id,
            historical_file=historical_file,
            as_of=as_of,
        )
    requires_market_id = not is_fixture
    configuration_error = None
    if requires_market_id and not market_id:
        configuration_error = (
            f"--market-id is required when --market-source is {source}; "
            "Phase 7 does not guess live market identifiers."
        )
    return Phase7MarketDataAudit(
        market_source=source,
        market_id=market_id,
        data_mode=DATA_MODE_FIXTURE if is_fixture else DATA_MODE_CURRENT_SNAPSHOT,
        network_calls_enabled=not is_fixture,
        is_fixture=is_fixture,
        is_historical=False,
        is_snapshot_only=not is_fixture,
        read_only=True,
        can_create_orders=False,
        profitability_claims_meaningful=False,
        requires_market_id=requires_market_id,
        evidence_source="fixture" if is_fixture else "none",
        configuration_error=configuration_error,
    )


def load_phase7_market_inputs(
    *,
    market_source: str | None,
    market_id: str | None,
    market_fixture: Path,
    evidence_fixture: Path,
    raw_cache_dir: Path,
    now: datetime,
    refresh_market_timestamp: bool,
    historical_file: str | Path | None = None,
) -> Phase7MarketInputs:
    market_id = _optional_text(market_id)
    audit = phase7_market_data_audit(
        market_source,
        market_id=market_id,
        historical_file=historical_file,
        as_of=now,
    )
    if audit.configuration_error:
        raise ValueError(audit.configuration_error)

    fixture = FixtureAdapter(market_fixture, evidence_fixture)
    if audit.market_source == MARKET_SOURCE_FIXTURE:
        snapshot = fixture.fetch_snapshot(market_id)
        evidence = fixture.fetch_evidence(snapshot.market.market_id)
    elif audit.market_source == MARKET_SOURCE_POLYMARKET:
        snapshot = PolymarketAdapter(raw_cache_dir).fetch_snapshot(str(market_id))
        evidence = []
    elif audit.market_source == MARKET_SOURCE_KALSHI:
        snapshot = KalshiAdapter(raw_cache_dir).fetch_snapshot(str(market_id))
        evidence = []
    elif audit.market_source == MARKET_SOURCE_YFINANCE:
        snapshot = _yfinance_snapshot(str(market_id))
        evidence = []
    elif audit.market_source == MARKET_SOURCE_HISTORICAL_FILE:
        dataset = load_historical_dataset(historical_file)
        record = input_record_at(dataset, now, market_id=market_id)
        if record_known_at(record, now):
            visible_record = record_with_visible_settlement(record, now)
            snapshot = record.to_snapshot()
        else:
            # The only row for this day is still ahead. Keep its quotes as the
            # single-day input, and do not treat its settlement as observed.
            visible_record = replace(
                record,
                settlement_outcome=None,
                settlement_ambiguous=None,
                settlement_status=None,
            )
            snapshot = visible_record.to_snapshot()
        evidence = list(record.evidence)
        audit = replace(
            audit,
            market_id=record.market_id,
            historical_record_date=record.record_date.isoformat(),
            evidence_source="historical-file" if record.evidence else "missing",
            evidence_count=len(record.evidence),
            settlement_outcome=visible_record.settlement_outcome,
            settlement_ambiguous=visible_record.settlement_ambiguous,
            settlement_status=visible_record.settlement_status,
        )
    else:
        # normalize_market_source prevents this branch; keep it for type checkers.
        msg = f"unsupported market source '{audit.market_source}'"
        raise ValueError(msg)

    if refresh_market_timestamp and audit.market_source == MARKET_SOURCE_FIXTURE:
        snapshot = snapshot.model_copy(
            update={"snapshot_id": new_id("snapshot"), "as_of": _as_utc(now)}
        )
    return Phase7MarketInputs(snapshot=snapshot, evidence=evidence, audit=audit)


def _historical_file_audit(
    *,
    market_id: str | None,
    historical_file: str | Path | None,
    as_of: datetime | None = None,
) -> Phase7MarketDataAudit:
    if historical_file is None:
        return Phase7MarketDataAudit(
            market_source=MARKET_SOURCE_HISTORICAL_FILE,
            market_id=market_id,
            data_mode=DATA_MODE_HISTORICAL_LOCAL,
            network_calls_enabled=False,
            is_fixture=False,
            is_historical=True,
            is_snapshot_only=False,
            read_only=True,
            can_create_orders=False,
            profitability_claims_meaningful=False,
            requires_market_id=False,
            evidence_source="unknown",
            historical_file=None,
            configuration_error=(
                "--historical-file is required when --market-source is historical-file"
            ),
            paper_profit_block_reason="historical_file_missing",
            paper_profit_label=_LABEL_SELECTION_ERROR,
            paper_profit_note=(
                "A historical file is required before paper profitability can be described."
            ),
        )
    dataset = load_historical_dataset(historical_file)
    selected_market_id = market_id or dataset.default_market_id()
    configuration_error = None
    if selected_market_id is None:
        configuration_error = (
            "historical dataset contains multiple market ids; provide --market-id to select one"
        )
    elif selected_market_id not in dataset.market_ids:
        configuration_error = (
            f"historical dataset has no records for market_id={selected_market_id}"
        )
    if configuration_error is not None:
        block_reason = (
            "market_unspecified"
            if selected_market_id is None
            else "market_not_in_dataset"
        )
        return Phase7MarketDataAudit(
            market_source=MARKET_SOURCE_HISTORICAL_FILE,
            market_id=selected_market_id,
            data_mode=DATA_MODE_HISTORICAL_LOCAL,
            network_calls_enabled=False,
            is_fixture=False,
            is_historical=True,
            is_snapshot_only=False,
            read_only=True,
            can_create_orders=False,
            profitability_claims_meaningful=False,
            requires_market_id=False,
            evidence_source="unknown",
            historical_file=str(Path(historical_file)),
            historical_record_count=len(dataset.records),
            historical_start_date=dataset.start_date.isoformat(),
            historical_end_date=dataset.end_date.isoformat(),
            historical_dataset_warnings=dataset.warnings,
            has_settlement=False,
            settlement_coverage="not_applicable",
            closed_position_evaluation_supported=False,
            configuration_error=configuration_error,
            paper_profit_block_reason=block_reason,
            paper_profit_label=_LABEL_SELECTION_ERROR,
            paper_profit_note=_selection_error_note(block_reason),
        )
    selected_records = dataset.records_for_market(selected_market_id)
    if as_of is not None:
        selected_records = records_known_at(selected_records, as_of)
    if selected_records:
        start_date = min(record.record_date for record in selected_records)
        end_date = max(record.record_date for record in selected_records)
        settlement_coverage = _settlement_coverage(selected_records)
    else:
        start_date = None
        end_date = None
        settlement_coverage = "none"
    qualification = qualify_historical_records(selected_records)
    has_evidence = any(record.evidence for record in selected_records)
    warnings = list(dataset.warnings)
    if not qualification.settlement_label_present and dataset.has_settlement and as_of is None:
        warnings.append(
            "Selected historical market has no settlement/outcome fields; "
            "final profitability claims are not meaningful."
        )
    if not has_evidence and dataset.has_evidence and as_of is None:
        warnings.append(
            "Selected historical market has no evidence records; research evidence "
            "is missing/limited."
        )
    if qualification.block_reason not in {None, "no_credible_settlement"} and as_of is None:
        warnings.append("Selected historical market cannot support paper-profit proof.")
    row_qualifications = ()
    if as_of is None:
        row_qualifications = tuple(record.as_dict() for record in qualification.records)
    return Phase7MarketDataAudit(
        market_source=MARKET_SOURCE_HISTORICAL_FILE,
        market_id=selected_market_id,
        data_mode=DATA_MODE_HISTORICAL_LOCAL,
        network_calls_enabled=False,
        is_fixture=False,
        is_historical=True,
        is_snapshot_only=False,
        read_only=True,
        can_create_orders=False,
        profitability_claims_meaningful=qualification.profitability_claims_meaningful,
        requires_market_id=False,
        evidence_source="historical-file" if has_evidence else "missing",
        historical_file=str(Path(historical_file)),
        historical_record_count=len(selected_records),
        historical_start_date=start_date.isoformat() if start_date is not None else None,
        historical_end_date=end_date.isoformat() if end_date is not None else None,
        historical_dataset_warnings=tuple(warnings),
        has_settlement=qualification.has_settlement,
        settlement_coverage=settlement_coverage,
        settlement_outcome=qualification.settlement_outcome,
        closed_position_evaluation_supported=(
            qualification.closed_position_evaluation_supported
        ),
        settlement_label_present=qualification.settlement_label_present,
        settlement_ambiguous=qualification.settlement_ambiguous,
        settlement_status=qualification.settlement_status,
        credible_settlement=qualification.credible_settlement,
        paper_pnl_allowed=qualification.paper_pnl_allowed,
        acceptance_candidate=qualification.acceptance_candidate,
        historical_profile=qualification.historical_profile,
        paper_profit_block_reason=qualification.block_reason,
        paper_profit_label=qualification.paper_profit_label,
        paper_profit_note=qualification.paper_profit_note,
        eligible_historical_row_count=qualification.eligible_row_count,
        ineligible_historical_row_count=qualification.ineligible_row_count,
        historical_record_qualifications=row_qualifications,
    )


def _settlement_coverage(records: tuple[HistoricalMarketRecord, ...]) -> str:
    settled = sum(record.settlement_outcome is not None for record in records)
    if settled == 0:
        return "none"
    if settled == len(records):
        return "full"
    return "partial"


def _yfinance_snapshot(symbol: str) -> MarketSnapshot:
    data = YFinanceAdapter().history(symbol)
    latest = data.iloc[-1]
    as_of = _datetime_from_index_value(data.index[-1])
    close = _float_or_none(latest.get("Close"))
    volume = _float_or_none(latest.get("Volume"))
    market = Market(
        market_id=symbol,
        title=f"{symbol} latest OHLCV snapshot",
        platform="yfinance",
        market_type=MarketType.EQUITY,
        status=MarketStatus.UNKNOWN,
        outcomes=[],
    )
    last_price = close if close is not None and 0 <= close <= 1 else None
    return MarketSnapshot(
        market=market,
        as_of=as_of,
        last_price=last_price,
        volume=volume,
    )


def _datetime_from_index_value(value: object) -> datetime:
    if hasattr(value, "to_pydatetime"):
        parsed = value.to_pydatetime()
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.now(UTC)
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


_LABEL_SELECTION_ERROR = "historical local dataset selection error"
_SELECTION_ERROR_NOTES = {
    "market_unspecified": (
        "No historical market is selected. Paper profitability claims are not meaningful."
    ),
    "market_not_in_dataset": (
        "The requested market is not in the historical file. "
        "Paper profitability claims are not meaningful."
    ),
    "historical_file_missing": (
        "A historical file is required before paper profitability can be described."
    ),
}


def _selection_error_note(reason: str) -> str:
    return _SELECTION_ERROR_NOTES[reason]
