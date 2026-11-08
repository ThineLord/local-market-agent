import json
from datetime import UTC, datetime

import pytest

from local_market_agent.evidence_packet import load_packet
from local_market_agent.public_weather import collect_weather_packet

NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)
TICKER = "KXHIGHNY-26NOV09-T57"


def install_public_responses(monkeypatch, *, wrong_market=False):
    calls = []
    market = {"ticker": "WRONG" if wrong_market else TICKER, "event_ticker": "KXHIGHNY-26NOV09",
              "title": "Synthetic test only", "market_type": "binary", "status": "active",
              "yes_bid_dollars": "0.12", "yes_ask_dollars": "0.13",
              "yes_bid_size_fp": "30.00", "yes_ask_size_fp": "10.00",
              "close_time": "2026-11-10T06:00:00Z", "rules_primary": "Synthetic rule"}
    def get(url):
        calls.append(url)
        if "/series/" in url:
            return {"series": {"ticker": "KXHIGHNY", "settlement_sources": [{"url": "https://example.test/final"}]}}
        if "/forecast" in url:
            return {"properties": {"generatedAt": "2026-11-08T11:00:00Z", "periods": [
                {"name": "Tomorrow", "startTime": "2026-11-09T06:00:00-05:00", "endTime": "2026-11-09T18:00:00-05:00", "temperature": 59, "temperatureUnit": "F"}]}}
        if "/observations/" in url:
            return {"properties": {"timestamp": "2026-11-08T10:00:00Z", "temperature": {"value": 15, "unitCode": "wmoUnit:degC"}}}
        if "event_ticker=" in url:
            return {"markets": [market]}
        if url.endswith("/orderbook"):
            return {"orderbook_fp": {"yes_dollars": [["0.12", "30.00"]], "no_dollars": [["0.87", "10.00"]]}}
        return {"market": market}
    monkeypatch.setattr("local_market_agent.public_weather.safe_get_json", get)
    monkeypatch.setattr("local_market_agent.public_weather.utc_now", lambda: NOW)
    return calls


def test_collector_is_bounded_hashed_and_observe_only(tmp_path, monkeypatch):
    calls = install_public_responses(monkeypatch)
    path = collect_weather_packet(tmp_path / "packet", TICKER, allow_network=True)
    packet = load_packet(path)
    report = json.loads((path.parent / "collection.json").read_text())
    assert len(calls) == 6 and all(url.startswith("https://") for url in calls)
    assert packet.snapshot.liquidity == 1.3 and len(packet.sources) == 6
    assert packet.brief.estimated_probability is None
    assert packet.brief.recommended_action == "observe" and packet.brief.must_not_trade_reasons
    assert packet.brief.evidence == packet.evidence
    assert not report["review_created"] and not report["order_created"]
    assert report["before_brief"]["brief_present"] is False
    assert report["after_brief"]["brief_present"] is True
    assert not report["after_brief"]["research_ready"]
    assert report["liquidity"]["no_buy_capacity_usd"] == 26.4
    assert not list(path.parent.glob("*.sqlite"))
    with pytest.raises(FileExistsError):
        collect_weather_packet(path.parent, TICKER, allow_network=True)
    assert len(calls) == 6


def test_collector_network_and_market_scope_fail_before_io(tmp_path, monkeypatch):
    calls = install_public_responses(monkeypatch)
    with pytest.raises(ValueError, match="allow-network"):
        collect_weather_packet(tmp_path / "packet", TICKER)
    with pytest.raises(ValueError, match="Only KXHIGHNY"):
        collect_weather_packet(tmp_path / "packet", "OTHER", allow_network=True)
    assert not calls and not (tmp_path / "packet").exists()


def test_collector_rejects_wrong_market_without_packet(tmp_path, monkeypatch):
    install_public_responses(monkeypatch, wrong_market=True)
    with pytest.raises(ValueError, match="identity"):
        collect_weather_packet(tmp_path / "packet", TICKER, allow_network=True)
    assert not (tmp_path / "packet/packet.json").exists()
