from __future__ import annotations

import runpy
from pathlib import Path

from local_market_agent.paper import PaperLedger
from local_market_agent.risk import RiskEngine
from local_market_agent.strategy import PredictionMarketEdgeStrategy


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
