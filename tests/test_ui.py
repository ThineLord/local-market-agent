from __future__ import annotations

import runpy
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from local_market_agent.config import RiskGateConfig, Settings, load_settings
from local_market_agent.operations import Phase7DailyRunner
from local_market_agent.paper import PaperLedger
from local_market_agent.risk import RiskEngine
from local_market_agent.schemas.models import RiskStatus
from local_market_agent.storage import SQLiteRepository
from local_market_agent.strategy import PredictionMarketEdgeStrategy
from ui.app import _audit_chain_rows
from ui.server import DashboardRepository, dashboard_payload

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
    order = PaperLedger(repo, simulation_only=True).create_order(
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


def _track_bounded_reads(monkeypatch, repo):
    limits = {"briefs": [], "signals": [], "decisions": [], "orders": []}
    loaded = {"briefs": [], "signals": [], "decisions": []}

    def wrap_list(name, method):
        def inner(market_id=None, limit=None):
            limits[name].append(limit)
            return method(market_id=market_id, limit=limit)

        return inner

    def wrap_load(name, method):
        def inner(key):
            loaded[name].append(key)
            return method(key)

        return inner

    monkeypatch.setattr(repo, "list_briefs", wrap_list("briefs", repo.list_briefs))
    monkeypatch.setattr(repo, "list_signals", wrap_list("signals", repo.list_signals))
    monkeypatch.setattr(repo, "list_risk_decisions", wrap_list("decisions", repo.list_risk_decisions))
    monkeypatch.setattr(repo, "list_paper_orders", wrap_list("orders", repo.list_paper_orders))
    monkeypatch.setattr(repo, "load_brief", wrap_load("briefs", repo.load_brief))
    monkeypatch.setattr(repo, "load_signal", wrap_load("signals", repo.load_signal))
    monkeypatch.setattr(repo, "load_risk_decision", wrap_load("decisions", repo.load_risk_decision))
    return limits, loaded


def _order_rows(rows, order_id):
    return [row for row in rows if row["paper_order_id"] == order_id]


def test_audit_chain_keeps_order_when_approval_falls_outside_window(
    monkeypatch, repo, brief, snapshot
):
    repo.save_brief(brief)
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.is_approved
    repo.save_signal(signal)
    repo.save_risk_decision(decision)
    order = PaperLedger(repo, simulation_only=True).create_order(
        signal=signal,
        risk_decision=decision,
        snapshot=snapshot,
    )
    for index in range(100):
        repo.save_risk_decision(
            decision.model_copy(
                update={
                    "risk_decision_id": f"risk-synthetic-{index:03d}",
                    "created_at": decision.created_at + timedelta(seconds=index + 1),
                }
            )
        )
    no_order_signal = signal.model_copy(update={"signal_id": "signal-no-order"})
    repo.save_signal(no_order_signal)
    newest = decision.created_at + timedelta(days=1)
    repo.save_risk_decision(
        decision.model_copy(
            update={
                "risk_decision_id": "risk-no-order",
                "signal_id": no_order_signal.signal_id,
                "created_at": newest,
            }
        )
    )
    repo.save_risk_decision(
        decision.model_copy(
            update={
                "risk_decision_id": "risk-rejected",
                "signal_id": no_order_signal.signal_id,
                "created_at": newest + timedelta(seconds=1),
                "status": RiskStatus.VETOED,
                "reasons": ["spread too wide"],
            }
        )
    )
    repo.save_brief(
        brief.model_copy(
            update={
                "brief_id": "brief-no-signal",
                "created_at": brief.created_at + timedelta(days=1),
            }
        )
    )
    window_ids = {item.risk_decision_id for item in repo.list_risk_decisions(limit=100)}
    assert decision.risk_decision_id not in window_ids
    assert repo.load_risk_decision(decision.risk_decision_id).risk_decision_id == (
        decision.risk_decision_id
    )
    order_before = repo.load_paper_order(order.order_id).model_dump(mode="json")
    decision_count = repo.count("risk_decisions")
    limits, loaded = _track_bounded_reads(monkeypatch, repo)

    rows = _audit_chain_rows(repo)

    assert limits == {"briefs": [100], "signals": [100], "decisions": [100], "orders": [100]}
    assert decision.risk_decision_id in loaded["decisions"]
    assert None not in limits["decisions"]
    order_rows = _order_rows(rows, order.order_id)
    assert len(order_rows) == 1
    row = order_rows[0]
    assert row["risk_decision_id"] == decision.risk_decision_id
    assert row["_risk_decision"].risk_decision_id == decision.risk_decision_id
    assert row["_risk_decision"].is_approved is True
    assert row["_signal"].signal_id == signal.signal_id
    assert row["_brief"].brief_id == brief.brief_id
    assert row["risk_approved"] is True
    assert all(item["paper_order_id"] == "" for item in rows if item["risk_decision_id"] in window_ids)
    no_order = next(item for item in rows if item["risk_decision_id"] == "risk-no-order")
    assert no_order["paper_order_id"] == ""
    assert no_order["_paper_order"] is None
    rejected = next(item for item in rows if item["risk_decision_id"] == "risk-rejected")
    assert rejected["paper_order_id"] == ""
    assert rejected["risk_approved"] is False
    assert rejected["veto_reasons"] == "spread too wide"
    unlinked = next(item for item in rows if item["brief_id"] == "brief-no-signal")
    assert unlinked["signal_id"] == ""
    assert unlinked["paper_order_id"] == ""
    assert unlinked["_signal"] is None
    assert repo.count("risk_decisions") == decision_count
    assert repo.load_paper_order(order.order_id).model_dump(mode="json") == order_before

    before = repo.db_path.read_bytes()
    payload = dashboard_payload(replace(load_settings(), db_path=repo.db_path))
    assert repo.db_path.read_bytes() == before
    assert [item.order_id for item in payload["orders"]] == [order.order_id]
    payload_orders = _order_rows(payload["audit"], order.order_id)
    assert len(payload_orders) == 1
    assert payload_orders[0]["_risk_decision"].risk_decision_id == decision.risk_decision_id
    assert payload_orders[0]["_signal"].signal_id == signal.signal_id
    assert payload_orders[0]["_brief"].brief_id == brief.brief_id
    assert repo.count("risk_decisions") == decision_count
    assert repo.load_paper_order(order.order_id).model_dump(mode="json") == order_before


def test_audit_chain_resolves_signal_and_brief_outside_window_by_id(
    monkeypatch, repo, brief, snapshot
):
    repo.save_brief(brief)
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.is_approved
    repo.save_signal(signal)
    repo.save_risk_decision(decision)
    order = PaperLedger(repo, simulation_only=True).create_order(
        signal=signal,
        risk_decision=decision,
        snapshot=snapshot,
    )
    for index in range(100):
        created_at = signal.created_at + timedelta(seconds=index + 1)
        repo.save_signal(
            signal.model_copy(
                update={
                    "signal_id": f"signal-newer-{index:03d}",
                    "brief_id": f"brief-filler-{index:03d}",
                    "created_at": created_at,
                }
            )
        )
        repo.save_brief(
            brief.model_copy(
                update={"brief_id": f"brief-filler-{index:03d}", "created_at": created_at}
            )
        )
    assert signal.signal_id not in {item.signal_id for item in repo.list_signals(limit=100)}
    assert brief.brief_id not in {item.brief_id for item in repo.list_briefs(limit=100)}
    assert decision.risk_decision_id in {
        item.risk_decision_id for item in repo.list_risk_decisions(limit=100)
    }
    limits, loaded = _track_bounded_reads(monkeypatch, repo)

    rows = _audit_chain_rows(repo)

    assert limits == {"briefs": [100], "signals": [100], "decisions": [100], "orders": [100]}
    assert signal.signal_id in loaded["signals"]
    assert brief.brief_id in loaded["briefs"]
    order_rows = _order_rows(rows, order.order_id)
    assert len(order_rows) == 1
    row = order_rows[0]
    assert row["_signal"].signal_id == signal.signal_id
    assert row["_brief"].brief_id == brief.brief_id
    assert row["_risk_decision"].risk_decision_id == decision.risk_decision_id
    filler = next(item for item in rows if item["signal_id"] == "signal-newer-099")
    assert filler["paper_order_id"] == ""
    assert filler["_paper_order"] is None
    assert filler["_risk_decision"] is None


def test_audit_chain_missing_approval_stays_missing(repo, brief, snapshot):
    repo.save_brief(brief)
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.is_approved
    repo.save_signal(signal)
    repo.save_risk_decision(decision)
    order = PaperLedger(repo, simulation_only=True).create_order(
        signal=signal,
        risk_decision=decision,
        snapshot=snapshot,
    )
    for index in range(100):
        repo.save_risk_decision(
            decision.model_copy(
                update={
                    "risk_decision_id": f"risk-synthetic-{index:03d}",
                    "created_at": decision.created_at + timedelta(seconds=index + 1),
                }
            )
        )
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute(
            "DELETE FROM risk_decisions WHERE risk_decision_id = ?",
            (decision.risk_decision_id,),
        )
    assert repo.load_risk_decision(decision.risk_decision_id) is None
    decision_count = repo.count("risk_decisions")

    rows = _audit_chain_rows(repo)

    order_rows = _order_rows(rows, order.order_id)
    assert len(order_rows) == 1
    assert order_rows[0]["_risk_decision"] is None
    assert order_rows[0]["risk_approved"] is None
    assert order_rows[0]["_signal"].signal_id == signal.signal_id
    assert order_rows[0]["_brief"].brief_id == brief.brief_id
    assert all(
        item["paper_order_id"] != order.order_id
        for item in rows
        if str(item["risk_decision_id"]).startswith("risk-synthetic-")
    )
    assert repo.count("risk_decisions") == decision_count
    assert repo.load_risk_decision(decision.risk_decision_id) is None


def test_audit_chain_missing_signal_stays_missing(repo, brief, snapshot):
    repo.save_brief(brief)
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.is_approved
    repo.save_signal(signal)
    repo.save_risk_decision(decision)
    order = PaperLedger(repo, simulation_only=True).create_order(
        signal=signal,
        risk_decision=decision,
        snapshot=snapshot,
    )
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("DELETE FROM signals WHERE signal_id = ?", (signal.signal_id,))
    assert repo.load_signal(signal.signal_id) is None

    rows = _audit_chain_rows(repo)

    order_rows = _order_rows(rows, order.order_id)
    assert len(order_rows) == 1
    assert order_rows[0]["_signal"] is None
    assert order_rows[0]["_brief"] is None
    assert order_rows[0]["signal_action"] == ""
    assert order_rows[0]["_risk_decision"].risk_decision_id == decision.risk_decision_id
    assert order_rows[0]["_paper_order"].order_id == order.order_id
    assert repo.load_signal(signal.signal_id) is None


def test_audit_chain_missing_decision_table_stays_missing(repo, brief, snapshot):
    repo.save_brief(brief)
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.is_approved
    repo.save_signal(signal)
    repo.save_risk_decision(decision)
    order = PaperLedger(repo, simulation_only=True).create_order(
        signal=signal,
        risk_decision=decision,
        snapshot=snapshot,
    )
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("DROP TABLE risk_decisions")
    reader = DashboardRepository(repo.db_path)

    rows = _audit_chain_rows(reader)

    order_rows = _order_rows(rows, order.order_id)
    assert len(order_rows) == 1
    assert order_rows[0]["_risk_decision"] is None
    assert order_rows[0]["risk_approved"] is None
    assert order_rows[0]["_signal"].signal_id == signal.signal_id
    assert order_rows[0]["_paper_order"].order_id == order.order_id
    with sqlite3.connect(repo.db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert "risk_decisions" not in tables


def _seed_phase7_run(tmp_path: Path, settings: Settings):
    repo = SQLiteRepository(settings.db_path)
    runner = Phase7DailyRunner(
        repository=repo,
        settings=settings,
        report_dir=tmp_path / "reports",
    )
    record = runner.run(now=NOW)
    return repo, record
