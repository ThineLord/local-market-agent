from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path("scripts/local_only/prepare_kalshi_evidence_worksheet.py")


def load_worksheet_module():
    spec = importlib.util.spec_from_file_location(
        "prepare_kalshi_evidence_worksheet",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_prepare_worksheet_from_synthetic_local_export(tmp_path: Path):
    worksheet = load_worksheet_module()
    export_dir = write_synthetic_export(tmp_path)

    result = worksheet.prepare_worksheet(export_dir, evidence_needed_count=2)

    assert result.market_count == 2
    assert result.template_row_count == 4
    assert result.csv_path == export_dir / "evidence_worksheet.csv"
    assert result.markdown_path == export_dir / "evidence_worksheet.md"
    assert result.template_path == export_dir / "evidence_template.jsonl"
    assert result.csv_path.exists()
    assert result.markdown_path.exists()
    assert result.template_path.exists()

    with result.csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[0]["market_ticker"] == "KXBTCDEMO-26JUN05-UP"
    assert rows[0]["earliest_candle_ts"] == "2026-06-05T12:00:00Z"
    assert rows[0]["latest_candle_ts"] == "2026-06-05T12:01:00Z"
    assert rows[0]["number_of_candles"] == "2"
    assert rows[0]["required_evidence_before_ts"] == "2026-06-05T12:00:00Z"
    assert "official source" in rows[0]["suggested_evidence_query_1"]
    assert rows[0]["suggested_primary_source_type"] == "market/reference price source"


def test_evidence_template_shape_and_placeholder_metadata(tmp_path: Path):
    worksheet = load_worksheet_module()
    export_dir = write_synthetic_export(tmp_path)

    result = worksheet.prepare_worksheet(export_dir, evidence_needed_count=1)
    template_rows = read_jsonl(result.template_path)

    assert len(template_rows) == 2
    assert set(template_rows[0]) == {
        "market_ticker",
        "evidence_id",
        "source",
        "title",
        "url",
        "published_at",
        "retrieved_at",
        "summary",
        "relevance_score",
        "credibility_score",
        "metadata",
    }
    assert template_rows[0]["published_at"].startswith("TODO_")
    assert template_rows[0]["retrieved_at"].startswith("TODO_")
    assert template_rows[0]["metadata"]["placeholder"] is True
    assert template_rows[0]["metadata"]["replace_before_import"] is True
    assert (
        template_rows[0]["metadata"]["required_published_at_lte"]
        == "2026-06-05T12:00:00Z"
    )


def test_required_timestamp_fields_are_in_csv_and_markdown(tmp_path: Path):
    worksheet = load_worksheet_module()
    export_dir = write_synthetic_export(tmp_path)

    result = worksheet.prepare_worksheet(export_dir, evidence_needed_count=1)
    csv_text = result.csv_path.read_text(encoding="utf-8")
    markdown_text = result.markdown_path.read_text(encoding="utf-8")

    for field in (
        "settlement_ts",
        "earliest_candle_ts",
        "latest_candle_ts",
        "required_evidence_before_ts",
    ):
        assert field in csv_text
    assert "Required evidence before" in markdown_text
    assert "2026-06-05T12:00:00Z" in markdown_text


def test_worksheet_script_has_no_network_or_browser_access():
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()

    forbidden_terms = (
        "urllib",
        "requests",
        "http.client",
        "socket",
        "webbrowser",
        "selenium",
        "playwright",
        "portfolio",
        "orders",
        "fills",
        "account",
        "api key",
        "cookie",
    )
    assert all(term not in source for term in forbidden_terms)


def write_synthetic_export(tmp_path: Path) -> Path:
    export_dir = tmp_path / "kalshi_sprint1_unit"
    export_dir.mkdir()
    (export_dir / "source_manifest.json").write_text(
        json.dumps(
            {
                "export_id": "kalshi_sprint1_unit",
                "dataset_id": "phase7g_kalshi_sprint1_unit",
                "terms_review": "pending_review",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_jsonl(
        export_dir / "markets.jsonl",
        [
            {
                "ticker": "KXBTCDEMO-26JUN05-UP",
                "title": "BTC price up in next 15 mins?",
                "subtitle": "Bitcoin price reference",
                "rules_primary": "YES if the BTC reference price is higher.",
                "rules_secondary": "Use the published reference price.",
                "result": "yes",
                "settlement_ts": "2026-06-05T12:20:00Z",
            },
            {
                "ticker": "KXDEMO-26JUN05-MATCH",
                "title": "Will Demo Player win the match?",
                "subtitle": "Synthetic match",
                "rules_primary": "YES if Demo Player wins the tennis match.",
                "rules_secondary": "Use the official match result.",
                "result": "no",
                "settlement_ts": "2026-06-05T13:00:00Z",
            },
        ],
    )
    write_jsonl(
        export_dir / "candlesticks.jsonl",
        [
            candle("KXBTCDEMO-26JUN05-UP", "2026-06-05T12:00:00Z"),
            candle("KXBTCDEMO-26JUN05-UP", "2026-06-05T12:01:00Z"),
            candle("KXDEMO-26JUN05-MATCH", "2026-06-05T12:10:00Z"),
        ],
    )
    return export_dir


def candle(ticker: str, timestamp: str) -> dict[str, object]:
    return {
        "market_ticker": ticker,
        "end_period_ts": timestamp,
        "yes_bid": {"close_dollars": "0.40"},
        "yes_ask": {"close_dollars": "0.42"},
        "price": {"close_dollars": "0.41"},
    }


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
