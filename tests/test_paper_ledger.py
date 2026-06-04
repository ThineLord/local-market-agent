from __future__ import annotations

import pytest

from local_market_agent.paper import PaperLedger
from local_market_agent.risk import RiskEngine
from local_market_agent.schemas.models import (
    OrderSide,
    OrderStatus,
    RecommendedAction,
    RiskStatus,
    SignalAction,
)
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
    assert order.side == OrderSide.BUY_YES
    assert order.status == OrderStatus.FILLED

    positions = repo.list_positions()
    assert len(positions) == 1
    assert positions[0].is_open
    fills = repo.list_paper_fills()
    assert len(fills) == 1
    assert fills[0].order_id == order.order_id
    assert fills[0].position_id == positions[0].position_id
    assert not fills[0].is_closing

    closed = ledger.close_position(positions[0].position_id, close_price=0.60)
    assert not closed.is_open
    assert closed.realized_pnl > 0
    assert ledger.realized_pnl() == closed.realized_pnl
    assert ledger.open_positions() == []

    fills = repo.list_paper_fills()
    assert len(fills) == 2
    assert any(fill.is_closing and fill.side == OrderSide.SELL for fill in fills)


def test_vetoed_decision_cannot_create_order(repo, brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(
        brief.model_copy(update={"confidence": 0.40}), snapshot
    )
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.status == RiskStatus.VETOED
    with pytest.raises(ValueError, match="approved risk decision"):
        PaperLedger(repo).create_order(signal=signal, risk_decision=decision, snapshot=snapshot)


def test_paper_buy_no_order_uses_no_side(repo, brief, snapshot):
    no_brief = brief.model_copy(
        update={
            "estimated_probability": 0.35,
            "recommended_action": RecommendedAction.PAPER_BUY_NO,
        }
    )
    signal = PredictionMarketEdgeStrategy().generate_signal(no_brief, snapshot)
    assert signal.action == SignalAction.PAPER_BUY_NO
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.status == RiskStatus.APPROVED
    repo.save_signal(signal)
    repo.save_risk_decision(decision)

    order = PaperLedger(repo).create_order(
        signal=signal,
        risk_decision=decision,
        snapshot=snapshot,
    )
    assert order.side == OrderSide.BUY_NO
    assert order.limit_price == 1 - snapshot.best_bid


def test_open_position_returns_position_and_persists_a_fill(repo, brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.status == RiskStatus.APPROVED
    repo.save_signal(signal)
    repo.save_risk_decision(decision)

    position = PaperLedger(repo).open_position(
        signal=signal,
        risk_decision=decision,
        snapshot=snapshot,
    )

    assert position.is_open
    assert repo.load_position(position.position_id) == position
    assert repo.list_paper_fills()[0].position_id == position.position_id


def test_portfolio_snapshot_tracks_cash_pnl_and_fees(repo, brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.status == RiskStatus.APPROVED
    repo.save_signal(signal)
    repo.save_risk_decision(decision)

    ledger = PaperLedger(repo)
    position = ledger.open_position(signal=signal, risk_decision=decision, snapshot=snapshot)
    mark = 0.60
    snapshot_record = ledger.snapshot_portfolio({snapshot.market.market_id: mark})

    assert snapshot_record.open_positions == 1
    assert snapshot_record.closed_positions == 0
    assert snapshot_record.unrealized_pnl == ledger.unrealized_pnl(
        {snapshot.market.market_id: mark}
    )
    assert snapshot_record.realized_pnl == 0
    assert snapshot_record.total_fees > 0
    assert snapshot_record.market_values[position.position_id] == round(
        mark * position.quantity,
        4,
    )
    assert repo.list_portfolio_snapshots(limit=1)[0].snapshot_id == snapshot_record.snapshot_id

    closed = ledger.close_position(position.position_id, close_price=mark)
    closed_snapshot = ledger.snapshot_portfolio()

    assert closed_snapshot.open_positions == 0
    assert closed_snapshot.closed_positions == 1
    assert closed_snapshot.realized_pnl == closed.realized_pnl
    assert closed_snapshot.portfolio_value == closed_snapshot.cash_balance
