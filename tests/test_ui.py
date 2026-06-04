from __future__ import annotations

import runpy
from datetime import UTC, datetime
from pathlib import Path

from local_market_agent.config import RiskGateConfig, Settings
from local_market_agent.operations import Phase7DailyRunner
from local_market_agent.paper import PaperLedger
from local_market_agent.risk import RiskEngine
from local_market_agent.storage import SQLiteRepository
from local_market_agent.strategy import PredictionMarketEdgeStrategy

NOW = datetime(2026, 6, 5, 0, 1, tzinfo=UTC)


def test_streamlit_audit_chain_rows_include_linked_objects(
    monkeypatch,
    tmp_path,
    repo,
    brief,
    snapshot,
):
    repo.save_brief(brief)
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.is_approved
    repo.save_signal(signal)
    repo.save_risk_decision(decision)
    order = PaperLedger(repo).create_order(
        signal=signal,
        risk_decision=decision,
        snapshot=snapshot,
    )

    monkeypatch.setenv("LMA_DB_PATH", str(tmp_path / "ui-smoke.sqlite"))
    module = runpy.run_path(str(Path("ui/app.py")))
    rows = module["_audit_chain_rows"](repo)

    assert len(rows) == 1
    row = rows[0]
    assert row["brief_id"] == brief.brief_id
    assert row["signal_id"] == signal.signal_id
    assert row["risk_decision_id"] == decision.risk_decision_id
    assert row["paper_order_id"] == order.order_id
    assert row["market_id"] == brief.market_id
    assert row["recommended_action"] == "paper_buy_yes"
    assert row["signal_action"] == "paper_buy_yes"
    assert row["risk_approved"] is True
    assert row["veto_reasons"] == ""
    assert row["order_side"] == "BUY_YES"
    assert row["order_status"] == "filled"


def test_phase7_operations_view_model_handles_empty_repo(monkeypatch, tmp_path, repo):
    monkeypatch.setenv("LMA_DB_PATH", str(tmp_path / "ui-empty.sqlite"))
    module = runpy.run_path(str(Path("ui/app.py")))

    model = module["_phase7_operations_view_model"](repo)

    assert model["latest_run"] is None
    assert model["latest_report_path"] == ""
    assert model["run_rows"] == []
    assert model["open_positions"] == []
    assert model["paper_orders"] == []
    assert model["paper_fills"] == []
    assert model["risk_gate_decisions"] == []
    assert model["portfolio_summary"]["portfolio_value"] == 0.0
    assert model["portfolio_summary"]["exposure_pct"] == 0.0


def test_phase7_operations_view_model_reads_local_paper_records(monkeypatch, tmp_path):
    settings = Settings(
        db_path=tmp_path / "phase7-ui.sqlite",
        research_brief_dir=tmp_path / "briefs",
        risk_gates=RiskGateConfig(require_manual_approval=False),
    )
    repo, record = _seed_phase7_run(tmp_path, settings)

    monkeypatch.setenv("LMA_DB_PATH", str(tmp_path / "ui-phase7.sqlite"))
    module = runpy.run_path(str(Path("ui/app.py")))
    model = module["_phase7_operations_view_model"](repo)

    assert model["latest_run"]["run_id"] == record.run_id
    assert model["latest_run"]["status"] == "completed"
    assert model["latest_run"]["paper_order_id"] == record.paper_order_id
    assert model["latest_report_path"] == record.report_path
    assert Path(str(model["latest_report_path"])).exists()
    assert model["portfolio_summary"]["open_positions"] == 1
    assert model["portfolio_summary"]["portfolio_value"] > 0
    assert model["portfolio_summary"]["exposure"] > 0
    assert model["open_positions"][0]["market_id"] == record.market_id
    assert model["paper_orders"][0]["order_id"] == record.paper_order_id
    assert model["paper_fills"][0]["order_id"] == record.paper_order_id
    assert model["risk_gate_decisions"][0]["risk_gate_decision_id"] == (
        record.risk_gate_decision_id
    )
    assert model["risk_gate_decisions"][0]["status"] == "approved"


def _seed_phase7_run(tmp_path: Path, settings: Settings):
    repo = SQLiteRepository(settings.db_path)
    runner = Phase7DailyRunner(
        repository=repo,
        settings=settings,
        report_dir=tmp_path / "reports",
    )
    record = runner.run(now=NOW)
    return repo, record
