from __future__ import annotations

import pytest

from local_market_agent.adapters import KalshiAdapter, PolymarketAdapter


def test_polymarket_price_and_orderbook_methods_are_read_only(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_get_json(url: str, *, headers=None):
        calls.append(url)
        if "/price?" in url:
            return {"price": "0.42"}
        return {"bids": [{"price": "0.41", "size": "10"}], "asks": []}

    monkeypatch.setattr("local_market_agent.adapters.polymarket.safe_get_json", fake_get_json)
    adapter = PolymarketAdapter(raw_cache_dir=tmp_path)

    assert adapter.fetch_price("token-1", side="buy") == 0.42
    assert adapter.fetch_orderbook("token-1")["bids"][0]["price"] == "0.41"
    assert all("/order" not in url for url in calls)


def test_kalshi_dollar_fields_and_one_cent_are_not_confused(tmp_path):
    adapter = KalshiAdapter(raw_cache_dir=tmp_path)
    legacy = adapter.normalize_market({"ticker": "CENT", "yes_bid": 1, "yes_ask": 2})
    assert (legacy.best_bid, legacy.best_ask) == (0.01, 0.02)
    current = adapter.normalize_market({
        "ticker": "CURRENT", "status": "active", "yes_bid": 50,
        "yes_bid_dollars": "0.0100", "yes_ask_dollars": "0.0200",
        "last_price_dollars": "0.0150", "volume_fp": "100.50",
        "close_time": "2026-10-15T15:00:00Z",
    })
    assert (current.best_bid, current.best_ask, current.last_price) == (0.01, 0.02, 0.015)
    assert current.volume == 100.5
    assert current.liquidity is None
    assert current.market.close_time is not None


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-0.1", "1.1", "broken"])
def test_kalshi_invalid_price_is_not_clipped(price):
    with pytest.raises(ValueError):
        KalshiAdapter().normalize_market({"ticker": "BAD", "yes_bid_dollars": price})


def test_polymarket_zero_midpoint_and_bad_probability():
    adapter = PolymarketAdapter()
    snapshot = adapter._normalize({"id": "zero", "bestBid": 0, "bestAsk": 0, "lastTradePrice": 0.3})
    assert snapshot.market_implied_probability == 0
    with pytest.raises(ValueError):
        adapter._normalize({"id": "bad", "bestBid": 2})


def test_kalshi_fetch_snapshot_is_read_only(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_get_json(url: str, *, headers=None):
        calls.append(url)
        return {
            "market": {
                "ticker": "KXTEST",
                "title": "Will test market resolve yes?",
                "status": "active",
                "yes_bid": 41,
                "yes_ask": 43,
                "volume": 1000,
                "liquidity": 500,
            }
        }

    monkeypatch.setattr("local_market_agent.adapters.kalshi.safe_get_json", fake_get_json)
    adapter = KalshiAdapter(raw_cache_dir=tmp_path)

    snapshot = adapter.fetch_snapshot("KXTEST")

    assert snapshot.market.market_id == "KXTEST"
    assert snapshot.market.platform == "kalshi"
    assert snapshot.best_bid == 0.41
    assert snapshot.best_ask == 0.43
    assert calls == [f"{KalshiAdapter.BASE_URL}/markets/KXTEST"]
    assert all("/order" not in url for url in calls)
