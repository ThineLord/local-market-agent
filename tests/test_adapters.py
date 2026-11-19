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


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-0.1", "1.1", "broken", True, False, "true", "false"])
def test_kalshi_invalid_price_is_not_clipped(price):
    with pytest.raises(ValueError):
        KalshiAdapter().normalize_market({"ticker": "BAD", "yes_bid_dollars": price})


def test_kalshi_boolean_cent_price_is_not_one_cent():
    with pytest.raises(ValueError, match="probability"):
        KalshiAdapter().normalize_market({"ticker": "BAD", "yes_bid": True})
    legacy = KalshiAdapter().normalize_market({"ticker": "CENT", "yes_bid": 1, "yes_ask": 2})
    assert (legacy.best_bid, legacy.best_ask) == (0.01, 0.02)


def test_polymarket_zero_midpoint_and_bad_probability():
    adapter = PolymarketAdapter()
    snapshot = adapter._normalize({"id": "zero", "bestBid": 0, "bestAsk": 0, "lastTradePrice": 0.3})
    assert snapshot.market_implied_probability == 0
    with pytest.raises(ValueError):
        adapter._normalize({"id": "bad", "bestBid": 2})
    boolean_quote = adapter._normalize({"id": "flag", "bestBid": True, "lastTradePrice": 0.3})
    assert boolean_quote.best_bid is None
    assert boolean_quote.market_implied_probability == 0.3


def test_polymarket_missing_id_is_not_the_string_none():
    adapter = PolymarketAdapter()
    for payload in ({}, {"id": None, "conditionId": None, "slug": None}, {"id": "", "slug": None}):
        with pytest.raises(ValueError, match="missing its id"):
            adapter._normalize(payload)
    numeric = adapter._normalize({"id": 12345, "slug": "kept", "question": "Q"})
    assert numeric.market.market_id == "12345"
    assert numeric.market.url == "https://polymarket.com/event/kept"
    condition = adapter._normalize({"conditionId": "0xabc", "slug": None, "question": "Q"})
    assert condition.market.market_id == "0xabc"
    assert condition.market.url == "https://polymarket.com/event/0xabc"
    literal = adapter._normalize({"id": "m2", "slug": "literal-None"})
    assert literal.market.url == "https://polymarket.com/event/literal-None"


def test_polymarket_boolean_strings_and_comma_outcomes():
    adapter = PolymarketAdapter()
    inactive = adapter._normalize({"id": "a", "active": "false"})
    assert inactive.market.status == "closed"
    opened = adapter._normalize({"id": "b", "active": "true", "closed": "false"})
    assert opened.market.status == "open"
    still_open = adapter._normalize({"id": "d", "active": True, "closed": False})
    assert still_open.market.status == "open"
    still_closed = adapter._normalize({"id": "e", "active": False, "closed": True})
    assert still_closed.market.status == "closed"
    quoted = adapter._normalize({
        "id": "labels",
        "outcomes": '["Alpha, Beta", "Gamma"]',
    })
    assert quoted.market.outcomes == ["Alpha, Beta", "Gamma"]
    both = adapter._normalize({
        "id": "both",
        "outcomes": '["S&P 500 above 5,000", "S&P 500 below 5,000"]',
    })
    assert both.market.outcomes == ["S&P 500 above 5,000", "S&P 500 below 5,000"]
    plain = adapter._normalize({"id": "plain", "outcomes": "Yes,No"})
    assert plain.market.outcomes == ["Yes", "No"]
    tokens = adapter._normalize({"id": "tokens", "outcomes": "[true, false]"})
    assert tokens.market.outcomes == ["true", "false"]
    listed = adapter._normalize({"id": "listed", "outcomes": ["Yes", "No"]})
    assert listed.market.outcomes == ["Yes", "No"]


def test_polymarket_search_encodes_ampersand(monkeypatch):
    calls: list[str] = []

    def fake_get_json(url: str, *, headers=None):
        calls.append(url)
        return []

    monkeypatch.setattr("local_market_agent.adapters.polymarket.safe_get_json", fake_get_json)
    PolymarketAdapter().search("S&P")
    PolymarketAdapter().search("election")
    assert calls == [
        "https://gamma-api.polymarket.com/markets?search=S%26P&limit=10",
        "https://gamma-api.polymarket.com/markets?search=election&limit=10",
    ]


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


@pytest.mark.parametrize(("bid_size", "ask_size", "expected"), [
    ("30.00", "10.00", 1.3), ("300.50", "1000.00", 130.0),
    ("0.00", "1000.00", 0), (None, "1000.00", None),
])
def test_kalshi_current_best_ask_capacity(bid_size, ask_size, expected):
    payload = {"ticker": "DEPTH", "yes_bid_dollars": "0.1200", "yes_ask_dollars": "0.1300",
               "yes_bid_size_fp": bid_size, "yes_ask_size_fp": ask_size,
               "volume_fp": "999999", "open_interest_fp": "999999", "liquidity_dollars": "999999"}
    snapshot = KalshiAdapter().normalize_market(payload)
    assert snapshot.liquidity == expected


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "broken", True])
def test_kalshi_rejects_invalid_depth(value):
    with pytest.raises(ValueError):
        KalshiAdapter().normalize_market({"ticker": "BAD", "yes_bid_size_fp": value})


def test_kalshi_legacy_liquidity_units_and_missing_depth():
    adapter = KalshiAdapter()
    assert adapter.normalize_market({"ticker": "X", "liquidity": 12345}).liquidity == 123.45
    assert adapter.normalize_market({"ticker": "X", "liquidity_dollars": "123.45", "liquidity": 999}).liquidity == 123.45
    assert adapter.normalize_market({"ticker": "X", "volume_fp": "99999", "open_interest_fp": "99999"}).liquidity is None
    assert adapter.normalize_market({"ticker": "X", "liquidity_dollars": None, "liquidity": 999}).liquidity is None
