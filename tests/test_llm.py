from __future__ import annotations

import pytest

from local_market_agent.llm import MockLLMProvider, StructuredOutputError, structured_completion
from local_market_agent.schemas import ResearchBrief


class AlwaysInvalidProvider:
    def complete_json(self, prompt: str) -> str:
        return "not-json"


def test_mock_llm_deterministic_fields(snapshot, evidence):
    provider = MockLLMProvider()
    from local_market_agent.agents import Researcher

    first = Researcher(provider).draft(snapshot, evidence)
    second = Researcher(provider).draft(snapshot, evidence)
    assert first.recommended_action == second.recommended_action
    assert first.confidence == second.confidence
    assert first.evidence_quality == second.evidence_quality
    assert first.estimated_probability == second.estimated_probability


def test_invalid_json_is_caught_with_bounded_retries(snapshot, evidence):
    from local_market_agent.agents.research import Researcher

    prompt = Researcher(MockLLMProvider()).draft(snapshot, evidence).model_dump_json()
    with pytest.raises(StructuredOutputError):
        structured_completion(AlwaysInvalidProvider(), prompt, ResearchBrief, max_retries=1)
