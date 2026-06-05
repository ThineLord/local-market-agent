from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import local_market_agent.data.historical_builder as builder_module
from local_market_agent.cli import app
from local_market_agent.data import build_historical_dataset, validate_historical_dataset

FIXTURE_DIR = Path("data/fixtures/historical_builder")
CSV_ACCEPTANCE = FIXTURE_DIR / "manual_acceptance_sample.csv"
JSONL_ACCEPTANCE = FIXTURE_DIR / "manual_acceptance_sample.jsonl"
CSV_CALIBRATION = FIXTURE_DIR / "manual_calibration_sample.csv"
MALFORMED_CSV = FIXTURE_DIR / "malformed_manual_sample.csv"


def test_csv_acceptance_input_builds_valid_phase7g_jsonl(tmp_path: Path):
    result = build_historical_dataset(
        CSV_ACCEPTANCE,
        input_format="csv",
        profile="acceptance_candidate",
        output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        validate=True,
    )

    rows = _read_jsonl(result.output_jsonl)
    validation = validate_historical_dataset(result.output_jsonl)

    assert result.validation_valid is True
    assert validation.valid is True
    assert validation.acceptance_candidate is True
    assert validation.paper_pnl_allowed is True
    assert result.dataset_id == "phase7g_manual_builder_acceptance_fixture"
    assert result.row_count == 2
    assert result.market_count == 1
    assert {row["schema_version"] for row in rows} == {"phase7g.historical_dataset.v1"}
    assert all(row["profile"] == "acceptance_candidate" for row in rows)
    assert all(row["bid"] is not None and row["ask"] is not None for row in rows)
    assert all("settlement_outcome" not in row for row in rows)


def test_jsonl_acceptance_input_builds_valid_phase7g_jsonl(tmp_path: Path):
    result = build_historical_dataset(
        JSONL_ACCEPTANCE,
        input_format="jsonl",
        profile="acceptance_candidate",
        output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        validate=True,
    )

    rows = _read_jsonl(result.output_jsonl)

    assert result.validation_valid is True
    assert result.dataset_id.startswith(
        "phase7g_polymarket_acceptance_candidate_2026_05_03_1r_"
    )
    assert result.row_count == 1
    assert rows[0]["acceptance_candidate"] is True
    assert rows[0]["paper_pnl_allowed"] is True
    assert rows[0]["evidence"][0]["evidence_id"].startswith("ev_")


def test_calibration_only_input_forces_no_bid_ask_or_paper_pnl(tmp_path: Path):
    result = build_historical_dataset(
        CSV_CALIBRATION,
        input_format="csv",
        profile="calibration_only_last_price",
        output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        validate=True,
    )

    rows = _read_jsonl(result.output_jsonl)

    assert result.validation_valid is True
    assert result.validation_result is not None
    assert result.validation_result.paper_pnl_allowed is False
    assert result.validation_result.acceptance_candidate is False
    assert all(row["bid"] is None and row["ask"] is None for row in rows)
    assert all(row["paper_pnl_allowed"] is False for row in rows)
    assert all(row["acceptance_candidate"] is False for row in rows)
    assert all(row["calibration_only_reason"] == "missing_point_in_time_bid_ask" for row in rows)


def test_missing_row_and_evidence_ids_are_generated_deterministically(tmp_path: Path):
    first = build_historical_dataset(
        CSV_ACCEPTANCE,
        input_format="csv",
        profile="acceptance_candidate",
        output_dir=tmp_path / "first",
        validate=False,
    )
    second = build_historical_dataset(
        CSV_ACCEPTANCE,
        input_format="csv",
        profile="acceptance_candidate",
        output_dir=tmp_path / "second",
        validate=False,
    )

    first_rows = _read_jsonl(first.output_jsonl)
    second_rows = _read_jsonl(second.output_jsonl)

    assert [row["row_id"] for row in first_rows] == [row["row_id"] for row in second_rows]
    assert [row["evidence"][0]["evidence_id"] for row in first_rows] == [
        row["evidence"][0]["evidence_id"] for row in second_rows
    ]
    assert all(row["row_id"].startswith("row_") for row in first_rows)
    assert all(row["evidence"][0]["evidence_id"].startswith("ev_") for row in first_rows)


def test_output_is_sorted_deterministically(tmp_path: Path):
    result = build_historical_dataset(
        CSV_ACCEPTANCE,
        input_format="csv",
        profile="acceptance_candidate",
        output_dir=tmp_path / "historical",
        validate=False,
    )

    rows = _read_jsonl(result.output_jsonl)
    sort_keys = [
        (row["timestamp"], row["platform"], row["market_id"], row["row_id"])
        for row in rows
    ]

    assert sort_keys == sorted(sort_keys)
    assert [row["timestamp"] for row in rows] == [
        "2026-05-01T20:00:00Z",
        "2026-05-02T20:00:00Z",
    ]


def test_builder_runs_validator_and_reports_artifacts(tmp_path: Path):
    result = build_historical_dataset(
        CSV_ACCEPTANCE,
        input_format="csv",
        profile="acceptance_candidate",
        output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        validate=True,
    )
    summary = result.as_summary()

    assert summary["validation_valid"] is True
    assert summary["error_count"] == 0
    assert result.validation_artifacts is not None
    assert result.validation_artifacts.json_path.exists()
    assert result.validation_artifacts.markdown_path.exists()
    assert "Historical Dataset Validation Audit" in result.validation_artifacts.markdown_path.read_text(
        encoding="utf-8"
    )


def test_malformed_manual_input_fails_with_clear_error(tmp_path: Path):
    with pytest.raises(ValueError, match="missing required field: market_id"):
        build_historical_dataset(
            MALFORMED_CSV,
            input_format="csv",
            profile="acceptance_candidate",
            output_dir=tmp_path / "historical",
            validate=False,
        )


def test_cli_build_command_writes_jsonl_manifest_and_validation_reports(tmp_path: Path):
    result = CliRunner().invoke(
        app,
        [
            "build-historical-dataset",
            "--input",
            str(CSV_ACCEPTANCE),
            "--input-format",
            "csv",
            "--profile",
            "acceptance_candidate",
            "--output-dir",
            str(tmp_path / "historical"),
            "--report-dir",
            str(tmp_path / "reports"),
            "--validate",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dataset_id"] == "phase7g_manual_builder_acceptance_fixture"
    assert payload["profile"] == "acceptance_candidate"
    assert payload["validation_valid"] is True
    assert payload["row_count"] == 2
    assert payload["market_count"] == 1
    assert payload["error_count"] == 0
    assert Path(payload["output_jsonl"]).exists()
    assert Path(payload["manifest_path"]).exists()
    assert Path(payload["validation_json_path"]).exists()
    assert Path(payload["validation_markdown_path"]).exists()


def test_builder_adds_no_downloader_network_or_source_adapter():
    source = inspect.getsource(builder_module)
    tree = ast.parse(source)
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    referenced_symbols = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    forbidden_modules = {"httpx", "requests", "urllib.request", "aiohttp"}
    forbidden_symbols = {
        "FixtureAdapter",
        "KalshiAdapter",
        "PolymarketAdapter",
        "YFinanceAdapter",
        "urlopen",
        "fetch_snapshot",
        "fetch_orderbook",
        "download",
        "request",
    }
    assert forbidden_modules.isdisjoint(imported_modules)
    assert forbidden_symbols.isdisjoint(referenced_symbols)
    assert "local_market_agent.adapters" not in imported_modules


def test_builder_adds_no_broker_live_or_order_api():
    source = inspect.getsource(builder_module)
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
        "LIVE",
        "create_order",
        "place_order",
        "open_position",
    }
    assert forbidden_symbols.isdisjoint(referenced_symbols)
    assert "local_market_agent.paper" not in source
    assert "local_market_agent.risk" not in source
    assert "broker" not in source.lower()


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
