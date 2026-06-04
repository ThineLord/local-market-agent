from __future__ import annotations

import pytest

from local_market_agent.agents import ResearchBriefGenerator
from local_market_agent.risk import RiskEngine
from local_market_agent.schemas.models import OrderSide, PaperOrder
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
