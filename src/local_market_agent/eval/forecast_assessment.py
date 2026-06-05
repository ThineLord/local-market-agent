from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from local_market_agent.schemas.models import (
    EvidenceItem,
    ForecastAssessment,
    MarketSnapshot,
    ProbabilitySource,
    ResearchBrief,
)

REASON_MISSING_STRUCTURED_PROBABILITY = "missing_structured_probability"
REASON_PROSE_ONLY_PROBABILITY = "prose_only_probability_not_accepted"
REASON_INVALID_PROBABILITY = "invalid_probability_out_of_range"
REASON_PROVIDER_STRUCTURED_OUTPUT_INCOMPLETE = "provider_structured_output_incomplete"
REASON_MARKET_ID_MISMATCH = "market_id_mismatch"
REASON_SNAPSHOT_ID_MISMATCH = "snapshot_id_mismatch"
REASON_MISSING_MARKET_PROBABILITY = "missing_market_probability"
REASON_MISSING_BID_ASK = "missing_bid_ask"
REASON_MISSING_EVIDENCE = "missing_evidence"
REASON_STALE_EVIDENCE = "stale_evidence"
REASON_FUTURE_EVIDENCE_LEAKAGE = "future_evidence_leakage"

_PROSE_PROBABILITY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:0?\.\d+|1\.0+|\d{1,2}(?:\.\d+)?\s*%)"
)


@dataclass(frozen=True)
class ForecastAssessmentEvaluator:
    max_evidence_age_days: int = 30

    def evaluate(
        self,
        brief: ResearchBrief,
        snapshot: MarketSnapshot,
        *,
        evidence_metadata: Mapping[str, Any] | None = None,
    ) -> ForecastAssessment:
        metadata = dict(evidence_metadata or {})
        evidence = _assessment_evidence(brief)
        raw_probability = brief.estimated_probability
        probability, probability_valid = _valid_probability(raw_probability)
        prose_probability_detected = _has_prose_probability(brief)

        rejection_reasons: list[str] = []
        if raw_probability is None:
            rejection_reasons.append(REASON_MISSING_STRUCTURED_PROBABILITY)
            rejection_reasons.append(REASON_PROVIDER_STRUCTURED_OUTPUT_INCOMPLETE)
            if prose_probability_detected:
                rejection_reasons.append(REASON_PROSE_ONLY_PROBABILITY)
        elif not probability_valid:
            rejection_reasons.append(REASON_INVALID_PROBABILITY)
            rejection_reasons.append(REASON_PROVIDER_STRUCTURED_OUTPUT_INCOMPLETE)

        if brief.market_id != snapshot.market.market_id:
            rejection_reasons.append(REASON_MARKET_ID_MISMATCH)
        if brief.snapshot_id != snapshot.snapshot_id:
            rejection_reasons.append(REASON_SNAPSHOT_ID_MISMATCH)
        if snapshot.market_implied_probability is None:
            rejection_reasons.append(REASON_MISSING_MARKET_PROBABILITY)
        if snapshot.best_bid is None or snapshot.best_ask is None:
            rejection_reasons.append(REASON_MISSING_BID_ASK)

        evidence_state = _evidence_state(
            evidence,
            as_of=snapshot.as_of,
            max_age=timedelta(days=self.max_evidence_age_days),
        )
        if evidence_state["missing_evidence"]:
            rejection_reasons.append(REASON_MISSING_EVIDENCE)
        if evidence_state["stale_evidence"]:
            rejection_reasons.append(REASON_STALE_EVIDENCE)
        if evidence_state["future_evidence_leakage"]:
            rejection_reasons.append(REASON_FUTURE_EVIDENCE_LEAKAGE)

        probability_source = _probability_source(
            probability=probability if probability_valid else None,
            snapshot=snapshot,
            evidence=evidence,
            metadata=metadata,
        )
        structured_output_complete = probability is not None and probability_valid
        forecast_confidence, forecast_confidence_valid = _valid_probability(
            metadata.get("forecast_confidence")
        )
        if not forecast_confidence_valid:
            forecast_confidence = None
        action_eligible = (
            structured_output_complete
            and probability_source != ProbabilitySource.MARKET_IMPLIED_ONLY
            and not rejection_reasons
        )
        input_score = _input_completeness_score(
            brief=brief,
            snapshot=snapshot,
            probability_complete=structured_output_complete,
            future_evidence_leakage=bool(evidence_state["future_evidence_leakage"]),
        )
        evidence_score = _evidence_completeness_score(evidence_state)

        provenance = {
            "source": probability_source.value,
            "brief_id": brief.brief_id,
            "market_probability": snapshot.market_implied_probability,
            "observed_probability_raw": raw_probability,
            "probability_hint_count": _probability_hint_count(evidence),
            "prose_probability_detected": prose_probability_detected,
            "evidence_sources": sorted({item.source for item in evidence}),
            "provider_label": metadata.get("provider_label"),
            "provider_confidence": brief.confidence,
            "provider_evidence_quality": brief.evidence_quality,
            "forecast_confidence_source": (
                "calibrated_metadata" if forecast_confidence is not None else "missing"
            ),
            "market_source": metadata.get("market_source"),
            "data_mode": metadata.get("data_mode"),
        }

        return ForecastAssessment(
            market_id=brief.market_id,
            snapshot_id=brief.snapshot_id,
            as_of=_as_utc(snapshot.as_of),
            estimated_probability_yes=probability if probability_valid else None,
            probability_source=probability_source,
            probability_provenance=provenance,
            input_completeness_score=input_score,
            evidence_completeness_score=evidence_score,
            structured_output_complete=structured_output_complete,
            forecast_confidence=forecast_confidence,
            forecast_rationale=_forecast_rationale(brief),
            rejection_reasons=sorted(set(rejection_reasons)),
            calibration_bucket=assign_calibration_bucket(probability)
            if probability_valid
            else None,
            action_eligible=action_eligible,
            evidence_count=len(brief.evidence),
            counter_evidence_count=len(brief.counter_evidence),
            future_evidence_leakage=bool(evidence_state["future_evidence_leakage"]),
            stale_evidence=bool(evidence_state["stale_evidence"]),
            missing_evidence=bool(evidence_state["missing_evidence"]),
            metadata={
                "latest_evidence_published_at": evidence_state[
                    "latest_evidence_published_at"
                ],
                "timestamp_unknown_count": evidence_state["timestamp_unknown_count"],
                "paper_only": True,
                "can_create_orders": False,
                "strategy_policy": "not_evaluated",
            },
        )


def assign_calibration_bucket(probability: float | None) -> str | None:
    if probability is None:
        return None
    if not 0 <= probability <= 1:
        return None
    bucket_index = min(9, int(probability * 10))
    lower = bucket_index / 10
    upper = (bucket_index + 1) / 10
    return f"{lower:.2f}-{upper:.2f}"


def _assessment_evidence(brief: ResearchBrief) -> list[EvidenceItem]:
    return list(brief.evidence) + list(brief.counter_evidence)


def _valid_probability(value: object) -> tuple[float | None, bool]:
    if value is None:
        return None, True
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None, False
    if not 0 <= probability <= 1:
        return None, False
    return probability, True


def _has_prose_probability(brief: ResearchBrief) -> bool:
    text = " ".join(
        [
            brief.thesis,
            brief.rationale,
            " ".join(brief.uncertainty_notes),
            " ".join(brief.must_not_trade_reasons),
        ]
    )
    return _PROSE_PROBABILITY_PATTERN.search(text) is not None


def _probability_source(
    *,
    probability: float | None,
    snapshot: MarketSnapshot,
    evidence: Sequence[EvidenceItem],
    metadata: Mapping[str, Any],
) -> ProbabilitySource:
    explicit = _explicit_probability_source(metadata)
    if explicit is not None:
        return explicit
    if probability is None:
        return ProbabilitySource.MISSING

    hint_count = _probability_hint_count(evidence)
    if hint_count > 0:
        if _is_historical_context(snapshot, evidence, metadata):
            return ProbabilitySource.HISTORICAL_HINT
        if _is_fixture_context(snapshot, evidence, metadata):
            return ProbabilitySource.FIXTURE_HINT
        return ProbabilitySource.HISTORICAL_HINT

    market_probability = snapshot.market_implied_probability
    if market_probability is not None and abs(probability - market_probability) <= 1e-9:
        return ProbabilitySource.MARKET_IMPLIED_ONLY
    return ProbabilitySource.MODEL_STRUCTURED


def _explicit_probability_source(metadata: Mapping[str, Any]) -> ProbabilitySource | None:
    raw = metadata.get("probability_source")
    if raw is None:
        return None
    try:
        return ProbabilitySource(str(raw))
    except ValueError:
        return None


def _probability_hint_count(evidence: Sequence[EvidenceItem]) -> int:
    return sum(1 for item in evidence if "probability_hint" in item.metadata)


def _is_fixture_context(
    snapshot: MarketSnapshot,
    evidence: Sequence[EvidenceItem],
    metadata: Mapping[str, Any],
) -> bool:
    values = [
        snapshot.market.platform,
        str(metadata.get("market_source", "")),
        str(metadata.get("data_mode", "")),
        *(item.source for item in evidence),
    ]
    return any("fixture" in value.lower() for value in values)


def _is_historical_context(
    snapshot: MarketSnapshot,
    evidence: Sequence[EvidenceItem],
    metadata: Mapping[str, Any],
) -> bool:
    values = [
        snapshot.market.platform,
        str(metadata.get("market_source", "")),
        str(metadata.get("data_mode", "")),
        *(item.source for item in evidence),
    ]
    return any("historical" in value.lower() for value in values)


def _evidence_state(
    evidence: Sequence[EvidenceItem],
    *,
    as_of: datetime,
    max_age: timedelta,
) -> dict[str, Any]:
    as_of = _as_utc(as_of)
    if not evidence:
        return {
            "missing_evidence": True,
            "future_evidence_leakage": False,
            "stale_evidence": False,
            "latest_evidence_published_at": None,
            "timestamp_unknown_count": 0,
        }

    timestamped = [
        _as_utc(item.published_at) for item in evidence if item.published_at is not None
    ]
    future_leakage = any(published_at > as_of for published_at in timestamped)
    latest = max(timestamped) if timestamped else None
    stale = latest is not None and as_of - latest > max_age
    return {
        "missing_evidence": False,
        "future_evidence_leakage": future_leakage,
        "stale_evidence": stale,
        "latest_evidence_published_at": latest.isoformat() if latest is not None else None,
        "timestamp_unknown_count": len(evidence) - len(timestamped),
    }


def _input_completeness_score(
    *,
    brief: ResearchBrief,
    snapshot: MarketSnapshot,
    probability_complete: bool,
    future_evidence_leakage: bool,
) -> float:
    checks = [
        brief.market_id == snapshot.market.market_id,
        brief.snapshot_id == snapshot.snapshot_id,
        snapshot.as_of is not None,
        probability_complete,
        snapshot.market_implied_probability is not None,
        snapshot.best_bid is not None,
        snapshot.best_ask is not None,
        not future_evidence_leakage,
    ]
    return round(sum(1 for check in checks if check) / len(checks), 4)


def _evidence_completeness_score(evidence_state: Mapping[str, Any]) -> float:
    if evidence_state["missing_evidence"]:
        return 0.0
    checks = [
        not evidence_state["missing_evidence"],
        evidence_state["timestamp_unknown_count"] == 0,
        not evidence_state["future_evidence_leakage"],
        not evidence_state["stale_evidence"],
    ]
    return round(sum(1 for check in checks if check) / len(checks), 4)


def _forecast_rationale(brief: ResearchBrief) -> str:
    return (
        "Structured forecast assessment for "
        f"brief={brief.brief_id}; provider rationale: {brief.rationale}"
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
