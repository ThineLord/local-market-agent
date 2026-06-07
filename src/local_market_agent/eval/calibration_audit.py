from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from local_market_agent.data.historical_validator import (
    ERROR_AMBIGUOUS_SETTLEMENT,
    ERROR_BID_EXCEEDS_ASK,
    ERROR_DUPLICATE_MARKET_TIMESTAMP,
    ERROR_DUPLICATE_ROW_ID,
    ERROR_EVIDENCE_TIMESTAMP_MISSING_FOR_ACCEPTANCE,
    ERROR_FUTURE_EVIDENCE_LEAKAGE,
    ERROR_INVALID_JSON,
    ERROR_INVALID_PROBABILITY,
    ERROR_INVALID_SCHEMA_VERSION,
    ERROR_INVALID_TIMESTAMP,
    ERROR_MISSING_BID_ASK_FOR_ACCEPTANCE,
    ERROR_MISSING_REQUIRED_FIELD,
    ERROR_MISSING_SETTLEMENT_FOR_SCORED_MARKET,
    ERROR_MISSING_SOURCE_PROVENANCE,
    ERROR_POST_SETTLEMENT_FORECAST_ROW,
    ERROR_PRIVATE_SOURCE_DETECTED,
    ERROR_ROW_NOT_OBJECT,
    ERROR_SECRET_PATTERN_DETECTED,
    ERROR_SOURCE_TERMS_BLOCKED,
    PROFILE_ACCEPTANCE,
    TERMS_REVIEWED,
    HistoricalDatasetValidationResult,
    validate_historical_dataset,
)

CLASSIFICATION_UNUSABLE = "calibration_unusable"
CLASSIFICATION_MINIMUM = "calibration_minimum"
CLASSIFICATION_PREFERRED = "calibration_preferred"
CLASSIFICATION_STRETCH = "calibration_stretch"
CLASSIFICATION_ACCEPTANCE_POSSIBLE = "acceptance_candidate_possible"

MINIMUM_MARKETS = 25
MINIMUM_ROWS = 250
PREFERRED_MARKETS = 60
PREFERRED_ROWS = 720
STRETCH_MARKETS = 150
STRETCH_ROWS = 2000
MINIMUM_CANDIDATE_FORECAST_ROWS = 50
ACCEPTANCE_EVIDENCE_TIMESTAMP_COVERAGE = 0.95

_CALIBRATION_NON_FATAL_VALIDATOR_ERRORS = {
    ERROR_EVIDENCE_TIMESTAMP_MISSING_FOR_ACCEPTANCE,
    ERROR_MISSING_BID_ASK_FOR_ACCEPTANCE,
}
_CALIBRATION_FATAL_VALIDATOR_ERRORS = {
    ERROR_AMBIGUOUS_SETTLEMENT,
    ERROR_BID_EXCEEDS_ASK,
    ERROR_DUPLICATE_MARKET_TIMESTAMP,
    ERROR_DUPLICATE_ROW_ID,
    ERROR_FUTURE_EVIDENCE_LEAKAGE,
    ERROR_INVALID_JSON,
    ERROR_INVALID_PROBABILITY,
    ERROR_INVALID_SCHEMA_VERSION,
    ERROR_INVALID_TIMESTAMP,
    ERROR_MISSING_REQUIRED_FIELD,
    ERROR_MISSING_SETTLEMENT_FOR_SCORED_MARKET,
    ERROR_MISSING_SOURCE_PROVENANCE,
    ERROR_POST_SETTLEMENT_FORECAST_ROW,
    ERROR_PRIVATE_SOURCE_DETECTED,
    ERROR_ROW_NOT_OBJECT,
    ERROR_SECRET_PATTERN_DETECTED,
    ERROR_SOURCE_TERMS_BLOCKED,
}


@dataclass(frozen=True)
class CalibrationAuditArtifacts:
    json_path: Path
    markdown_path: Path


@dataclass(frozen=True)
class CalibrationAuditResult:
    dataset_id: str
    classification: str
    historical_file: Path
    created_at: str
    row_count: int
    market_count: int
    resolved_market_count: int
    scored_row_count: int
    settlement_coverage_pct: float
    evidence_timestamp_coverage_pct: float
    bid_ask_coverage_pct: float
    last_price_coverage_pct: float
    category_count: int
    platform_distribution: dict[str, int]
    source_distribution: dict[str, int]
    duplicate_market_timestamp_rows: int
    missing_outcome_count: int
    missing_price_count: int
    acceptance_blockers: tuple[str, ...]
    calibration_warnings: tuple[str, ...]
    claim_guardrails: dict[str, bool]
    validation_summary: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "classification": self.classification,
            "historical_file": str(self.historical_file),
            "created_at": self.created_at,
            "row_count": self.row_count,
            "market_count": self.market_count,
            "resolved_market_count": self.resolved_market_count,
            "scored_row_count": self.scored_row_count,
            "settlement_coverage_pct": self.settlement_coverage_pct,
            "evidence_timestamp_coverage_pct": self.evidence_timestamp_coverage_pct,
            "bid_ask_coverage_pct": self.bid_ask_coverage_pct,
            "last_price_coverage_pct": self.last_price_coverage_pct,
            "category_count": self.category_count,
            "platform_distribution": self.platform_distribution,
            "source_distribution": self.source_distribution,
            "duplicate_market_timestamp_rows": self.duplicate_market_timestamp_rows,
            "missing_outcome_count": self.missing_outcome_count,
            "missing_price_count": self.missing_price_count,
            "acceptance_blockers": list(self.acceptance_blockers),
            "calibration_warnings": list(self.calibration_warnings),
            "claim_guardrails": self.claim_guardrails,
            "validation_summary": self.validation_summary,
        }


def audit_calibration_dataset(historical_file: str | Path) -> CalibrationAuditResult:
    historical_path = Path(historical_file)
    validation = validate_historical_dataset(historical_path)
    rows = _load_jsonl_rows(historical_path)
    row_metrics = _row_metrics(rows)

    acceptance_blockers = _acceptance_blockers(validation, row_metrics)
    calibration_warnings = _calibration_warnings(validation, row_metrics)
    classification = _classify(validation, row_metrics, acceptance_blockers)
    claim_guardrails = _claim_guardrails(
        classification=classification,
        row_metrics=row_metrics,
    )

    return CalibrationAuditResult(
        dataset_id=validation.dataset_id,
        classification=classification,
        historical_file=historical_path,
        created_at=datetime.now(UTC).isoformat(),
        row_count=row_metrics["row_count"],
        market_count=row_metrics["market_count"],
        resolved_market_count=row_metrics["resolved_market_count"],
        scored_row_count=row_metrics["scored_row_count"],
        settlement_coverage_pct=row_metrics["settlement_coverage_pct"],
        evidence_timestamp_coverage_pct=row_metrics["evidence_timestamp_coverage_pct"],
        bid_ask_coverage_pct=row_metrics["bid_ask_coverage_pct"],
        last_price_coverage_pct=row_metrics["last_price_coverage_pct"],
        category_count=row_metrics["category_count"],
        platform_distribution=row_metrics["platform_distribution"],
        source_distribution=row_metrics["source_distribution"],
        duplicate_market_timestamp_rows=validation.duplicate_market_timestamp_count,
        missing_outcome_count=row_metrics["missing_outcome_count"],
        missing_price_count=row_metrics["missing_price_count"],
        acceptance_blockers=tuple(acceptance_blockers),
        calibration_warnings=tuple(calibration_warnings),
        claim_guardrails=claim_guardrails,
        validation_summary=_validation_summary(validation),
    )


def write_calibration_audit_reports(
    result: CalibrationAuditResult,
    output_dir: str | Path,
) -> CalibrationAuditArtifacts:
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    safe_dataset_id = _safe_filename(result.dataset_id)
    json_path = report_dir / f"{safe_dataset_id}.calibration_audit.json"
    markdown_path = report_dir / f"{safe_dataset_id}_calibration_audit.md"
    json_path.write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown_report(result), encoding="utf-8")
    return CalibrationAuditArtifacts(json_path=json_path, markdown_path=markdown_path)


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _row_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    row_count = len(rows)
    market_ids = [_text(row.get("market_id")) for row in rows]
    markets = {market_id for market_id in market_ids if market_id}
    rows_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row, market_id in zip(rows, market_ids, strict=True):
        if market_id:
            rows_by_market[market_id].append(row)

    settled_rows = [row for row in rows if _has_unambiguous_settlement(row)]
    resolved_markets = {
        market_id
        for market_id, market_rows in rows_by_market.items()
        if market_rows
        and all(_has_unambiguous_settlement(row) for row in market_rows)
        and all(_text(row.get("market_type")) == "binary_prediction" for row in market_rows)
    }
    candidate_rows = [row for row in rows if _is_candidate_forecast_row(row)]
    evidence_timestamp_rows = [
        row for row in candidate_rows if _has_time_valid_evidence(row)
    ]
    bid_ask_rows = [row for row in rows if _valid_probability(row.get("bid")) and _valid_probability(row.get("ask"))]
    last_price_rows = [row for row in rows if _valid_probability(row.get("last_price"))]
    rows_with_price = [
        row
        for row in rows
        if _valid_probability(row.get("last_price"))
        or _valid_probability(row.get("implied_probability"))
    ]
    scored_rows = [row for row in rows_with_price if _has_unambiguous_settlement(row)]
    categories = Counter(
        category
        for row in rows
        if (category := _category(row))
    )
    platform_distribution = Counter(_text(row.get("platform")) or "missing" for row in rows)
    source_distribution = Counter(_source_name(row) or "missing" for row in rows)
    source_provenance_complete_count = sum(
        _source_provenance_complete(row) for row in rows
    )
    terms_pending_count = sum(_source_terms_pending(row) for row in rows)
    private_source_count = sum(_private_or_authenticated_source(row) for row in rows)
    paper_pnl_claim_count = sum(row.get("paper_pnl_allowed") is True for row in rows)

    return {
        "row_count": row_count,
        "market_count": len(markets),
        "resolved_market_count": len(resolved_markets),
        "scored_row_count": len(scored_rows),
        "settlement_coverage_pct": _coverage_pct(len(settled_rows), row_count),
        "evidence_timestamp_coverage_pct": _coverage_pct(
            len(evidence_timestamp_rows),
            len(candidate_rows),
        ),
        "bid_ask_coverage_pct": _coverage_pct(len(bid_ask_rows), row_count),
        "last_price_coverage_pct": _coverage_pct(len(last_price_rows), row_count),
        "category_count": len(categories),
        "platform_distribution": dict(sorted(platform_distribution.items())),
        "source_distribution": dict(sorted(source_distribution.items())),
        "missing_outcome_count": row_count - len(settled_rows),
        "missing_price_count": row_count - len(rows_with_price),
        "source_provenance_complete_count": source_provenance_complete_count,
        "terms_pending_count": terms_pending_count,
        "private_source_count": private_source_count,
        "paper_pnl_claim_count": paper_pnl_claim_count,
    }


def _acceptance_blockers(
    validation: HistoricalDatasetValidationResult,
    metrics: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if metrics["market_count"] < MINIMUM_MARKETS:
        blockers.append("market_count_below_acceptance_minimum")
    if metrics["row_count"] < MINIMUM_ROWS:
        blockers.append("row_count_below_acceptance_minimum")
    if validation.candidate_forecast_row_count < MINIMUM_CANDIDATE_FORECAST_ROWS:
        blockers.append("candidate_forecast_rows_below_acceptance_minimum")
    if metrics["resolved_market_count"] < MINIMUM_MARKETS:
        blockers.append("resolved_market_count_below_acceptance_minimum")
    if metrics["settlement_coverage_pct"] < 1.0:
        blockers.append("settlement_coverage_below_100_pct")
    if metrics["evidence_timestamp_coverage_pct"] < ACCEPTANCE_EVIDENCE_TIMESTAMP_COVERAGE:
        blockers.append("evidence_timestamp_coverage_below_95_pct")
    if metrics["bid_ask_coverage_pct"] < 1.0:
        blockers.append("bid_ask_coverage_incomplete")
    if metrics["source_provenance_complete_count"] < metrics["row_count"]:
        blockers.append("source_provenance_incomplete")
    if metrics["terms_pending_count"]:
        blockers.append("source_terms_pending_or_blocked")
    if metrics["private_source_count"]:
        blockers.append("private_or_authenticated_source_detected")
    if metrics["paper_pnl_claim_count"] == 0:
        blockers.append("paper_pnl_not_allowed_by_dataset")
    if validation.duplicate_market_timestamp_count:
        blockers.append("duplicate_market_timestamp_rows")
    if validation.future_evidence_leakage_count:
        blockers.append("future_evidence_leakage")
    if validation.error_count:
        blockers.extend(
            f"validator_error.{code}"
            for code in sorted(validation.error_counts)
        )
    return _dedupe(blockers)


def _calibration_warnings(
    validation: HistoricalDatasetValidationResult,
    metrics: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if metrics["evidence_timestamp_coverage_pct"] < ACCEPTANCE_EVIDENCE_TIMESTAMP_COVERAGE:
        warnings.append("timestamp_safe_evidence_incomplete_acceptance_blocker_only")
    if metrics["bid_ask_coverage_pct"] < 1.0:
        warnings.append("bid_ask_incomplete_paper_pnl_blocked")
    if metrics["category_count"] < 3:
        warnings.append("category_count_below_minimum_target")
    if metrics["category_count"] < 5 and metrics["row_count"] >= PREFERRED_ROWS:
        warnings.append("category_count_below_preferred_target")
    if metrics["last_price_coverage_pct"] < 1.0:
        warnings.append("last_price_coverage_incomplete")
    if metrics["terms_pending_count"]:
        warnings.append("source_terms_not_fully_reviewed_for_acceptance")
    warnings.extend(
        f"validator_warning.{code}"
        for code in sorted(validation.warning_counts)
    )
    non_fatal_error_codes = {
        code
        for code in validation.error_counts
        if code in _CALIBRATION_NON_FATAL_VALIDATOR_ERRORS
    }
    warnings.extend(
        f"validator_error_nonfatal_for_calibration.{code}"
        for code in sorted(non_fatal_error_codes)
    )
    return _dedupe(warnings)


def _classify(
    validation: HistoricalDatasetValidationResult,
    metrics: dict[str, Any],
    acceptance_blockers: list[str],
) -> str:
    if _acceptance_candidate_possible(validation, metrics, acceptance_blockers):
        return CLASSIFICATION_ACCEPTANCE_POSSIBLE
    if _calibration_unusable(validation, metrics):
        return CLASSIFICATION_UNUSABLE
    if metrics["market_count"] >= STRETCH_MARKETS and metrics["row_count"] >= STRETCH_ROWS:
        return CLASSIFICATION_STRETCH
    if metrics["market_count"] >= PREFERRED_MARKETS and metrics["row_count"] >= PREFERRED_ROWS:
        return CLASSIFICATION_PREFERRED
    if metrics["market_count"] >= MINIMUM_MARKETS and metrics["row_count"] >= MINIMUM_ROWS:
        return CLASSIFICATION_MINIMUM
    return CLASSIFICATION_UNUSABLE


def _calibration_unusable(
    validation: HistoricalDatasetValidationResult,
    metrics: dict[str, Any],
) -> bool:
    if metrics["market_count"] < MINIMUM_MARKETS or metrics["row_count"] < MINIMUM_ROWS:
        return True
    if metrics["resolved_market_count"] < MINIMUM_MARKETS:
        return True
    if metrics["settlement_coverage_pct"] < 1.0 or metrics["missing_outcome_count"]:
        return True
    if metrics["last_price_coverage_pct"] < 1.0 or metrics["missing_price_count"]:
        return True
    return bool(
        validation.duplicate_market_timestamp_count
        or validation.duplicate_row_count
        or _calibration_blocking_errors(validation)
    )


def _calibration_blocking_errors(
    validation: HistoricalDatasetValidationResult,
) -> list[str]:
    blocking: list[str] = []
    for issue in validation.errors:
        if issue.code in _CALIBRATION_NON_FATAL_VALIDATOR_ERRORS:
            continue
        if issue.code == ERROR_MISSING_REQUIRED_FIELD and issue.field == "evidence":
            continue
        if issue.code in _CALIBRATION_FATAL_VALIDATOR_ERRORS:
            blocking.append(issue.code)
    return blocking


def _acceptance_candidate_possible(
    validation: HistoricalDatasetValidationResult,
    metrics: dict[str, Any],
    acceptance_blockers: list[str],
) -> bool:
    return (
        not acceptance_blockers
        and validation.profile == PROFILE_ACCEPTANCE
        and validation.valid
        and validation.acceptance_candidate
        and validation.paper_pnl_allowed
        and metrics["market_count"] >= MINIMUM_MARKETS
        and metrics["row_count"] >= MINIMUM_ROWS
    )


def _claim_guardrails(
    *,
    classification: str,
    row_metrics: dict[str, Any],
) -> dict[str, bool]:
    calibration_usable = classification != CLASSIFICATION_UNUSABLE
    return {
        "forecast_calibration_diagnostics": calibration_usable,
        "strategy_comparison_diagnostics": calibration_usable,
        "paper_simulation_diagnostics": calibration_usable
        and (
            row_metrics["bid_ask_coverage_pct"] == 1.0
            or row_metrics["last_price_coverage_pct"] == 1.0
        ),
        "acceptance_gate_evaluation_possible": classification
        == CLASSIFICATION_ACCEPTANCE_POSSIBLE,
        "acceptance_gate_pass": False,
        "strategy_v2_superiority": False,
        "profitability_claim": False,
    }


def _validation_summary(
    validation: HistoricalDatasetValidationResult,
) -> dict[str, object]:
    return {
        "valid": validation.valid,
        "profile": validation.profile,
        "acceptance_candidate": validation.acceptance_candidate,
        "paper_pnl_allowed": validation.paper_pnl_allowed,
        "row_count": validation.row_count,
        "market_count": validation.market_count,
        "candidate_forecast_row_count": validation.candidate_forecast_row_count,
        "error_count": validation.error_count,
        "warning_count": validation.warning_count,
        "error_counts": validation.error_counts,
        "warning_counts": validation.warning_counts,
    }


def _has_unambiguous_settlement(row: dict[str, Any]) -> bool:
    settlement = row.get("settlement")
    if isinstance(settlement, dict):
        return (
            _text(settlement.get("outcome")) in {"yes", "no"}
            and settlement.get("ambiguous") is False
        )
    return _text(row.get("settlement_outcome")) in {"yes", "no"}


def _is_candidate_forecast_row(row: dict[str, Any]) -> bool:
    status = _text(row.get("market_status_at_timestamp"))
    if status == "settled" or _text(row.get("settlement_outcome")) in {"yes", "no"}:
        return False
    timestamp = _parse_timestamp(row.get("timestamp"))
    label_available_at = None
    settlement = row.get("settlement")
    if isinstance(settlement, dict):
        label_available_at = _parse_timestamp(settlement.get("label_available_at"))
    return timestamp is not None and (
        label_available_at is None or timestamp < label_available_at
    )


def _has_time_valid_evidence(row: dict[str, Any]) -> bool:
    timestamp = _parse_timestamp(row.get("timestamp"))
    evidence = row.get("evidence")
    if timestamp is None or not isinstance(evidence, list):
        return False
    for item in evidence:
        if not isinstance(item, dict):
            continue
        published_at = _parse_timestamp(item.get("published_at"))
        if published_at is not None and published_at <= timestamp:
            return True
    return False


def _source_provenance_complete(row: dict[str, Any]) -> bool:
    value = row.get("source_provenance")
    if not isinstance(value, dict):
        return False
    required = {
        "source_name",
        "source_type",
        "source_url",
        "source_record_id",
        "retrieved_at",
        "exported_at",
        "transform_version",
        "terms_review",
        "network_used_by_builder",
        "private_or_authenticated_source",
    }
    return all(not _blank(value.get(field)) for field in required)


def _source_terms_pending(row: dict[str, Any]) -> bool:
    value = row.get("source_provenance")
    if not isinstance(value, dict):
        return True
    return _text(value.get("terms_review")) != TERMS_REVIEWED


def _private_or_authenticated_source(row: dict[str, Any]) -> bool:
    value = row.get("source_provenance")
    if not isinstance(value, dict):
        return True
    return value.get("private_or_authenticated_source") is not False


def _source_name(row: dict[str, Any]) -> str | None:
    value = row.get("source_provenance")
    if not isinstance(value, dict):
        return None
    return _text(value.get("source_name"))


def _category(row: dict[str, Any]) -> str | None:
    for key in ("category", "market_category", "event_category"):
        value = _text(row.get(key))
        if value:
            return value
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        return _text(metadata.get("category"))
    return None


def _valid_probability(value: object) -> bool:
    if value is None or value == "":
        return False
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return 0 <= parsed <= 1


def _parse_timestamp(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _coverage_pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text.lower() if text else None


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return safe or "calibration_dataset"


def _render_markdown_report(result: CalibrationAuditResult) -> str:
    guardrails = result.claim_guardrails
    lines = [
        "# Calibration Dataset Audit",
        "",
        f"Dataset id: `{result.dataset_id}`",
        f"Historical file: `{result.historical_file}`",
        f"Classification: `{result.classification}`",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Row count | {result.row_count} |",
        f"| Market count | {result.market_count} |",
        f"| Resolved market count | {result.resolved_market_count} |",
        f"| Scored row count | {result.scored_row_count} |",
        f"| Settlement coverage | {result.settlement_coverage_pct:.6f} |",
        f"| Evidence timestamp coverage | {result.evidence_timestamp_coverage_pct:.6f} |",
        f"| Bid/ask coverage | {result.bid_ask_coverage_pct:.6f} |",
        f"| Last price coverage | {result.last_price_coverage_pct:.6f} |",
        f"| Category count | {result.category_count} |",
        f"| Duplicate market/timestamp rows | {result.duplicate_market_timestamp_rows} |",
        f"| Missing outcome count | {result.missing_outcome_count} |",
        f"| Missing price count | {result.missing_price_count} |",
        "",
        "## Claim Guardrails",
        "",
        "| Claim | Allowed |",
        "| --- | --- |",
        f"| Forecast calibration diagnostics | {guardrails['forecast_calibration_diagnostics']} |",
        f"| Strategy comparison diagnostics | {guardrails['strategy_comparison_diagnostics']} |",
        f"| Paper simulation diagnostics | {guardrails['paper_simulation_diagnostics']} |",
        f"| Acceptance gate evaluation possible | {guardrails['acceptance_gate_evaluation_possible']} |",
        f"| Acceptance gate pass | {guardrails['acceptance_gate_pass']} |",
        f"| Strategy v2 superiority | {guardrails['strategy_v2_superiority']} |",
        f"| Profitability claim | {guardrails['profitability_claim']} |",
        "",
        "This audit never marks the Strategy v2 acceptance gate as passed and never "
        "allows Strategy v2 superiority or profitability claims.",
        "",
        "## Acceptance Blockers",
        "",
    ]
    lines.extend(_bullet_lines(result.acceptance_blockers, empty="None."))
    lines.extend(["", "## Calibration Warnings", ""])
    lines.extend(_bullet_lines(result.calibration_warnings, empty="None."))
    lines.extend(["", "## Platform Distribution", ""])
    lines.extend(_distribution_lines(result.platform_distribution))
    lines.extend(["", "## Source Distribution", ""])
    lines.extend(_distribution_lines(result.source_distribution))
    lines.append("")
    return "\n".join(lines)


def _bullet_lines(values: tuple[str, ...], *, empty: str) -> list[str]:
    if not values:
        return [empty]
    return [f"- `{value}`" for value in values]


def _distribution_lines(distribution: dict[str, int]) -> list[str]:
    if not distribution:
        return ["None."]
    return [f"- `{key}`: {value}" for key, value in sorted(distribution.items())]
