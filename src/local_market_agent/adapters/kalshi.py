from __future__ import annotations

from pathlib import Path
from typing import Any

from local_market_agent.adapters.base import cache_json, safe_get_json
from local_market_agent.schemas import Market, MarketSnapshot
from local_market_agent.schemas.models import MarketStatus, MarketType


class KalshiAdapter:
    """Read-only Kalshi public/demo adapter.

    This adapter intentionally exposes only public market metadata methods. It does not support
    private endpoints, credentials, order placement, or withdrawals.
    """

    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

    def __init__(self, raw_cache_dir: str | Path = "data/raw_cache") -> None:
        self.raw_cache_dir = Path(raw_cache_dir)

    def list_markets(self, limit: int = 10) -> list[dict[str, Any]]:
        url = f"{self.BASE_URL}/markets?limit={limit}"
        payload = safe_get_json(url)
        cache_json(self.raw_cache_dir, url, payload)
        if isinstance(payload, dict) and isinstance(payload.get("markets"), list):
            return [item for item in payload["markets"] if isinstance(item, dict)]
        return []

    def normalize_market(self, payload: dict[str, Any]) -> MarketSnapshot:
        ticker = str(payload.get("ticker") or payload.get("event_ticker") or "kalshi-demo")
        yes_bid = _price(payload.get("yes_bid"))
        yes_ask = _price(payload.get("yes_ask"))
        market = Market(
            market_id=ticker,
            title=str(payload.get("title") or payload.get("subtitle") or ticker),
            platform="kalshi",
            market_type=MarketType.PREDICTION,
            status=MarketStatus.OPEN if payload.get("status") == "active" else MarketStatus.UNKNOWN,
            url=None,
            outcomes=["yes", "no"],
        )
        implied = None
        if yes_bid is not None and yes_ask is not None:
            implied = round((yes_bid + yes_ask) / 2, 4)
        return MarketSnapshot(
            market=market,
            best_bid=yes_bid,
            best_ask=yes_ask,
            market_implied_probability=implied,
            volume=_float_or_none(payload.get("volume")),
            liquidity=_float_or_none(payload.get("liquidity")),
        )


def _price(value: object) -> float | None:
    parsed = _float_or_none(value)
    if parsed is None:
        return None
    if parsed > 1:
        parsed = parsed / 100
    return min(1.0, max(0.0, parsed))


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
