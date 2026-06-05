from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from local_market_agent.adapters import (
    FixtureAdapter,
    KalshiAdapter,
    PolymarketAdapter,
    YFinanceAdapter,
)
from local_market_agent.schemas import EvidenceItem, Market, MarketSnapshot
from local_market_agent.schemas.models import MarketStatus, MarketType, new_id

MARKET_SOURCE_FIXTURE = "fixture"
MARKET_SOURCE_POLYMARKET = "polymarket"
MARKET_SOURCE_KALSHI = "kalshi"
MARKET_SOURCE_YFINANCE = "yfinance"
SUPPORTED_MARKET_SOURCES = {
    MARKET_SOURCE_FIXTURE,
    MARKET_SOURCE_POLYMARKET,
    MARKET_SOURCE_KALSHI,
    MARKET_SOURCE_YFINANCE,
}

DATA_MODE_FIXTURE = "fixture"
DATA_MODE_CURRENT_SNAPSHOT = "current_snapshot"


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
    configuration_error: str | None = None

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
            "configuration_error": self.configuration_error,
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
) -> Phase7MarketDataAudit:
    source = normalize_market_source(market_source)
    market_id = _optional_text(market_id)
    is_fixture = source == MARKET_SOURCE_FIXTURE
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
) -> Phase7MarketInputs:
    market_id = _optional_text(market_id)
    audit = phase7_market_data_audit(market_source, market_id=market_id)
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
    else:
        # normalize_market_source prevents this branch; keep it for type checkers.
        msg = f"unsupported market source '{audit.market_source}'"
        raise ValueError(msg)

    if refresh_market_timestamp:
        snapshot = snapshot.model_copy(
            update={"snapshot_id": new_id("snapshot"), "as_of": _as_utc(now)}
        )
    return Phase7MarketInputs(snapshot=snapshot, evidence=evidence, audit=audit)


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
