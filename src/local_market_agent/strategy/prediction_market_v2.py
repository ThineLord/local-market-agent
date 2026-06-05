from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from local_market_agent.config import RiskConfig
from local_market_agent.schemas.models import (
    ForecastAssessment,
    MarketSnapshot,
    ProbabilitySource,
    RecommendedAction,
    Signal,
    SignalAction,
)

REASON_MISSING_PROBABILITY = "missing_probability"
REASON_PROSE_ONLY_PROBABILITY = "prose_only_probability_not_accepted"
REASON_INCOMPLETE_STRUCTURED_OUTPUT = "incomplete_structured_output"
REASON_FUTURE_EVIDENCE_LEAKAGE = "future_evidence_leakage"
REASON_INSUFFICIENT_EVIDENCE = "insufficient_evidence_completeness"
REASON_MARKET_IMPLIED_BASELINE = "market_implied_only_baseline"
REASON_HINT_SOURCE_NOT_ELIGIBLE = "hint_source_not_eligible_outside_evaluation"
REASON_UNSUPPORTED_PROBABILITY_SOURCE = "unsupported_probability_source"
REASON_MISSING_BID_ASK = "missing_bid_ask"
REASON_SPREAD_TOO_WIDE = "spread_too_wide"
REASON_LIQUIDITY_TOO_THIN = "liquidity_too_thin"
REASON_EXECUTABLE_EV_BELOW_THRESHOLD = "executable_side_ev_below_threshold"
REASON_EDGE_WITHIN_UNCERTAINTY = "edge_within_uncertainty_band"
REASON_RECOMMENDATION_SIDE_MISMATCH = "recommendation_side_mismatch"

YES_RECOMMENDATIONS = {
    RecommendedAction.PAPER_BUY_YES.value,
    RecommendedAction.PAPER_BUY.value,
}
NO_RECOMMENDATIONS = {RecommendedAction.PAPER_BUY_NO.value}
HINT_PROBABILITY_SOURCES = {
    ProbabilitySource.FIXTURE_HINT,
    ProbabilitySource.HISTORICAL_HINT,
}
INDEPENDENT_PROBABILITY_SOURCES = {
    ProbabilitySource.MODEL_STRUCTURED,
    ProbabilitySource.MODEL_PLUS_RULES,
    ProbabilitySource.HUMAN_LABELED_DATASET,
}


@dataclass(frozen=True)
class StrategyV2Config:
    min_evidence_completeness_score: float = 0.5
    allow_hint_sources_in_evaluation: bool = True
    require_recommendation_match: bool = True


@dataclass(frozen=True)
class PredictionMarketV2CandidateStrategy:
    risk_config: RiskConfig = field(default_factory=RiskConfig)
    strategy_config: StrategyV2Config = field(default_factory=StrategyV2Config)

    def generate_signal(
        self,
        assessment: ForecastAssessment,
        snapshot: MarketSnapshot,
    ) -> Signal:
        probability = assessment.estimated_probability_yes
        market_probability = snapshot.market_implied_probability
        spread = snapshot.spread
        base_metadata = _base_metadata(assessment)

        if assessment.future_evidence_leakage:
            return self._signal(
                assessment,
                snapshot,
                SignalAction.SKIP,
                probability,
                market_probability,
                spread,
                None,
                REASON_FUTURE_EVIDENCE_LEAKAGE,
                base_metadata,
            )
        if REASON_PROSE_ONLY_PROBABILITY in assessment.rejection_reasons:
            return self._signal(
                assessment,
                snapshot,
                SignalAction.OBSERVE,
                probability,
                market_probability,
                spread,
                None,
                REASON_PROSE_ONLY_PROBABILITY,
                base_metadata,
            )
        if probability is None or assessment.probability_source == ProbabilitySource.MISSING:
            return self._signal(
                assessment,
                snapshot,
                SignalAction.OBSERVE,
                probability,
                market_probability,
                spread,
                None,
                REASON_MISSING_PROBABILITY,
                base_metadata,
            )
        if not assessment.structured_output_complete:
            return self._signal(
                assessment,
                snapshot,
                SignalAction.OBSERVE,
                probability,
                market_probability,
                spread,
                None,
                REASON_INCOMPLETE_STRUCTURED_OUTPUT,
                base_metadata,
            )
        if assessment.probability_source == ProbabilitySource.MARKET_IMPLIED_ONLY:
            return self._signal(
                assessment,
                snapshot,
                SignalAction.OBSERVE,
                probability,
                market_probability,
                spread,
                None,
                REASON_MARKET_IMPLIED_BASELINE,
                base_metadata,
            )
        if (
            assessment.evidence_completeness_score
            < self.strategy_config.min_evidence_completeness_score
        ):
            return self._signal(
                assessment,
                snapshot,
                SignalAction.OBSERVE,
                probability,
                market_probability,
                spread,
                None,
                REASON_INSUFFICIENT_EVIDENCE,
                base_metadata,
            )
        if assessment.probability_source in HINT_PROBABILITY_SOURCES:
            if not _hint_source_allowed(assessment, self.strategy_config):
                return self._signal(
                    assessment,
                    snapshot,
                    SignalAction.OBSERVE,
                    probability,
                    market_probability,
                    spread,
                    None,
                    REASON_HINT_SOURCE_NOT_ELIGIBLE,
                    base_metadata,
                )
            base_metadata["hint_source_evaluation_only"] = True
        elif assessment.probability_source not in INDEPENDENT_PROBABILITY_SOURCES:
            return self._signal(
                assessment,
                snapshot,
                SignalAction.OBSERVE,
                probability,
                market_probability,
                spread,
                None,
                REASON_UNSUPPORTED_PROBABILITY_SOURCE,
                base_metadata,
            )

        if snapshot.liquidity is not None and snapshot.liquidity < self.risk_config.min_liquidity_depth:
            return self._signal(
                assessment,
                snapshot,
                SignalAction.SKIP,
                probability,
                market_probability,
                spread,
                None,
                REASON_LIQUIDITY_TOO_THIN,
                base_metadata,
            )
        if spread is None or snapshot.best_bid is None or snapshot.best_ask is None:
            return self._signal(
                assessment,
                snapshot,
                SignalAction.OBSERVE,
                probability,
                market_probability,
                spread,
                None,
                REASON_MISSING_BID_ASK,
                base_metadata,
            )
        if spread > self.risk_config.max_spread:
            return self._signal(
                assessment,
                snapshot,
                SignalAction.SKIP,
                probability,
                market_probability,
                spread,
                None,
                REASON_SPREAD_TOO_WIDE,
                base_metadata,
            )

        ev = _executable_ev(assessment, snapshot, self.risk_config)
        metadata = {**base_metadata, "executable_ev": ev}
        threshold = ev["threshold"]
        yes_ev = ev["yes_adjusted_ev"]
        no_ev = ev["no_adjusted_ev"]
        best_adjusted_ev = max(yes_ev, no_ev)
        if best_adjusted_ev < threshold:
            reason = REASON_EXECUTABLE_EV_BELOW_THRESHOLD
            if ev["best_raw_ev"] >= threshold and ev["uncertainty_applied"]:
                reason = REASON_EDGE_WITHIN_UNCERTAINTY
            return self._signal(
                assessment,
                snapshot,
                SignalAction.OBSERVE,
                probability,
                market_probability,
                spread,
                best_adjusted_ev,
                reason,
                metadata,
            )

        action = SignalAction.PAPER_BUY_YES
        selected_ev = yes_ev
        if no_ev > yes_ev:
            action = SignalAction.PAPER_BUY_NO
            selected_ev = no_ev

        mismatch = _recommendation_mismatch(assessment, action)
        if mismatch:
            return self._signal(
                assessment,
                snapshot,
                SignalAction.OBSERVE,
                probability,
                market_probability,
                spread,
                selected_ev,
                REASON_RECOMMENDATION_SIDE_MISMATCH,
                {**metadata, "recommendation_mismatch": mismatch},
            )

        reason = (
            "v2_executable_yes_ev_clears_threshold"
            if action == SignalAction.PAPER_BUY_YES
            else "v2_executable_no_ev_clears_threshold"
        )
        return self._signal(
            assessment,
            snapshot,
            action,
            probability,
            market_probability,
            spread,
            selected_ev,
            reason,
            metadata,
        )

    def _signal(
        self,
        assessment: ForecastAssessment,
        snapshot: MarketSnapshot,
        action: SignalAction,
        probability: float | None,
        market_probability: float | None,
        spread: float | None,
        edge: float | None,
        rationale: str,
        metadata: dict[str, Any],
    ) -> Signal:
        reasons = list(metadata.get("strategy_v2_reasons", []))
        reasons.append(rationale)
        metadata = {
            **metadata,
            "strategy_v2_reasons": reasons,
            "paper_only": True,
            "evaluation_only": True,
            "mutates_state": False,
        }
        return Signal(
            brief_id=str(assessment.probability_provenance.get("brief_id") or assessment.forecast_id),
            market_id=snapshot.market.market_id,
            strategy_name="prediction_market_v2_candidate",
            action=action,
            agent_probability=probability,
            market_probability=market_probability,
            spread=spread,
            edge=round(edge, 8) if edge is not None else None,
            confidence=assessment.forecast_confidence
            if assessment.forecast_confidence is not None
            else min(
                assessment.input_completeness_score,
                assessment.evidence_completeness_score,
            ),
            evidence_quality=assessment.evidence_completeness_score,
            rationale=rationale,
            metadata=metadata,
        )


def _base_metadata(assessment: ForecastAssessment) -> dict[str, Any]:
    return {
        "forecast_id": assessment.forecast_id,
        "probability_source": assessment.probability_source.value,
        "calibration_bucket": assessment.calibration_bucket,
        "forecast_rejection_reasons": list(assessment.rejection_reasons),
        "input_completeness_score": assessment.input_completeness_score,
        "evidence_completeness_score": assessment.evidence_completeness_score,
        "strategy_v2_reasons": [],
    }


def _hint_source_allowed(
    assessment: ForecastAssessment,
    config: StrategyV2Config,
) -> bool:
    if not config.allow_hint_sources_in_evaluation:
        return False
    values = [
        str(assessment.probability_provenance.get("market_source", "")),
        str(assessment.probability_provenance.get("data_mode", "")),
        str(assessment.metadata.get("evaluation_context", "")),
    ]
    return any(
        value.lower() in {"fixture", "historical-file", "offline_evaluation"}
        or "historical" in value.lower()
        or "fixture" in value.lower()
        for value in values
    )


def _executable_ev(
    assessment: ForecastAssessment,
    snapshot: MarketSnapshot,
    risk_config: RiskConfig,
) -> dict[str, Any]:
    probability = float(assessment.estimated_probability_yes)
    spread = snapshot.spread or 0.0
    yes_entry = float(snapshot.best_ask)
    no_entry = round(1 - float(snapshot.best_bid), 10)
    yes_uncertainty, no_uncertainty = _uncertainty_margins(assessment, probability)
    yes_cost = _cost_buffer(yes_entry, risk_config)
    no_cost = _cost_buffer(no_entry, risk_config)
    yes_raw_ev = probability - yes_entry
    no_raw_ev = (1 - probability) - no_entry
    yes_adjusted_ev = yes_raw_ev - yes_cost - yes_uncertainty
    no_adjusted_ev = no_raw_ev - no_cost - no_uncertainty
    threshold = max(risk_config.min_edge, 2 * spread)
    return {
        "yes_entry_price": yes_entry,
        "no_entry_price": no_entry,
        "yes_raw_ev": round(yes_raw_ev, 8),
        "no_raw_ev": round(no_raw_ev, 8),
        "yes_adjusted_ev": round(yes_adjusted_ev, 8),
        "no_adjusted_ev": round(no_adjusted_ev, 8),
        "yes_cost_buffer": round(yes_cost, 8),
        "no_cost_buffer": round(no_cost, 8),
        "yes_uncertainty_buffer": round(yes_uncertainty, 8),
        "no_uncertainty_buffer": round(no_uncertainty, 8),
        "threshold": round(threshold, 8),
        "best_raw_ev": round(max(yes_raw_ev, no_raw_ev), 8),
        "uncertainty_applied": yes_uncertainty > 0 or no_uncertainty > 0,
    }


def _cost_buffer(entry_price: float, risk_config: RiskConfig) -> float:
    fee_buffer = entry_price * risk_config.paper_fee_rate
    slippage_buffer = entry_price * (risk_config.paper_slippage_bps / 10_000)
    return fee_buffer + slippage_buffer


def _uncertainty_margins(
    assessment: ForecastAssessment,
    probability: float,
) -> tuple[float, float]:
    margin = _number_from_metadata(assessment, "uncertainty_margin")
    if margin is not None:
        return margin, margin

    band = (
        assessment.metadata.get("uncertainty_band")
        or assessment.probability_provenance.get("uncertainty_band")
    )
    lower: float | None = None
    upper: float | None = None
    if isinstance(band, dict):
        lower = _float_or_none(band.get("lower"))
        upper = _float_or_none(band.get("upper"))
    elif isinstance(band, (list, tuple)) and len(band) == 2:
        lower = _float_or_none(band[0])
        upper = _float_or_none(band[1])

    if lower is None or upper is None:
        return 0.0, 0.0
    lower = max(0.0, min(1.0, lower))
    upper = max(0.0, min(1.0, upper))
    if lower > upper:
        lower, upper = upper, lower
    return max(0.0, probability - lower), max(0.0, upper - probability)


def _number_from_metadata(
    assessment: ForecastAssessment,
    key: str,
) -> float | None:
    return _float_or_none(
        assessment.metadata.get(key, assessment.probability_provenance.get(key))
    )


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _recommendation_mismatch(
    assessment: ForecastAssessment,
    action: SignalAction,
) -> dict[str, str] | None:
    raw = assessment.probability_provenance.get("recommended_action")
    if raw is None:
        return None
    recommended = str(raw)
    if action == SignalAction.PAPER_BUY_YES and recommended not in YES_RECOMMENDATIONS:
        return {"recommended_action": recommended, "selected_action": action.value}
    if action == SignalAction.PAPER_BUY_NO and recommended not in NO_RECOMMENDATIONS:
        return {"recommended_action": recommended, "selected_action": action.value}
    return None
