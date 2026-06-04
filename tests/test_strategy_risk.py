from __future__ import annotations

import pytest

from local_market_agent.paper import PaperLedger
from local_market_agent.risk import RiskEngine
from local_market_agent.schemas.models import (
    ExecutionMode,
    RecommendedAction,
    RiskStatus,
    SignalAction,
)
from local_market_agent.strategy import PredictionMarketEdgeStrategy


def test_prediction_strategy_produces_paper_signal_for_demo(brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    assert signal.action == SignalAction.PAPER_BUY_YES
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


def test_prediction_strategy_can_generate_paper_buy_no(brief, snapshot):
    no_brief = brief.model_copy(
        update={
            "estimated_probability": 0.35,
            "recommended_action": RecommendedAction.PAPER_BUY_NO,
        }
    )
    signal = PredictionMarketEdgeStrategy().generate_signal(no_brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert signal.action == SignalAction.PAPER_BUY_NO
    assert signal.edge is not None and signal.edge >= 0.08
    assert decision.status == RiskStatus.APPROVED


def test_low_liquidity_skips(brief, snapshot):
    thin = snapshot.model_copy(update={"liquidity": 10.0})
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, thin)
    decision = RiskEngine().evaluate_signal(signal)
    assert signal.action == SignalAction.SKIP
    assert decision.status == RiskStatus.VETOED


def test_resolution_ambiguity_skips(brief, snapshot):
    ambiguous = brief.model_copy(update={"resolution_ambiguity": True})
    signal = PredictionMarketEdgeStrategy().generate_signal(ambiguous, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert signal.action == SignalAction.SKIP
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


def test_risk_defaults_match_original_master_plan(brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.max_position_pct == 0.01
    assert decision.config_snapshot["max_daily_loss_pct"] == 0.02
    assert decision.config_snapshot["max_total_drawdown_pct"] == 0.05
    assert decision.requires_human_approval is True
    assert decision.live_trading_allowed is False
