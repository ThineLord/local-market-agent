from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from local_market_agent.config import Settings
from local_market_agent.llm.providers import (
    BaseLLMProvider,
    MockLLMProvider,
    OpenAICompatibleProvider,
)

MOCK_PROVIDER = "mock"
OPENAI_COMPATIBLE_PROVIDER = "openai-compatible"
SUPPORTED_PROVIDERS = {MOCK_PROVIDER, OPENAI_COMPATIBLE_PROVIDER}


@dataclass(frozen=True)
class LLMProviderAudit:
    provider: str
    model: str | None
    base_url: str | None
    network_calls_enabled: bool
    is_mock: bool
    is_real: bool
    api_key_configured: bool
    research_only: bool = True
    can_create_orders: bool = False
    configuration_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "network_calls_enabled": self.network_calls_enabled,
            "is_mock": self.is_mock,
            "is_real": self.is_real,
            "api_key_configured": self.api_key_configured,
            "research_only": self.research_only,
            "can_create_orders": self.can_create_orders,
        }
        if self.configuration_error is not None:
            payload["configuration_error"] = self.configuration_error
        return payload


def build_llm_provider(settings: Settings) -> BaseLLMProvider:
    audit = llm_provider_audit(settings)
    if audit.configuration_error is not None:
        raise ValueError(audit.configuration_error)
    if audit.provider == OPENAI_COMPATIBLE_PROVIDER:
        return OpenAICompatibleProvider(
            base_url=settings.openai_compatible_base_url,
            api_key=settings.openai_compatible_api_key,
            model=settings.openai_compatible_model,
        )
    return MockLLMProvider()


def llm_provider_audit(settings: Settings) -> LLMProviderAudit:
    provider = settings.llm_provider.strip().lower()
    if provider == MOCK_PROVIDER:
        return LLMProviderAudit(
            provider=MOCK_PROVIDER,
            model=None,
            base_url=None,
            network_calls_enabled=False,
            is_mock=True,
            is_real=False,
            api_key_configured=False,
        )
    if provider == OPENAI_COMPATIBLE_PROVIDER:
        return LLMProviderAudit(
            provider=OPENAI_COMPATIBLE_PROVIDER,
            model=settings.openai_compatible_model,
            base_url=settings.openai_compatible_base_url,
            network_calls_enabled=True,
            is_mock=False,
            is_real=True,
            api_key_configured=bool(settings.openai_compatible_api_key),
        )
    return LLMProviderAudit(
        provider=provider or settings.llm_provider,
        model=None,
        base_url=None,
        network_calls_enabled=False,
        is_mock=False,
        is_real=False,
        api_key_configured=False,
        configuration_error=(
            f"Unsupported LLM provider '{settings.llm_provider}'. "
            f"Supported providers: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
        ),
    )
