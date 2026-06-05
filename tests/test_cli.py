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
