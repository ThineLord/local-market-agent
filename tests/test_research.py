from __future__ import annotations

from local_market_agent.agents import ResearchBriefGenerator
from local_market_agent.schemas.models import RecommendedAction


def test_research_brief_generator_outputs_valid_brief(snapshot, evidence):
    brief = ResearchBriefGenerator().generate(snapshot, evidence)
    assert brief.market_id == snapshot.market.market_id
    assert brief.recommended_action == RecommendedAction.PAPER_BUY_YES
    assert brief.uncertainty_notes
    assert brief.must_not_trade_reasons


def test_sparse_evidence_lowers_confidence(snapshot, evidence):
    full = ResearchBriefGenerator().generate(snapshot, evidence)
    sparse = ResearchBriefGenerator().generate(snapshot, evidence[:1])
    assert sparse.confidence < full.confidence
    assert sparse.confidence <= 0.45


def test_missing_market_price_prevents_paper_buy(snapshot, evidence):
    missing_price = snapshot.model_copy(
        update={
            "best_bid": None,
            "best_ask": None,
            "last_price": None,
            "market_implied_probability": None,
        }
    )
    brief = ResearchBriefGenerator().generate(missing_price, evidence)
    assert brief.recommended_action not in {
        RecommendedAction.PAPER_BUY_YES,
        RecommendedAction.PAPER_BUY_NO,
    }
    assert any("Missing market price" in reason for reason in brief.must_not_trade_reasons)


def test_no_evidence_means_no_trade(snapshot):
    brief = ResearchBriefGenerator().generate(snapshot, [])
    assert brief.recommended_action == RecommendedAction.SKIP
    assert any("No evidence" in reason for reason in brief.must_not_trade_reasons)
