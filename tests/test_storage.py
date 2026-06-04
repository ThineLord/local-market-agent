from __future__ import annotations

import pytest

from local_market_agent.agents import ResearchBriefGenerator
from local_market_agent.risk import RiskEngine
from local_market_agent.schemas.models import (
    OrderSide,
    PaperFill,
    PaperOrder,
    PortfolioSnapshot,
    Position,
    RiskGateCheck,
    RiskGateDecision,
    RiskGateDecisionStatus,
)
from local_market_agent.strategy import PredictionMarketEdgeStrategy


def test_storage_roundtrip(repo, snapshot, evidence):
    repo.save_market_snapshot(snapshot)
    loaded_snapshot = repo.load_market_snapshot(snapshot.snapshot_id)
    assert loaded_snapshot == snapshot

    brief = ResearchBriefGenerator(repository=repo).generate(snapshot, evidence)
    loaded_brief = repo.load_brief(brief.brief_id)
    assert loaded_brief == brief

    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    repo.save_signal(signal)
    assert repo.load_signal(signal.signal_id) == signal

    decision = RiskEngine().evaluate_signal(signal)
    repo.save_risk_decision(decision)
    assert repo.load_risk_decision(decision.risk_decision_id) == decision

    order = PaperOrder(
        signal_id=signal.signal_id,
        risk_decision_id=decision.risk_decision_id,
        market_id=signal.market_id,
        side=OrderSide.BUY_YES,
        quantity=10,
        limit_price=0.5,
        fill_price=0.5,
    )
    repo.append_paper_order(order)
    assert repo.load_paper_order(order.order_id) == order

    position = Position(
        market_id=signal.market_id,
        signal_id=signal.signal_id,
        risk_decision_id=decision.risk_decision_id,
        order_id=order.order_id,
        side=OrderSide.BUY_YES,
        quantity=10,
        average_price=0.5,
    )
    repo.save_position(position)
    assert repo.load_position(position.position_id) == position

    fill = PaperFill(
        order_id=order.order_id,
        position_id=position.position_id,
        signal_id=signal.signal_id,
        risk_decision_id=decision.risk_decision_id,
        market_id=signal.market_id,
        side=OrderSide.BUY_YES,
        quantity=10,
        price=0.5,
        fees=0.01,
    )
    repo.append_paper_fill(fill)
    assert repo.load_paper_fill(fill.fill_id) == fill

    portfolio_snapshot = PortfolioSnapshot(
        starting_cash=10_000,
        cash_balance=9_994.99,
        portfolio_value=9_999.99,
        realized_pnl=0,
        unrealized_pnl=-0.01,
        total_fees=0.01,
        open_positions=1,
        closed_positions=0,
        total_positions=1,
        market_values={position.position_id: 5.0},
    )
    repo.save_portfolio_snapshot(portfolio_snapshot)
    assert repo.load_portfolio_snapshot(portfolio_snapshot.snapshot_id) == portfolio_snapshot

    gate_decision = RiskGateDecision(
        intent_id="intent_test",
        signal_id=signal.signal_id,
        market_id=signal.market_id,
        status=RiskGateDecisionStatus.APPROVED,
        reasons=["Approved by paper risk gates."],
        checks=[
            RiskGateCheck(
                gate="market_data_freshness",
                status=RiskGateDecisionStatus.APPROVED,
                passed=True,
                reason="fresh",
            )
        ],
    )
    repo.save_risk_gate_decision(gate_decision)
    assert repo.load_risk_gate_decision(gate_decision.risk_gate_decision_id) == gate_decision


def test_storage_rejects_paper_order_without_saved_relationships(repo, brief):
    order = PaperOrder(
        signal_id="missing_signal",
        risk_decision_id="missing_risk",
        market_id=brief.market_id,
        side=OrderSide.BUY_YES,
        quantity=1,
        limit_price=0.5,
        fill_price=0.5,
    )
    with pytest.raises(ValueError, match="unknown signal_id"):
        repo.append_paper_order(order)


def test_storage_rejects_paper_fill_without_saved_order(repo, brief):
    fill = PaperFill(
        order_id="missing_order",
        position_id="position_test",
        signal_id="signal_test",
        risk_decision_id="risk_test",
        market_id=brief.market_id,
        side=OrderSide.BUY_YES,
        quantity=1,
        price=0.5,
    )
    with pytest.raises(ValueError, match="unknown order_id"):
        repo.append_paper_fill(fill)
