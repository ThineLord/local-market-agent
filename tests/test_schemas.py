from __future__ import annotations

import pytest
from pydantic import ValidationError

from local_market_agent.schemas.models import (
    ExecutionMode,
    MarketSnapshot,
    OrderSide,
    PaperOrder,
    RiskDecision,
    RiskStatus,
    Signal,
    SignalAction,
)


def test_probability_fields_validate(snapshot):
    payload = snapshot.model_dump(mode="json")
    payload["market_implied_probability"] = 1.2
    with pytest.raises(ValidationError):
        MarketSnapshot.model_validate(payload)


def test_signal_risk_order_relationships_are_required(brief):
    signal = Signal(
        brief_id=brief.brief_id,
        market_id=brief.market_id,
        action=SignalAction.PAPER_BUY,
        agent_probability=0.65,
        market_probability=0.50,
        spread=0.03,
        edge=0.15,
        confidence=0.8,
        evidence_quality=0.8,
        rationale="test",
    )
    decision = RiskDecision(
        signal_id=signal.signal_id,
        status=RiskStatus.APPROVED,
        reasons=["Approved for paper trading only."],
    )
    order = PaperOrder(
        signal_id=signal.signal_id,
        risk_decision_id=decision.risk_decision_id,
        market_id=signal.market_id,
        side=OrderSide.BUY,
        quantity=1,
        limit_price=0.51,
        fill_price=0.51,
    )
    assert order.signal_id == signal.signal_id
    assert order.risk_decision_id == decision.risk_decision_id


def test_paper_order_rejects_live_execution_mode(brief):
    signal = Signal(
        brief_id=brief.brief_id,
        market_id=brief.market_id,
        action=SignalAction.PAPER_BUY,
        agent_probability=0.65,
        market_probability=0.50,
        spread=0.03,
        edge=0.15,
        confidence=0.8,
        evidence_quality=0.8,
        rationale="test",
    )
    with pytest.raises(ValidationError):
        PaperOrder(
            signal_id=signal.signal_id,
            risk_decision_id="risk_test",
            market_id=signal.market_id,
            side=OrderSide.BUY,
            quantity=1,
            limit_price=0.51,
            fill_price=0.51,
            execution_mode=ExecutionMode.LIVE,
        )
