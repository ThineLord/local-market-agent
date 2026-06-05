from __future__ import annotations

import ast
import inspect
from datetime import timedelta

import local_market_agent.eval.forecast_assessment as forecast_assessment_module
from local_market_agent.eval import ForecastAssessmentEvaluator, assign_calibration_bucket
from local_market_agent.schemas.models import ProbabilitySource, RecommendedAction


def test_missing_structured_probability_blocks_action_eligibility(brief, snapshot):
    missing = brief.model_copy(update={"estimated_probability": None})

    assessment = ForecastAssessmentEvaluator().evaluate(missing, snapshot)

    assert assessment.estimated_probability_yes is None
    assert assessment.probability_source == ProbabilitySource.MISSING
    assert assessment.structured_output_complete is False
    assert assessment.action_eligible is False
    assert "missing_structured_probability" in assessment.rejection_reasons
    assert "provider_structured_output_incomplete" in assessment.rejection_reasons


def test_prose_only_probability_does_not_recover_missing_structured_field(
    brief,
    snapshot,
):
    prose_only = brief.model_copy(
        update={
            "estimated_probability": None,
            "rationale": "The prose estimate is 70% YES, but no structured field is present.",
        }
    )

    assessment = ForecastAssessmentEvaluator().evaluate(prose_only, snapshot)

    assert assessment.estimated_probability_yes is None
    assert assessment.structured_output_complete is False
    assert assessment.action_eligible is False
    assert assessment.probability_provenance["prose_probability_detected"] is True
    assert "prose_only_probability_not_accepted" in assessment.rejection_reasons


def test_out_of_range_probability_is_rejected(brief, snapshot):
    invalid = brief.model_copy(update={"estimated_probability": 1.2})

    assessment = ForecastAssessmentEvaluator().evaluate(invalid, snapshot)

    assert assessment.estimated_probability_yes is None
    assert assessment.structured_output_complete is False
    assert assessment.action_eligible is False
    assert assessment.calibration_bucket is None
    assert "invalid_probability_out_of_range" in assessment.rejection_reasons


def test_hint_derived_probability_is_labeled_correctly(brief, snapshot):
    assessment = ForecastAssessmentEvaluator().evaluate(
        brief,
        snapshot,
        evidence_metadata={"market_source": "fixture"},
    )

    assert assessment.probability_source == ProbabilitySource.FIXTURE_HINT
    assert assessment.probability_provenance["probability_hint_count"] == 3
    assert assessment.estimated_probability_yes == brief.estimated_probability
    assert assessment.rejection_reasons == []


def test_market_implied_only_probability_is_labeled_correctly(brief, snapshot):
    market_only = brief.model_copy(
        update={
            "estimated_probability": snapshot.market_implied_probability,
            "recommended_action": RecommendedAction.OBSERVE,
            "evidence": [],
            "counter_evidence": [],
        }
    )

    assessment = ForecastAssessmentEvaluator().evaluate(market_only, snapshot)

    assert assessment.probability_source == ProbabilitySource.MARKET_IMPLIED_ONLY
    assert assessment.estimated_probability_yes == snapshot.market_implied_probability
    assert assessment.action_eligible is False


def test_future_evidence_leakage_is_rejected(brief, snapshot):
    future_evidence = brief.evidence[0].model_copy(
        update={"published_at": snapshot.as_of + timedelta(days=1)}
    )
    leaked = brief.model_copy(update={"evidence": [future_evidence, *brief.evidence[1:]]})

    assessment = ForecastAssessmentEvaluator().evaluate(leaked, snapshot)

    assert assessment.future_evidence_leakage is True
    assert assessment.evidence_completeness_score < 1
    assert assessment.action_eligible is False
    assert "future_evidence_leakage" in assessment.rejection_reasons


def test_missing_evidence_lowers_completeness(brief, snapshot):
    no_evidence = brief.model_copy(update={"evidence": [], "counter_evidence": []})

    assessment = ForecastAssessmentEvaluator().evaluate(no_evidence, snapshot)

    assert assessment.missing_evidence is True
    assert assessment.evidence_count == 0
    assert assessment.evidence_completeness_score == 0
    assert "missing_evidence" in assessment.rejection_reasons


def test_calibration_bucket_assigned_correctly():
    assert assign_calibration_bucket(0.0) == "0.00-0.10"
    assert assign_calibration_bucket(0.6083) == "0.60-0.70"
    assert assign_calibration_bucket(0.1) == "0.10-0.20"
    assert assign_calibration_bucket(1.0) == "0.90-1.00"
    assert assign_calibration_bucket(None) is None
    assert assign_calibration_bucket(1.2) is None


def test_forecast_assessment_layer_adds_no_live_trading_path():
    source = inspect.getsource(forecast_assessment_module)

    assert "ExecutionMode.LIVE" not in source
    assert "live_order" not in source
    assert "ALLOW_LIVE_ORDERS" not in source


def test_forecast_assessment_layer_adds_no_broker_or_order_apis():
    source = inspect.getsource(forecast_assessment_module)
    tree = ast.parse(source)
    referenced_symbols = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    forbidden = [
        "PaperLedger",
        "PaperOrder",
        "PaperOrderIntent",
        "RiskEngine",
        "RiskGateEvaluator",
        "create_order",
        "open_position",
    ]
    assert all(term not in referenced_symbols for term in forbidden)
    assert "local_market_agent.paper" not in source
    assert "local_market_agent.risk" not in source
    assert "broker" not in source.lower()
