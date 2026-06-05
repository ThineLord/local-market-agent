from __future__ import annotations

import ast
import inspect
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import local_market_agent.data.kalshi_export_adapter as kalshi_adapter_module
from local_market_agent.cli import app
from local_market_agent.data import import_kalshi_export, validate_historical_dataset

FIXTURE_DIR = Path("data/fixtures/kalshi_export")
SAMPLE_ACCEPTANCE_EXPORT = FIXTURE_DIR / "sample_acceptance_export"
MISSING_BID_ASK_EXPORT = FIXTURE_DIR / "missing_bid_ask_export"
TERMS_PENDING_EXPORT = FIXTURE_DIR / "terms_pending_export"
FUTURE_EVIDENCE_EXPORT = FIXTURE_DIR / "future_evidence_export"
CALIBRATION_ONLY_EXPORT = FIXTURE_DIR / "calibration_only_export"


def test_valid_local_kalshi_acceptance_export_builds_valid_phase7g_jsonl(tmp_path: Path):
    result = import_kalshi_export(
        SAMPLE_ACCEPTANCE_EXPORT,
        profile="acceptance_candidate",
        output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        source_audit_dir=tmp_path / "source_audits",
        validate=True,
    )

    rows = _read_jsonl(result.output_jsonl)
    validation = validate_historical_dataset(result.output_jsonl)

    assert result.dataset_id == "phase7g_kalshi_local_acceptance_fixture"
    assert result.profile == "acceptance_candidate"
    assert result.validation_valid is True
    assert validation.valid is True
    assert validation.acceptance_candidate is True
    assert validation.paper_pnl_allowed is True
    assert result.row_count == 2
    assert result.market_count == 1
    assert all(row["platform"] == "kalshi" for row in rows)
    assert all(row["bid"] is not None and row["ask"] is not None for row in rows)
    assert all("settlement_outcome" not in row for row in rows)
    assert rows[0]["implied_probability"] == 0.43
    assert rows[0]["metadata"]["bid_source"] == "yes_bid.close_dollars"
    assert rows[0]["metadata"]["ask_source"] == "yes_ask.close_dollars"


def test_missing_candle_bid_or_ask_blocks_acceptance_without_downgrade(tmp_path: Path):
    with pytest.raises(ValueError, match="missing bid/ask close dollars"):
        import_kalshi_export(
            MISSING_BID_ASK_EXPORT,
            profile="acceptance_candidate",
            output_dir=tmp_path / "historical",
            report_dir=tmp_path / "reports",
            source_audit_dir=tmp_path / "source_audits",
            validate=True,
        )


def test_missing_candle_bid_or_ask_downgrades_only_with_explicit_flag(tmp_path: Path):
    result = import_kalshi_export(
        MISSING_BID_ASK_EXPORT,
        profile="acceptance_candidate",
        output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        source_audit_dir=tmp_path / "source_audits",
        validate=True,
        allow_downgrade=True,
    )

    rows = _read_jsonl(result.output_jsonl)

    assert result.profile == "calibration_only_last_price"
    assert result.downgraded is True
    assert "missing bid/ask" in str(result.downgrade_reason)
    assert result.validation_valid is True
    assert result.validation_result is not None
    assert result.validation_result.paper_pnl_allowed is False
    assert result.validation_result.acceptance_candidate is False
    assert all(row["bid"] is None and row["ask"] is None for row in rows)
    assert all(row["paper_pnl_allowed"] is False for row in rows)


def test_bid_greater_than_ask_fails_validation(tmp_path: Path):
    export_dir = _copy_fixture("sample_acceptance_export", tmp_path)
    candles = _read_jsonl(export_dir / "candlesticks.jsonl")
    candles[0]["yes_bid"]["close_dollars"] = 0.7
    candles[0]["yes_ask"]["close_dollars"] = 0.6
    _write_jsonl(export_dir / "candlesticks.jsonl", candles)

    result = import_kalshi_export(
        export_dir,
        profile="acceptance_candidate",
        output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        source_audit_dir=tmp_path / "source_audits",
        validate=True,
    )

    assert result.validation_valid is False
    assert result.validation_result is not None
    assert result.validation_result.bid_exceeds_ask_count == 1
    assert "bid_exceeds_ask" in result.validation_result.error_counts


def test_settlement_missing_blocks_acceptance(tmp_path: Path):
    export_dir = _copy_fixture("sample_acceptance_export", tmp_path)
    markets = _read_jsonl(export_dir / "markets.jsonl")
    markets[0]["result"] = None
    markets[0]["settlement_ts"] = None
    markets[0]["settlement_value_dollars"] = None
    _write_jsonl(export_dir / "markets.jsonl", markets)

    with pytest.raises(ValueError, match="missing unambiguous settlement"):
        import_kalshi_export(
            export_dir,
            profile="acceptance_candidate",
            output_dir=tmp_path / "historical",
            report_dir=tmp_path / "reports",
            source_audit_dir=tmp_path / "source_audits",
            validate=True,
        )


def test_terms_review_pending_blocks_acceptance(tmp_path: Path):
    with pytest.raises(ValueError, match="terms_review must be reviewed_public_research_local_only"):
        import_kalshi_export(
            TERMS_PENDING_EXPORT,
            profile="acceptance_candidate",
            output_dir=tmp_path / "historical",
            report_dir=tmp_path / "reports",
            source_audit_dir=tmp_path / "source_audits",
            validate=True,
        )


def test_private_or_authenticated_source_blocks_acceptance(tmp_path: Path):
    export_dir = _copy_fixture("sample_acceptance_export", tmp_path)
    manifest_path = export_dir / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["private_or_authenticated_source"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="private_or_authenticated_source"):
        import_kalshi_export(
            export_dir,
            profile="acceptance_candidate",
            output_dir=tmp_path / "historical",
            report_dir=tmp_path / "reports",
            source_audit_dir=tmp_path / "source_audits",
            validate=True,
        )


def test_future_evidence_leakage_is_blocked_before_acceptance_output(tmp_path: Path):
    with pytest.raises(ValueError, match="evidence timestamp coverage missing"):
        import_kalshi_export(
            FUTURE_EVIDENCE_EXPORT,
            profile="acceptance_candidate",
            output_dir=tmp_path / "historical",
            report_dir=tmp_path / "reports",
            source_audit_dir=tmp_path / "source_audits",
            validate=True,
        )


def test_duplicate_market_timestamp_rows_fail_validation(tmp_path: Path):
    export_dir = _copy_fixture("sample_acceptance_export", tmp_path)
    candles = _read_jsonl(export_dir / "candlesticks.jsonl")
    candles.append(dict(candles[0]))
    _write_jsonl(export_dir / "candlesticks.jsonl", candles)

    result = import_kalshi_export(
        export_dir,
        profile="acceptance_candidate",
        output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        source_audit_dir=tmp_path / "source_audits",
        validate=True,
    )

    assert result.validation_valid is False
    assert result.validation_result is not None
    assert result.validation_result.duplicate_market_timestamp_count == 1
    assert result.validation_result.duplicate_row_count == 1


def test_calibration_only_fallback_forces_no_paper_pnl(tmp_path: Path):
    result = import_kalshi_export(
        CALIBRATION_ONLY_EXPORT,
        profile="calibration_only_last_price",
        output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        source_audit_dir=tmp_path / "source_audits",
        validate=True,
    )

    rows = _read_jsonl(result.output_jsonl)

    assert result.validation_valid is True
    assert result.validation_result is not None
    assert result.validation_result.paper_pnl_allowed is False
    assert result.validation_result.acceptance_candidate is False
    assert all(row["bid"] is None and row["ask"] is None for row in rows)
    assert all(row["profile"] == "calibration_only_last_price" for row in rows)


def test_source_audit_report_is_written(tmp_path: Path):
    result = import_kalshi_export(
        SAMPLE_ACCEPTANCE_EXPORT,
        profile="acceptance_candidate",
        output_dir=tmp_path / "historical",
        report_dir=tmp_path / "reports",
        source_audit_dir=tmp_path / "source_audits",
        validate=True,
    )

    audit_text = result.source_audit_path.read_text(encoding="utf-8")
    assert "# Kalshi Local Export Source Audit" in audit_text
    assert "yes_bid.close_dollars" in audit_text
    assert "network_used: False" in audit_text


def test_cli_import_writes_jsonl_manifest_validation_reports_and_source_audit(tmp_path: Path):
    result = CliRunner().invoke(
        app,
        [
            "import-kalshi-export",
            "--export-dir",
            str(SAMPLE_ACCEPTANCE_EXPORT),
            "--profile",
            "acceptance_candidate",
            "--output-dir",
            str(tmp_path / "historical"),
            "--report-dir",
            str(tmp_path / "reports"),
            "--source-audit-dir",
            str(tmp_path / "source_audits"),
            "--validate",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dataset_id"] == "phase7g_kalshi_local_acceptance_fixture"
    assert payload["profile"] == "acceptance_candidate"
    assert payload["validation_valid"] is True
    assert payload["row_count"] == 2
    assert payload["market_count"] == 1
    assert payload["error_count"] == 0
    assert payload["downgraded"] is False
    assert Path(payload["output_jsonl"]).exists()
    assert Path(payload["manifest_path"]).exists()
    assert Path(payload["validation_json_path"]).exists()
    assert Path(payload["validation_markdown_path"]).exists()
    assert Path(payload["source_audit_path"]).exists()


def test_kalshi_adapter_adds_no_downloader_network_or_external_source_clients():
    source = inspect.getsource(kalshi_adapter_module)
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

    forbidden_modules = {
        "aiohttp",
        "http.client",
        "httpx",
        "requests",
        "socket",
        "urllib.request",
        "websocket",
    }
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


def test_kalshi_adapter_adds_no_broker_live_or_order_api():
    source = inspect.getsource(kalshi_adapter_module)
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


def _copy_fixture(name: str, tmp_path: Path) -> Path:
    destination = tmp_path / name
    shutil.copytree(FIXTURE_DIR / name, destination)
    return destination


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
