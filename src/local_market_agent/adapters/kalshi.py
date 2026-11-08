from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from urllib.parse import quote

from local_market_agent.adapters.base import cache_json, safe_get_json
from local_market_agent.schemas import Market, MarketSnapshot
from local_market_agent.schemas.models import MarketStatus, MarketType


class KalshiAdapter:
    """Read-only Kalshi public/demo adapter.

    This adapter intentionally exposes only public market metadata methods. It does not support
    private endpoints, credentials, order placement, or withdrawals.
    """

    BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

    def __init__(self, raw_cache_dir: str | Path = "data/raw_cache") -> None:
        self.raw_cache_dir = Path(raw_cache_dir)

    def list_markets(self, limit: int = 10) -> list[dict[str, Any]]:
        url = f"{self.BASE_URL}/markets?limit={limit}"
        payload = safe_get_json(url)
        cache_json(self.raw_cache_dir, url, payload)
        if isinstance(payload, dict) and isinstance(payload.get("markets"), list):
            return [item for item in payload["markets"] if isinstance(item, dict)]
        return []

    def fetch_snapshot(self, market_id: str) -> MarketSnapshot:
        url = f"{self.BASE_URL}/markets/{quote(market_id, safe='')}"
        payload = safe_get_json(url)
        cache_json(self.raw_cache_dir, url, payload)
        if isinstance(payload, dict) and isinstance(payload.get("market"), dict):
            return self.normalize_market(payload["market"])
        if isinstance(payload, dict):
            return self.normalize_market(payload)
        msg = "unexpected Kalshi market response"
        raise RuntimeError(msg)

    def normalize_market(self, payload: dict[str, Any]) -> MarketSnapshot:
        ticker = payload.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("Kalshi market response is missing its ticker")
        if payload.get("market_type", "binary") != "binary":
            raise ValueError("Only binary Kalshi market snapshots are supported")
        yes_bid = _price(payload, "yes_bid")
        yes_ask = _price(payload, "yes_ask")
        status = {
            "active": MarketStatus.OPEN,
            "closed": MarketStatus.CLOSED,
            "determined": MarketStatus.CLOSED,
            "finalized": MarketStatus.SETTLED,
            "settled": MarketStatus.SETTLED,
        }.get(payload.get("status"), MarketStatus.UNKNOWN)
        market = Market(
            market_id=ticker,
            title=str(payload.get("title") or payload.get("subtitle") or ticker),
            platform="kalshi",
            market_type=MarketType.PREDICTION,
            status=status,
            close_time=payload.get("close_time"),
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
            last_price=_price(payload, "last_price"),
            market_implied_probability=implied,
            volume=_float_or_none(payload.get("volume_fp", payload.get("volume"))),
            liquidity=liquidity_details(payload)["value_usd"],
        )


def _price(payload: dict[str, Any], key: str) -> float | None:
    # Legacy fields are cents, even at 0 or 1; dollar strings are already probabilities.
    dollar_key = f"{key}_dollars"
    value = payload[dollar_key] if dollar_key in payload else payload.get(key)
    if value is None or value == "":
        return None
    parsed = float(value) / (1 if dollar_key in payload else 100)
    if not 0 <= parsed <= 1:
        raise ValueError(f"Invalid Kalshi {key} probability")
    return parsed


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def liquidity_details(payload: dict[str, Any]) -> dict[str, Any]:
    """Conservative buy capacity at the best YES and NO asks, in USD.

    YES ask size is the resting NO bid size; YES bid size is the resting
    YES bid size available to a buyer of NO at (1 - YES bid). No volume or
    open-interest fallback: those describe past trades/holdings, not capacity.
    """
    size_keys = ("yes_bid_size_fp", "yes_ask_size_fp")
    if any(key in payload for key in size_keys):
        bid, ask = _price(payload, "yes_bid"), _price(payload, "yes_ask")
        bid_size, ask_size = (_nonnegative(payload.get(key), key) for key in size_keys)
        yes_usd = ask * ask_size if ask is not None and ask_size is not None else None
        no_usd = (1 - bid) * bid_size if bid is not None and bid_size is not None else None
        return {"basis": "minimum_best_ask_buy_capacity_usd", "unit": "USD",
                "value_usd": min(yes_usd, no_usd) if yes_usd is not None and no_usd is not None else None,
                "yes_buy_capacity_usd": yes_usd, "no_buy_capacity_usd": no_usd,
                "yes_ask_size_contracts": ask_size, "yes_bid_size_contracts": bid_size}
    if "liquidity_dollars" in payload:
        value = _nonnegative(payload["liquidity_dollars"], "liquidity_dollars")
        basis = "legacy_reported_liquidity_dollars"
    else:
        cents = _nonnegative(payload.get("liquidity"), "liquidity")
        value = cents / 100 if cents is not None else None
        basis = "legacy_reported_liquidity_cents" if cents is not None else "unavailable"
    return {"basis": basis, "unit": "USD", "value_usd": value}


def _nonnegative(value: object, name: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"Invalid Kalshi {name}")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"Invalid Kalshi {name}")
    return parsed
