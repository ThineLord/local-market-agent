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
from local_market_agent.eval.category_balance_plan import (
    CategoryBalancePlanArtifacts,
    CategoryBalancePlanResult,
    run_category_balance_plan,
    write_category_balance_plan_reports,
)
from local_market_agent.eval.category_calibration import (
    CategoryCalibrationArtifacts,
    CategoryCalibrationResult,
    run_category_calibration_analysis,
    write_category_calibration_reports,
)
from local_market_agent.eval.category_normalization import (
    CategoryNormalizationArtifacts,
    CategoryNormalizationExportResult,
    NormalizedCategoryResult,
    normalize_market_category,
    run_category_normalization_export,
    write_category_normalization_reports,
)
from local_market_agent.eval.category_taxonomy_audit import (
    CategoryTaxonomyAuditArtifacts,
    CategoryTaxonomyAuditResult,
    run_category_taxonomy_audit,
    write_category_taxonomy_audit_reports,
)
from local_market_agent.eval.collector_diagnostics import (
    CollectorDiagnostics,
    build_collector_diagnostics,
)
from local_market_agent.eval.forecast_assessment import (
    ForecastAssessmentEvaluator,
    assign_calibration_bucket,
)
from local_market_agent.eval.normalized_availability_audit import (
    NormalizedAvailabilityAuditArtifacts,
    NormalizedAvailabilityAuditResult,
    run_normalized_availability_audit,
    write_normalized_availability_audit_reports,
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
    "CategoryBalancePlanArtifacts",
    "CategoryBalancePlanResult",
    "CategoryCalibrationArtifacts",
    "CategoryCalibrationResult",
    "CategoryNormalizationArtifacts",
    "CategoryNormalizationExportResult",
    "CategoryTaxonomyAuditArtifacts",
    "CategoryTaxonomyAuditResult",
    "CollectorDiagnostics",
    "DEFAULT_QWEN_BASE_URL",
    "DEFAULT_QWEN_MODEL",
    "ForecastAssessmentEvaluator",
    "NormalizedCategoryResult",
    "NormalizedAvailabilityAuditArtifacts",
    "NormalizedAvailabilityAuditResult",
    "ResearchQualityProviderSpec",
    "StrategyOfflineEvaluationResult",
    "audit_calibration_dataset",
    "assign_calibration_bucket",
    "build_collector_diagnostics",
    "qwen_provider_spec",
    "normalize_market_category",
    "run_calibration_bucket_qa",
    "run_category_balance_plan",
    "run_category_calibration_analysis",
    "run_category_normalization_export",
    "run_category_taxonomy_audit",
    "run_daily_provider_comparison",
    "run_normalized_availability_audit",
    "run_sandbox_provider_comparison",
    "run_strategy_offline_evaluation",
    "write_calibration_audit_reports",
    "write_calibration_bucket_qa_reports",
    "write_category_balance_plan_reports",
    "write_category_calibration_reports",
    "write_category_normalization_reports",
    "write_category_taxonomy_audit_reports",
    "write_normalized_availability_audit_reports",
]


def __getattr__(name: str) -> Any:
    if name not in _RESEARCH_QUALITY_EXPORTS:
        raise AttributeError(name)
    module = import_module("local_market_agent.eval.research_quality")
    value = getattr(module, name)
    globals()[name] = value
    return value
