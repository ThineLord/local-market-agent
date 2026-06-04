from __future__ import annotations

import pytest

from local_market_agent.paper import PaperLedger
from local_market_agent.risk import RiskEngine
from local_market_agent.schemas.models import RiskStatus
from local_market_agent.strategy import PredictionMarketEdgeStrategy


def test_paper_order_position_lifecycle(repo, brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.status == RiskStatus.APPROVED
    repo.save_signal(signal)
    repo.save_risk_decision(decision)

    ledger = PaperLedger(repo)
    order = ledger.create_order(signal=signal, risk_decision=decision, snapshot=snapshot)
    assert order.risk_decision_id == decision.risk_decision_id

    positions = repo.list_positions()
    assert len(positions) == 1
    assert positions[0].is_open

    closed = ledger.close_position(positions[0].position_id, close_price=0.60)
    assert not closed.is_open
    assert closed.realized_pnl > 0


def test_vetoed_decision_cannot_create_order(repo, brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(
        brief.model_copy(update={"confidence": 0.40}), snapshot
    )
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.status == RiskStatus.VETOED
    with pytest.raises(ValueError, match="approved risk decision"):
        PaperLedger(repo).create_order(signal=signal, risk_decision=decision, snapshot=snapshot)
