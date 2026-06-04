from __future__ import annotations

from local_market_agent.agents import ResearchBriefGenerator
from local_market_agent.risk import RiskEngine
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
