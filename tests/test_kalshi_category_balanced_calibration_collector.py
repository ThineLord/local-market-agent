from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path("scripts/local_only/collect_kalshi_category_balanced_calibration.py")


def load_collector_module():
    script_dir = str(SCRIPT_PATH.parent.resolve())
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location(
        "collect_kalshi_category_balanced_calibration",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_quota_enforcement(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[
            market("KXPUBLIC-1", "Will the public demo event happen?"),
            market("KXPUBLIC-2", "Will the public demo event happen again?"),
            market("KXPUBLIC-3", "Will the public demo event happen a third time?"),
            market("KXNBA-1", "Will the NBA Finals game go over 210 points?"),
            market("KXNBA-2", "Will an NBA playoff game go over 220 points?"),
            market("KXNBA-3", "Will an NBA game go under 199 points?"),
            market("KXWEATHER-1", "Will the temperature be above 80 degrees?"),
            market("KXWEATHER-2", "Will rain occur in New York?"),
            market("KXFED-1", "Will the Fed announce an interest rate cut?"),
        ]
    )

    result = collector.collect_category_balanced_calibration(
        client=client,
        export_id="category_balanced_quota",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        target_markets=8,
        rows_per_market=2,
        quotas={"public_event": 2, "major_sports": 2, "weather": 2, "fed_policy": 2},
        public_event_cap=2,
        max_candle_market_attempts=20,
        period_interval=60,
        dry_run=True,
    )

    assert result.category_counts == {
        "fed_policy": 1,
        "major_sports": 2,
        "public_event": 2,
        "weather": 2,
    }
    assert result.selected_count == 7
    assert result.availability_limitations == (
        {
            "category": "fed_policy",
            "selected_markets": 1,
            "quota_markets": 2,
            "missing_markets": 1,
            "classification": "available_source_limitation",
            "not_a_true_category_effect": True,
            "public_event_backfilled": False,
        },
    )


def test_public_event_cap_enforced(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[
            market(f"KXPUBLIC-{index}", f"Will public event {index} happen?")
            for index in range(1, 6)
        ]
    )

    result = collector.collect_category_balanced_calibration(
        client=client,
        export_id="category_balanced_public_cap",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        target_markets=4,
        rows_per_market=2,
        quotas={"public_event": 2},
        public_event_cap=2,
        max_candle_market_attempts=10,
        period_interval=60,
        dry_run=True,
    )

    assert result.category_counts == {"public_event": 2}
    assert result.selected_count == 2


def test_unavailable_non_public_categories_emit_limitation(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[
            market("KXPUBLIC-1", "Will a public demo event happen?"),
            market("KXPUBLIC-2", "Will another public demo event happen?"),
        ]
    )

    result = collector.collect_category_balanced_calibration(
        client=client,
        export_id="category_balanced_missing_non_public",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        target_markets=4,
        rows_per_market=2,
        quotas={"public_event": 2, "weather": 2},
        public_event_cap=2,
        max_candle_market_attempts=10,
        period_interval=60,
        dry_run=True,
    )

    assert result.category_counts == {"public_event": 2}
    assert result.availability_limitations[0]["category"] == "weather"
    assert result.availability_limitations[0]["classification"] == "available_source_limitation"
    assert result.availability_limitations[0]["not_a_true_category_effect"] is True


def test_no_public_event_backfill_beyond_cap(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[
            market(f"KXPUBLIC-{index}", f"Will public event {index} happen?")
            for index in range(1, 8)
        ]
    )

    result = collector.collect_category_balanced_calibration(
        client=client,
        export_id="category_balanced_no_backfill",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        target_markets=4,
        rows_per_market=2,
        quotas={"public_event": 2, "weather": 2},
        public_event_cap=2,
        max_candle_market_attempts=20,
        period_interval=60,
        dry_run=True,
    )

    assert result.category_counts == {"public_event": 2}
    assert result.selected_count == 2
    assert all(item["public_event_backfilled"] is False for item in result.availability_limitations)


def test_output_rows_are_calibration_only_shape(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[market("KXWEATHER-1", "Will the temperature be above 80 degrees?")],
        include_bid_ask=False,
    )

    result = collector.collect_category_balanced_calibration(
        client=client,
        export_id="category_balanced_shape",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        target_markets=1,
        rows_per_market=2,
        quotas={"weather": 1},
        public_event_cap=1,
        max_candle_market_attempts=5,
        period_interval=60,
        dry_run=False,
    )

    assert result.historical_jsonl is not None
    rows = read_jsonl(result.historical_jsonl)
    assert rows
    assert {row["profile"] for row in rows} == {"calibration_only_last_price"}
    assert {row["paper_pnl_allowed"] for row in rows} == {False}
    assert {row["acceptance_candidate"] for row in rows} == {False}
    assert all(row["bid"] is None for row in rows)
    assert all(row["ask"] is None for row in rows)
    assert all(row["evidence"] == [] for row in rows)
    assert all(row["last_price"] is not None for row in rows)


def test_dry_run_does_not_write_export_or_historical_outputs(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[market("KXNBA-1", "Will the NBA Finals game go over 210 points?")]
    )

    result = collector.collect_category_balanced_calibration(
        client=client,
        export_id="category_balanced_dry",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        target_markets=1,
        rows_per_market=2,
        quotas={"major_sports": 1},
        public_event_cap=1,
        max_candle_market_attempts=5,
        period_interval=60,
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.selected_count == 1
    assert result.historical_jsonl is None
    assert not result.export_dir.exists()
    assert not (tmp_path / "historical").exists()


def test_no_broker_live_order_api_added():
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    forbidden_terms = (
        "place_order",
        "submit_order",
        "live_order",
        "/portfolio",
        "/account",
        "/orders",
        "/fills",
        "broker_client",
    )
    for term in forbidden_terms:
        assert term not in source


class FakeKalshiClient:
    def __init__(self, *, markets: list[dict[str, object]], include_bid_ask: bool = True) -> None:
        self.markets = markets
        self.include_bid_ask = include_bid_ask
        self.requested_urls: list[str] = []
        self.requests: list[tuple[str, dict[str, object]]] = []

    def get_json(self, path: str, params: dict[str, object]) -> dict[str, Any]:
        self.requests.append((path, params))
        if path == "/markets":
            return {"markets": self.markets, "cursor": ""}
        if path == "/historical/markets":
            return {"markets": [], "cursor": ""}
        if path == "/markets/candlesticks":
            ticker = str(params["market_tickers"])
            return {
                "markets": [
                    {
                        "market_ticker": ticker,
                        "candlesticks": candles(include_bid_ask=self.include_bid_ask),
                    }
                ]
            }
        if path.startswith("/historical/markets/"):
            return {"candlesticks": candles(include_bid_ask=self.include_bid_ask)}
        raise AssertionError(f"unexpected fake request: {path}")


def market(ticker: str, title: str) -> dict[str, object]:
    return {
        "ticker": ticker,
        "event_ticker": ticker.rsplit("-", maxsplit=1)[0],
        "series_ticker": ticker.split("-", maxsplit=1)[0],
        "title": title,
        "status": "finalized",
        "result": "yes",
        "market_type": "binary",
        "open_time": "2026-05-01T00:00:00Z",
        "close_time": "2026-06-01T12:00:00Z",
        "expected_expiration_time": "2026-06-01T12:00:00Z",
        "latest_expiration_time": "2026-06-01T12:00:00Z",
        "settlement_ts": "2026-06-01T12:00:00Z",
        "rules_primary": "Resolved according to public market rules.",
        "rules_secondary": "Unit-test public local fixture.",
        "volume_fp": "1000.0",
        "settlement_value_dollars": "1.0000",
        "liquidity_dollars": "100.0",
    }


def candles(*, include_bid_ask: bool) -> list[dict[str, object]]:
    rows = []
    for index, timestamp in enumerate(
        (
            "2026-05-20T12:00:00Z",
            "2026-05-22T12:00:00Z",
            "2026-05-24T12:00:00Z",
            "2026-05-26T12:00:00Z",
        ),
        start=1,
    ):
        row: dict[str, object] = {
            "end_period_ts": timestamp,
            "price": {"close_dollars": f"0.{40 + index:02d}00"},
            "volume_fp": "10.0",
            "open_interest_fp": "20.0",
        }
        if include_bid_ask:
            row["yes_bid"] = {"close_dollars": "0.4000"}
            row["yes_ask"] = {"close_dollars": "0.5000"}
        rows.append(row)
    return rows


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
