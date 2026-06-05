from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from local_market_agent.cli import app
from local_market_agent.storage import SQLiteRepository


def test_cli_offline_demo_chain(tmp_path):
    runner = CliRunner()
    db = tmp_path / "cli.sqlite"

    result = runner.invoke(app, ["ingest-demo", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["evidence_items"] == 3

    result = runner.invoke(app, ["generate-brief", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["recommended_action"] == "paper_buy_yes"

    result = runner.invoke(app, ["risk-check", "--db", str(db)])
    assert result.exit_code == 0, result.output
    risk_payload = json.loads(result.output)
    assert risk_payload["signal_action"] == "paper_buy_yes"
    assert risk_payload["risk_status"] == "approved"

    result = runner.invoke(app, ["paper-log", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "paper_order_filled"

    result = runner.invoke(app, ["report-daily", "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["orders"] == 1


def test_cli_phase7_run_daily_fixture_smoke(tmp_path):
    runner = CliRunner()
    db = tmp_path / "phase7-cli.sqlite"
    report_dir = tmp_path / "reports"

    result = runner.invoke(
        app,
        [
            "phase7-run-daily",
            "--db",
            str(db),
            "--report-dir",
            str(report_dir),
            "--no-require-manual-approval",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "completed"
    assert payload["paper_order_id"] is not None
    assert payload["manifest_id"] == payload["run_id"]
    assert payload["report_checksum"] is not None
    assert payload["market_data"]["market_source"] == "fixture"
    assert payload["market_data"]["network_calls_enabled"] is False
    assert payload["market_data"]["profitability_claims_meaningful"] is False
    report_path = Path(payload["report_path"])
    assert report_path.exists()
    assert report_path.name == f"phase7_daily_report_{payload['run_id']}.md"
    assert report_path.suffix == ".md"

    repo = SQLiteRepository(db)
    counts_before = {
        table: repo.count(table)
        for table in [
            "phase7_run_records",
            "phase7_run_manifests",
            "paper_orders",
            "paper_fills",
            "positions",
        ]
    }

    result = runner.invoke(
        app,
        [
            "phase7-replay",
            "--db",
            str(db),
            "--run-id",
            payload["run_id"],
        ],
    )

    assert result.exit_code == 0, result.output
    replay_payload = json.loads(result.output)
    assert replay_payload["ok"] is True
    assert replay_payload["run_id"] == payload["run_id"]
    assert replay_payload["artifacts"]["run_manifest"]["present"] is True
    assert replay_payload["artifacts"]["report"]["present"] is True
    assert replay_payload["report_checksum"] == payload["report_checksum"]
    assert counts_before == {
        table: repo.count(table)
        for table in [
            "phase7_run_records",
            "phase7_run_manifests",
            "paper_orders",
            "paper_fills",
            "positions",
        ]
    }


def test_cli_llm_provider_audit_reports_default_mock():
    runner = CliRunner()

    result = runner.invoke(app, ["llm-provider-audit"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["provider"] == "mock"
    assert payload["model"] is None
    assert payload["network_calls_enabled"] is False
    assert payload["is_mock"] is True
    assert payload["is_real"] is False
    assert payload["can_create_orders"] is False


def test_cli_llm_provider_audit_reports_openai_compatible_without_secret():
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "llm-provider-audit",
            "--llm-provider",
            "openai-compatible",
            "--llm-model",
            "audit-model",
            "--llm-base-url",
            "http://127.0.0.1:9999/v1",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["provider"] == "openai-compatible"
    assert payload["model"] == "audit-model"
    assert payload["base_url"] == "http://127.0.0.1:9999/v1"
    assert payload["network_calls_enabled"] is True
    assert payload["is_mock"] is False
    assert payload["is_real"] is True
    assert payload["api_key_configured"] is False
    assert "api_key" not in payload


def test_cli_market_data_audit_reports_default_fixture():
    runner = CliRunner()

    result = runner.invoke(app, ["market-data-audit"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["market_source"] == "fixture"
    assert payload["data_mode"] == "fixture"
    assert payload["network_calls_enabled"] is False
    assert payload["is_fixture"] is True
    assert payload["is_historical"] is False
    assert payload["profitability_claims_meaningful"] is False
    assert payload["can_create_orders"] is False


def test_cli_market_data_audit_treats_blank_market_id_as_unset(monkeypatch):
    monkeypatch.setenv("LMA_MARKET_SOURCE", "fixture")
    monkeypatch.setenv("LMA_MARKET_ID", "")
    runner = CliRunner()

    result = runner.invoke(app, ["market-data-audit"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["market_source"] == "fixture"
    assert payload["market_id"] is None


def test_cli_market_data_audit_reports_snapshot_source_without_network_call():
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "market-data-audit",
            "--market-source",
            "polymarket",
            "--market-id",
            "pm-audit-market",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["market_source"] == "polymarket"
    assert payload["market_id"] == "pm-audit-market"
    assert payload["data_mode"] == "current_snapshot"
    assert payload["network_calls_enabled"] is True
    assert payload["is_historical"] is False
    assert payload["is_snapshot_only"] is True
    assert payload["read_only"] is True
    assert payload["can_create_orders"] is False
    assert payload["configuration_error"] is None


def test_cli_market_data_audit_reports_missing_non_fixture_market_id():
    runner = CliRunner()

    result = runner.invoke(app, ["market-data-audit", "--market-source", "kalshi"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["market_source"] == "kalshi"
    assert payload["requires_market_id"] is True
    assert "--market-id is required" in payload["configuration_error"]


def test_cli_market_data_audit_reports_historical_file():
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "market-data-audit",
            "--market-source",
            "historical-file",
            "--historical-file",
            "data/fixtures/phase7_historical_5d.jsonl",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["market_source"] == "historical-file"
    assert payload["data_mode"] == "historical_local_dataset"
    assert payload["network_calls_enabled"] is False
    assert payload["is_historical"] is True
    assert payload["historical_record_count"] == 5
    assert payload["historical_start_date"] == "2026-05-01"
    assert payload["historical_end_date"] == "2026-05-05"
    assert payload["has_settlement"] is True
    assert payload["profitability_claims_meaningful"] is True
    assert payload["can_create_orders"] is False


def test_cli_market_data_audit_uses_selected_historical_market(tmp_path):
    historical_file = tmp_path / "multi-market-history.jsonl"
    rows = [
        {
            "date": "2026-05-01",
            "market_id": "market-without-settlement",
            "bid": 0.48,
            "ask": 0.50,
            "last_price": 0.49,
        },
        {
            "date": "2026-05-01",
            "market_id": "market-with-settlement",
            "bid": 0.60,
            "ask": 0.62,
            "last_price": 0.61,
            "evidence": [
                {
                    "title": "Selected elsewhere",
                    "published_at": "2026-05-01T10:00:00Z",
                }
            ],
            "settlement_outcome": "yes",
        },
    ]
    historical_file.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "market-data-audit",
            "--market-source",
            "historical-file",
            "--historical-file",
            str(historical_file),
            "--market-id",
            "market-without-settlement",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["market_id"] == "market-without-settlement"
    assert payload["historical_record_count"] == 1
    assert payload["has_settlement"] is False
    assert payload["settlement_coverage"] == "none"
    assert payload["profitability_claims_meaningful"] is False
    assert payload["evidence_source"] == "missing"
    assert any(
        "selected historical market" in warning.lower()
        for warning in payload["historical_dataset_warnings"]
    )
