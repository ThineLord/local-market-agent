from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from local_market_agent.schemas import EvidenceItem, Market, MarketSnapshot
from local_market_agent.schemas.models import MarketStatus, MarketType

SUPPORTED_SETTLEMENT_OUTCOMES = {"yes", "no"}
PROFILE_CALIBRATION_ONLY_LAST_PRICE = "calibration_only_last_price"
CALIBRATION_ONLY_PROFILES = {PROFILE_CALIBRATION_ONLY_LAST_PRICE}


@dataclass(frozen=True)
class HistoricalMarketRecord:
    timestamp: datetime
    market_id: str
    bid: float | None
    ask: float | None
    last_price: float
    implied_probability: float
    liquidity: float | None
    volume: float | None
    evidence: tuple[EvidenceItem, ...]
    settlement_outcome: str | None
    line_number: int
    title: str
    platform: str
    profile: str | None
    paper_pnl_allowed: bool
    acceptance_candidate: bool
    settlement_ambiguous: bool | None = None
    settlement_status: str | None = None
    settlement_resolved_at: datetime | None = None
    settlement_label_available_at: datetime | None = None
    observation_time_explicit: bool = False

    @property
    def record_date(self) -> date:
        return self.timestamp.date()

    def to_snapshot(self) -> MarketSnapshot:
        market = Market(
            market_id=self.market_id,
            title=self.title,
            platform=self.platform,
            market_type=MarketType.PREDICTION,
            status=MarketStatus.SETTLED if self.settlement_outcome else MarketStatus.OPEN,
            outcomes=["yes", "no"],
        )
        return MarketSnapshot(
            market=market,
            as_of=self.timestamp,
            best_bid=self.bid,
            best_ask=self.ask,
            last_price=self.last_price,
            market_implied_probability=self.implied_probability,
            volume=self.volume,
            liquidity=self.liquidity,
            evidence_ids=[item.evidence_id for item in self.evidence],
        )


@dataclass(frozen=True)
class HistoricalDataset:
    path: Path
    records: tuple[HistoricalMarketRecord, ...]
    warnings: tuple[str, ...]

    @property
    def market_ids(self) -> tuple[str, ...]:
        return tuple(sorted({record.market_id for record in self.records}))

    @property
    def start_date(self) -> date:
        return min(record.record_date for record in self.records)

    @property
    def end_date(self) -> date:
        return max(record.record_date for record in self.records)

    @property
    def has_settlement(self) -> bool:
        return any(record.settlement_outcome is not None for record in self.records)

    @property
    def settlement_coverage(self) -> str:
        settled = len([record for record in self.records if record.settlement_outcome is not None])
        if settled == 0:
            return "none"
        if settled == len(self.records):
            return "full"
        return "partial"

    @property
    def has_evidence(self) -> bool:
        return any(record.evidence for record in self.records)

    def default_market_id(self) -> str | None:
        market_ids = self.market_ids
        return market_ids[0] if len(market_ids) == 1 else None

    def records_for_market(
        self,
        market_id: str | None,
    ) -> tuple[HistoricalMarketRecord, ...]:
        return self._records_for_market(market_id)

    def has_settlement_for_market(self, market_id: str | None) -> bool:
        return any(
            record.settlement_outcome is not None
            for record in self._records_for_market(market_id)
        )

    def settlement_coverage_for_market(self, market_id: str | None) -> str:
        records = self._records_for_market(market_id)
        settled = len([record for record in records if record.settlement_outcome is not None])
        if settled == 0:
            return "none"
        if settled == len(records):
            return "full"
        return "partial"

    def has_evidence_for_market(self, market_id: str | None) -> bool:
        return any(record.evidence for record in self._records_for_market(market_id))

    def range_for_market(self, market_id: str | None) -> tuple[date, date]:
        records = self._records_for_market(market_id)
        return (
            min(record.record_date for record in records),
            max(record.record_date for record in records),
        )

    def record_for_date(
        self,
        record_date: date,
        *,
        market_id: str | None = None,
    ) -> HistoricalMarketRecord:
        records = [
            record
            for record in self._records_for_market(market_id)
            if record.record_date == record_date
        ]
        if not records:
            selected = market_id or self.default_market_id() or "unselected"
            msg = f"historical record not found for {selected} on {record_date.isoformat()}"
            raise ValueError(msg)
        if len(records) > 1:
            msg = f"multiple historical records found for {record_date.isoformat()}; provide --market-id"
            raise ValueError(msg)
        return records[0]

    def validate_date_range(
        self,
        start_date: date,
        end_date: date,
        *,
        market_id: str | None = None,
    ) -> None:
        expected = {
            start_date.toordinal() + offset
            for offset in range((end_date - start_date).days + 1)
        }
        available = {
            record.record_date.toordinal()
            for record in self._records_for_market(market_id)
            if start_date <= record.record_date <= end_date
        }
        missing = sorted(date.fromordinal(day).isoformat() for day in expected - available)
        if missing:
            msg = f"historical dataset is missing records for dates: {', '.join(missing)}"
            raise ValueError(msg)

    def _records_for_market(self, market_id: str | None) -> tuple[HistoricalMarketRecord, ...]:
        selected = market_id or self.default_market_id()
        if selected is None:
            msg = (
                "historical dataset contains multiple market ids; provide --market-id "
                "to select one"
            )
            raise ValueError(msg)
        records = tuple(record for record in self.records if record.market_id == selected)
        if not records:
            msg = f"historical dataset has no records for market_id={selected}"
            raise ValueError(msg)
        return records


def load_historical_dataset(path: str | Path | None) -> HistoricalDataset:
    if path is None:
        msg = "--historical-file is required when --market-source is historical-file"
        raise ValueError(msg)
    dataset_path = Path(path)
    if not dataset_path.exists():
        msg = f"historical file not found: {dataset_path}"
        raise ValueError(msg)
    if dataset_path.suffix.lower() != ".jsonl":
        msg = "historical-file currently supports JSONL files only"
        raise ValueError(msg)

    records: list[HistoricalMarketRecord] = []
    for line_number, line in enumerate(dataset_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            msg = f"historical JSONL line {line_number} is invalid JSON"
            raise ValueError(msg) from exc
        if not isinstance(payload, dict):
            msg = f"historical JSONL line {line_number} must be an object"
            raise ValueError(msg)
        records.append(_record_from_payload(payload, line_number=line_number))

    if not records:
        msg = "historical dataset contains no records"
        raise ValueError(msg)

    sorted_records = sorted(records, key=lambda record: (record.timestamp, record.market_id))
    warnings: list[str] = []
    if records != sorted_records:
        warnings.append("Historical records were explicitly sorted by timestamp and market id.")
    _validate_duplicate_market_timestamps(sorted_records)
    if not any(record.settlement_outcome is not None for record in sorted_records):
        warnings.append(
            "Historical dataset has no settlement/outcome fields; final profitability "
            "claims are not meaningful."
        )
    if not any(record.evidence for record in sorted_records):
        warnings.append(
            "Historical dataset has no evidence records; research evidence is missing/limited."
        )
    return HistoricalDataset(
        path=dataset_path,
        records=tuple(sorted_records),
        warnings=tuple(warnings),
    )


def _record_from_payload(
    payload: dict[str, Any],
    *,
    line_number: int,
) -> HistoricalMarketRecord:
    timestamp = _parse_timestamp(payload, line_number=line_number)
    market_id = _required_text(payload, "market_id", line_number=line_number)
    profile = _optional_text(payload.get("profile"))
    calibration_only = profile in CALIBRATION_ONLY_PROFILES
    bid = _row_probability(
        payload,
        "bid",
        line_number=line_number,
        required=not calibration_only,
    )
    ask = _row_probability(
        payload,
        "ask",
        line_number=line_number,
        required=not calibration_only,
    )
    if bid is not None and ask is not None and bid > ask:
        msg = f"historical JSONL line {line_number} has invalid spread: bid exceeds ask"
        raise ValueError(msg)
    last_price = _required_probability(payload, "last_price", line_number=line_number)
    implied = _optional_probability(payload.get("implied_probability"), "implied_probability", line_number)
    if implied is None:
        implied = round((bid + ask) / 2, 4) if bid is not None and ask is not None else last_price
    liquidity = _optional_nonnegative(payload.get("liquidity"), "liquidity", line_number)
    volume = _optional_nonnegative(payload.get("volume"), "volume", line_number)
    evidence = tuple(_evidence_items(payload.get("evidence"), timestamp, line_number=line_number))
    (
        settlement,
        settlement_ambiguous,
        settlement_status,
        settlement_resolved_at,
        settlement_label_available_at,
    ) = _settlement_facts(payload, line_number=line_number)
    paper_pnl_allowed = _optional_bool(
        payload.get("paper_pnl_allowed"),
        default=not calibration_only,
        field="paper_pnl_allowed",
        line_number=line_number,
    )
    acceptance_candidate = _optional_bool(
        payload.get("acceptance_candidate"),
        default=not calibration_only,
        field="acceptance_candidate",
        line_number=line_number,
    )
    return HistoricalMarketRecord(
        timestamp=timestamp,
        market_id=market_id,
        bid=bid,
        ask=ask,
        last_price=last_price,
        implied_probability=implied,
        liquidity=liquidity,
        volume=volume,
        evidence=evidence,
        settlement_outcome=settlement,
        line_number=line_number,
        title=str(payload.get("title") or market_id),
        platform=str(payload.get("platform") or "historical-file"),
        profile=profile,
        paper_pnl_allowed=paper_pnl_allowed,
        acceptance_candidate=acceptance_candidate,
        settlement_ambiguous=settlement_ambiguous,
        settlement_status=settlement_status,
        settlement_resolved_at=settlement_resolved_at,
        settlement_label_available_at=settlement_label_available_at,
        observation_time_explicit=payload.get("timestamp") is not None,
    )


def _parse_timestamp(payload: dict[str, Any], *, line_number: int) -> datetime:
    raw_timestamp = payload.get("timestamp")
    raw_date = payload.get("date")
    if raw_timestamp is None and raw_date is None:
        msg = f"historical JSONL line {line_number} must include timestamp or date"
        raise ValueError(msg)
    if raw_timestamp is not None:
        value = str(raw_timestamp).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            msg = f"historical JSONL line {line_number} has invalid timestamp"
            raise ValueError(msg) from exc
        return _as_utc(parsed)
    try:
        parsed_date = date.fromisoformat(str(raw_date))
    except ValueError as exc:
        msg = f"historical JSONL line {line_number} has invalid date"
        raise ValueError(msg) from exc
    return datetime.combine(parsed_date, time(hour=16), tzinfo=UTC)


def _required_text(payload: dict[str, Any], field: str, *, line_number: int) -> str:
    value = payload.get(field)
    if value is None or not str(value).strip():
        msg = f"historical JSONL line {line_number} is missing required field: {field}"
        raise ValueError(msg)
    return str(value).strip()


def _optional_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    return text or None


def _row_probability(
    payload: dict[str, Any],
    field: str,
    *,
    line_number: int,
    required: bool,
) -> float | None:
    if required:
        return _required_probability(payload, field, line_number=line_number)
    return _optional_probability(payload.get(field), field, line_number)


def _required_probability(payload: dict[str, Any], field: str, *, line_number: int) -> float:
    if field not in payload:
        msg = f"historical JSONL line {line_number} is missing required field: {field}"
        raise ValueError(msg)
    value = _optional_probability(payload[field], field, line_number)
    if value is None:
        msg = f"historical JSONL line {line_number} has invalid probability field: {field}"
        raise ValueError(msg)
    return value


def _optional_probability(value: object, field: str, line_number: int) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        msg = f"historical JSONL line {line_number} has invalid probability field: {field}"
        raise ValueError(msg) from exc
    if not 0 <= parsed <= 1:
        msg = f"historical JSONL line {line_number} probability field out of range: {field}"
        raise ValueError(msg)
    return parsed


def _optional_nonnegative(value: object, field: str, line_number: int) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        msg = f"historical JSONL line {line_number} has invalid nonnegative field: {field}"
        raise ValueError(msg) from exc
    if parsed < 0:
        msg = f"historical JSONL line {line_number} field must be nonnegative: {field}"
        raise ValueError(msg)
    return parsed


def _optional_bool(
    value: object,
    *,
    default: bool,
    field: str,
    line_number: int,
) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    msg = f"historical JSONL line {line_number} has invalid boolean field: {field}"
    raise ValueError(msg)


def _evidence_items(
    raw_evidence: object,
    record_timestamp: datetime,
    *,
    line_number: int,
) -> list[EvidenceItem]:
    if raw_evidence in (None, ""):
        return []
    if not isinstance(raw_evidence, list):
        msg = f"historical JSONL line {line_number} evidence must be a list"
        raise ValueError(msg)
    items: list[EvidenceItem] = []
    for index, item in enumerate(raw_evidence, start=1):
        if not isinstance(item, dict):
            msg = f"historical JSONL line {line_number} evidence item {index} must be an object"
            raise ValueError(msg)
        payload = dict(item)
        if "published_at" in payload and payload["published_at"] not in (None, ""):
            published_at = _as_utc(
                datetime.fromisoformat(str(payload["published_at"]).replace("Z", "+00:00"))
            )
            if published_at > record_timestamp:
                msg = (
                    f"historical JSONL line {line_number} evidence item {index} "
                    "is published after the market record timestamp"
                )
                raise ValueError(msg)
            payload["published_at"] = published_at
        payload.setdefault("source", "historical-file")
        payload.setdefault("title", f"Historical evidence line {line_number}.{index}")
        payload.setdefault("summary", payload["title"])
        payload.setdefault("relevance_score", 0.5)
        payload.setdefault("credibility_score", 0.5)
        items.append(EvidenceItem.model_validate(payload))
    return items


def _settlement_facts(
    payload: dict[str, Any],
    *,
    line_number: int,
) -> tuple[str | None, bool | None, str | None, datetime | None, datetime | None]:
    raw_settlement = payload.get("settlement")
    ambiguous = None
    status = None
    resolved_at = None
    label_available_at = None
    if isinstance(raw_settlement, dict):
        ambiguous = _optional_nullable_bool(
            raw_settlement.get("ambiguous"),
            field="settlement.ambiguous",
            line_number=line_number,
        )
        status = _optional_text(raw_settlement.get("status"))
        resolved_at = _optional_timestamp(
            raw_settlement.get("resolved_at"),
            field="settlement.resolved_at",
            line_number=line_number,
        )
        label_available_at = _optional_timestamp(
            raw_settlement.get("label_available_at"),
            field="settlement.label_available_at",
            line_number=line_number,
        )
    value = payload.get("settlement_outcome", payload.get("outcome", raw_settlement))
    if isinstance(value, dict):
        value = value.get("outcome")
    if value is None or value == "":
        return None, ambiguous, status, resolved_at, label_available_at
    normalized = str(value).strip().lower()
    if normalized not in SUPPORTED_SETTLEMENT_OUTCOMES:
        msg = (
            f"historical JSONL line {line_number} has unsupported settlement outcome: "
            f"{value}"
        )
        raise ValueError(msg)
    return normalized, ambiguous, status, resolved_at, label_available_at


def _optional_timestamp(value: object, *, field: str, line_number: int) -> datetime | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        msg = f"historical JSONL line {line_number} has invalid {field}"
        raise ValueError(msg) from exc
    return _as_utc(parsed)


def settlement_label_publication_time(record: HistoricalMarketRecord) -> datetime | None:
    """Return when a settlement label may be shown, if the row documents that time."""
    times = [
        moment
        for moment in (record.settlement_label_available_at, record.settlement_resolved_at)
        if moment is not None
    ]
    if not times:
        return None
    return max(times)


def _without_settlement_label(record: HistoricalMarketRecord) -> HistoricalMarketRecord:
    if (
        record.settlement_outcome is None
        and record.settlement_ambiguous is None
        and record.settlement_status is None
    ):
        return record
    return replace(
        record,
        settlement_outcome=None,
        settlement_ambiguous=None,
        settlement_status=None,
    )


def record_with_visible_settlement(
    record: HistoricalMarketRecord,
    as_of: datetime,
) -> HistoricalMarketRecord:
    """Drop a settlement label that is not published yet. The row itself stays."""
    published_at = settlement_label_publication_time(record)
    if record.settlement_outcome is None or published_at is None or published_at <= _as_utc(as_of):
        return record
    return _without_settlement_label(record)


def record_known_at(record: HistoricalMarketRecord, as_of: datetime) -> bool:
    """Whether this observation exists at as_of.

    A date-only row is visible for that whole UTC date. An explicit timestamp
    stays hidden until that UTC instant.
    """
    moment = _as_utc(as_of)
    if record.observation_time_explicit:
        return record.timestamp <= moment
    return record.record_date <= moment.date()


def records_known_at(
    records: tuple[HistoricalMarketRecord, ...] | list[HistoricalMarketRecord],
    as_of: datetime,
) -> tuple[HistoricalMarketRecord, ...]:
    """Rows already observed at as_of, with unpublished settlement labels removed."""
    return tuple(
        record_with_visible_settlement(record, as_of)
        for record in records
        if record_known_at(record, as_of)
    )


def input_record_at(
    dataset: HistoricalDataset,
    as_of: datetime,
    *,
    market_id: str | None = None,
) -> HistoricalMarketRecord:
    """Choose the row a simulated day may use as its market input.

    The row for that date is the input once it is observed. If its explicit
    timestamp is still ahead and an earlier row is already visible, that
    earlier row is the input. A file with no earlier row keeps the dated row
    so the single-day input still exists; the caller hides its label.
    """
    dated = dataset.record_for_date(_as_utc(as_of).date(), market_id=market_id)
    if record_known_at(dated, as_of):
        return dated
    known = records_known_at(dataset.records_for_market(dated.market_id), as_of)
    if known:
        return known[-1]
    return dated


def _optional_nullable_bool(value: object, *, field: str, line_number: int) -> bool | None:
    if value is None or value == "":
        return None
    return _optional_bool(value, default=False, field=field, line_number=line_number)


def _validate_duplicate_market_timestamps(records: list[HistoricalMarketRecord]) -> None:
    seen: set[tuple[datetime, str]] = set()
    for record in records:
        key = (record.timestamp, record.market_id)
        if key in seen:
            msg = (
                "historical dataset contains duplicate records for "
                f"market_id={record.market_id} timestamp={record.timestamp.isoformat()}"
            )
            raise ValueError(msg)
        seen.add(key)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


_ACCEPTED_SETTLEMENT_STATUSES = {None, "settled"}
LABEL_WITH_SETTLEMENT = "historical local dataset with settlement"
LABEL_WITHOUT_SETTLEMENT = "historical local dataset without settlement"
LABEL_PAPER_INELIGIBLE = "historical local dataset without paper-profit eligibility"
NOTE_WITH_SETTLEMENT = (
    "A local time-indexed historical dataset with settlement/outcome fields "
    "was used; paper PnL can be interpreted only within the dataset and "
    "paper-fill assumptions."
)
NOTE_WITHOUT_SETTLEMENT = (
    "A local time-indexed historical dataset was used, but settlement/outcome "
    "fields are missing; final profitability claims are not meaningful."
)
_BLOCK_NOTES = {
    "calibration_only_last_price": (
        "Calibration-only last-price data cannot be used as paper-profit proof. "
        "Settlement labels stay available for calibration and are not a "
        "closed-position paper result."
    ),
    "paper_pnl_not_allowed": (
        "Paper PnL is explicitly not allowed for this selection. "
        "Profitability claims are not meaningful."
    ),
    "acceptance_not_allowed": (
        "This selection is not an acceptance candidate. "
        "Profitability claims are not meaningful."
    ),
    "missing_bid_ask": (
        "Bid and ask quotes are missing, so closed-position paper evaluation "
        "is not supported."
    ),
    "ambiguous_settlement": (
        "Settlement is explicitly ambiguous. The original settlement information "
        "stays visible, and it is not paper-profit proof."
    ),
    "pending_settlement": (
        "Settlement is pending or not a settled outcome. "
        "Profitability claims are not meaningful."
    ),
    "conflicting_settlement": (
        "Selected rows disagree on the settlement outcome. "
        "Profitability claims are not meaningful."
    ),
    "ineligible_rows": (
        "This selection includes rows that are not eligible for paper evaluation. "
        "Only eligible rows can support paper evaluation, and the selection is "
        "not paper-profit proof."
    ),
}
_MIXED_ROW_SENTENCE = (
    " Eligible rows remain marked individually and are the only rows that can "
    "support paper evaluation."
)


@dataclass(frozen=True)
class HistoricalRecordQualification:
    line_number: int
    record_date: str
    market_id: str
    profile: str | None
    paper_pnl_allowed: bool
    acceptance_candidate: bool
    bid_ask_present: bool
    settlement_outcome: str | None
    settlement_ambiguous: bool | None
    settlement_status: str | None
    credible_settlement: bool
    paper_evaluation_allowed: bool
    block_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "line_number": self.line_number,
            "record_date": self.record_date,
            "market_id": self.market_id,
            "profile": self.profile,
            "paper_pnl_allowed": self.paper_pnl_allowed,
            "acceptance_candidate": self.acceptance_candidate,
            "bid_ask_present": self.bid_ask_present,
            "settlement_outcome": self.settlement_outcome,
            "settlement_ambiguous": self.settlement_ambiguous,
            "settlement_status": self.settlement_status,
            "credible_settlement": self.credible_settlement,
            "paper_evaluation_allowed": self.paper_evaluation_allowed,
            "block_reason": self.block_reason,
        }


@dataclass(frozen=True)
class HistoricalSelectionQualification:
    records: tuple[HistoricalRecordQualification, ...]
    profitability_claims_meaningful: bool
    closed_position_evaluation_supported: bool
    has_settlement: bool
    settlement_label_present: bool
    credible_settlement: bool
    settlement_outcome: str | None
    settlement_ambiguous: bool | None
    settlement_status: str | None
    paper_pnl_allowed: bool | None
    acceptance_candidate: bool | None
    historical_profile: str | None
    block_reason: str | None
    paper_profit_label: str
    paper_profit_note: str

    @property
    def eligible_row_count(self) -> int:
        return sum(record.paper_evaluation_allowed for record in self.records)

    @property
    def ineligible_row_count(self) -> int:
        return len(self.records) - self.eligible_row_count


def credible_settlement_accepted(record: HistoricalMarketRecord) -> bool:
    """Accept a settlement label for paper evaluation only when it is explicit and unambiguous."""
    if record.settlement_outcome not in SUPPORTED_SETTLEMENT_OUTCOMES:
        return False
    if record.settlement_ambiguous is True:
        return False
    return _settlement_status_key(record.settlement_status) in _ACCEPTED_SETTLEMENT_STATUSES


def qualify_historical_records(
    records: tuple[HistoricalMarketRecord, ...] | list[HistoricalMarketRecord],
) -> HistoricalSelectionQualification:
    selected = tuple(records)
    qualifications = tuple(_qualify_record(record) for record in selected)
    outcomes = {
        record.settlement_outcome
        for record in selected
        if record.settlement_outcome in SUPPORTED_SETTLEMENT_OUTCOMES
    }
    settlement_outcome = next(iter(outcomes)) if len(outcomes) == 1 else None
    ambiguous_flags = [
        record.settlement_ambiguous
        for record in selected
        if record.settlement_ambiguous is not None
    ]
    if any(flag is True for flag in ambiguous_flags):
        settlement_ambiguous: bool | None = True
    elif ambiguous_flags:
        settlement_ambiguous = False
    else:
        settlement_ambiguous = None
    statuses = {
        record.settlement_status
        for record in selected
        if _settlement_status_key(record.settlement_status) is not None
    }
    settlement_status = next(iter(statuses)) if len(statuses) == 1 else None
    profiles = {record.profile for record in selected if record.profile}
    historical_profile = next(iter(profiles)) if len(profiles) == 1 else None
    paper_pnl_allowed = all(record.paper_pnl_allowed for record in selected) if selected else None
    acceptance_candidate = (
        all(record.acceptance_candidate for record in selected) if selected else None
    )
    credible_rows = [record for record in selected if credible_settlement_accepted(record)]
    block_reason = _selection_block_reason(
        selected,
        qualifications,
        conflicting_outcomes=len(outcomes) > 1,
        credible_rows=len(credible_rows),
    )
    allowed = block_reason is None
    settlement_label_present = bool(outcomes)
    label, note = _paper_profit_copy(block_reason, qualifications)
    return HistoricalSelectionQualification(
        records=qualifications,
        profitability_claims_meaningful=allowed,
        closed_position_evaluation_supported=allowed,
        has_settlement=settlement_label_present,
        settlement_label_present=settlement_label_present,
        credible_settlement=bool(credible_rows) and len(outcomes) <= 1,
        settlement_outcome=settlement_outcome,
        settlement_ambiguous=settlement_ambiguous,
        settlement_status=settlement_status,
        paper_pnl_allowed=paper_pnl_allowed,
        acceptance_candidate=acceptance_candidate,
        historical_profile=historical_profile,
        block_reason=block_reason,
        paper_profit_label=label,
        paper_profit_note=note,
    )


def _qualify_record(record: HistoricalMarketRecord) -> HistoricalRecordQualification:
    block_reason = _record_block_reason(record)
    return HistoricalRecordQualification(
        line_number=record.line_number,
        record_date=record.record_date.isoformat(),
        market_id=record.market_id,
        profile=record.profile,
        paper_pnl_allowed=record.paper_pnl_allowed,
        acceptance_candidate=record.acceptance_candidate,
        bid_ask_present=record.bid is not None and record.ask is not None,
        settlement_outcome=record.settlement_outcome,
        settlement_ambiguous=record.settlement_ambiguous,
        settlement_status=record.settlement_status,
        credible_settlement=credible_settlement_accepted(record),
        paper_evaluation_allowed=block_reason is None,
        block_reason=block_reason,
    )


def _record_block_reason(record: HistoricalMarketRecord) -> str | None:
    if record.profile in CALIBRATION_ONLY_PROFILES:
        return "calibration_only_last_price"
    if not record.paper_pnl_allowed:
        return "paper_pnl_not_allowed"
    if not record.acceptance_candidate:
        return "acceptance_not_allowed"
    if record.bid is None or record.ask is None:
        return "missing_bid_ask"
    if record.settlement_ambiguous is True:
        return "ambiguous_settlement"
    if _settlement_status_key(record.settlement_status) not in _ACCEPTED_SETTLEMENT_STATUSES:
        return "pending_settlement"
    return None


def _selection_block_reason(
    records: tuple[HistoricalMarketRecord, ...],
    qualifications: tuple[HistoricalRecordQualification, ...],
    *,
    conflicting_outcomes: bool,
    credible_rows: int,
) -> str | None:
    if any(record.profile in CALIBRATION_ONLY_PROFILES for record in records):
        return "calibration_only_last_price"
    if any(not record.paper_pnl_allowed for record in records):
        return "paper_pnl_not_allowed"
    if any(not record.acceptance_candidate for record in records):
        return "acceptance_not_allowed"
    if any(record.bid is None or record.ask is None for record in records):
        return "missing_bid_ask"
    if any(record.settlement_ambiguous is True for record in records):
        return "ambiguous_settlement"
    if any(
        _settlement_status_key(record.settlement_status) not in _ACCEPTED_SETTLEMENT_STATUSES
        for record in records
    ):
        return "pending_settlement"
    if conflicting_outcomes:
        return "conflicting_settlement"
    if any(record.block_reason for record in qualifications):
        return "ineligible_rows"
    if credible_rows == 0:
        return "no_credible_settlement"
    return None


def _paper_profit_copy(
    block_reason: str | None,
    qualifications: tuple[HistoricalRecordQualification, ...],
) -> tuple[str, str]:
    if block_reason is None:
        return LABEL_WITH_SETTLEMENT, NOTE_WITH_SETTLEMENT
    if block_reason == "no_credible_settlement":
        return LABEL_WITHOUT_SETTLEMENT, NOTE_WITHOUT_SETTLEMENT
    note = _BLOCK_NOTES[block_reason]
    eligible = sum(record.paper_evaluation_allowed for record in qualifications)
    ineligible = len(qualifications) - eligible
    if eligible and ineligible:
        note += _MIXED_ROW_SENTENCE
    return LABEL_PAPER_INELIGIBLE, note


def _settlement_status_key(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = status.strip().lower()
    return normalized or None
