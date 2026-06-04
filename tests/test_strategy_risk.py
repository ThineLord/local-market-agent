from __future__ import annotations

import pytest

from local_market_agent.paper import PaperLedger
from local_market_agent.risk import RiskEngine
from local_market_agent.schemas.models import ExecutionMode, RiskStatus, SignalAction
from local_market_agent.strategy import PredictionMarketEdgeStrategy


def test_prediction_strategy_produces_paper_signal_for_demo(brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    assert signal.action == SignalAction.PAPER_BUY
    assert signal.edge is not None and signal.edge >= 0.08


def test_low_confidence_veto(brief, snapshot):
    weak = brief.model_copy(update={"confidence": 0.40})
    signal = PredictionMarketEdgeStrategy().generate_signal(weak, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert signal.action == SignalAction.SKIP
    assert decision.status == RiskStatus.VETOED


def test_wide_spread_veto(brief, snapshot):
    wide = snapshot.model_copy(update={"best_bid": 0.40, "best_ask": 0.55})
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, wide)
    decision = RiskEngine().evaluate_signal(signal)
    assert signal.action == SignalAction.SKIP
    assert decision.status == RiskStatus.VETOED


def test_insufficient_edge_observe(brief, snapshot):
    weak_edge = brief.model_copy(update={"estimated_probability": 0.53})
    signal = PredictionMarketEdgeStrategy().generate_signal(weak_edge, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert signal.action == SignalAction.OBSERVE
    assert decision.status == RiskStatus.VETOED


def test_live_trading_attempt_is_vetoed(brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    live_signal = signal.model_copy(update={"execution_mode": ExecutionMode.LIVE})
    decision = RiskEngine().evaluate_signal(live_signal, live_order_requested=True)
    assert decision.status == RiskStatus.VETOED
    assert any("Live trading" in reason for reason in decision.reasons)


def test_missing_risk_decision_blocks_paper_order(repo, brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    with pytest.raises(ValueError, match="approved risk decision"):
        PaperLedger(repo).create_order(signal=signal, risk_decision=None, snapshot=snapshot)


def test_llm_cannot_bypass_risk(brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    attempted_bypass = signal.model_copy(
        update={
            "execution_mode": ExecutionMode.LIVE,
            "metadata": {"llm_override": "approve_and_trade_now"},
        }
    )
    decision = RiskEngine().evaluate_signal(attempted_bypass, live_order_requested=True)
    assert decision.status == RiskStatus.VETOED
