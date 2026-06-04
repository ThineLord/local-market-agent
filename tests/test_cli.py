from __future__ import annotations

import json

from typer.testing import CliRunner

from local_market_agent.cli import app


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
