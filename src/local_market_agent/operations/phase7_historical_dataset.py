from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from local_market_agent.schemas import EvidenceItem, Market, MarketSnapshot
from local_market_agent.schemas.models import MarketStatus, MarketType

SUPPORTED_SETTLEMENT_OUTCOMES = {"yes", "no"}


@dataclass(frozen=True)
class HistoricalMarketRecord:
    timestamp: datetime
    market_id: str
    bid: float
    ask: float
    last_price: float
    implied_probability: float
    liquidity: float | None
    volume: float | None
    evidence: tuple[EvidenceItem, ...]
    settlement_outcome: str | None
    line_number: int
    title: str
    platform: str

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
    _validate_duplicate_dates(sorted_records)
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
    bid = _required_probability(payload, "bid", line_number=line_number)
    ask = _required_probability(payload, "ask", line_number=line_number)
    if bid > ask:
        msg = f"historical JSONL line {line_number} has invalid spread: bid exceeds ask"
        raise ValueError(msg)
    last_price = _required_probability(payload, "last_price", line_number=line_number)
    implied = _optional_probability(payload.get("implied_probability"), "implied_probability", line_number)
    if implied is None:
        implied = round((bid + ask) / 2, 4)
    liquidity = _optional_nonnegative(payload.get("liquidity"), "liquidity", line_number)
    volume = _optional_nonnegative(payload.get("volume"), "volume", line_number)
    evidence = tuple(_evidence_items(payload.get("evidence"), timestamp, line_number=line_number))
    settlement = _settlement_outcome(payload, line_number=line_number)
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


def _settlement_outcome(payload: dict[str, Any], *, line_number: int) -> str | None:
    value = payload.get("settlement_outcome", payload.get("outcome", payload.get("settlement")))
    if value is None or value == "":
        return None
    normalized = str(value).strip().lower()
    if normalized not in SUPPORTED_SETTLEMENT_OUTCOMES:
        msg = (
            f"historical JSONL line {line_number} has unsupported settlement outcome: "
            f"{value}"
        )
        raise ValueError(msg)
    return normalized


def _validate_duplicate_dates(records: list[HistoricalMarketRecord]) -> None:
    seen: set[tuple[date, str]] = set()
    for record in records:
        key = (record.record_date, record.market_id)
        if key in seen:
            msg = (
                "historical dataset contains duplicate records for "
                f"market_id={record.market_id} date={record.record_date.isoformat()}"
            )
            raise ValueError(msg)
        seen.add(key)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
