from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from local_market_agent.adapters.base import cache_json, safe_get_json
from local_market_agent.schemas import Market, MarketSnapshot
from local_market_agent.schemas.models import MarketStatus, MarketType


class PolymarketAdapter:
    """Read-only public Polymarket metadata adapter."""

    BASE_URL = "https://gamma-api.polymarket.com"
    CLOB_URL = "https://clob.polymarket.com"

    def __init__(self, raw_cache_dir: str | Path = "data/raw_cache") -> None:
        self.raw_cache_dir = Path(raw_cache_dir)

    def fetch_snapshot(self, market_id: str) -> MarketSnapshot:
        url = f"{self.BASE_URL}/markets/{quote(market_id, safe='')}"
        payload = safe_get_json(url)
        cache_json(self.raw_cache_dir, url, payload)
        if not isinstance(payload, dict):
            msg = "unexpected Polymarket response"
            raise RuntimeError(msg)
        return self._normalize(payload)

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        url = f"{self.BASE_URL}/markets?search={query}&limit={limit}"
        payload = safe_get_json(url)
        cache_json(self.raw_cache_dir, url, payload)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def fetch_price(self, token_id: str, side: str = "buy") -> float | None:
        normalized_side = side.lower()
        if normalized_side not in {"buy", "sell"}:
            msg = "side must be buy or sell"
            raise ValueError(msg)
        url = f"{self.CLOB_URL}/price?token_id={token_id}&side={normalized_side}"
        payload = safe_get_json(url)
        cache_json(self.raw_cache_dir, url, payload)
        if not isinstance(payload, dict):
            msg = "unexpected Polymarket price response"
            raise RuntimeError(msg)
        return _first_probability(payload, ["price"])

    def fetch_orderbook(self, token_id: str) -> dict[str, Any]:
        url = f"{self.CLOB_URL}/book?token_id={token_id}"
        payload = safe_get_json(url)
        cache_json(self.raw_cache_dir, url, payload)
        if not isinstance(payload, dict):
            msg = "unexpected Polymarket orderbook response"
            raise RuntimeError(msg)
        return payload

    def _normalize(self, payload: dict[str, Any]) -> MarketSnapshot:
        market_id = str(payload.get("id") or payload.get("conditionId") or payload.get("slug"))
        title = str(payload.get("question") or payload.get("title") or market_id)
        active = bool(payload.get("active", False))
        closed = bool(payload.get("closed", False))
        status = MarketStatus.OPEN if active and not closed else MarketStatus.CLOSED
        market = Market(
            market_id=market_id,
            title=title,
            platform="polymarket",
            market_type=MarketType.PREDICTION,
            status=status,
            url=f"https://polymarket.com/event/{payload.get('slug', market_id)}",
            outcomes=_as_list(payload.get("outcomes")),
        )
        best_bid = _first_probability(payload, ["bestBid", "best_bid"])
        best_ask = _first_probability(payload, ["bestAsk", "best_ask"])
        last_price = _first_probability(payload, ["lastTradePrice", "last_price", "price"])
        implied = _midpoint(best_bid, best_ask)
        if implied is None:
            implied = last_price
        return MarketSnapshot(
            market=market,
            best_bid=best_bid,
            best_ask=best_ask,
            last_price=last_price,
            market_implied_probability=implied,
            volume=_float_or_none(payload.get("volume")),
            liquidity=_float_or_none(payload.get("liquidity")),
        )


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [part.strip() for part in value.strip("[]").replace('"', "").split(",") if part]
    return []


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _first_probability(payload: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = _float_or_none(payload.get(key))
        if value is not None:
            if not 0 <= value <= 1:
                raise ValueError("Invalid Polymarket probability")
            return value
    return None


def _midpoint(best_bid: float | None, best_ask: float | None) -> float | None:
    if best_bid is None or best_ask is None:
        return None
    return round((best_bid + best_ask) / 2, 4)
