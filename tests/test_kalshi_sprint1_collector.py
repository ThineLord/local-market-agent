from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path("scripts/local_only/collect_kalshi_sprint1.py")


def load_collector_module():
    spec = importlib.util.spec_from_file_location("collect_kalshi_sprint1", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalize_candidate_derives_series_ticker_for_finalized_binary_market():
    collector = load_collector_module()
    candidate = collector.normalize_candidate(
        "live_settled_markets",
        {
            "ticker": "KXDEMO-26JUN05-YES",
            "event_ticker": "KXDEMO-26JUN05",
            "market_type": "binary",
            "title": "Will the demo event happen?",
            "status": "finalized",
            "result": "yes",
            "settlement_ts": "2026-06-05T12:30:00Z",
            "volume_fp": "1200.00",
        },
    )

    assert candidate is not None
    assert candidate.ticker == "KXDEMO-26JUN05-YES"
    assert candidate.series_ticker == "KXDEMO"
    assert candidate.result == "yes"
    assert candidate.volume == 1200.0


def test_collect_export_writes_pr_data_3_files_without_network(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient()

    result = collector.collect_export(
        client=client,
        export_id="kalshi_sprint1_unit",
        output_root=tmp_path / "kalshi",
        max_markets=1,
        rows_per_market=2,
        period_interval=1,
        terms_review="pending_review",
        dry_run=False,
    )

    export_dir = tmp_path / "kalshi" / "kalshi_sprint1_unit"
    manifest = json.loads((export_dir / "source_manifest.json").read_text(encoding="utf-8"))
    markets = read_jsonl(export_dir / "markets.jsonl")
    candles = read_jsonl(export_dir / "candlesticks.jsonl")
    evidence = read_jsonl(export_dir / "evidence.jsonl")

    assert result.selected_count == 1
    assert result.candle_count == 2
    assert manifest["terms_review"] == "pending_review"
    assert manifest["private_or_authenticated_source"] is False
    assert manifest["network_used_by_adapter"] is False
    assert "evidence.jsonl" in manifest["raw_file_sha256"]
    assert "evidence curation remains required" in manifest["notes"]
    assert markets[0]["ticker"] == "KXDEMO-26JUN05-YES"
    assert candles[0]["market_ticker"] == "KXDEMO-26JUN05-YES"
    assert candles[0]["yes_bid"]["close_dollars"] == "0.4100"
    assert candles[0]["yes_ask"]["close_dollars"] == "0.4300"
    assert candles[0]["price"]["close_dollars"] == "0.4200"
    assert evidence == []
    assert any(path == "/markets" for path, _ in client.requests)
    assert any(path == "/markets/candlesticks" for path, _ in client.requests)


def test_dry_run_does_not_write_export_directory(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient()

    result = collector.collect_export(
        client=client,
        export_id="kalshi_sprint1_dry_run",
        output_root=tmp_path / "kalshi",
        max_markets=1,
        rows_per_market=2,
        period_interval=1,
        terms_review="pending_review",
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.selected_count == 1
    assert not result.export_dir.exists()


def test_collector_source_avoids_private_or_trading_endpoint_paths():
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()

    forbidden_paths = (
        "/portfolio",
        "/account",
        "/orders",
        "/fills",
        "/api-keys",
        "/communications",
        "portfolio/",
        "account/",
        "orders/",
        "fills/",
    )
    assert all(path not in source for path in forbidden_paths)
    assert "api key" not in source
    assert "cookie" not in source


class FakeKalshiClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, object]]] = []

    def get_json(self, path: str, params: dict[str, object]) -> dict[str, Any]:
        self.requests.append((path, params))
        if path == "/markets":
            return {"markets": [fake_market()], "cursor": ""}
        if path == "/historical/markets":
            return {"markets": [], "cursor": ""}
        if path == "/markets/candlesticks":
            return {
                "markets": [
                    {
                        "market_ticker": "KXDEMO-26JUN05-YES",
                        "candlesticks": fake_candles(),
                    }
                ]
            }
        raise AssertionError(f"unexpected fake request: {path}")


def fake_market() -> dict[str, object]:
    return {
        "ticker": "KXDEMO-26JUN05-YES",
        "event_ticker": "KXDEMO-26JUN05",
        "market_type": "binary",
        "title": "Will the demo event happen?",
        "status": "finalized",
        "result": "yes",
        "open_time": "2026-06-05T12:00:00Z",
        "close_time": "2026-06-05T12:30:00Z",
        "settlement_ts": "2026-06-05T12:31:00Z",
        "settlement_value_dollars": "1.0000",
        "rules_primary": "YES if the demo event happens.",
        "rules_secondary": "Synthetic unit-test response.",
        "volume_fp": "1200.00",
        "liquidity_dollars": "100.00",
    }


def fake_candles() -> list[dict[str, object]]:
    return [
        candle(1780661100, "0.4100", "0.4300", "0.4200"),
        candle(1780661160, "0.4400", "0.4600", "0.4500"),
        candle(1780661220, "0.4700", "0.4900", "0.4800"),
    ]


def candle(timestamp: int, bid: str, ask: str, price: str) -> dict[str, object]:
    return {
        "end_period_ts": timestamp,
        "yes_bid": {"close_dollars": bid},
        "yes_ask": {"close_dollars": ask},
        "price": {"close_dollars": price},
        "volume_fp": "10.00",
        "open_interest_fp": "20.00",
    }


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
