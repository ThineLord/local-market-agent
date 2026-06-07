from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path("scripts/local_only/collect_kalshi_calibration_dataset.py")


def load_collector_module():
    script_dir = str(SCRIPT_PATH.parent.resolve())
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location(
        "collect_kalshi_calibration_dataset",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_calibration_market_selection_keeps_broad_resolved_markets(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(markets=[market("KXCPI-1"), market("KXNBA-2"), market("KXEVENT-3")])

    result = collector.collect_calibration_dataset(
        client=client,
        export_id="kalshi_calibration_unit",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        min_markets=1,
        max_markets=3,
        rows_per_market=2,
        max_candle_market_attempts=5,
        period_interval=60,
        dry_run=False,
    )

    assert result.selected_count == 3
    assert result.candle_count == 6
    assert set(result.category_counts) >= {"economic_indicator", "major_sports", "public_event"}


def test_malformed_and_no_settlement_markets_are_excluded(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[
            market("KXGOOD-1"),
            {**market("KXBROKEN-2"), "result": None, "settlement_value_dollars": None},
            {
                **market("KXUNSETTLED-3"),
                "settlement_ts": None,
                "close_time": None,
                "expected_expiration_time": None,
                "latest_expiration_time": None,
            },
            {**market("KXNONBINARY-4"), "market_type": "range"},
        ]
    )

    result = collector.collect_calibration_dataset(
        client=client,
        export_id="kalshi_calibration_filtered",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        min_markets=1,
        max_markets=4,
        rows_per_market=2,
        max_candle_market_attempts=5,
        period_interval=60,
        dry_run=False,
    )

    markets = read_jsonl(result.export_dir / "markets.jsonl")
    assert result.selected_count == 1
    assert [row["ticker"] for row in markets] == ["KXGOOD-1"]


def test_output_rows_are_calibration_only_and_bid_ask_not_invented(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(markets=[market("KXPRICEONLY-1")], include_bid_ask=False)

    result = collector.collect_calibration_dataset(
        client=client,
        export_id="kalshi_calibration_price_only",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        min_markets=1,
        max_markets=1,
        rows_per_market=2,
        max_candle_market_attempts=2,
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
    assert all(row["last_price"] is not None for row in rows)


def test_evidence_remains_empty_and_terms_are_not_auto_reviewed(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(markets=[market("KXEVIDENCE-1")])

    result = collector.collect_calibration_dataset(
        client=client,
        export_id="kalshi_calibration_no_evidence",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        min_markets=1,
        max_markets=1,
        rows_per_market=2,
        max_candle_market_attempts=2,
        period_interval=60,
        dry_run=False,
    )

    assert read_jsonl(result.export_dir / "evidence.jsonl") == []
    manifest = json.loads((result.export_dir / "source_manifest.json").read_text(encoding="utf-8"))
    assert manifest["terms_review"] == "pending_review"
    assert manifest["terms_reviewed_by"] == "pending_review"
    assert manifest["safety"]["evidence_approval_performed"] is False
    assert manifest["safety"]["terms_review_mutated"] is False


def test_no_automatic_acceptance_or_superiority_claims(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(markets=[market("KXCLAIM-1")])

    result = collector.collect_calibration_dataset(
        client=client,
        export_id="kalshi_calibration_claims",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        min_markets=1,
        max_markets=1,
        rows_per_market=2,
        max_candle_market_attempts=2,
        period_interval=60,
        dry_run=False,
    )

    assert result.claim_guardrails["acceptance_gate_pass"] is False
    assert result.claim_guardrails["strategy_v2_superiority"] is False
    assert result.claim_guardrails["profitability_claim"] is False
    assert result.audit_classification == "calibration_unusable"


def test_dry_run_does_not_write_export_or_historical_outputs(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(markets=[market("KXDRY-1")])

    result = collector.collect_calibration_dataset(
        client=client,
        export_id="kalshi_calibration_dry",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        min_markets=1,
        max_markets=1,
        rows_per_market=2,
        max_candle_market_attempts=2,
        period_interval=60,
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.selected_count == 1
    assert result.historical_jsonl is None
    assert not result.export_dir.exists()
    assert not (tmp_path / "historical").exists()


def test_no_broker_live_order_account_api_added():
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


def market(ticker: str) -> dict[str, object]:
    title = "Will CPI inflation be above 3.0%?"
    if "NBA" in ticker:
        title = "Will the NBA Finals game go over 210 points?"
    elif "EVENT" in ticker:
        title = "Will the public demo event happen?"
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
