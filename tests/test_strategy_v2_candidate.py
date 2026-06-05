from __future__ import annotations

import ast
import inspect

import local_market_agent.strategy.prediction_market_v2 as strategy_v2_module
from local_market_agent.schemas.models import (
    ForecastAssessment,
    ProbabilitySource,
    SignalAction,
)
from local_market_agent.strategy import (
    PredictionMarketV2CandidateStrategy,
    StrategyV2Config,
)
from local_market_agent.strategy.prediction_market_v2 import (
    REASON_EDGE_WITHIN_UNCERTAINTY,
    REASON_EXECUTABLE_EV_BELOW_THRESHOLD,
    REASON_FUTURE_EVIDENCE_LEAKAGE,
    REASON_HINT_SOURCE_NOT_ELIGIBLE,
    REASON_MARKET_IMPLIED_BASELINE,
    REASON_MISSING_PROBABILITY,
    REASON_PROSE_ONLY_PROBABILITY,
)


def test_strategy_v2_missing_structured_probability_observes(brief, snapshot):
    assessment = _assessment(
        brief,
        snapshot,
        probability=None,
        source=ProbabilitySource.MISSING,
        structured=False,
        rejection_reasons=["missing_structured_probability"],
    )

    signal = PredictionMarketV2CandidateStrategy().generate_signal(assessment, snapshot)

    assert signal.action == SignalAction.OBSERVE
    assert signal.rationale == REASON_MISSING_PROBABILITY


def test_strategy_v2_prose_only_probability_observes(brief, snapshot):
    assessment = _assessment(
        brief,
        snapshot,
        probability=None,
        source=ProbabilitySource.MISSING,
        structured=False,
        rejection_reasons=["prose_only_probability_not_accepted"],
    )

    signal = PredictionMarketV2CandidateStrategy().generate_signal(assessment, snapshot)

    assert signal.action == SignalAction.OBSERVE
    assert signal.rationale == REASON_PROSE_ONLY_PROBABILITY


def test_strategy_v2_market_implied_only_does_not_trade_as_alpha(brief, snapshot):
    assessment = _assessment(
        brief,
        snapshot,
        probability=snapshot.market_implied_probability,
        source=ProbabilitySource.MARKET_IMPLIED_ONLY,
    )

    signal = PredictionMarketV2CandidateStrategy().generate_signal(assessment, snapshot)

    assert signal.action == SignalAction.OBSERVE
    assert signal.rationale == REASON_MARKET_IMPLIED_BASELINE


def test_strategy_v2_fixture_hint_trades_only_in_evaluation_context(brief, snapshot):
    assessment = _assessment(
        brief,
        snapshot,
        probability=0.70,
        source=ProbabilitySource.FIXTURE_HINT,
        provenance={"market_source": "fixture", "data_mode": "fixture"},
    )

    enabled = PredictionMarketV2CandidateStrategy().generate_signal(assessment, snapshot)
    disabled = PredictionMarketV2CandidateStrategy(
        strategy_config=StrategyV2Config(allow_hint_sources_in_evaluation=False)
    ).generate_signal(assessment, snapshot)

    assert enabled.action == SignalAction.PAPER_BUY_YES
    assert enabled.metadata["hint_source_evaluation_only"] is True
    assert disabled.action == SignalAction.OBSERVE
    assert disabled.rationale == REASON_HINT_SOURCE_NOT_ELIGIBLE


def test_strategy_v2_executable_yes_ev_required(brief, snapshot):
    low_yes_ev_snapshot = snapshot.model_copy(
        update={
            "best_bid": 0.56,
            "best_ask": 0.58,
            "market_implied_probability": 0.50,
        }
    )
    assessment = _assessment(
        brief,
        low_yes_ev_snapshot,
        probability=0.65,
        source=ProbabilitySource.MODEL_STRUCTURED,
    )

    signal = PredictionMarketV2CandidateStrategy().generate_signal(
        assessment,
        low_yes_ev_snapshot,
    )

    assert signal.action == SignalAction.OBSERVE
    assert signal.rationale == REASON_EXECUTABLE_EV_BELOW_THRESHOLD


def test_strategy_v2_executable_no_ev_required(brief, snapshot):
    low_no_ev_snapshot = snapshot.model_copy(
        update={
            "best_bid": 0.42,
            "best_ask": 0.44,
            "market_implied_probability": 0.50,
        }
    )
    assessment = _assessment(
        brief,
        low_no_ev_snapshot,
        probability=0.35,
        source=ProbabilitySource.MODEL_STRUCTURED,
        recommended_action="paper_buy_no",
    )

    signal = PredictionMarketV2CandidateStrategy().generate_signal(
        assessment,
        low_no_ev_snapshot,
    )

    assert signal.action == SignalAction.OBSERVE
    assert signal.rationale == REASON_EXECUTABLE_EV_BELOW_THRESHOLD


def test_strategy_v2_uncertainty_band_can_force_abstention(brief, snapshot):
    uncertain_snapshot = snapshot.model_copy(
        update={
            "best_bid": 0.53,
            "best_ask": 0.55,
            "market_implied_probability": 0.50,
        }
    )
    assessment = _assessment(
        brief,
        uncertain_snapshot,
        probability=0.70,
        source=ProbabilitySource.MODEL_STRUCTURED,
        metadata={"uncertainty_band": [0.60, 0.80]},
    )

    signal = PredictionMarketV2CandidateStrategy().generate_signal(
        assessment,
        uncertain_snapshot,
    )

    assert signal.action == SignalAction.OBSERVE
    assert signal.rationale == REASON_EDGE_WITHIN_UNCERTAINTY


def test_strategy_v2_future_evidence_leakage_blocks_action(brief, snapshot):
    assessment = _assessment(
        brief,
        snapshot,
        probability=0.70,
        source=ProbabilitySource.MODEL_STRUCTURED,
        future_evidence_leakage=True,
        rejection_reasons=["future_evidence_leakage"],
    )

    signal = PredictionMarketV2CandidateStrategy().generate_signal(assessment, snapshot)

    assert signal.action == SignalAction.SKIP
    assert signal.rationale == REASON_FUTURE_EVIDENCE_LEAKAGE


def test_strategy_v2_adds_no_broker_live_or_order_apis():
    source = inspect.getsource(strategy_v2_module)
    tree = ast.parse(source)
    referenced_symbols = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    forbidden_symbols = {
        "PaperLedger",
        "PaperOrder",
        "PaperOrderIntent",
        "RiskEngine",
        "RiskGateEvaluator",
        "ExecutionMode.LIVE",
        "create_order",
        "open_position",
    }
    assert forbidden_symbols.isdisjoint(referenced_symbols)
    assert "local_market_agent.paper" not in source
    assert "local_market_agent.risk" not in source
    assert "broker" not in source.lower()


def _assessment(
    brief,
    snapshot,
    *,
    probability: float | None,
    source: ProbabilitySource,
    structured: bool = True,
    evidence_score: float = 1.0,
    rejection_reasons: list[str] | None = None,
    provenance: dict[str, object] | None = None,
    metadata: dict[str, object] | None = None,
    future_evidence_leakage: bool = False,
    recommended_action: str = "paper_buy_yes",
) -> ForecastAssessment:
    probability_provenance = {
        "brief_id": brief.brief_id,
        "recommended_action": recommended_action,
        "market_source": "model",
        "data_mode": "offline_evaluation",
    }
    probability_provenance.update(provenance or {})
    return ForecastAssessment(
        market_id=snapshot.market.market_id,
        snapshot_id=snapshot.snapshot_id,
        as_of=snapshot.as_of,
        estimated_probability_yes=probability,
        probability_source=source,
        probability_provenance=probability_provenance,
        input_completeness_score=1.0,
        evidence_completeness_score=evidence_score,
        structured_output_complete=structured,
        forecast_confidence=0.80 if probability is not None else None,
        forecast_rationale="test forecast assessment",
        rejection_reasons=rejection_reasons or [],
        calibration_bucket="0.60-0.70" if probability is not None else None,
        future_evidence_leakage=future_evidence_leakage,
        metadata=metadata or {"evaluation_context": "offline_evaluation"},
    )
