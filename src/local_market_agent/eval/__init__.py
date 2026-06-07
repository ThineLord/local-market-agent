from __future__ import annotations

from importlib import import_module
from typing import Any

from local_market_agent.eval.calibration_audit import (
    CalibrationAuditArtifacts,
    CalibrationAuditResult,
    audit_calibration_dataset,
    write_calibration_audit_reports,
)
from local_market_agent.eval.calibration_bucket_qa import (
    CalibrationBucketQAArtifacts,
    CalibrationBucketQAResult,
    run_calibration_bucket_qa,
    write_calibration_bucket_qa_reports,
)
from local_market_agent.eval.forecast_assessment import (
    ForecastAssessmentEvaluator,
    assign_calibration_bucket,
)
from local_market_agent.eval.offline_strategy import (
    StrategyOfflineEvaluationResult,
    run_strategy_offline_evaluation,
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
    "CalibrationAuditArtifacts",
    "CalibrationAuditResult",
    "CalibrationBucketQAArtifacts",
    "CalibrationBucketQAResult",
    "DEFAULT_QWEN_BASE_URL",
    "DEFAULT_QWEN_MODEL",
    "ForecastAssessmentEvaluator",
    "ResearchQualityProviderSpec",
    "StrategyOfflineEvaluationResult",
    "audit_calibration_dataset",
    "assign_calibration_bucket",
    "qwen_provider_spec",
    "run_calibration_bucket_qa",
    "run_daily_provider_comparison",
    "run_sandbox_provider_comparison",
    "run_strategy_offline_evaluation",
    "write_calibration_audit_reports",
    "write_calibration_bucket_qa_reports",
]


def __getattr__(name: str) -> Any:
    if name not in _RESEARCH_QUALITY_EXPORTS:
        raise AttributeError(name)
    module = import_module("local_market_agent.eval.research_quality")
    value = getattr(module, name)
    globals()[name] = value
    return value
