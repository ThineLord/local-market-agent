from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path("scripts/local_only/collect_kalshi_normalized_calibration.py")


def load_collector_module():
    script_dir = str(SCRIPT_PATH.parent.resolve())
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location(
        "collect_kalshi_normalized_calibration",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalized_category_quota_selection(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[
            market(
                "KXWTAMATCH-1",
                "Will Donna Vekic win the professional tennis match?",
                source_category="public_event",
            ),
            market(
                "KXATPMATCH-1",
                "Will an ATP player win the professional tennis match?",
                source_category="public_event",
            ),
            market(
                "KXMLB-1",
                "Will the Yankees beat the Red Sox in the MLB baseball game?",
                source_category="public_event",
            ),
            market(
                "KXPERSONMENTION-1-WEAT",
                "What will any NASA Participant say during Daily news conference?",
                source_category="weather",
                rules_primary=(
                    "If any NASA Participant says Weather as part of Daily news "
                    "conference, then the market resolves to Yes."
                ),
            ),
            market(
                "KXRAIN-1",
                "Will New York City receive rain tomorrow?",
                source_category="weather",
            ),
        ]
    )

    result = collector.collect_normalized_calibration(
        client=client,
        export_id="normalized_quota",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        target_markets=5,
        rows_per_market=2,
        quotas={
            "sports_tennis": 2,
            "sports_major": 1,
            "mention_market": 1,
            "weather": 1,
        },
        max_candle_market_attempts=10,
        period_interval=60,
        dry_run=True,
    )

    assert result.category_counts == {
        "mention_market": 1,
        "sports_major": 1,
        "sports_tennis": 2,
        "weather": 1,
    }
    assert result.selected_count == 5
    assert result.availability_limitations == ()


def test_raw_public_event_sports_count_to_sports_not_public_event_generic(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[
            market(
                "KXWTAMATCH-1",
                "Will Donna Vekic win the professional tennis match?",
                source_category="public_event",
            ),
            market(
                "KXMLB-1",
                "Will the Yankees beat the Red Sox in the MLB baseball game?",
                source_category="public_event",
            ),
        ]
    )

    result = collector.collect_normalized_calibration(
        client=client,
        export_id="normalized_public_event_override",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        target_markets=3,
        rows_per_market=2,
        quotas={"sports_tennis": 1, "sports_major": 1, "public_event_generic": 1},
        max_candle_market_attempts=10,
        period_interval=60,
        dry_run=True,
    )

    assert result.category_counts == {"sports_major": 1, "sports_tennis": 1}
    assert "public_event_generic" not in result.category_counts
    assert result.diagnostics["selected_category_counts"] == {
        "sports_major": 1,
        "sports_tennis": 1,
    }
    assert result.diagnostics["quota_shortfalls"] == {"public_event_generic": 1}


def test_quota_shortfalls_emitted(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[
            market(
                "KXWTAMATCH-1",
                "Will Donna Vekic win the professional tennis match?",
                source_category="public_event",
            )
        ]
    )

    result = collector.collect_normalized_calibration(
        client=client,
        export_id="normalized_shortfall",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        target_markets=3,
        rows_per_market=2,
        quotas={"sports_tennis": 1, "weather": 2},
        max_candle_market_attempts=10,
        period_interval=60,
        dry_run=True,
    )

    assert result.category_counts == {"sports_tennis": 1}
    assert result.availability_limitations[0]["category"] == "weather"
    assert result.availability_limitations[0]["missing_count"] == 2
    assert result.availability_limitations[0]["classification"] == (
        "available_source_limitation"
    )
    assert result.availability_limitations[0]["not_a_true_category_effect"] is True


def test_collector_diagnostics_aggregate_counts_failures_and_shortfalls(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[
            market(
                "KXWTAMATCH-1",
                "Will Donna Vekic win the professional tennis match?",
                source_category="public_event",
            ),
            market(
                "KXRAIN-1",
                "Will New York City receive rain tomorrow?",
                source_category="weather",
            ),
            market(
                "KXOPEN-1",
                "Will an unresolved event happen?",
                source_category="public_event",
                status="open",
            ),
            market(
                "KXNONBINARY-1",
                "Non-binary collection",
                source_category="public_event",
                market_type="multi",
            ),
        ],
        empty_candle_tickers={"KXRAIN-1"},
    )

    result = collector.collect_normalized_calibration(
        client=client,
        export_id="normalized_diagnostics",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        target_markets=3,
        rows_per_market=2,
        quotas={"sports_tennis": 1, "weather": 1, "public_event_generic": 1},
        max_candle_market_attempts=10,
        period_interval=60,
        dry_run=True,
    )

    diagnostics = result.diagnostics
    assert diagnostics["discovered_count"] == 4
    assert diagnostics["pre_filter_category_counts"]["sports_tennis"] == 1
    assert diagnostics["post_filter_category_counts"]["sports_tennis"] == 1
    assert diagnostics["selected_category_counts"] == {"sports_tennis": 1}
    assert diagnostics["filter_losses"]["not_finalized_loss"] == 1
    assert diagnostics["filter_losses"]["non_binary_loss"] == 1
    assert diagnostics["candle_attempt_count"] == 2
    assert diagnostics["candle_success_count"] == 1
    assert diagnostics["candle_failure_count"] == 1
    assert diagnostics["candle_failure_reasons"]["no_candles_returned"] == 1
    assert diagnostics["quota_shortfalls"] == {
        "public_event_generic": 1,
        "weather": 1,
    }


def test_output_rows_are_calibration_only_shape(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[
            market(
                "KXWTAMATCH-1",
                "Will Donna Vekic win the professional tennis match?",
                source_category="public_event",
            )
        ],
        include_bid_ask=False,
    )

    result = collector.collect_normalized_calibration(
        client=client,
        export_id="normalized_shape",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        target_markets=1,
        rows_per_market=2,
        quotas={"sports_tennis": 1},
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
    assert result.diagnostics_json is not None
    assert result.diagnostics_markdown is not None
    assert result.diagnostics_json.exists()
    assert result.diagnostics_markdown.exists()


def test_dry_run_does_not_write_export_or_historical_outputs(tmp_path: Path):
    collector = load_collector_module()
    client = FakeKalshiClient(
        markets=[
            market(
                "KXMLB-1",
                "Will the Yankees beat the Red Sox in the MLB baseball game?",
                source_category="public_event",
            )
        ]
    )

    result = collector.collect_normalized_calibration(
        client=client,
        export_id="normalized_dry",
        output_root=tmp_path / "exports",
        historical_output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        target_markets=1,
        rows_per_market=2,
        quotas={"sports_major": 1},
        max_candle_market_attempts=5,
        period_interval=60,
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.selected_count == 1
    assert result.historical_jsonl is None
    assert result.diagnostics_json is None
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
    def __init__(
        self,
        *,
        markets: list[dict[str, object]],
        include_bid_ask: bool = True,
        empty_candle_tickers: set[str] | None = None,
    ) -> None:
        self.markets = markets
        self.include_bid_ask = include_bid_ask
        self.empty_candle_tickers = empty_candle_tickers or set()
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
                        "candlesticks": self._candles_for(ticker),
                    }
                ]
            }
        if path.startswith("/historical/markets/"):
            ticker = path.split("/")[-2]
            return {"candlesticks": self._candles_for(ticker)}
        raise AssertionError(f"unexpected fake request: {path}")

    def _candles_for(self, ticker: str) -> list[dict[str, object]]:
        if ticker in self.empty_candle_tickers:
            return []
        return candles(include_bid_ask=self.include_bid_ask)


def market(
    ticker: str,
    title: str,
    *,
    source_category: str,
    status: str = "finalized",
    market_type: str = "binary",
    rules_primary: str | None = None,
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "event_ticker": ticker.rsplit("-", maxsplit=1)[0],
        "series_ticker": ticker.split("-", maxsplit=1)[0],
        "title": title,
        "status": status,
        "result": "yes",
        "market_type": market_type,
        "open_time": "2026-05-01T00:00:00Z",
        "close_time": "2026-06-01T12:00:00Z",
        "expected_expiration_time": "2026-06-01T12:00:00Z",
        "latest_expiration_time": "2026-06-01T12:00:00Z",
        "settlement_ts": "2026-06-01T12:00:00Z",
        "rules_primary": rules_primary or title,
        "rules_secondary": "Unit-test public local fixture.",
        "volume_fp": "1000.0",
        "settlement_value_dollars": "1.0000",
        "liquidity_dollars": "100.0",
        "metadata": {"calibration_category": source_category},
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
