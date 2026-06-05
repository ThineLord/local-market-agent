from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from local_market_agent.data.historical_validator import (
    PROFILE_ACCEPTANCE,
    PROFILE_CALIBRATION_ONLY,
    SCHEMA_VERSION,
    TERMS_REVIEWED,
    HistoricalDatasetValidationArtifacts,
    HistoricalDatasetValidationResult,
    validate_historical_dataset,
    write_historical_validation_reports,
)

KALSHI_EXPORT_ADAPTER_VERSION = "phase7g.kalshi_local_export_adapter.v1"
REQUIRED_EXPORT_FILES = {
    "source_manifest.json",
    "markets.jsonl",
    "candlesticks.jsonl",
    "evidence.jsonl",
}
OPTIONAL_EXPORT_FILES = {
    "trades.jsonl",
    "market_rules.jsonl",
    "settlement_overrides.jsonl",
}
REQUIRED_MANIFEST_FIELDS = {
    "export_id",
    "dataset_id",
    "source_name",
    "source_type",
    "source_urls",
    "retrieved_at",
    "exported_at",
    "terms_review",
    "terms_reviewed_by",
    "terms_reviewed_at",
    "private_or_authenticated_source",
    "network_used_by_adapter",
    "raw_file_sha256",
    "notes",
}


@dataclass(frozen=True)
class KalshiExportImportResult:
    dataset_id: str
    profile: str
    output_jsonl: Path
    manifest_path: Path
    source_audit_path: Path
    row_count: int
    market_count: int
    candle_count: int
    evidence_count: int
    downgraded: bool
    downgrade_reason: str | None
    failure_reasons: tuple[str, ...]
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
            "profile": self.profile,
            "output_jsonl": str(self.output_jsonl),
            "manifest_path": str(self.manifest_path),
            "validation_json_path": str(self.validation_artifacts.json_path)
            if self.validation_artifacts is not None
            else None,
            "validation_markdown_path": str(self.validation_artifacts.markdown_path)
            if self.validation_artifacts is not None
            else None,
            "source_audit_path": str(self.source_audit_path),
            "row_count": self.row_count,
            "market_count": self.market_count,
            "validation_valid": self.validation_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "downgraded": self.downgraded,
            "downgrade_reason": self.downgrade_reason,
        }


def import_kalshi_export(
    export_dir: str | Path,
    *,
    profile: str,
    output_dir: str | Path,
    report_dir: str | Path,
    source_audit_dir: str | Path,
    validate: bool = True,
    allow_downgrade: bool = False,
) -> KalshiExportImportResult:
    export_path = Path(export_dir)
    if not export_path.exists() or not export_path.is_dir():
        msg = f"Kalshi export directory not found: {export_path}"
        raise ValueError(msg)

    normalized_profile = _normalize_profile(profile)
    _require_export_files(export_path)

    manifest = _load_manifest(export_path / "source_manifest.json")
    input_files = _discover_input_files(export_path)
    input_checksums = {name: _file_sha256(path) for name, path in input_files.items()}
    _validate_manifest(manifest)

    markets = _load_jsonl(export_path / "markets.jsonl", "markets")
    candles = _load_jsonl(export_path / "candlesticks.jsonl", "candlesticks")
    evidence_rows = _load_jsonl(export_path / "evidence.jsonl", "evidence")
    trades = _load_jsonl(export_path / "trades.jsonl", "trades", optional=True)
    market_rules = _index_optional_rows(
        _load_jsonl(export_path / "market_rules.jsonl", "market_rules", optional=True)
    )
    settlement_overrides = _index_optional_rows(
        _load_jsonl(
            export_path / "settlement_overrides.jsonl",
            "settlement_overrides",
            optional=True,
        )
    )

    markets_by_ticker = _index_markets(markets, market_rules)
    evidence_by_ticker = _index_evidence(evidence_rows)
    dataset_id = _required_manifest_text(manifest, "dataset_id")
    dataset_label = _coerce_text(manifest.get("dataset_label")) or (
        f"kalshi_local_export_{dataset_id}"
    )

    target_profile = normalized_profile
    downgraded = False
    downgrade_reason: str | None = None
    preflight_failures = _acceptance_preflight_failures(
        manifest=manifest,
        candles=candles,
        markets_by_ticker=markets_by_ticker,
        settlement_overrides=settlement_overrides,
        evidence_by_ticker=evidence_by_ticker,
    )
    if normalized_profile == PROFILE_ACCEPTANCE and preflight_failures:
        downgradable = _downgradable_failures(preflight_failures)
        if allow_downgrade and downgradable:
            target_profile = PROFILE_CALIBRATION_ONLY
            downgraded = True
            downgrade_reason = "; ".join(preflight_failures)
        else:
            msg = "acceptance_candidate Kalshi import blocked: " + "; ".join(
                preflight_failures
            )
            raise ValueError(msg)

    rows = _build_phase7g_rows(
        manifest=manifest,
        dataset_id=dataset_id,
        dataset_label=dataset_label,
        profile=target_profile,
        candles=candles,
        markets_by_ticker=markets_by_ticker,
        settlement_overrides=settlement_overrides,
        evidence_by_ticker=evidence_by_ticker,
        input_checksums=input_checksums,
    )
    if not rows:
        msg = "Kalshi export contains no usable candlestick rows"
        raise ValueError(msg)
    rows.sort(key=_row_sort_key)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_jsonl = output_path / f"{dataset_id}.jsonl"
    output_jsonl.write_text(
        "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
        + "\n",
        encoding="utf-8",
    )

    validation_result: HistoricalDatasetValidationResult | None = None
    validation_artifacts: HistoricalDatasetValidationArtifacts | None = None
    if validate:
        validation_result = validate_historical_dataset(output_jsonl)
        validation_artifacts = write_historical_validation_reports(
            validation_result,
            report_dir,
        )

    manifest_path = output_path / f"{dataset_id}.manifest.json"
    source_audit_path = Path(source_audit_dir) / f"{dataset_id}_source_audit.md"
    market_count = len({row["market_id"] for row in rows})
    failure_reasons = tuple(preflight_failures)
    output_manifest = _build_output_manifest(
        manifest=manifest,
        export_dir=export_path,
        dataset_id=dataset_id,
        dataset_label=dataset_label,
        profile=target_profile,
        output_jsonl=output_jsonl,
        row_count=len(rows),
        market_count=market_count,
        candle_count=len(candles),
        evidence_count=len(evidence_rows),
        trade_count=len(trades),
        input_checksums=input_checksums,
        downgraded=downgraded,
        downgrade_reason=downgrade_reason,
        failure_reasons=failure_reasons,
        validation_result=validation_result,
        validation_artifacts=validation_artifacts,
    )
    manifest_path.write_text(
        json.dumps(output_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    source_audit_path.parent.mkdir(parents=True, exist_ok=True)
    source_audit_path.write_text(
        _render_source_audit(
            manifest=manifest,
            output_manifest=output_manifest,
            validation_result=validation_result,
        ),
        encoding="utf-8",
    )

    return KalshiExportImportResult(
        dataset_id=dataset_id,
        profile=target_profile,
        output_jsonl=output_jsonl,
        manifest_path=manifest_path,
        source_audit_path=source_audit_path,
        row_count=len(rows),
        market_count=market_count,
        candle_count=len(candles),
        evidence_count=len(evidence_rows),
        downgraded=downgraded,
        downgrade_reason=downgrade_reason,
        failure_reasons=failure_reasons,
        validation_result=validation_result,
        validation_artifacts=validation_artifacts,
    )


def _build_phase7g_rows(
    *,
    manifest: dict[str, Any],
    dataset_id: str,
    dataset_label: str,
    profile: str,
    candles: list[dict[str, Any]],
    markets_by_ticker: dict[str, dict[str, Any]],
    settlement_overrides: dict[str, dict[str, Any]],
    evidence_by_ticker: dict[str, list[dict[str, Any]]],
    input_checksums: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, candle in enumerate(candles, start=1):
        ticker = _required_row_text(candle, "market_ticker", "candlestick", index)
        market = markets_by_ticker.get(ticker)
        if market is None:
            msg = f"candlestick row {index} references unknown market_ticker: {ticker}"
            raise ValueError(msg)
        timestamp = _canonical_timestamp(
            _required_row_text(candle, "end_period_ts", "candlestick", index),
            field=f"candlestick row {index} end_period_ts",
        )
        timestamp_dt = _parse_timestamp(timestamp, field=f"candlestick row {index} end_period_ts")
        bid = _optional_float(_nested_get(candle, "yes_bid.close_dollars"))
        ask = _optional_float(_nested_get(candle, "yes_ask.close_dollars"))
        last_price = _optional_float(_nested_get(candle, "price.close_dollars"))
        if last_price is None and profile == PROFILE_CALIBRATION_ONLY:
            last_price = _optional_float(_nested_get(candle, "price.mean_dollars"))
        if last_price is None:
            msg = f"candlestick row {index} missing price.close_dollars"
            raise ValueError(msg)

        valid_evidence = _evidence_available_at(
            evidence_by_ticker.get(ticker, []),
            timestamp_dt,
            dataset_id=dataset_id,
            row_index=index,
        )
        settlement = _build_settlement(
            market,
            settlement_overrides.get(ticker, {}),
            manifest=manifest,
        )
        if profile == PROFILE_ACCEPTANCE:
            output_bid = bid
            output_ask = ask
            implied_probability = (
                round((bid + ask) / 2, 6) if bid is not None and ask is not None else last_price
            )
            paper_pnl_allowed = bid is not None and ask is not None
            acceptance_candidate = paper_pnl_allowed
            calibration_reason = None
        else:
            output_bid = None
            output_ask = None
            implied_probability = last_price
            paper_pnl_allowed = False
            acceptance_candidate = False
            calibration_reason = "missing_point_in_time_bid_ask"

        source_record_id = f"{ticker}:{timestamp}"
        row: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "row_id": _stable_id("row", {"dataset_id": dataset_id, "record": source_record_id}),
            "dataset_id": dataset_id,
            "dataset_label": dataset_label,
            "profile": profile,
            "timestamp": timestamp,
            "date": timestamp[:10],
            "market_id": ticker,
            "platform": "kalshi",
            "title": _market_title(market),
            "market_type": "binary_prediction",
            "outcome_side": "yes",
            "bid": output_bid,
            "ask": output_ask,
            "last_price": last_price,
            "implied_probability": implied_probability,
            "liquidity": _optional_float(market.get("liquidity_dollars")),
            "volume": _optional_float(candle.get("volume_fp")),
            "market_status_at_timestamp": _market_status_at_timestamp(market, timestamp_dt),
            "evidence": valid_evidence,
            "settlement": settlement,
            "source_provenance": _build_source_provenance(
                manifest=manifest,
                source_record_id=source_record_id,
                input_checksums=input_checksums,
            ),
            "paper_pnl_allowed": paper_pnl_allowed,
            "acceptance_candidate": acceptance_candidate,
            "metadata": _strip_none(
                {
                    "adapter_version": KALSHI_EXPORT_ADAPTER_VERSION,
                    "export_id": manifest.get("export_id"),
                    "period_interval": candle.get("period_interval"),
                    "bid_source": "yes_bid.close_dollars",
                    "ask_source": "yes_ask.close_dollars",
                    "last_price_source": "price.close_dollars",
                    "implied_probability_source": "bid_ask_midpoint"
                    if profile == PROFILE_ACCEPTANCE
                    else "last_price",
                    "price_open_dollars": _optional_float(
                        _nested_get(candle, "price.open_dollars")
                    ),
                    "price_mean_dollars": _optional_float(
                        _nested_get(candle, "price.mean_dollars")
                    ),
                    "price_previous_dollars": _optional_float(
                        _nested_get(candle, "price.previous_dollars")
                    ),
                    "open_interest_fp": _optional_float(candle.get("open_interest_fp")),
                    "market_status_source": market.get("status"),
                }
            ),
        }
        if calibration_reason is not None:
            row["calibration_only_reason"] = calibration_reason
        rows.append(row)
    return rows


def _acceptance_preflight_failures(
    *,
    manifest: dict[str, Any],
    candles: list[dict[str, Any]],
    markets_by_ticker: dict[str, dict[str, Any]],
    settlement_overrides: dict[str, dict[str, Any]],
    evidence_by_ticker: dict[str, list[dict[str, Any]]],
) -> list[str]:
    failures: list[str] = []
    if manifest.get("private_or_authenticated_source") is not False:
        failures.append("private_or_authenticated_source must be false for acceptance")
    terms_review = manifest.get("terms_review")
    if terms_review == "blocked":
        failures.append("terms_review blocked for local research export")
    elif terms_review != TERMS_REVIEWED:
        failures.append(
            "terms_review must be reviewed_public_research_local_only for acceptance"
        )

    for index, candle in enumerate(candles, start=1):
        ticker = _coerce_text(candle.get("market_ticker")) or f"line_{index}"
        bid = _optional_float(_nested_get(candle, "yes_bid.close_dollars"))
        ask = _optional_float(_nested_get(candle, "yes_ask.close_dollars"))
        if bid is None or ask is None:
            failures.append(f"missing bid/ask close dollars for market {ticker}")
        market = markets_by_ticker.get(ticker)
        if market is None:
            failures.append(f"missing market row for candlestick market {ticker}")
            continue
        settlement = _build_settlement(
            market,
            settlement_overrides.get(ticker, {}),
            manifest=manifest,
        )
        if not settlement or settlement.get("outcome") not in {"yes", "no"}:
            failures.append(f"missing unambiguous settlement for market {ticker}")
        if not settlement.get("resolved_at") or not settlement.get("label_available_at"):
            failures.append(f"missing settlement timestamp for market {ticker}")
        raw_timestamp = _coerce_text(candle.get("end_period_ts"))
        if raw_timestamp is None:
            failures.append(f"missing candle timestamp for market {ticker}")
            continue
        timestamp = _parse_timestamp(raw_timestamp, field=f"candlestick {ticker} end_period_ts")
        evidence_before = _evidence_available_at(
            evidence_by_ticker.get(ticker, []),
            timestamp,
            dataset_id="preflight",
            row_index=index,
        )
        if not evidence_before:
            failures.append(
                f"evidence timestamp coverage missing for market {ticker} at {raw_timestamp}"
            )
    return _dedupe(failures)


def _downgradable_failures(failures: list[str]) -> bool:
    if not failures:
        return False
    hard_markers = (
        "private_or_authenticated_source",
        "terms_review blocked",
        "missing market row",
        "missing unambiguous settlement",
        "missing settlement timestamp",
        "missing candle timestamp",
    )
    return not any(any(marker in failure for marker in hard_markers) for failure in failures)


def _validate_manifest(manifest: dict[str, Any]) -> None:
    missing = sorted(field for field in REQUIRED_MANIFEST_FIELDS if _is_blank(manifest.get(field)))
    if missing:
        msg = "source_manifest.json missing required fields: " + ", ".join(missing)
        raise ValueError(msg)
    if not isinstance(manifest.get("source_urls"), list) or not manifest["source_urls"]:
        msg = "source_manifest.json source_urls must be a non-empty list"
        raise ValueError(msg)
    if manifest.get("network_used_by_adapter") is not False:
        msg = "network_used_by_adapter must be false for local Kalshi export imports"
        raise ValueError(msg)
    _canonical_timestamp(manifest["retrieved_at"], field="source_manifest.retrieved_at")
    _canonical_timestamp(manifest["exported_at"], field="source_manifest.exported_at")
    _canonical_timestamp(
        manifest["terms_reviewed_at"],
        field="source_manifest.terms_reviewed_at",
    )


def _build_settlement(
    market: dict[str, Any],
    override: dict[str, Any],
    *,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    data = {**market, **override}
    outcome = _normalize_outcome(data.get("outcome") or data.get("result"))
    resolved_at = _first_text(
        data,
        (
            "resolved_at",
            "settlement_ts",
            "label_available_at",
            "latest_expiration_time",
            "expected_expiration_time",
            "close_time",
        ),
    )
    resolved_at = _canonical_timestamp(resolved_at, field="settlement.resolved_at") if resolved_at else None
    status = _coerce_text(data.get("settlement_status") or data.get("status")) or "settled"
    ambiguous = outcome not in {"yes", "no"} or status.lower() in {
        "ambiguous",
        "canceled",
        "cancelled",
        "disputed",
        "void",
    }
    return _strip_none(
        {
            "outcome": outcome,
            "status": status,
            "resolved_at": resolved_at,
            "label_available_at": resolved_at,
            "source": _coerce_text(manifest.get("source_name")) or "kalshi_public_export",
            "source_url": _source_url(manifest),
            "resolution_rule": _resolution_rule(data),
            "verified_at": _canonical_timestamp(
                manifest.get("exported_at"),
                field="source_manifest.exported_at",
            ),
            "ambiguous": ambiguous,
            "method": "kalshi_market_export",
            "settlement_price": _settlement_price(outcome, data.get("settlement_value_dollars")),
            "raw_outcome_value": _coerce_text(data.get("result")),
        }
    )


def _build_source_provenance(
    *,
    manifest: dict[str, Any],
    source_record_id: str,
    input_checksums: dict[str, str],
) -> dict[str, Any]:
    return {
        "source_name": _required_manifest_text(manifest, "source_name"),
        "source_type": _required_manifest_text(manifest, "source_type"),
        "source_url": _source_url(manifest),
        "source_record_id": source_record_id,
        "retrieved_at": _canonical_timestamp(
            manifest.get("retrieved_at"),
            field="source_manifest.retrieved_at",
        ),
        "exported_at": _canonical_timestamp(
            manifest.get("exported_at"),
            field="source_manifest.exported_at",
        ),
        "raw_sha256": _short_hash(input_checksums, length=16),
        "transform_version": KALSHI_EXPORT_ADAPTER_VERSION,
        "terms_review": _required_manifest_text(manifest, "terms_review"),
        "network_used_by_builder": False,
        "private_or_authenticated_source": manifest.get("private_or_authenticated_source"),
    }


def _evidence_available_at(
    evidence_rows: list[dict[str, Any]],
    timestamp: datetime,
    *,
    dataset_id: str,
    row_index: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for evidence_index, item in enumerate(evidence_rows, start=1):
        published_raw = _coerce_text(item.get("published_at"))
        if published_raw is None:
            continue
        published_at = _parse_timestamp(published_raw, field="evidence.published_at")
        if published_at > timestamp:
            continue
        evidence_id = _coerce_text(item.get("evidence_id")) or _stable_id(
            "ev",
            {
                "dataset_id": dataset_id,
                "row_index": row_index,
                "evidence_index": evidence_index,
                "source": item.get("source"),
                "title": item.get("title"),
                "published_at": item.get("published_at"),
            },
        )
        selected.append(
            _strip_none(
                {
                    "evidence_id": evidence_id,
                    "source": _coerce_text(item.get("source")),
                    "title": _coerce_text(item.get("title")),
                    "url": _coerce_text(item.get("url")),
                    "published_at": _canonical_timestamp(
                        item.get("published_at"),
                        field="evidence.published_at",
                    ),
                    "retrieved_at": _canonical_timestamp(
                        item.get("retrieved_at"),
                        field="evidence.retrieved_at",
                    )
                    if item.get("retrieved_at")
                    else None,
                    "summary": _coerce_text(item.get("summary")),
                    "relevance_score": _optional_float(item.get("relevance_score")),
                    "credibility_score": _optional_float(item.get("credibility_score")),
                    "metadata": _json_object(item.get("metadata")) or {},
                }
            )
        )
    return selected


def _build_output_manifest(
    *,
    manifest: dict[str, Any],
    export_dir: Path,
    dataset_id: str,
    dataset_label: str,
    profile: str,
    output_jsonl: Path,
    row_count: int,
    market_count: int,
    candle_count: int,
    evidence_count: int,
    trade_count: int,
    input_checksums: dict[str, str],
    downgraded: bool,
    downgrade_reason: str | None,
    failure_reasons: tuple[str, ...],
    validation_result: HistoricalDatasetValidationResult | None,
    validation_artifacts: HistoricalDatasetValidationArtifacts | None,
) -> dict[str, Any]:
    validation = None
    if validation_result is not None:
        validation = {
            "valid": validation_result.valid,
            "error_count": validation_result.error_count,
            "warning_count": validation_result.warning_count,
            "json_path": str(validation_artifacts.json_path)
            if validation_artifacts is not None
            else None,
            "markdown_path": str(validation_artifacts.markdown_path)
            if validation_artifacts is not None
            else None,
        }
    return {
        "manifest_version": KALSHI_EXPORT_ADAPTER_VERSION,
        "dataset_id": dataset_id,
        "dataset_label": dataset_label,
        "profile": profile,
        "export_id": manifest.get("export_id"),
        "export_dir": str(export_dir),
        "output_jsonl": str(output_jsonl),
        "row_count": row_count,
        "market_count": market_count,
        "candle_count": candle_count,
        "evidence_count": evidence_count,
        "trade_count": trade_count,
        "input_checksums": input_checksums,
        "source_name": manifest.get("source_name"),
        "source_type": manifest.get("source_type"),
        "source_urls": manifest.get("source_urls"),
        "source_terms_review": manifest.get("terms_review"),
        "terms_reviewed_by": manifest.get("terms_reviewed_by"),
        "terms_reviewed_at": manifest.get("terms_reviewed_at"),
        "private_or_authenticated_source": manifest.get("private_or_authenticated_source"),
        "local_only": True,
        "file_only": True,
        "network_used": False,
        "downloader_implemented": False,
        "source_specific_adapter": "kalshi_local_public_export",
        "bid_ask_source_semantics": "candlestick yes_bid.close_dollars and yes_ask.close_dollars",
        "high_low_used_as_quotes": False,
        "bid_ask_inferred_from_last_price": False,
        "paper_pnl_allowed": validation_result.paper_pnl_allowed
        if validation_result is not None
        else profile == PROFILE_ACCEPTANCE,
        "acceptance_candidate": validation_result.acceptance_candidate
        if validation_result is not None
        else profile == PROFILE_ACCEPTANCE,
        "downgraded": downgraded,
        "downgrade_reason": downgrade_reason,
        "failure_reasons": list(failure_reasons),
        "validation": validation,
    }


def _render_source_audit(
    *,
    manifest: dict[str, Any],
    output_manifest: dict[str, Any],
    validation_result: HistoricalDatasetValidationResult | None,
) -> str:
    validation_lines = ["Validation not run."]
    if validation_result is not None:
        validation_lines = [
            f"Valid: {validation_result.valid}",
            f"Acceptance candidate: {validation_result.acceptance_candidate}",
            f"Paper PnL allowed: {validation_result.paper_pnl_allowed}",
            f"Error count: {validation_result.error_count}",
            f"Warning count: {validation_result.warning_count}",
            f"Settlement coverage pct: {validation_result.settlement_coverage_pct}",
            f"Evidence timestamp coverage pct: {validation_result.evidence_timestamp_coverage_pct}",
        ]
    checksum_lines = [
        f"- `{name}`: `{digest}`"
        for name, digest in sorted(output_manifest["input_checksums"].items())
    ]
    failure_reasons = output_manifest.get("failure_reasons") or ["none"]
    failure_lines = [f"- {reason}" for reason in failure_reasons]
    return "\n".join(
        [
            "# Kalshi Local Export Source Audit",
            "",
            f"Dataset: `{output_manifest['dataset_id']}`",
            f"Export id: `{manifest.get('export_id')}`",
            f"Profile: `{output_manifest['profile']}`",
            "",
            "## Source Files",
            "",
            *checksum_lines,
            "",
            "## Terms Review",
            "",
            f"- terms_review: `{manifest.get('terms_review')}`",
            f"- terms_reviewed_by: `{manifest.get('terms_reviewed_by')}`",
            f"- terms_reviewed_at: `{manifest.get('terms_reviewed_at')}`",
            f"- private_or_authenticated_source: {manifest.get('private_or_authenticated_source')}",
            f"- network_used_by_adapter: {manifest.get('network_used_by_adapter')}",
            "",
            "## Counts",
            "",
            f"- row_count: {output_manifest['row_count']}",
            f"- market_count: {output_manifest['market_count']}",
            f"- candle_count: {output_manifest['candle_count']}",
            f"- evidence_count: {output_manifest['evidence_count']}",
            "",
            "## Source Semantics",
            "",
            "- `bid` maps from `yes_bid.close_dollars`.",
            "- `ask` maps from `yes_ask.close_dollars`.",
            "- Candle high/low values are preserved only in raw exports and are not used as quotes.",
            "- Missing bid/ask values are not synthesized from last price.",
            "",
            "## Downgrade Or Failure Reasons",
            "",
            *failure_lines,
            "",
            "## Safety Flags",
            "",
            f"- local_only: {output_manifest['local_only']}",
            f"- file_only: {output_manifest['file_only']}",
            f"- network_used: {output_manifest['network_used']}",
            f"- downloader_implemented: {output_manifest['downloader_implemented']}",
            "",
            "## Validation",
            "",
            *validation_lines,
            "",
        ]
    )


def _require_export_files(export_path: Path) -> None:
    missing = sorted(name for name in REQUIRED_EXPORT_FILES if not (export_path / name).exists())
    if missing:
        msg = "Kalshi export directory missing required files: " + ", ".join(missing)
        raise ValueError(msg)


def _discover_input_files(export_path: Path) -> dict[str, Path]:
    names = sorted(REQUIRED_EXPORT_FILES | {name for name in OPTIONAL_EXPORT_FILES if (export_path / name).exists()})
    return {name: export_path / name for name in names}


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = "source_manifest.json is invalid JSON"
        raise ValueError(msg) from exc
    if not isinstance(payload, dict):
        msg = "source_manifest.json must contain one JSON object"
        raise ValueError(msg)
    return payload


def _load_jsonl(path: Path, label: str, *, optional: bool = False) -> list[dict[str, Any]]:
    if optional and not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            msg = f"{label}.jsonl line {line_number} is invalid JSON"
            raise ValueError(msg) from exc
        if not isinstance(payload, dict):
            msg = f"{label}.jsonl line {line_number} must be an object"
            raise ValueError(msg)
        rows.append(payload)
    return rows


def _index_markets(
    markets: list[dict[str, Any]],
    market_rules: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for index, market in enumerate(markets, start=1):
        ticker = _required_row_text(market, "ticker", "market", index)
        indexed[ticker] = {**market_rules.get(ticker, {}), **market}
    return indexed


def _index_evidence(evidence_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for index, item in enumerate(evidence_rows, start=1):
        ticker = _required_row_text(item, "market_ticker", "evidence", index)
        indexed.setdefault(ticker, []).append(item)
    for rows in indexed.values():
        rows.sort(key=lambda row: str(row.get("published_at") or ""))
    return indexed


def _index_optional_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = _coerce_text(row.get("market_ticker") or row.get("ticker"))
        if ticker:
            indexed[ticker] = row
    return indexed


def _nested_get(row: dict[str, Any], dotted_key: str) -> Any:
    if dotted_key in row:
        return row[dotted_key]
    current: Any = row
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _normalize_profile(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {PROFILE_ACCEPTANCE, PROFILE_CALIBRATION_ONLY}:
        msg = "profile must be acceptance_candidate or calibration_only_last_price"
        raise ValueError(msg)
    return normalized


def _normalize_outcome(value: object) -> str | None:
    text = _coerce_text(value)
    if text is None:
        return None
    normalized = text.lower()
    if normalized in {"yes", "y", "true", "1", "yes_win", "settled_yes"}:
        return "yes"
    if normalized in {"no", "n", "false", "0", "no_win", "settled_no"}:
        return "no"
    parsed = _optional_float(value)
    if parsed == 1:
        return "yes"
    if parsed == 0:
        return "no"
    return normalized


def _settlement_price(outcome: str | None, raw_value: object) -> float | None:
    parsed = _optional_float(raw_value)
    if parsed is not None:
        return parsed
    if outcome == "yes":
        return 1.0
    if outcome == "no":
        return 0.0
    return None


def _market_title(market: dict[str, Any]) -> str:
    title = _coerce_text(market.get("title"))
    subtitle = _coerce_text(market.get("subtitle"))
    if title and subtitle:
        return f"{title} - {subtitle}"
    if title:
        return title
    ticker = _coerce_text(market.get("ticker")) or "unknown"
    return f"Kalshi market {ticker}"


def _market_status_at_timestamp(market: dict[str, Any], timestamp: datetime) -> str:
    label_time = _coerce_text(
        market.get("settlement_ts")
        or market.get("latest_expiration_time")
        or market.get("expected_expiration_time")
    )
    if label_time and timestamp >= _parse_timestamp(label_time, field="market settlement timestamp"):
        return "closed"
    return "open"


def _resolution_rule(data: dict[str, Any]) -> str | None:
    primary = _coerce_text(data.get("rules_primary") or data.get("primary_rule"))
    secondary = _coerce_text(data.get("rules_secondary") or data.get("secondary_rule"))
    if primary and secondary:
        return f"{primary} {secondary}"
    return primary or secondary or _coerce_text(data.get("title"))


def _source_url(manifest: dict[str, Any]) -> str:
    urls = manifest.get("source_urls")
    if isinstance(urls, list) and urls:
        return str(urls[0])
    return "local_kalshi_public_export"


def _first_text(row: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = _coerce_text(row.get(field))
        if value is not None:
            return value
    return None


def _required_manifest_text(manifest: dict[str, Any], field: str) -> str:
    value = _coerce_text(manifest.get(field))
    if value is None:
        msg = f"source_manifest.json missing required field: {field}"
        raise ValueError(msg)
    return value


def _required_row_text(
    row: dict[str, Any],
    field: str,
    label: str,
    row_index: int,
) -> str:
    value = _coerce_text(row.get(field))
    if value is None:
        msg = f"{label} row {row_index} missing required field: {field}"
        raise ValueError(msg)
    return value


def _canonical_timestamp(value: object, *, field: str) -> str:
    parsed = _parse_timestamp(value, field=field)
    return parsed.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object, *, field: str) -> datetime:
    text = _coerce_text(value)
    if text is None:
        msg = f"{field} is required and must be timezone-aware ISO 8601"
        raise ValueError(msg)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        msg = f"{field} must be timezone-aware ISO 8601"
        raise ValueError(msg) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        msg = f"{field} must include a timezone offset"
        raise ValueError(msg)
    return parsed


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_object(value: object) -> dict[str, Any] | None:
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            msg = "evidence metadata must be a JSON object when provided as a string"
            raise ValueError(msg) from exc
        if isinstance(parsed, dict):
            return parsed
    msg = "evidence metadata must be an object"
    raise ValueError(msg)


def _coerce_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_blank(value: object) -> bool:
    return value is None or value == ""


def _strip_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


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


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
