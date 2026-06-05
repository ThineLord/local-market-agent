from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from typer.testing import CliRunner

import local_market_agent.data.historical_validator as validator_module
from local_market_agent.cli import app
from local_market_agent.data import validate_historical_dataset

FIXTURE_DIR = Path("data/fixtures/historical_validator")
VALID_ACCEPTANCE = FIXTURE_DIR / "valid_acceptance_candidate.jsonl"
VALID_CALIBRATION = FIXTURE_DIR / "valid_calibration_only.jsonl"


def test_valid_acceptance_fixture_passes():
    result = validate_historical_dataset(VALID_ACCEPTANCE)

    assert result.valid is True
    assert result.profile == "acceptance_candidate"
    assert result.acceptance_candidate is True
    assert result.paper_pnl_allowed is True
    assert result.row_count == 2
    assert result.market_count == 1
    assert result.resolved_binary_market_count == 1
    assert result.candidate_forecast_row_count == 2
    assert result.settlement_coverage_pct == 1.0
    assert result.evidence_timestamp_coverage_pct == 1.0
    assert result.error_count == 0


def test_valid_calibration_only_fixture_passes_without_paper_pnl():
    result = validate_historical_dataset(VALID_CALIBRATION)

    assert result.valid is True
    assert result.profile == "calibration_only_last_price"
    assert result.acceptance_candidate is False
    assert result.paper_pnl_allowed is False
    assert result.missing_bid_ask_count == 1
    assert result.warning_counts["last_price_only"] == 1


def test_missing_required_field_fails(tmp_path):
    payload = _first_payload(VALID_ACCEPTANCE)
    payload.pop("title")
    path = _write_rows(tmp_path, [payload])

    result = validate_historical_dataset(path)

    assert result.valid is False
    assert "missing_required_field" in _error_codes(result)


def test_invalid_timestamp_fails(tmp_path):
    payload = _first_payload(VALID_ACCEPTANCE)
    payload["timestamp"] = "2026-05-01T20:00:00"
    path = _write_rows(tmp_path, [payload])

    result = validate_historical_dataset(path)

    assert result.valid is False
    assert "invalid_timestamp" in _error_codes(result)


def test_bid_greater_than_ask_fails(tmp_path):
    payload = _first_payload(VALID_ACCEPTANCE)
    payload["bid"] = 0.80
    payload["ask"] = 0.70
    path = _write_rows(tmp_path, [payload])

    result = validate_historical_dataset(path)

    assert result.valid is False
    assert result.bid_exceeds_ask_count == 1
    assert "bid_exceeds_ask" in _error_codes(result)


def test_future_evidence_leakage_fails():
    result = validate_historical_dataset(FIXTURE_DIR / "invalid_future_evidence.jsonl")

    assert result.valid is False
    assert result.future_evidence_leakage_count == 1
    assert "future_evidence_leakage" in _error_codes(result)


def test_missing_settlement_fails(tmp_path):
    payload = _first_payload(VALID_ACCEPTANCE)
    payload.pop("settlement")
    path = _write_rows(tmp_path, [payload])

    result = validate_historical_dataset(path)

    assert result.valid is False
    assert "missing_settlement_for_scored_market" in _error_codes(result)


def test_ambiguous_settlement_fails():
    result = validate_historical_dataset(FIXTURE_DIR / "invalid_ambiguous_settlement.jsonl")

    assert result.valid is False
    assert "ambiguous_settlement" in _error_codes(result)
    assert result.acceptance_candidate is False


def test_private_authenticated_source_fails_acceptance(tmp_path):
    payload = _first_payload(VALID_ACCEPTANCE)
    payload["source_provenance"]["private_or_authenticated_source"] = True
    path = _write_rows(tmp_path, [payload])

    result = validate_historical_dataset(path)

    assert result.valid is False
    assert "private_source_detected" in _error_codes(result)


def test_secret_like_field_fails():
    result = validate_historical_dataset(FIXTURE_DIR / "invalid_secret_like_field.jsonl")

    assert result.valid is False
    assert "secret_pattern_detected" in _error_codes(result)


def test_duplicate_row_and_timestamp_detected():
    result = validate_historical_dataset(FIXTURE_DIR / "invalid_duplicate_row_timestamp.jsonl")

    assert result.valid is False
    assert result.duplicate_row_count == 1
    assert result.duplicate_market_timestamp_count == 1
    assert {"duplicate_row_id", "duplicate_market_timestamp"}.issubset(_error_codes(result))


def test_acceptance_missing_bid_ask_fixture_fails():
    result = validate_historical_dataset(FIXTURE_DIR / "invalid_missing_bid_ask.jsonl")

    assert result.valid is False
    assert result.missing_bid_ask_count == 1
    assert "missing_bid_ask_for_acceptance" in _error_codes(result)


def test_cli_writes_json_and_markdown_reports(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "validate-historical-dataset",
            "--historical-file",
            str(VALID_ACCEPTANCE),
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["valid"] is True
    assert payload["profile"] == "acceptance_candidate"
    assert payload["acceptance_candidate"] is True
    assert payload["paper_pnl_allowed"] is True
    assert payload["row_count"] == 2
    assert payload["market_count"] == 1
    assert payload["error_count"] == 0
    assert Path(payload["json_path"]).exists()
    assert Path(payload["markdown_path"]).exists()

    report = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    assert report["dataset_id"] == "phase7g_validator_acceptance_fixture"
    assert "Historical Dataset Validation Audit" in Path(
        payload["markdown_path"]
    ).read_text(encoding="utf-8")


def test_validator_adds_no_downloader_source_adapter_or_network_automation():
    source = inspect.getsource(validator_module)
    tree = ast.parse(source)
    referenced_symbols = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    forbidden_symbols = {
        "FixtureAdapter",
        "KalshiAdapter",
        "PolymarketAdapter",
        "YFinanceAdapter",
        "httpx",
        "requests",
        "urlopen",
        "fetch_snapshot",
        "fetch_orderbook",
    }
    assert forbidden_symbols.isdisjoint(referenced_symbols)
    assert "local_market_agent.adapters" not in source
    assert "httpx" not in source
    assert "requests" not in source


def test_validator_adds_no_broker_live_or_order_api():
    source = inspect.getsource(validator_module)
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
    assert "broker" not in source.lower()


def _first_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8").splitlines()[0])


def _write_rows(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def _error_codes(result) -> set[str]:
    return {issue.code for issue in result.errors}
