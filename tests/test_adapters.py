from __future__ import annotations

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
