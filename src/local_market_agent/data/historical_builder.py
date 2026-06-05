from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from hashlib import sha256
from pathlib import Path
from typing import Any

from local_market_agent.data.historical_validator import (
    PROFILE_ACCEPTANCE,
    PROFILE_CALIBRATION_ONLY,
    SCHEMA_VERSION,
    HistoricalDatasetValidationArtifacts,
    HistoricalDatasetValidationResult,
    validate_historical_dataset,
    write_historical_validation_reports,
)

BUILDER_VERSION = "phase7g.manual_builder.v1"
SUPPORTED_INPUT_FORMATS = {"csv", "json", "jsonl"}


@dataclass(frozen=True)
class HistoricalDatasetBuildResult:
    dataset_id: str
    output_jsonl: Path
    manifest_path: Path
    row_count: int
    market_count: int
    profile: str
    validation_result: HistoricalDatasetValidationResult | None = None
    validation_artifacts: HistoricalDatasetValidationArtifacts | None = None

    @property
    def validation_valid(self) -> bool | None:
        if self.validation_result is None:
            return None
        return self.validation_result.valid

    @property
    def error_count(self) -> int | None:
        if self.validation_result is None:
            return None
        return self.validation_result.error_count

    @property
    def warning_count(self) -> int | None:
        if self.validation_result is None:
            return None
        return self.validation_result.warning_count

    def as_summary(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "output_jsonl": str(self.output_jsonl),
            "manifest_path": str(self.manifest_path),
            "validation_json_path": str(self.validation_artifacts.json_path)
            if self.validation_artifacts is not None
            else None,
            "validation_markdown_path": str(self.validation_artifacts.markdown_path)
            if self.validation_artifacts is not None
            else None,
            "row_count": self.row_count,
            "market_count": self.market_count,
            "profile": self.profile,
            "validation_valid": self.validation_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }


def build_historical_dataset(
    input_path: str | Path,
    *,
    input_format: str,
    profile: str,
    output_dir: str | Path,
    report_dir: str | Path | None = None,
    validate: bool = True,
) -> HistoricalDatasetBuildResult:
    source_path = Path(input_path)
    if not source_path.exists():
        msg = f"manual input file not found: {source_path}"
        raise ValueError(msg)
    normalized_format = input_format.strip().lower()
    if normalized_format not in SUPPORTED_INPUT_FORMATS:
        msg = "input_format must be csv, json, or jsonl"
        raise ValueError(msg)
    normalized_profile = _normalize_profile(profile)
    manual_rows, top_level_defaults = _load_manual_rows(source_path, normalized_format)
    if not manual_rows:
        msg = "manual input contains no rows"
        raise ValueError(msg)

    dataset_id = _resolve_dataset_id(
        manual_rows,
        top_level_defaults=top_level_defaults,
        input_path=source_path,
        profile=normalized_profile,
    )
    dataset_label = _resolve_dataset_label(
        manual_rows,
        top_level_defaults=top_level_defaults,
        profile=normalized_profile,
    )
    phase7g_rows = [
        _build_phase7g_row(
            row,
            row_index=index,
            dataset_id=dataset_id,
            dataset_label=dataset_label,
            profile=normalized_profile,
        )
        for index, row in enumerate(manual_rows, start=1)
    ]
    phase7g_rows.sort(key=_row_sort_key)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_jsonl = output_path / f"{dataset_id}.jsonl"
    output_jsonl.write_text(
        "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in phase7g_rows)
        + "\n",
        encoding="utf-8",
    )

    manifest_path = output_path / f"{dataset_id}.manifest.json"
    market_count = len({row["market_id"] for row in phase7g_rows if row.get("market_id")})
    manifest = _build_manifest(
        dataset_id=dataset_id,
        dataset_label=dataset_label,
        profile=normalized_profile,
        input_path=source_path,
        input_format=normalized_format,
        output_jsonl=output_jsonl,
        row_count=len(phase7g_rows),
        market_count=market_count,
    )
    validation_result: HistoricalDatasetValidationResult | None = None
    validation_artifacts: HistoricalDatasetValidationArtifacts | None = None
    if validate:
        validation_result = validate_historical_dataset(output_jsonl)
        validation_artifacts = write_historical_validation_reports(
            validation_result,
            report_dir or output_path,
        )
        manifest["validation"] = {
            "valid": validation_result.valid,
            "error_count": validation_result.error_count,
            "warning_count": validation_result.warning_count,
            "json_path": str(validation_artifacts.json_path),
            "markdown_path": str(validation_artifacts.markdown_path),
        }
    else:
        manifest["validation"] = None
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return HistoricalDatasetBuildResult(
        dataset_id=dataset_id,
        output_jsonl=output_jsonl,
        manifest_path=manifest_path,
        row_count=len(phase7g_rows),
        market_count=market_count,
        profile=normalized_profile,
        validation_result=validation_result,
        validation_artifacts=validation_artifacts,
    )


def _load_manual_rows(
    path: Path,
    input_format: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if input_format == "csv":
        with path.open(newline="", encoding="utf-8") as handle:
            rows = [_clean_manual_row(row) for row in csv.DictReader(handle)]
        return rows, {}
    if input_format == "jsonl":
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                msg = f"manual JSONL line {line_number} is invalid JSON"
                raise ValueError(msg) from exc
            if not isinstance(payload, dict):
                msg = f"manual JSONL line {line_number} must be an object"
                raise ValueError(msg)
            rows.append(_clean_manual_row(payload))
        return rows, {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = "manual JSON input is invalid JSON"
        raise ValueError(msg) from exc
    if isinstance(payload, list):
        return [_clean_manual_row(row) for row in payload], {}
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        defaults = {key: value for key, value in payload.items() if key != "rows"}
        rows = []
        for row in payload["rows"]:
            if not isinstance(row, dict):
                msg = "manual JSON rows must be objects"
                raise ValueError(msg)
            merged = {**defaults, **row}
            rows.append(_clean_manual_row(merged))
        return rows, _clean_manual_row(defaults)
    msg = "manual JSON input must be a list of rows or an object with a rows array"
    raise ValueError(msg)


def _build_phase7g_row(
    row: dict[str, Any],
    *,
    row_index: int,
    dataset_id: str,
    dataset_label: str,
    profile: str,
) -> dict[str, Any]:
    timestamp = _resolve_timestamp(row, row_index)
    market_id = _required_text(row, "market_id", row_index)
    platform = _required_text(row, "platform", row_index)
    title = _required_text(row, "title", row_index)
    output: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "dataset_label": dataset_label,
        "profile": profile,
        "timestamp": timestamp,
        "date": _coerce_text(row.get("date")) or timestamp[:10],
        "market_id": market_id,
        "platform": platform,
        "title": title,
        "market_type": _coerce_text(row.get("market_type")) or "binary_prediction",
        "outcome_side": _coerce_text(row.get("outcome_side")) or "yes",
        "last_price": _required_float(row, "last_price", row_index),
        "implied_probability": _required_float(row, "implied_probability", row_index),
        "liquidity": _optional_float(row.get("liquidity")),
        "volume": _optional_float(row.get("volume")),
        "market_status_at_timestamp": _coerce_text(row.get("market_status_at_timestamp"))
        or "open",
        "evidence": _build_evidence(row, dataset_id=dataset_id, row_index=row_index),
    }
    _copy_optional(output, row, ("category", "split", "market_url", "series_id"))
    if metadata := _json_object(row.get("metadata"), "metadata", row_index):
        output["metadata"] = metadata

    if profile == PROFILE_CALIBRATION_ONLY:
        output["bid"] = None
        output["ask"] = None
        output["paper_pnl_allowed"] = False
        output["acceptance_candidate"] = False
        output["calibration_only_reason"] = (
            _coerce_text(row.get("calibration_only_reason"))
            or "missing_point_in_time_bid_ask"
        )
    else:
        bid = _optional_float(row.get("bid"))
        ask = _optional_float(row.get("ask"))
        output["bid"] = bid
        output["ask"] = ask
        has_bid_ask = bid is not None and ask is not None
        output["paper_pnl_allowed"] = bool(has_bid_ask)
        output["acceptance_candidate"] = bool(has_bid_ask)

    if settlement := _build_settlement(row, row_index):
        output["settlement"] = settlement
    if source_provenance := _build_source_provenance(row, row_index):
        output["source_provenance"] = source_provenance

    output["row_id"] = _coerce_text(row.get("row_id")) or _stable_id(
        "row",
        {
            "dataset_id": dataset_id,
            "timestamp": timestamp,
            "platform": platform,
            "market_id": market_id,
            "source_record_id": source_provenance.get("source_record_id")
            if source_provenance
            else None,
            "row_index": row_index,
        },
    )
    return output


def _build_evidence(
    row: dict[str, Any],
    *,
    dataset_id: str,
    row_index: int,
) -> list[dict[str, Any]]:
    nested = row.get("evidence")
    if isinstance(nested, list):
        evidence_items = [dict(item) for item in nested if isinstance(item, dict)]
    else:
        evidence_json = row.get("evidence_json")
        if evidence_json not in (None, ""):
            parsed = _json_value(evidence_json, "evidence_json", row_index)
            if not isinstance(parsed, list):
                msg = f"manual row {row_index} evidence_json must be a list"
                raise ValueError(msg)
            evidence_items = [dict(item) for item in parsed if isinstance(item, dict)]
        elif _has_any(row, "evidence_"):
            evidence_items = [
                {
                    "evidence_id": _coerce_text(row.get("evidence_id")),
                    "source": _coerce_text(row.get("evidence_source")),
                    "title": _coerce_text(row.get("evidence_title")),
                    "url": _coerce_text(row.get("evidence_url")),
                    "published_at": _coerce_text(row.get("evidence_published_at")),
                    "retrieved_at": _coerce_text(row.get("evidence_retrieved_at")),
                    "summary": _coerce_text(row.get("evidence_summary")),
                    "relevance_score": _optional_float(row.get("evidence_relevance_score")),
                    "credibility_score": _optional_float(row.get("evidence_credibility_score")),
                    "metadata": _json_object(
                        row.get("evidence_metadata"),
                        "evidence_metadata",
                        row_index,
                    )
                    or _json_object(
                        row.get("evidence_metadata_json"),
                        "evidence_metadata_json",
                        row_index,
                    )
                    or {},
                }
            ]
        else:
            evidence_items = []
    for index, item in enumerate(evidence_items, start=1):
        item["evidence_id"] = _coerce_text(item.get("evidence_id")) or _stable_id(
            "ev",
            {
                "dataset_id": dataset_id,
                "row_index": row_index,
                "evidence_index": index,
                "source": item.get("source"),
                "title": item.get("title"),
                "published_at": item.get("published_at"),
            },
        )
        if "metadata" not in item or item["metadata"] is None:
            item["metadata"] = {}
    return [_strip_none(item) for item in evidence_items]


def _build_settlement(row: dict[str, Any], row_index: int) -> dict[str, Any] | None:
    nested = row.get("settlement")
    if isinstance(nested, dict):
        return dict(nested)
    if row.get("settlement_json") not in (None, ""):
        parsed = _json_value(row["settlement_json"], "settlement_json", row_index)
        if not isinstance(parsed, dict):
            msg = f"manual row {row_index} settlement_json must be an object"
            raise ValueError(msg)
        return parsed
    if not _has_any(row, "settlement_"):
        return None
    return _strip_none(
        {
            "outcome": _coerce_text(row.get("settlement_outcome")),
            "status": _coerce_text(row.get("settlement_status")),
            "resolved_at": _coerce_text(row.get("settlement_resolved_at")),
            "label_available_at": _coerce_text(row.get("settlement_label_available_at")),
            "source": _coerce_text(row.get("settlement_source")),
            "source_url": _coerce_text(row.get("settlement_source_url")),
            "resolution_rule": _coerce_text(row.get("settlement_resolution_rule")),
            "verified_at": _coerce_text(row.get("settlement_verified_at")),
            "ambiguous": _optional_bool(row.get("settlement_ambiguous")),
            "method": _coerce_text(row.get("settlement_method")),
            "settlement_price": _optional_float(row.get("settlement_price")),
            "notes": _coerce_text(row.get("settlement_notes")),
            "raw_outcome_value": _coerce_text(row.get("settlement_raw_outcome_value")),
        }
    )


def _build_source_provenance(row: dict[str, Any], row_index: int) -> dict[str, Any] | None:
    nested = row.get("source_provenance")
    if isinstance(nested, dict):
        return dict(nested)
    if row.get("source_provenance_json") not in (None, ""):
        parsed = _json_value(row["source_provenance_json"], "source_provenance_json", row_index)
        if not isinstance(parsed, dict):
            msg = f"manual row {row_index} source_provenance_json must be an object"
            raise ValueError(msg)
        return parsed
    if not _has_any(row, "source_"):
        return None
    return _strip_none(
        {
            "source_name": _coerce_text(row.get("source_name")),
            "source_type": _coerce_text(row.get("source_type")),
            "source_url": _coerce_text(row.get("source_url")),
            "source_record_id": _coerce_text(row.get("source_record_id")),
            "retrieved_at": _coerce_text(row.get("source_retrieved_at")),
            "exported_at": _coerce_text(row.get("source_exported_at")),
            "raw_sha256": _coerce_text(row.get("source_raw_sha256")),
            "transform_version": _coerce_text(row.get("source_transform_version")),
            "terms_review": _coerce_text(row.get("source_terms_review")),
            "network_used_by_builder": _optional_bool(row.get("source_network_used_by_builder")),
            "private_or_authenticated_source": _optional_bool(
                row.get("source_private_or_authenticated_source")
            ),
        }
    )


def _build_manifest(
    *,
    dataset_id: str,
    dataset_label: str,
    profile: str,
    input_path: Path,
    input_format: str,
    output_jsonl: Path,
    row_count: int,
    market_count: int,
) -> dict[str, object]:
    return {
        "manifest_version": BUILDER_VERSION,
        "dataset_id": dataset_id,
        "dataset_label": dataset_label,
        "profile": profile,
        "input_path": str(input_path),
        "input_format": input_format,
        "input_sha256": _file_sha256(input_path),
        "output_jsonl": str(output_jsonl),
        "row_count": row_count,
        "market_count": market_count,
        "local_only": True,
        "manual_input_only": True,
        "network_used": False,
        "downloader_implemented": False,
        "source_specific_adapter": None,
        "builder_version": BUILDER_VERSION,
    }


def _resolve_dataset_id(
    rows: list[dict[str, Any]],
    *,
    top_level_defaults: dict[str, Any],
    input_path: Path,
    profile: str,
) -> str:
    for source in (*rows, top_level_defaults):
        if dataset_id := _coerce_text(source.get("dataset_id")):
            return dataset_id
    dates = sorted(
        {
            (_coerce_text(row.get("date")) or _coerce_text(row.get("timestamp")) or "undated")[:10]
            for row in rows
        }
    )
    platforms = sorted({_coerce_text(row.get("platform")) or "manual" for row in rows})
    digest = _short_hash(
        {
            "input_name": input_path.name,
            "profile": profile,
            "rows": rows,
        }
    )
    source = _safe_token(platforms[0])
    date_label = _safe_token(dates[0] if dates else "undated")
    return f"phase7g_{source}_{profile}_{date_label}_{len(rows)}r_{digest}"


def _resolve_dataset_label(
    rows: list[dict[str, Any]],
    *,
    top_level_defaults: dict[str, Any],
    profile: str,
) -> str:
    for source in (*rows, top_level_defaults):
        if dataset_label := _coerce_text(source.get("dataset_label")):
            return dataset_label
    if profile == PROFILE_CALIBRATION_ONLY:
        return "manual_calibration_only_last_price_v1"
    return "manual_acceptance_candidate_v1"


def _resolve_timestamp(row: dict[str, Any], row_index: int) -> str:
    if timestamp := _coerce_text(row.get("timestamp")):
        return timestamp
    if raw_date := _coerce_text(row.get("date")):
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError as exc:
            msg = f"manual row {row_index} date must use YYYY-MM-DD"
            raise ValueError(msg) from exc
        return datetime.combine(parsed, time(hour=16), tzinfo=UTC).isoformat().replace(
            "+00:00",
            "Z",
        )
    msg = f"manual row {row_index} must include timestamp or date"
    raise ValueError(msg)


def _normalize_profile(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {PROFILE_ACCEPTANCE, PROFILE_CALIBRATION_ONLY}:
        msg = "profile must be acceptance_candidate or calibration_only_last_price"
        raise ValueError(msg)
    return normalized


def _required_text(row: dict[str, Any], field: str, row_index: int) -> str:
    value = _coerce_text(row.get(field))
    if value is None:
        msg = f"manual row {row_index} missing required field: {field}"
        raise ValueError(msg)
    return value


def _required_float(row: dict[str, Any], field: str, row_index: int) -> float:
    parsed = _optional_float(row.get(field))
    if parsed is None:
        msg = f"manual row {row_index} missing required numeric field: {field}"
        raise ValueError(msg)
    return parsed


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        msg = f"expected numeric value, got {value!r}"
        raise ValueError(msg) from exc


def _optional_bool(value: object) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    msg = f"expected boolean value, got {value!r}"
    raise ValueError(msg)


def _json_value(value: object, field: str, row_index: int) -> object:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        msg = f"manual row {row_index} {field} is invalid JSON"
        raise ValueError(msg) from exc


def _json_object(value: object, field: str, row_index: int) -> dict[str, Any] | None:
    if value in (None, ""):
        return None
    parsed = _json_value(value, field, row_index)
    if not isinstance(parsed, dict):
        msg = f"manual row {row_index} {field} must be a JSON object"
        raise ValueError(msg)
    return parsed


def _clean_manual_row(row: object) -> dict[str, Any]:
    if not isinstance(row, dict):
        msg = "manual input rows must be objects"
        raise ValueError(msg)
    return {str(key).strip(): _clean_value(value) for key, value in row.items()}


def _clean_value(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return None if stripped == "" else stripped
    return value


def _copy_optional(output: dict[str, Any], row: dict[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        if value := _coerce_text(row.get(field)):
            output[field] = value


def _coerce_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _strip_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _has_any(row: dict[str, Any], prefix: str) -> bool:
    return any(key.startswith(prefix) and row.get(key) not in (None, "") for key in row)


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("timestamp") or ""),
        str(row.get("platform") or ""),
        str(row.get("market_id") or ""),
        str(row.get("row_id") or ""),
    )


def _stable_id(prefix: str, payload: object) -> str:
    return f"{prefix}_{_short_hash(payload, length=16)}"


def _short_hash(payload: object, *, length: int = 10) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()[:length]


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _safe_token(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "manual"
