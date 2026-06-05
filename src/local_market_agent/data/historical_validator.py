from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "phase7g.historical_dataset.v1"
PROFILE_ACCEPTANCE = "acceptance_candidate"
PROFILE_CALIBRATION_ONLY = "calibration_only_last_price"
TERMS_REVIEWED = "reviewed_public_research_local_only"

ERROR_INVALID_JSON = "invalid_json"
ERROR_ROW_NOT_OBJECT = "row_not_object"
ERROR_MISSING_REQUIRED_FIELD = "missing_required_field"
ERROR_INVALID_SCHEMA_VERSION = "invalid_schema_version"
ERROR_INVALID_TIMESTAMP = "invalid_timestamp"
ERROR_DATE_TIMESTAMP_MISMATCH = "date_timestamp_mismatch"
ERROR_UNSUPPORTED_MARKET_TYPE = "unsupported_market_type"
ERROR_INVALID_PROBABILITY = "invalid_probability"
ERROR_BID_EXCEEDS_ASK = "bid_exceeds_ask"
ERROR_MISSING_BID_ASK_FOR_ACCEPTANCE = "missing_bid_ask_for_acceptance"
ERROR_DUPLICATE_MARKET_TIMESTAMP = "duplicate_market_timestamp"
ERROR_DUPLICATE_ROW_ID = "duplicate_row_id"
ERROR_FUTURE_EVIDENCE_LEAKAGE = "future_evidence_leakage"
ERROR_EVIDENCE_TIMESTAMP_MISSING_FOR_ACCEPTANCE = (
    "evidence_timestamp_missing_for_acceptance"
)
ERROR_MISSING_SETTLEMENT_FOR_SCORED_MARKET = "missing_settlement_for_scored_market"
ERROR_AMBIGUOUS_SETTLEMENT = "ambiguous_settlement"
ERROR_POST_SETTLEMENT_FORECAST_ROW = "post_settlement_forecast_row"
ERROR_MISSING_SOURCE_PROVENANCE = "missing_source_provenance"
ERROR_SOURCE_TERMS_BLOCKED = "source_terms_blocked"
ERROR_PRIVATE_SOURCE_DETECTED = "private_source_detected"
ERROR_SECRET_PATTERN_DETECTED = "secret_pattern_detected"

WARNING_MISSING_EVIDENCE = "missing_evidence"
WARNING_SINGLE_SOURCE_EVIDENCE = "single_source_evidence"
WARNING_TIMESTAMP_UNKNOWN = "timestamp_unknown"
WARNING_DATE_ONLY_EVIDENCE_TIMESTAMP = "date_only_evidence_timestamp"
WARNING_STALE_EVIDENCE = "stale_evidence"
WARNING_WIDE_SPREAD = "wide_spread"
WARNING_THIN_LIQUIDITY = "thin_liquidity"
WARNING_MISSING_VOLUME = "missing_volume"
WARNING_MISSING_LIQUIDITY = "missing_liquidity"
WARNING_DERIVED_BID_ASK = "derived_bid_ask"
WARNING_LAST_PRICE_ONLY = "last_price_only"
WARNING_SOURCE_TERMS_PENDING = "source_terms_pending"
WARNING_COARSE_TIMESTAMP = "coarse_timestamp"
WARNING_CALENDAR_GAP = "calendar_gap"
WARNING_CATEGORY_CONCENTRATION = "category_concentration"
WARNING_MARKET_CONCENTRATION = "market_concentration"

_EVERY_ROW_FIELDS = {
    "schema_version",
    "row_id",
    "dataset_id",
    "dataset_label",
    "profile",
    "timestamp",
    "market_id",
    "platform",
    "title",
    "market_type",
    "outcome_side",
    "last_price",
    "implied_probability",
    "evidence",
    "source_provenance",
}
_ACCEPTANCE_FIELDS = {
    "bid",
    "ask",
    "settlement",
    "paper_pnl_allowed",
    "acceptance_candidate",
}
_CALIBRATION_FIELDS = {
    "bid",
    "ask",
    "settlement",
    "paper_pnl_allowed",
    "acceptance_candidate",
    "calibration_only_reason",
}
_SETTLEMENT_FIELDS = {
    "outcome",
    "status",
    "resolved_at",
    "label_available_at",
    "source",
    "source_url",
    "resolution_rule",
    "verified_at",
    "ambiguous",
}
_SOURCE_PROVENANCE_FIELDS = {
    "source_name",
    "source_type",
    "source_url",
    "source_record_id",
    "retrieved_at",
    "exported_at",
    "raw_sha256",
    "transform_version",
    "terms_review",
    "network_used_by_builder",
    "private_or_authenticated_source",
}
_ACCEPTANCE_EVIDENCE_FIELDS = {
    "evidence_id",
    "source",
    "title",
    "summary",
    "published_at",
    "retrieved_at",
    "relevance_score",
    "credibility_score",
}
_SECRET_KEYS = {
    "api_key",
    "access_token",
    "refresh_token",
    "authorization",
    "auth_header",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "password",
    "passwd",
    "private_key",
    "secret",
}
_SECRET_VALUE_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bbearer\s+[A-Za-z0-9._-]{16,}\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    line_number: int | None = None
    row_id: str | None = None
    field: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "line_number": self.line_number,
            "row_id": self.row_id,
            "field": self.field,
        }


@dataclass(frozen=True)
class HistoricalDatasetValidationArtifacts:
    json_path: Path
    markdown_path: Path


@dataclass(frozen=True)
class HistoricalDatasetValidationResult:
    path: Path
    dataset_id: str
    profile: str
    row_count: int
    market_count: int
    resolved_binary_market_count: int
    candidate_forecast_row_count: int
    settlement_coverage_pct: float
    evidence_timestamp_coverage_pct: float
    duplicate_row_count: int
    duplicate_market_timestamp_count: int
    missing_bid_ask_count: int
    bid_exceeds_ask_count: int
    future_evidence_leakage_count: int
    missing_source_provenance_count: int
    paper_pnl_allowed: bool
    acceptance_candidate: bool
    source_names: tuple[str, ...]
    raw_export_checksums: tuple[str, ...]
    errors: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def warning_counts(self) -> dict[str, int]:
        return dict(Counter(issue.code for issue in self.warnings))

    @property
    def error_counts(self) -> dict[str, int]:
        return dict(Counter(issue.code for issue in self.errors))

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "dataset_id": self.dataset_id,
            "profile": self.profile,
            "row_count": self.row_count,
            "market_count": self.market_count,
            "resolved_binary_market_count": self.resolved_binary_market_count,
            "candidate_forecast_row_count": self.candidate_forecast_row_count,
            "settlement_coverage_pct": self.settlement_coverage_pct,
            "evidence_timestamp_coverage_pct": self.evidence_timestamp_coverage_pct,
            "duplicate_row_count": self.duplicate_row_count,
            "duplicate_market_timestamp_count": self.duplicate_market_timestamp_count,
            "missing_bid_ask_count": self.missing_bid_ask_count,
            "bid_exceeds_ask_count": self.bid_exceeds_ask_count,
            "future_evidence_leakage_count": self.future_evidence_leakage_count,
            "missing_source_provenance_count": self.missing_source_provenance_count,
            "warning_counts": self.warning_counts,
            "error_counts": self.error_counts,
            "paper_pnl_allowed": self.paper_pnl_allowed,
            "acceptance_candidate": self.acceptance_candidate,
            "source_names": list(self.source_names),
            "raw_export_checksums": list(self.raw_export_checksums),
            "errors": [issue.as_dict() for issue in self.errors],
            "warnings": [issue.as_dict() for issue in self.warnings],
            "historical_file": str(self.path),
        }


@dataclass
class _RowState:
    line_number: int
    payload: dict[str, Any]
    row_id: str | None
    dataset_id: str | None
    profile: str | None
    timestamp: datetime | None
    market_id: str | None
    platform: str | None
    market_type: str | None
    has_settlement: bool
    settlement_is_unambiguous: bool
    has_good_evidence_timestamp: bool
    is_candidate_forecast_row: bool
    missing_bid_ask: bool
    bid_exceeds_ask: bool
    future_evidence_leakage: bool
    missing_source_provenance: bool
    source_name: str | None
    raw_sha256: str | None
    paper_pnl_allowed: bool | None
    acceptance_candidate: bool | None


def validate_historical_dataset(path: str | Path) -> HistoricalDatasetValidationResult:
    dataset_path = Path(path)
    if not dataset_path.exists():
        msg = f"historical dataset file not found: {dataset_path}"
        raise ValueError(msg)
    if dataset_path.suffix.lower() != ".jsonl":
        msg = "historical dataset validator supports JSONL files only"
        raise ValueError(msg)

    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    rows: list[_RowState] = []
    for line_number, line in enumerate(dataset_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(
                _error(
                    ERROR_INVALID_JSON,
                    "JSONL line is not valid JSON.",
                    line_number=line_number,
                    field=str(exc.pos),
                )
            )
            continue
        if not isinstance(payload, dict):
            errors.append(
                _error(
                    ERROR_ROW_NOT_OBJECT,
                    "JSONL line must contain one JSON object.",
                    line_number=line_number,
                )
            )
            continue
        rows.append(_validate_row(payload, line_number, errors, warnings))

    duplicate_row_count, duplicate_market_timestamp_count = _validate_duplicates(rows, errors)
    dataset_ids = sorted({row.dataset_id for row in rows if row.dataset_id})
    profiles = sorted({row.profile for row in rows if row.profile})
    if len(dataset_ids) > 1:
        errors.append(
            _error(
                ERROR_MISSING_REQUIRED_FIELD,
                "All rows in one export must share the same dataset_id.",
                field="dataset_id",
            )
        )
    if len(profiles) > 1:
        errors.append(
            _error(
                ERROR_MISSING_REQUIRED_FIELD,
                "All rows in one export must share the same profile.",
                field="profile",
            )
        )

    dataset_id = dataset_ids[0] if len(dataset_ids) == 1 else dataset_path.stem
    profile = profiles[0] if len(profiles) == 1 else "unknown"
    markets = {row.market_id for row in rows if row.market_id}
    resolved_binary_markets = {
        row.market_id
        for row in rows
        if row.market_id
        and row.market_type == "binary_prediction"
        and row.has_settlement
        and row.settlement_is_unambiguous
    }
    candidate_rows = [row for row in rows if row.is_candidate_forecast_row]
    settled_markets = {
        row.market_id
        for row in rows
        if row.market_id and row.has_settlement and row.settlement_is_unambiguous
    }
    evidence_rows_with_timestamp = [
        row for row in candidate_rows if row.has_good_evidence_timestamp
    ]
    error_codes = Counter(issue.code for issue in errors)
    warning_codes = Counter(issue.code for issue in warnings)
    missing_bid_ask_count = sum(row.missing_bid_ask for row in rows)
    paper_flags = [row.paper_pnl_allowed for row in rows if row.paper_pnl_allowed is not None]
    acceptance_flags = [
        row.acceptance_candidate for row in rows if row.acceptance_candidate is not None
    ]
    acceptance_blocking_warning = bool(warning_codes.get(WARNING_SOURCE_TERMS_PENDING))
    paper_pnl_allowed = (
        profile == PROFILE_ACCEPTANCE
        and not errors
        and not acceptance_blocking_warning
        and bool(paper_flags)
        and all(paper_flags)
        and missing_bid_ask_count == 0
    )
    acceptance_candidate = (
        paper_pnl_allowed
        and bool(acceptance_flags)
        and all(acceptance_flags)
        and all(row.market_type == "binary_prediction" for row in rows)
    )

    return HistoricalDatasetValidationResult(
        path=dataset_path,
        dataset_id=dataset_id,
        profile=profile,
        row_count=len(rows),
        market_count=len(markets),
        resolved_binary_market_count=len(resolved_binary_markets),
        candidate_forecast_row_count=len(candidate_rows),
        settlement_coverage_pct=_coverage_pct(len(settled_markets), len(markets)),
        evidence_timestamp_coverage_pct=_coverage_pct(
            len(evidence_rows_with_timestamp),
            len(candidate_rows),
        ),
        duplicate_row_count=duplicate_row_count,
        duplicate_market_timestamp_count=duplicate_market_timestamp_count,
        missing_bid_ask_count=missing_bid_ask_count,
        bid_exceeds_ask_count=error_codes.get(ERROR_BID_EXCEEDS_ASK, 0),
        future_evidence_leakage_count=error_codes.get(ERROR_FUTURE_EVIDENCE_LEAKAGE, 0),
        missing_source_provenance_count=sum(row.missing_source_provenance for row in rows),
        paper_pnl_allowed=paper_pnl_allowed,
        acceptance_candidate=acceptance_candidate,
        source_names=tuple(sorted({row.source_name for row in rows if row.source_name})),
        raw_export_checksums=tuple(sorted({row.raw_sha256 for row in rows if row.raw_sha256})),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def write_historical_validation_reports(
    result: HistoricalDatasetValidationResult,
    output_dir: str | Path,
) -> HistoricalDatasetValidationArtifacts:
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    safe_dataset_id = _safe_filename(result.dataset_id)
    json_path = report_dir / f"{safe_dataset_id}.validation.json"
    markdown_path = report_dir / f"{safe_dataset_id}_audit.md"
    json_path.write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown_report(result), encoding="utf-8")
    return HistoricalDatasetValidationArtifacts(json_path=json_path, markdown_path=markdown_path)


def _validate_row(
    payload: dict[str, Any],
    line_number: int,
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
) -> _RowState:
    row_id = _optional_text(payload.get("row_id"))
    for field in sorted(_EVERY_ROW_FIELDS):
        if field not in payload or _is_blank(payload[field]):
            errors.append(
                _error(
                    ERROR_MISSING_REQUIRED_FIELD,
                    f"Missing required field: {field}.",
                    line_number=line_number,
                    row_id=row_id,
                    field=field,
                )
            )

    schema_version = _optional_text(payload.get("schema_version"))
    if schema_version is not None and schema_version != SCHEMA_VERSION:
        errors.append(
            _error(
                ERROR_INVALID_SCHEMA_VERSION,
                f"Unsupported schema_version: {schema_version}.",
                line_number=line_number,
                row_id=row_id,
                field="schema_version",
            )
        )

    profile = _optional_text(payload.get("profile"))
    if profile == PROFILE_ACCEPTANCE:
        for field in sorted(_ACCEPTANCE_FIELDS):
            if field not in payload or _is_blank(payload[field]):
                errors.append(
                    _error(
                        ERROR_MISSING_REQUIRED_FIELD,
                        f"Missing required acceptance field: {field}.",
                        line_number=line_number,
                        row_id=row_id,
                        field=field,
                    )
                )
    elif profile == PROFILE_CALIBRATION_ONLY:
        for field in sorted(_CALIBRATION_FIELDS):
            if field not in payload or (
                field not in {"bid", "ask"} and _is_blank(payload[field])
            ):
                errors.append(
                    _error(
                        ERROR_MISSING_REQUIRED_FIELD,
                        f"Missing required calibration-only field: {field}.",
                        line_number=line_number,
                        row_id=row_id,
                        field=field,
                    )
                )
    elif profile is not None:
        errors.append(
            _error(
                ERROR_MISSING_REQUIRED_FIELD,
                "profile must be acceptance_candidate or calibration_only_last_price.",
                line_number=line_number,
                row_id=row_id,
                field="profile",
            )
        )

    timestamp = _parse_timestamp_field(payload.get("timestamp"), "timestamp", line_number, row_id, errors)
    _validate_date_alias(payload, timestamp, line_number, row_id, errors)
    _validate_probability(payload.get("last_price"), "last_price", line_number, row_id, errors)
    _validate_probability(
        payload.get("implied_probability"),
        "implied_probability",
        line_number,
        row_id,
        errors,
    )
    bid = _validate_probability(payload.get("bid"), "bid", line_number, row_id, errors)
    ask = _validate_probability(payload.get("ask"), "ask", line_number, row_id, errors)
    missing_bid_ask = payload.get("bid") is None or payload.get("ask") is None
    bid_exceeds_ask = False
    if profile == PROFILE_ACCEPTANCE and missing_bid_ask:
        errors.append(
            _error(
                ERROR_MISSING_BID_ASK_FOR_ACCEPTANCE,
                "acceptance_candidate rows require point-in-time bid and ask.",
                line_number=line_number,
                row_id=row_id,
                field="bid/ask",
            )
        )
    if bid is not None and ask is not None and bid > ask:
        bid_exceeds_ask = True
        errors.append(
            _error(
                ERROR_BID_EXCEEDS_ASK,
                "bid must be less than or equal to ask.",
                line_number=line_number,
                row_id=row_id,
                field="bid/ask",
            )
        )
    if bid is not None and ask is not None and ask - bid > 0.10:
        warnings.append(
            _warning(
                WARNING_WIDE_SPREAD,
                "bid/ask spread is wider than the configured quality threshold.",
                line_number=line_number,
                row_id=row_id,
                field="bid/ask",
            )
        )

    market_type = _optional_text(payload.get("market_type"))
    if profile == PROFILE_ACCEPTANCE and market_type != "binary_prediction":
        errors.append(
            _error(
                ERROR_UNSUPPORTED_MARKET_TYPE,
                "acceptance_candidate rows must use market_type=binary_prediction.",
                line_number=line_number,
                row_id=row_id,
                field="market_type",
            )
        )
    if _optional_text(payload.get("outcome_side")) not in (None, "yes"):
        errors.append(
            _error(
                ERROR_INVALID_PROBABILITY,
                "outcome_side must be yes for Phase 7G price fields.",
                line_number=line_number,
                row_id=row_id,
                field="outcome_side",
            )
        )

    source_name, raw_sha256, missing_source_provenance = _validate_source_provenance(
        payload.get("source_provenance"),
        line_number,
        row_id,
        profile,
        errors,
        warnings,
    )
    has_settlement, settlement_unambiguous, label_available_at = _validate_settlement(
        payload.get("settlement"),
        line_number,
        row_id,
        profile,
        errors,
    )
    status = _optional_text(payload.get("market_status_at_timestamp"))
    is_settlement_row = payload.get("settlement_outcome") in {"yes", "no"} or status == "settled"
    is_candidate_forecast_row = bool(
        timestamp is not None
        and (label_available_at is None or timestamp < label_available_at)
        and not is_settlement_row
    )
    if (
        timestamp is not None
        and label_available_at is not None
        and timestamp >= label_available_at
        and not is_settlement_row
    ):
        errors.append(
            _error(
                ERROR_POST_SETTLEMENT_FORECAST_ROW,
                "Forecast row timestamp is after outcome label availability.",
                line_number=line_number,
                row_id=row_id,
                field="timestamp",
            )
        )

    evidence_timestamp_ok, future_evidence = _validate_evidence(
        payload.get("evidence"),
        timestamp,
        line_number,
        row_id,
        profile,
        errors,
        warnings,
    )
    _validate_nonnegative_warning(payload, "volume", WARNING_MISSING_VOLUME, line_number, row_id, warnings)
    _validate_nonnegative_warning(
        payload,
        "liquidity",
        WARNING_MISSING_LIQUIDITY,
        line_number,
        row_id,
        warnings,
    )
    if _optional_float(payload.get("liquidity")) is not None and float(payload["liquidity"]) < 100:
        warnings.append(
            _warning(
                WARNING_THIN_LIQUIDITY,
                "liquidity is below the quality-audit threshold.",
                line_number=line_number,
                row_id=row_id,
                field="liquidity",
            )
        )
    if profile == PROFILE_CALIBRATION_ONLY:
        warnings.append(
            _warning(
                WARNING_LAST_PRICE_ONLY,
                "calibration_only_last_price rows cannot support paper PnL.",
                line_number=line_number,
                row_id=row_id,
            )
        )
        if payload.get("paper_pnl_allowed") is not False:
            errors.append(
                _error(
                    ERROR_MISSING_REQUIRED_FIELD,
                    "calibration_only_last_price rows must set paper_pnl_allowed=false.",
                    line_number=line_number,
                    row_id=row_id,
                    field="paper_pnl_allowed",
                )
            )
        if payload.get("acceptance_candidate") is not False:
            errors.append(
                _error(
                    ERROR_MISSING_REQUIRED_FIELD,
                    "calibration_only_last_price rows must set acceptance_candidate=false.",
                    line_number=line_number,
                    row_id=row_id,
                    field="acceptance_candidate",
                )
            )
    if _secret_path := _find_secret_like_path(payload):
        errors.append(
            _error(
                ERROR_SECRET_PATTERN_DETECTED,
                f"Secret-like material detected at {_secret_path}.",
                line_number=line_number,
                row_id=row_id,
                field=_secret_path,
            )
        )

    return _RowState(
        line_number=line_number,
        payload=payload,
        row_id=row_id,
        dataset_id=_optional_text(payload.get("dataset_id")),
        profile=profile,
        timestamp=timestamp,
        market_id=_optional_text(payload.get("market_id")),
        platform=_optional_text(payload.get("platform")),
        market_type=market_type,
        has_settlement=has_settlement,
        settlement_is_unambiguous=settlement_unambiguous,
        has_good_evidence_timestamp=evidence_timestamp_ok,
        is_candidate_forecast_row=is_candidate_forecast_row,
        missing_bid_ask=missing_bid_ask,
        bid_exceeds_ask=bid_exceeds_ask,
        future_evidence_leakage=future_evidence,
        missing_source_provenance=missing_source_provenance,
        source_name=source_name,
        raw_sha256=raw_sha256,
        paper_pnl_allowed=payload.get("paper_pnl_allowed")
        if isinstance(payload.get("paper_pnl_allowed"), bool)
        else None,
        acceptance_candidate=payload.get("acceptance_candidate")
        if isinstance(payload.get("acceptance_candidate"), bool)
        else None,
    )


def _validate_source_provenance(
    value: object,
    line_number: int,
    row_id: str | None,
    profile: str | None,
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
) -> tuple[str | None, str | None, bool]:
    if not isinstance(value, dict):
        errors.append(
            _error(
                ERROR_MISSING_SOURCE_PROVENANCE,
                "source_provenance must be present and must be an object.",
                line_number=line_number,
                row_id=row_id,
                field="source_provenance",
            )
        )
        return None, None, True
    missing = False
    for field in sorted(_SOURCE_PROVENANCE_FIELDS):
        if field not in value or (field != "raw_sha256" and _is_blank(value[field])):
            missing = True
            errors.append(
                _error(
                    ERROR_MISSING_SOURCE_PROVENANCE,
                    f"source_provenance is missing required field: {field}.",
                    line_number=line_number,
                    row_id=row_id,
                    field=f"source_provenance.{field}",
                )
            )
    _parse_timestamp_field(
        value.get("retrieved_at"),
        "source_provenance.retrieved_at",
        line_number,
        row_id,
        errors,
    )
    _parse_timestamp_field(
        value.get("exported_at"),
        "source_provenance.exported_at",
        line_number,
        row_id,
        errors,
    )
    terms_review = _optional_text(value.get("terms_review"))
    if terms_review == "blocked":
        errors.append(
            _error(
                ERROR_SOURCE_TERMS_BLOCKED,
                "Source terms review blocks this local research export.",
                line_number=line_number,
                row_id=row_id,
                field="source_provenance.terms_review",
            )
        )
    elif terms_review != TERMS_REVIEWED:
        warnings.append(
            _warning(
                WARNING_SOURCE_TERMS_PENDING,
                "Source terms review is not marked reviewed_public_research_local_only.",
                line_number=line_number,
                row_id=row_id,
                field="source_provenance.terms_review",
            )
        )
    if value.get("private_or_authenticated_source") is not False:
        issue = _error if profile == PROFILE_ACCEPTANCE else _warning
        errors_or_warnings = errors if profile == PROFILE_ACCEPTANCE else warnings
        errors_or_warnings.append(
            issue(
                ERROR_PRIVATE_SOURCE_DETECTED
                if profile == PROFILE_ACCEPTANCE
                else WARNING_SOURCE_TERMS_PENDING,
                "private_or_authenticated_source must be false for acceptance.",
                line_number=line_number,
                row_id=row_id,
                field="source_provenance.private_or_authenticated_source",
            )
        )
    return (
        _optional_text(value.get("source_name")),
        _optional_text(value.get("raw_sha256")),
        missing,
    )


def _validate_settlement(
    value: object,
    line_number: int,
    row_id: str | None,
    profile: str | None,
    errors: list[ValidationIssue],
) -> tuple[bool, bool, datetime | None]:
    if not isinstance(value, dict):
        errors.append(
            _error(
                ERROR_MISSING_SETTLEMENT_FOR_SCORED_MARKET,
                "settlement object is required for scored rows.",
                line_number=line_number,
                row_id=row_id,
                field="settlement",
            )
        )
        return False, False, None
    for field in sorted(_SETTLEMENT_FIELDS):
        if field not in value or _is_blank(value[field]):
            errors.append(
                _error(
                    ERROR_MISSING_SETTLEMENT_FOR_SCORED_MARKET,
                    f"settlement is missing required field: {field}.",
                    line_number=line_number,
                    row_id=row_id,
                    field=f"settlement.{field}",
                )
            )
    outcome = _optional_text(value.get("outcome"))
    if outcome not in {"yes", "no"}:
        errors.append(
            _error(
                ERROR_AMBIGUOUS_SETTLEMENT,
                "settlement.outcome must be yes or no.",
                line_number=line_number,
                row_id=row_id,
                field="settlement.outcome",
            )
        )
    ambiguous = value.get("ambiguous")
    if ambiguous is not False or outcome not in {"yes", "no"}:
        errors.append(
            _error(
                ERROR_AMBIGUOUS_SETTLEMENT,
                "Ambiguous, disputed, or unsupported settlement blocks acceptance.",
                line_number=line_number,
                row_id=row_id,
                field="settlement.ambiguous",
            )
        )
    resolved_at = _parse_timestamp_field(
        value.get("resolved_at"),
        "settlement.resolved_at",
        line_number,
        row_id,
        errors,
    )
    label_available_at = _parse_timestamp_field(
        value.get("label_available_at"),
        "settlement.label_available_at",
        line_number,
        row_id,
        errors,
    )
    _parse_timestamp_field(
        value.get("verified_at"),
        "settlement.verified_at",
        line_number,
        row_id,
        errors,
    )
    if profile == PROFILE_ACCEPTANCE and resolved_at is None:
        errors.append(
            _error(
                ERROR_MISSING_SETTLEMENT_FOR_SCORED_MARKET,
                "acceptance_candidate rows require settlement.resolved_at.",
                line_number=line_number,
                row_id=row_id,
                field="settlement.resolved_at",
            )
        )
    return True, ambiguous is False and outcome in {"yes", "no"}, label_available_at


def _validate_evidence(
    value: object,
    row_timestamp: datetime | None,
    line_number: int,
    row_id: str | None,
    profile: str | None,
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
) -> tuple[bool, bool]:
    if not isinstance(value, list):
        errors.append(
            _error(
                ERROR_MISSING_REQUIRED_FIELD,
                "evidence must be a list.",
                line_number=line_number,
                row_id=row_id,
                field="evidence",
            )
        )
        return False, False
    if not value:
        warnings.append(
            _warning(
                WARNING_MISSING_EVIDENCE,
                "Row has no evidence records.",
                line_number=line_number,
                row_id=row_id,
                field="evidence",
            )
        )
        return False, False

    source_labels: set[str] = set()
    has_good_timestamp = False
    future_evidence = False
    for index, item in enumerate(value):
        field_prefix = f"evidence[{index}]"
        if not isinstance(item, dict):
            errors.append(
                _error(
                    ERROR_MISSING_REQUIRED_FIELD,
                    "evidence items must be objects.",
                    line_number=line_number,
                    row_id=row_id,
                    field=field_prefix,
                )
            )
            continue
        for field in sorted(_ACCEPTANCE_EVIDENCE_FIELDS):
            if profile == PROFILE_ACCEPTANCE and (field not in item or _is_blank(item[field])):
                code = (
                    ERROR_EVIDENCE_TIMESTAMP_MISSING_FOR_ACCEPTANCE
                    if field == "published_at"
                    else ERROR_MISSING_REQUIRED_FIELD
                )
                errors.append(
                    _error(
                        code,
                        f"acceptance evidence is missing required field: {field}.",
                        line_number=line_number,
                        row_id=row_id,
                        field=f"{field_prefix}.{field}",
                    )
                )
        source = _optional_text(item.get("source"))
        if source:
            source_labels.add(source)
        _validate_probability(
            item.get("relevance_score"),
            f"{field_prefix}.relevance_score",
            line_number,
            row_id,
            errors,
        )
        _validate_probability(
            item.get("credibility_score"),
            f"{field_prefix}.credibility_score",
            line_number,
            row_id,
            errors,
        )
        _parse_timestamp_field(
            item.get("retrieved_at"),
            f"{field_prefix}.retrieved_at",
            line_number,
            row_id,
            errors,
            required=profile == PROFILE_ACCEPTANCE,
        )
        published_at = _parse_timestamp_field(
            item.get("published_at"),
            f"{field_prefix}.published_at",
            line_number,
            row_id,
            errors,
            required=False,
        )
        if published_at is None:
            if profile == PROFILE_ACCEPTANCE:
                errors.append(
                    _error(
                        ERROR_EVIDENCE_TIMESTAMP_MISSING_FOR_ACCEPTANCE,
                        "Evidence published_at is required for acceptance.",
                        line_number=line_number,
                        row_id=row_id,
                        field=f"{field_prefix}.published_at",
                    )
                )
            else:
                warnings.append(
                    _warning(
                        WARNING_TIMESTAMP_UNKNOWN,
                        "Evidence published_at is missing or unknown.",
                        line_number=line_number,
                        row_id=row_id,
                        field=f"{field_prefix}.published_at",
                    )
                )
            continue
        if _looks_date_only(item.get("published_at")):
            warnings.append(
                _warning(
                    WARNING_DATE_ONLY_EVIDENCE_TIMESTAMP,
                    "Evidence timestamp appears to be date-only.",
                    line_number=line_number,
                    row_id=row_id,
                    field=f"{field_prefix}.published_at",
                )
            )
        if row_timestamp is not None and published_at > row_timestamp:
            future_evidence = True
            errors.append(
                _error(
                    ERROR_FUTURE_EVIDENCE_LEAKAGE,
                    "Evidence published_at is after the row timestamp.",
                    line_number=line_number,
                    row_id=row_id,
                    field=f"{field_prefix}.published_at",
                )
            )
        elif row_timestamp is not None:
            has_good_timestamp = True
    if len(source_labels) == 1:
        warnings.append(
            _warning(
                WARNING_SINGLE_SOURCE_EVIDENCE,
                "Only one distinct evidence source is present.",
                line_number=line_number,
                row_id=row_id,
                field="evidence",
            )
        )
    return has_good_timestamp, future_evidence


def _validate_duplicates(
    rows: list[_RowState],
    errors: list[ValidationIssue],
) -> tuple[int, int]:
    duplicate_row_count = 0
    seen_rows: dict[str, _RowState] = {}
    for row in rows:
        if not row.row_id:
            continue
        if row.row_id in seen_rows:
            duplicate_row_count += 1
            errors.append(
                _error(
                    ERROR_DUPLICATE_ROW_ID,
                    f"Duplicate row_id also appears on line {seen_rows[row.row_id].line_number}.",
                    line_number=row.line_number,
                    row_id=row.row_id,
                    field="row_id",
                )
            )
        else:
            seen_rows[row.row_id] = row

    duplicate_market_timestamp_count = 0
    seen_market_timestamps: dict[tuple[str, str, datetime], _RowState] = {}
    for row in rows:
        if not (row.platform and row.market_id and row.timestamp):
            continue
        key = (row.platform, row.market_id, row.timestamp)
        if key in seen_market_timestamps:
            duplicate_market_timestamp_count += 1
            errors.append(
                _error(
                    ERROR_DUPLICATE_MARKET_TIMESTAMP,
                    "Duplicate platform + market_id + timestamp row.",
                    line_number=row.line_number,
                    row_id=row.row_id,
                    field="platform/market_id/timestamp",
                )
            )
        else:
            seen_market_timestamps[key] = row
    return duplicate_row_count, duplicate_market_timestamp_count


def _validate_date_alias(
    payload: dict[str, Any],
    timestamp: datetime | None,
    line_number: int,
    row_id: str | None,
    errors: list[ValidationIssue],
) -> None:
    if "date" not in payload or timestamp is None:
        return
    try:
        parsed_date = datetime.fromisoformat(str(payload["date"])).date()
    except ValueError:
        errors.append(
            _error(
                ERROR_DATE_TIMESTAMP_MISMATCH,
                "date alias must use YYYY-MM-DD and match timestamp date.",
                line_number=line_number,
                row_id=row_id,
                field="date",
            )
        )
        return
    if parsed_date != timestamp.date():
        errors.append(
            _error(
                ERROR_DATE_TIMESTAMP_MISMATCH,
                "date alias does not match timestamp date.",
                line_number=line_number,
                row_id=row_id,
                field="date",
            )
        )


def _validate_nonnegative_warning(
    payload: dict[str, Any],
    field: str,
    warning_code: str,
    line_number: int,
    row_id: str | None,
    warnings: list[ValidationIssue],
) -> None:
    value = payload.get(field)
    if value is None:
        warnings.append(
            _warning(
                warning_code,
                f"{field} is missing.",
                line_number=line_number,
                row_id=row_id,
                field=field,
            )
        )
        return
    parsed = _optional_float(value)
    if parsed is None or parsed < 0:
        warnings.append(
            _warning(
                warning_code,
                f"{field} is missing or invalid.",
                line_number=line_number,
                row_id=row_id,
                field=field,
            )
        )


def _validate_probability(
    value: object,
    field: str,
    line_number: int,
    row_id: str | None,
    errors: list[ValidationIssue],
) -> float | None:
    if value is None:
        return None
    parsed = _optional_float(value)
    if parsed is None or not 0 <= parsed <= 1:
        errors.append(
            _error(
                ERROR_INVALID_PROBABILITY,
                f"{field} must be a number in [0, 1].",
                line_number=line_number,
                row_id=row_id,
                field=field,
            )
        )
        return None
    return parsed


def _parse_timestamp_field(
    value: object,
    field: str,
    line_number: int,
    row_id: str | None,
    errors: list[ValidationIssue],
    *,
    required: bool = True,
) -> datetime | None:
    if value is None or value == "":
        if required:
            errors.append(
                _error(
                    ERROR_INVALID_TIMESTAMP,
                    f"{field} is required and must be timezone-aware ISO 8601.",
                    line_number=line_number,
                    row_id=row_id,
                    field=field,
                )
            )
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        errors.append(
            _error(
                ERROR_INVALID_TIMESTAMP,
                f"{field} must be a timezone-aware ISO 8601 timestamp.",
                line_number=line_number,
                row_id=row_id,
                field=field,
            )
        )
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        errors.append(
            _error(
                ERROR_INVALID_TIMESTAMP,
                f"{field} must include a timezone offset.",
                line_number=line_number,
                row_id=row_id,
                field=field,
            )
        )
        return None
    return parsed


def _find_secret_like_path(value: object, path: str = "$") -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_path = f"{path}.{key}"
            if str(key).lower() in _SECRET_KEYS and item not in (None, "", False):
                return key_path
            found = _find_secret_like_path(item, key_path)
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = _find_secret_like_path(item, f"{path}[{index}]")
            if found:
                return found
    elif isinstance(value, str):
        for pattern in _SECRET_VALUE_PATTERNS:
            if pattern.search(value):
                return path
    return None


def _render_markdown_report(result: HistoricalDatasetValidationResult) -> str:
    lines = [
        "# Historical Dataset Validation Audit",
        "",
        f"Dataset: `{result.dataset_id}`",
        f"Profile: `{result.profile}`",
        f"Valid: {result.valid}",
        f"Acceptance candidate: {result.acceptance_candidate}",
        f"Paper PnL allowed: {result.paper_pnl_allowed}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| row_count | {result.row_count} |",
        f"| market_count | {result.market_count} |",
        f"| resolved_binary_market_count | {result.resolved_binary_market_count} |",
        f"| candidate_forecast_row_count | {result.candidate_forecast_row_count} |",
        f"| settlement_coverage_pct | {result.settlement_coverage_pct} |",
        f"| evidence_timestamp_coverage_pct | {result.evidence_timestamp_coverage_pct} |",
        f"| duplicate_row_count | {result.duplicate_row_count} |",
        f"| duplicate_market_timestamp_count | {result.duplicate_market_timestamp_count} |",
        f"| missing_bid_ask_count | {result.missing_bid_ask_count} |",
        f"| bid_exceeds_ask_count | {result.bid_exceeds_ask_count} |",
        f"| future_evidence_leakage_count | {result.future_evidence_leakage_count} |",
        f"| missing_source_provenance_count | {result.missing_source_provenance_count} |",
        "",
        "## Errors",
        "",
        *_issue_lines(result.errors),
        "",
        "## Warnings",
        "",
        *_issue_lines(result.warnings),
        "",
        "## Source Names",
        "",
        *(f"- `{name}`" for name in result.source_names),
    ]
    return "\n".join(lines) + "\n"


def _issue_lines(issues: tuple[ValidationIssue, ...]) -> list[str]:
    if not issues:
        return ["_None._"]
    lines = ["| Code | Line | Field | Message |", "| --- | ---: | --- | --- |"]
    for issue in issues:
        line = "" if issue.line_number is None else str(issue.line_number)
        field = "" if issue.field is None else issue.field
        lines.append(f"| `{issue.code}` | {line} | `{field}` | {issue.message} |")
    return lines


def _error(
    code: str,
    message: str,
    *,
    line_number: int | None = None,
    row_id: str | None = None,
    field: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity="error",
        message=message,
        line_number=line_number,
        row_id=row_id,
        field=field,
    )


def _warning(
    code: str,
    message: str,
    *,
    line_number: int | None = None,
    row_id: str | None = None,
    field: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity="warning",
        message=message,
        line_number=line_number,
        row_id=row_id,
        field=field,
    )


def _coverage_pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_blank(value: object) -> bool:
    return value is None or value == "" or value == []


def _looks_date_only(value: object) -> bool:
    return isinstance(value, str) and len(value) == 10 and value.count("-") == 2


def _safe_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "historical_dataset_validation"
