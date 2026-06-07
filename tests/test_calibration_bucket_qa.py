from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from typer.testing import CliRunner

import local_market_agent.eval.calibration_bucket_qa as bucket_qa_module
from local_market_agent.cli import app
from local_market_agent.eval.calibration_bucket_qa import (
    WARNING_BID_ASK_MISSING,
    WARNING_CATEGORY_MISSING,
    WARNING_EVIDENCE_MISSING,
    WARNING_MARKET_CONCENTRATION,
    WARNING_SMALL_SAMPLE,
    run_calibration_bucket_qa,
    write_calibration_bucket_qa_reports,
)


def test_bucket_qa_detects_high_gap_bucket(tmp_path: Path):
    dataset_path = _write_high_gap_dataset(tmp_path)

    result = run_calibration_bucket_qa(dataset_path, gap_threshold=0.15)

    high_gap_buckets = result.high_gap_buckets
    assert [bucket["bucket"] for bucket in high_gap_buckets] == ["0.20-0.30"]
    bucket = high_gap_buckets[0]
    assert bucket["rows"] == 10
    assert bucket["absolute_gap"] == 0.75
    assert bucket["brier"] == 0.5625
    assert bucket["outcome_split"] == {"yes": 10}


def test_bucket_qa_reports_market_concentration_and_small_sample(tmp_path: Path):
    dataset_path = _write_high_gap_dataset(tmp_path)

    bucket = run_calibration_bucket_qa(dataset_path, gap_threshold=0.15).high_gap_buckets[0]

    assert WARNING_MARKET_CONCENTRATION in bucket["warnings"]
    assert WARNING_SMALL_SAMPLE in bucket["warnings"]
    assert bucket["dominance"]["dominated_by_few_markets"] is True
    assert bucket["dominance"]["top_market_id"] == "market-a"


def test_bucket_qa_reports_missing_category_bid_ask_and_evidence(tmp_path: Path):
    dataset_path = _write_high_gap_dataset(tmp_path)

    bucket = run_calibration_bucket_qa(dataset_path, gap_threshold=0.15).high_gap_buckets[0]

    assert WARNING_CATEGORY_MISSING in bucket["warnings"]
    assert WARNING_BID_ASK_MISSING in bucket["warnings"]
    assert WARNING_EVIDENCE_MISSING in bucket["warnings"]
    assert bucket["row_category_missing_count"] == 10
    assert bucket["bid_ask_missing_count"] == 10
    assert bucket["evidence_missing_count"] == 10


def test_bucket_qa_report_writer_outputs_json_and_markdown(tmp_path: Path):
    dataset_path = _write_high_gap_dataset(tmp_path)
    result = run_calibration_bucket_qa(dataset_path, gap_threshold=0.15)

    artifacts = write_calibration_bucket_qa_reports(result, tmp_path / "reports")

    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert payload["high_gap_buckets"][0]["bucket"] == "0.20-0.30"
    markdown = artifacts.markdown_path.read_text(encoding="utf-8")
    assert "Calibration Bucket QA Report" in markdown
    assert "Strategy v2 superiority | False" in markdown


def test_calibration_bucket_qa_cli_writes_json_and_markdown(tmp_path: Path):
    dataset_path = _write_high_gap_dataset(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "calibration-bucket-qa",
            "--historical-file",
            str(dataset_path),
            "--output-dir",
            str(tmp_path / "reports"),
            "--gap-threshold",
            "0.15",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["high_gap_buckets"][0]["bucket"] == "0.20-0.30"
    assert payload["guardrails"]["acceptance_gate_pass"] is False
    assert Path(payload["json_path"]).exists()
    assert Path(payload["markdown_path"]).exists()


def test_calibration_bucket_qa_adds_no_broker_live_or_order_api():
    source = inspect.getsource(bucket_qa_module)
    tree = ast.parse(source)
    referenced_symbols = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    forbidden_symbols = {
        "PaperLedger",
        "PaperOrder",
        "PaperOrderIntent",
        "RiskEngine",
        "RiskGateEvaluator",
        "ExecutionMode.LIVE",
        "create_order",
        "open_position",
    }
    assert forbidden_symbols.isdisjoint(referenced_symbols)
    assert "local_market_agent.paper" not in source
    assert "local_market_agent.risk" not in source


def _write_high_gap_dataset(tmp_path: Path) -> Path:
    rows = []
    for index in range(10):
        market_id = "market-a" if index < 8 else "market-b"
        rows.append(
            {
                "dataset_id": "bucket_qa_fixture",
                "row_id": f"row-{index}",
                "timestamp": f"2026-05-01T{index:02d}:00:00Z",
                "market_id": market_id,
                "platform": "kalshi",
                "profile": "calibration_only_last_price",
                "bid": None,
                "ask": None,
                "last_price": 0.25,
                "implied_probability": 0.25,
                "paper_pnl_allowed": False,
                "acceptance_candidate": False,
                "evidence": [],
                "settlement": {
                    "outcome": "yes",
                    "ambiguous": False,
                },
                "source_provenance": {
                    "source_name": "unit-test-source",
                },
                "metadata": {
                    "export_id": "missing-test-export",
                },
                "volume": 100 + index,
            }
        )
    path = tmp_path / "high_gap.jsonl"
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path
