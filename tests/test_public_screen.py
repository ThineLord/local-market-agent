from datetime import UTC, datetime

import pytest

from local_market_agent.public_screen import screen_public_markets

NOW = datetime(2026, 11, 9, tzinfo=UTC)


def market(ticker="KXNBAGAME-A", size="1000.00"):
    return {"ticker": ticker, "status": "active", "market_type": "binary",
        "yes_bid_dollars": "0.49", "yes_ask_dollars": "0.51", "yes_bid_size_fp": size,
        "yes_ask_size_fp": size, "notional_value_dollars": "1.0000",
        "close_time": "2026-11-10T00:00:00Z"}


def test_public_screen_ranks_depth_and_keeps_failures(tmp_path, monkeypatch):
    calls = []
    def get(url):
        calls.append(url)
        return {"markets": [market(), market("KXNBAGAME-B", "5"), market("KXNBAGAME-C", "2000")], "cursor": ""}
    monkeypatch.setattr("local_market_agent.public_screen.safe_get_json", get)
    monkeypatch.setattr("local_market_agent.public_screen.utc_now", lambda: NOW)
    report = screen_public_markets(tmp_path / "scan", allow_network=True)
    assert len(calls) == 1 and "limit=200" in calls[0]
    assert report["ranked_market_ids"] == ["KXNBAGAME-C", "KXNBAGAME-A"]
    assert report["market_count"] == 3 and report["eligible_count"] == 2
    assert report["markets"][1]["blockers"] and not report["markets"][0]["probability_ready"]
    assert report["risk_thresholds"]["min_liquidity_depth"] == 100
    assert not list((tmp_path / "scan").glob("*.sqlite"))
    with pytest.raises(FileExistsError):
        screen_public_markets(tmp_path / "scan", allow_network=True)


def test_public_screen_is_bounded_and_opt_in(tmp_path, monkeypatch):
    calls = []
    def get(url):
        calls.append(url)
        return {"markets": [market()], "cursor": "more"}
    monkeypatch.setattr("local_market_agent.public_screen.safe_get_json", get)
    monkeypatch.setattr("local_market_agent.public_screen.utc_now", lambda: NOW)
    with pytest.raises(ValueError):
        screen_public_markets(tmp_path / "scan")
    assert not calls
    report = screen_public_markets(tmp_path / "scan", max_pages=1, allow_network=True)
    assert len(calls) == 1 and report["truncated"]


@pytest.mark.parametrize("mutation", ["wrong_series", "duplicate", "oversize"])
def test_public_screen_rejects_ambiguous_response(tmp_path, monkeypatch, mutation):
    rows = [market()]
    if mutation == "wrong_series":
        rows = [market("OTHER")]
    if mutation == "duplicate":
        rows *= 2
    if mutation == "oversize":
        rows *= 201
    monkeypatch.setattr("local_market_agent.public_screen.safe_get_json", lambda _: {"markets": rows})
    monkeypatch.setattr("local_market_agent.public_screen.utc_now", lambda: NOW)
    with pytest.raises(ValueError):
        screen_public_markets(tmp_path / "scan", allow_network=True)


def test_legacy_aggregate_liquidity_cannot_pass_depth_discovery(tmp_path, monkeypatch):
    row = market()
    del row["yes_bid_size_fp"]
    del row["yes_ask_size_fp"]
    row["liquidity_dollars"] = "10000"
    monkeypatch.setattr("local_market_agent.public_screen.safe_get_json", lambda _: {"markets": [row]})
    monkeypatch.setattr("local_market_agent.public_screen.utc_now", lambda: NOW)
    report = screen_public_markets(tmp_path / "scan", allow_network=True)
    assert report["eligible_count"] == 0
    assert "legacy aggregate" in " ".join(report["markets"][0]["blockers"])
