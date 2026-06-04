from __future__ import annotations

import pytest
from pydantic import ValidationError

from local_market_agent.schemas.models import (
    ExecutionMode,
    MarketSnapshot,
    OrderSide,
    PaperFill,
    PaperOrder,
    PaperOrderIntent,
    Phase7RunRecord,
    Phase7RunStatus,
    PortfolioSnapshot,
    RiskDecision,
    RiskGateCheck,
    RiskGateDecision,
    RiskGateDecisionStatus,
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
        action=SignalAction.PAPER_BUY_YES,
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
        side=OrderSide.BUY_YES,
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
        action=SignalAction.PAPER_BUY_YES,
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
            side=OrderSide.BUY_YES,
            quantity=1,
            limit_price=0.51,
            fill_price=0.51,
            execution_mode=ExecutionMode.LIVE,
        )


def test_paper_fill_rejects_live_execution_mode(brief):
    with pytest.raises(ValidationError):
        PaperFill(
            order_id="paper_order_test",
            position_id="position_test",
            signal_id="signal_test",
            risk_decision_id="risk_test",
            market_id=brief.market_id,
            side=OrderSide.BUY_YES,
            quantity=1,
            price=0.51,
            execution_mode=ExecutionMode.LIVE,
        )


def test_paper_fill_only_allows_sell_for_closing_fills(brief):
    with pytest.raises(ValidationError, match="SELL fills can only close"):
        PaperFill(
            order_id="paper_order_test",
            position_id="position_test",
            signal_id="signal_test",
            risk_decision_id="risk_test",
            market_id=brief.market_id,
            side=OrderSide.SELL,
            quantity=1,
            price=0.51,
        )

    with pytest.raises(ValidationError, match="closing paper fills must use SELL"):
        PaperFill(
            order_id="paper_order_test",
            position_id="position_test",
            signal_id="signal_test",
            risk_decision_id="risk_test",
            market_id=brief.market_id,
            side=OrderSide.BUY_YES,
            quantity=1,
            price=0.51,
            is_closing=True,
        )


def test_portfolio_snapshot_rejects_live_execution_mode():
    with pytest.raises(ValidationError):
        PortfolioSnapshot(
            starting_cash=10_000,
            cash_balance=10_000,
            portfolio_value=10_000,
            realized_pnl=0,
            unrealized_pnl=0,
            total_fees=0,
            open_positions=0,
            closed_positions=0,
            total_positions=0,
            execution_mode=ExecutionMode.LIVE,
        )


def test_paper_order_intent_rejects_live_execution_mode(brief):
    with pytest.raises(ValidationError):
        PaperOrderIntent(
            signal_id="signal_test",
            market_id=brief.market_id,
            side=OrderSide.BUY_YES,
            quantity=1,
            limit_price=0.51,
            notional=0.51,
            execution_mode=ExecutionMode.LIVE,
        )


def test_risk_gate_decision_rejects_live_execution_mode(brief):
    with pytest.raises(ValidationError):
        RiskGateDecision(
            intent_id="intent_test",
            signal_id="signal_test",
            market_id=brief.market_id,
            status=RiskGateDecisionStatus.APPROVED,
            reasons=["Approved for paper gates only."],
            checks=[
                RiskGateCheck(
                    gate="paper_only",
                    status=RiskGateDecisionStatus.APPROVED,
                    passed=True,
                    reason="ok",
                )
            ],
            execution_mode=ExecutionMode.LIVE,
        )


def test_phase7_run_record_rejects_live_execution_mode(brief):
    with pytest.raises(ValidationError):
        Phase7RunRecord(
            report_date=brief.created_at,
            status=Phase7RunStatus.COMPLETED,
            market_id=brief.market_id,
            execution_mode=ExecutionMode.LIVE,
        )
