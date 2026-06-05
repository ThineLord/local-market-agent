from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from local_market_agent.config import Settings
from local_market_agent.llm import (
    MockLLMProvider,
    OpenAICompatibleProvider,
    StructuredOutputError,
    build_llm_provider,
    structured_completion,
)
from local_market_agent.schemas import ResearchBrief


class AlwaysInvalidProvider:
    def complete_json(self, prompt: str) -> str:
        return "not-json"


class TinyPayload(BaseModel):
    ok: bool


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


def test_structured_completion_sends_schema_and_extracts_reasoned_json():
    class ReasonedProvider:
        captured_prompt = ""

        def complete_json(self, prompt: str) -> str:
            self.captured_prompt = prompt
            return '<think>scratchpad</think>\n```json\n{"ok": true}\n```'

    provider = ReasonedProvider()

    result = structured_completion(provider, '{"input": "value"}', TinyPayload)

    payload = json.loads(provider.captured_prompt)
    assert result.ok is True
    assert payload["json_schema"]["title"] == "TinyPayload"
    assert payload["input"] == {"input": "value"}


def test_openai_compatible_provider_uses_timeout_and_ignores_reasoning(monkeypatch):
    calls: list[dict[str, object]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"ok": true}',
                            "reasoning": "model scratchpad that must not be parsed",
                        }
                    }
                ]
            }

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr("local_market_agent.llm.providers.httpx.post", fake_post)
    provider = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1",
        api_key=None,
        model="qwen3:14b",
        timeout_seconds=321.0,
    )

    raw = provider.complete_json("prompt")

    assert raw == '{"ok": true}'
    assert calls[0]["url"] == "http://localhost:11434/v1/chat/completions"
    assert calls[0]["timeout"] == 321.0
    assert calls[0]["json"]["stream"] is False
    assert calls[0]["json"]["response_format"] == {"type": "json_object"}
    assert "Authorization" not in calls[0]["headers"]


def test_build_llm_provider_uses_configured_openai_timeout():
    settings = Settings(
        llm_provider="openai-compatible",
        openai_compatible_base_url="http://localhost:11434/v1",
        openai_compatible_model="qwen3:14b",
        openai_compatible_timeout_seconds=456.0,
    )

    provider = build_llm_provider(settings)

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.timeout_seconds == 456.0
