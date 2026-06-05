from __future__ import annotations

from importlib import import_module
from typing import Any

from local_market_agent.eval.forecast_assessment import (
    ForecastAssessmentEvaluator,
    assign_calibration_bucket,
)

_RESEARCH_QUALITY_EXPORTS = {
    "DEFAULT_QWEN_BASE_URL",
    "DEFAULT_QWEN_MODEL",
    "ResearchQualityProviderSpec",
    "qwen_provider_spec",
    "run_daily_provider_comparison",
    "run_sandbox_provider_comparison",
}

__all__ = [
    "DEFAULT_QWEN_BASE_URL",
    "DEFAULT_QWEN_MODEL",
    "ForecastAssessmentEvaluator",
    "ResearchQualityProviderSpec",
    "assign_calibration_bucket",
    "qwen_provider_spec",
    "run_daily_provider_comparison",
    "run_sandbox_provider_comparison",
]


def __getattr__(name: str) -> Any:
    if name not in _RESEARCH_QUALITY_EXPORTS:
        raise AttributeError(name)
    module = import_module("local_market_agent.eval.research_quality")
    value = getattr(module, name)
    globals()[name] = value
    return value
