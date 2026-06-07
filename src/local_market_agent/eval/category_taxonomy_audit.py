from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from local_market_agent.eval.category_calibration import (
    CATEGORY_MISSING,
    CATEGORY_PUBLIC_EVENT,
)

DEFAULT_DOCS_REPORT_PATH = Path(
    "docs/reports/kalshi_category_taxonomy_availability_audit.md"
)
DEFAULT_REFERENCE_EXPORT_DIR = Path(
    "data/source_exports/kalshi/kalshi_calibration_preferred_20260607_public_probe"
)
WARNING_SUSPECTED_CATEGORY_MISMATCH = "suspected_category_mismatch"
WARNING_PUBLIC_EVENT_CATCH_ALL_OVERUSE = "public_event_catch_all_overuse"
WARNING_SPORTS_ASSIGNED_TO_WEATHER_OR_FED = "sports_assigned_to_weather_or_fed"
WARNING_WEATHER_ASSIGNED_ELSEWHERE = "weather_assigned_elsewhere"
WARNING_FED_MACRO_ASSIGNED_ELSEWHERE = "fed_macro_assigned_elsewhere"
WARNING_TOPIC_MENTION_MARKET = "topic_keyword_mention_market_warning"
WARNING_SOURCE_LOGS_MISSING = "source_logs_missing_warning"
WARNING_FILTER_COUNTS_MISSING = "filter_counts_missing_warning"
WARNING_CANDLE_ATTEMPT_LOGS_MISSING = "candle_attempt_logs_missing_warning"
WARNING_ROW_COUNT_BOTTLENECK = "row_count_bottleneck_warning"

SPORTS_PATTERNS = (
    ("tennis_ticker", r"kx(?:itf|itfw|wta|wtachallenger|atp).*match"),
    ("tennis_title", r"\bprofessional tennis match\b"),
    ("tennis_tour", r"\b(?:atp|wta|itf|challenger)\b"),
    ("match_round", r"\bround of\b|\bsemifinal\b|\bqualification final\b"),
    ("soccer", r"\bsoccer\b|\bchampions league\b|\bworld cup\b"),
    ("basketball", r"\bbasketball\b|\bncaamb\b|\bnba\b"),
    ("major_league", r"\bnfl\b|\bmlb\b|\bnhl\b"),
    ("sports_market_ticker", r"kx(?:ncaamb|ucl|nfl|nba|mlb|nhl)"),
)
WEATHER_PATTERNS = (
    ("weather", r"\bweather\b"),
    ("temperature", r"\btemperatures?\b|\bhigh temp\b|\blow temp\b"),
    ("precipitation", r"\brain\b|\bsnow\b|\bprecipitation\b"),
    ("storm", r"\bhurricane\b|\btornado\b|\bstorm\b"),
    ("agency", r"\bnoaa\b|\bnational weather service\b"),
    ("wind", r"\bwind\b|\bwindy\b"),
)
FED_MACRO_PATTERNS = (
    ("fed", r"\bfed\b|\bfederal reserve\b|\bfomc\b"),
    ("rate", r"\binterest rates?\b|\brate cut\b|\brate hike\b|\bcut rate\b"),
    ("inflation", r"\bcpi\b|\bppi\b|\binflation\b"),
    ("labor", r"\bunemployment\b|\bpayrolls?\b|\bjobs report\b"),
    ("growth", r"\bgdp\b|\bretail sales\b"),
    ("fed_speaker", r"\bpowell\b|\bgoolsbee\b|\bbowman\b|\bwaller\b"),
)
MENTION_MARKET_PATTERNS = (
    ("mention_ticker", r"kx(?:person|fedgov|fedgovmention).*mention"),
    ("what_will_say", r"\bwhat will\b.+\bsay\b"),
    ("says_as_part", r"\bsays?\b.+\bas part of\b"),
)


@dataclass(frozen=True)
class CategoryTaxonomyAuditArtifacts:
    json_path: Path
    markdown_path: Path
    docs_markdown_path: Path | None = None


@dataclass(frozen=True)
class CategoryTaxonomyAuditResult:
    report: dict[str, Any]

    @property
    def export_id(self) -> str:
        return str(self.report["source_export"]["export_id"])

    @property
    def guardrails(self) -> dict[str, bool]:
        guardrails = self.report["guardrails"]
        return guardrails if isinstance(guardrails, dict) else {}

    def as_dict(self) -> dict[str, Any]:
        return self.report


def run_category_taxonomy_audit(
    source_export_dir: str | Path,
    historical_file: str | Path,
    *,
    reference_export_dir: str | Path | None = DEFAULT_REFERENCE_EXPORT_DIR,
) -> CategoryTaxonomyAuditResult:
    export_dir = Path(source_export_dir)
    historical_path = Path(historical_file)
    historical_rows = _load_jsonl_required(historical_path, "historical file")
    markets_path = export_dir / "markets.jsonl"
    candles_path = export_dir / "candlesticks.jsonl"
    manifest_path = export_dir / "source_manifest.json"
    markets = _load_jsonl_optional(markets_path)
    candles = _load_jsonl_optional(candles_path)
    manifest = _load_json_optional(manifest_path)

    market_records = _market_records(
        markets=markets,
        candles=candles,
        historical_rows=historical_rows,
    )
    taxonomy_checks = _taxonomy_checks(market_records)
    source_metadata = _source_metadata(
        export_dir=export_dir,
        markets=markets,
        candles=candles,
        historical_rows=historical_rows,
        manifest=manifest,
    )
    availability = _availability_diagnosis(
        source_metadata=source_metadata,
        taxonomy_checks=taxonomy_checks,
        market_records=market_records,
    )
    reference_summary = _reference_export_summary(
        Path(reference_export_dir) if reference_export_dir is not None else None
    )
    report = {
        "report_id": f"category_taxonomy_audit_{_safe_filename(export_dir.name)}",
        "phase": "PR-CAL-9",
        "created_at": datetime.now(UTC).isoformat(),
        "source_export": source_metadata,
        "historical_file": str(historical_path),
        "market_label_comparisons": market_records,
        "taxonomy_checks": taxonomy_checks,
        "availability_diagnosis": availability,
        "reference_export_summary": reference_summary,
        "guardrails": _guardrails(),
    }
    return CategoryTaxonomyAuditResult(report=report)


def write_category_taxonomy_audit_reports(
    result: CategoryTaxonomyAuditResult,
    output_dir: str | Path,
    *,
    docs_markdown_path: str | Path | None = DEFAULT_DOCS_REPORT_PATH,
) -> CategoryTaxonomyAuditArtifacts:
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    safe_export_id = _safe_filename(result.export_id)
    json_path = report_dir / f"{safe_export_id}.category_taxonomy_audit.json"
    markdown_path = report_dir / f"{safe_export_id}_category_taxonomy_audit.md"
    markdown = _render_markdown(result.as_dict())
    json_path.write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(markdown, encoding="utf-8")

    docs_path = Path(docs_markdown_path) if docs_markdown_path is not None else None
    if docs_path is not None:
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        docs_path.write_text(markdown, encoding="utf-8")

    return CategoryTaxonomyAuditArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        docs_markdown_path=docs_path,
    )


def infer_semantic_category(market: dict[str, Any]) -> dict[str, Any]:
    text = _market_text(market)
    sports_matches = _matches(text, SPORTS_PATTERNS)
    weather_matches = _matches(text, WEATHER_PATTERNS)
    fed_matches = _matches(text, FED_MACRO_PATTERNS)
    mention_matches = _matches(text, MENTION_MARKET_PATTERNS)
    signals = {
        "sports": sports_matches,
        "weather": weather_matches,
        "fed_policy": fed_matches,
    }
    detected = [category for category, matches in signals.items() if matches]
    if sports_matches:
        category = "sports"
    elif fed_matches:
        category = "fed_policy"
    elif weather_matches:
        category = "weather"
    else:
        category = CATEGORY_PUBLIC_EVENT if _text(market.get("title")) else "unknown"
    confidence = "medium" if len(detected) == 1 else "low"
    if not detected and category != "unknown":
        confidence = "low"
    if len(detected) > 1:
        confidence = "mixed"
    return {
        "category": category,
        "confidence": confidence,
        "signals": signals,
        "matched_signal_count": sum(len(matches) for matches in signals.values()),
        "detected_categories": detected,
        "mention_market": bool(mention_matches),
        "mention_signals": mention_matches,
        "heuristic_not_hard_truth": True,
    }


def _source_metadata(
    *,
    export_dir: Path,
    markets: list[dict[str, Any]],
    candles: list[dict[str, Any]],
    historical_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    collection_summary = _collection_summary(manifest)
    categories_by_market = {
        _market_id(market): _market_category(market) for market in markets
    }
    return {
        "export_id": _text(manifest.get("export_id")) or export_dir.name,
        "source_export_dir": str(export_dir),
        "markets_path": str(export_dir / "markets.jsonl"),
        "candlesticks_path": str(export_dir / "candlesticks.jsonl"),
        "manifest_path": str(export_dir / "source_manifest.json"),
        "manifest_status": "loaded" if manifest else "missing",
        "markets_status": "loaded" if markets else "missing",
        "candlesticks_status": "loaded" if candles else "missing",
        "selected_market_count": len(markets),
        "historical_market_count": len({_row_market_id(row) for row in historical_rows}),
        "historical_row_count": len(historical_rows),
        "candle_row_count": len(candles),
        "candle_market_count": len({_text(row.get("market_ticker")) for row in candles}),
        "discovered_market_count": _int_or_none(collection_summary.get("discovered_count")),
        "target_market_count": _int_or_none(collection_summary.get("target_markets")),
        "target_row_count": _target_row_count(collection_summary),
        "rows_per_market_target": _int_or_none(collection_summary.get("rows_per_market")),
        "period_interval": _int_or_none(collection_summary.get("period_interval")),
        "max_candle_market_attempts": _int_or_none(
            collection_summary.get("max_candle_market_attempts")
        ),
        "quotas": _dict(collection_summary.get("quotas")),
        "category_counts": _dict(collection_summary.get("category_counts")),
        "availability_limitations": _list(
            collection_summary.get("availability_limitations")
        ),
        "target_status": _text(collection_summary.get("target_status")) or "missing",
        "public_event_backfill_beyond_cap": bool(
            collection_summary.get("public_event_backfill_beyond_cap", False)
        ),
        "raw_source_category_distribution": dict(
            sorted(Counter(categories_by_market.values()).items())
        ),
        "historical_enriched_category_distribution": dict(
            sorted(
                Counter(
                    categories_by_market.get(_row_market_id(row), CATEGORY_MISSING)
                    for row in historical_rows
                ).items()
            )
        ),
        "source_family_distribution": _market_metadata_counter(markets, "source_family"),
        "status_distribution": dict(
            sorted(Counter(_text(market.get("status")) or "missing" for market in markets).items())
        ),
        "market_type_distribution": dict(
            sorted(
                Counter(
                    _text(_metadata_value(market, "market_type"))
                    or _text(market.get("market_type"))
                    or "missing"
                    for market in markets
                ).items()
            )
        ),
        "event_ticker_count": len({_text(market.get("event_ticker")) for market in markets}),
        "series_ticker_distribution": _series_distribution(markets),
        "resolved_finalized_binary_filter_counts": _filter_counts(manifest),
        "candidate_category_counts": _candidate_category_counts(manifest),
        "candle_attempt_summary": _candle_attempt_summary(collection_summary),
        "missing_log_warnings": _missing_log_warnings(manifest, collection_summary),
    }


def _market_records(
    *,
    markets: list[dict[str, Any]],
    candles: list[dict[str, Any]],
    historical_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candles_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candle in candles:
        candles_by_market[_text(candle.get("market_ticker"))].append(candle)
    rows_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in historical_rows:
        rows_by_market[_row_market_id(row)].append(row)

    records: list[dict[str, Any]] = []
    for market in markets:
        market_id = _market_id(market)
        source_category = _market_category(market)
        semantic = infer_semantic_category(market)
        candle_category = _dominant_metadata_value(
            candles_by_market.get(market_id, []),
            "market_category",
        )
        historical_category = _dominant_metadata_value(
            rows_by_market.get(market_id, []),
            "market_category",
        )
        collector_quota_category = candle_category or source_category
        enriched_category = source_category if market_id in rows_by_market else CATEGORY_MISSING
        warnings = _market_warnings(
            source_category=source_category,
            collector_quota_category=collector_quota_category,
            semantic=semantic,
        )
        records.append(
            {
                "ticker": market_id,
                "title": _text(market.get("title")) or "missing",
                "event_ticker": _text(market.get("event_ticker"))
                or _text(_metadata_value(market, "event_ticker"))
                or "missing",
                "series_ticker": _text(market.get("series_ticker")) or "missing",
                "source_category": source_category,
                "inferred_semantic_category": semantic["category"],
                "semantic_confidence": semantic["confidence"],
                "semantic_signals": semantic["signals"],
                "mention_market": semantic["mention_market"],
                "mention_signals": semantic["mention_signals"],
                "collector_quota_category": collector_quota_category,
                "historical_row_lifted_category": historical_category
                or "not_lifted",
                "historical_enriched_category": enriched_category,
                "historical_row_count": len(rows_by_market.get(market_id, [])),
                "candle_row_count": len(candles_by_market.get(market_id, [])),
                "status": _text(market.get("status")) or "missing",
                "market_type": _text(_metadata_value(market, "market_type"))
                or _text(market.get("market_type"))
                or "missing",
                "source_family": _text(_metadata_value(market, "source_family"))
                or "missing",
                "warnings": warnings,
            }
        )
    return sorted(
        records,
        key=lambda item: (
            WARNING_SUSPECTED_CATEGORY_MISMATCH not in item["warnings"],
            -int(item["historical_row_count"]),
            item["ticker"],
        ),
    )


def _taxonomy_checks(records: list[dict[str, Any]]) -> dict[str, Any]:
    suspected = [
        _warning_summary(record)
        for record in records
        if WARNING_SUSPECTED_CATEGORY_MISMATCH in record["warnings"]
    ]
    sports_wrong = [
        _warning_summary(record)
        for record in records
        if WARNING_SPORTS_ASSIGNED_TO_WEATHER_OR_FED in record["warnings"]
    ]
    weather_wrong = [
        _warning_summary(record)
        for record in records
        if WARNING_WEATHER_ASSIGNED_ELSEWHERE in record["warnings"]
    ]
    fed_wrong = [
        _warning_summary(record)
        for record in records
        if WARNING_FED_MACRO_ASSIGNED_ELSEWHERE in record["warnings"]
    ]
    catch_all = [
        _warning_summary(record)
        for record in records
        if WARNING_PUBLIC_EVENT_CATCH_ALL_OVERUSE in record["warnings"]
    ]
    mention_markets = [
        _warning_summary(record)
        for record in records
        if WARNING_TOPIC_MENTION_MARKET in record["warnings"]
    ]
    semantic_distribution = Counter(
        record["inferred_semantic_category"] for record in records
    )
    source_by_semantic: dict[str, dict[str, int]] = {}
    for record in records:
        semantic = str(record["inferred_semantic_category"])
        source_by_semantic.setdefault(semantic, Counter())
        source_by_semantic[semantic][str(record["source_category"])] += 1
    return {
        "semantic_category_distribution": dict(sorted(semantic_distribution.items())),
        "source_category_by_semantic_category": {
            category: dict(sorted(counts.items()))
            for category, counts in sorted(source_by_semantic.items())
        },
        "suspected_category_mismatch_count": len(suspected),
        "suspected_category_mismatches": suspected,
        "sports_assigned_to_weather_or_fed_count": len(sports_wrong),
        "sports_assigned_to_weather_or_fed": sports_wrong,
        "weather_assigned_elsewhere_count": len(weather_wrong),
        "weather_assigned_elsewhere": weather_wrong,
        "fed_macro_assigned_elsewhere_count": len(fed_wrong),
        "fed_macro_assigned_elsewhere": fed_wrong,
        "public_event_catch_all_overuse_count": len(catch_all),
        "public_event_catch_all_overuse": catch_all,
        "topic_keyword_mention_market_count": len(mention_markets),
        "topic_keyword_mention_markets": mention_markets,
        "heuristics_not_hard_truth": True,
    }


def _availability_diagnosis(
    *,
    source_metadata: dict[str, Any],
    taxonomy_checks: dict[str, Any],
    market_records: list[dict[str, Any]],
) -> dict[str, Any]:
    limitations = source_metadata["availability_limitations"]
    quotas = source_metadata["quotas"]
    category_counts = source_metadata["category_counts"]
    candidate_counts = source_metadata["candidate_category_counts"]
    selected_count = int(source_metadata["selected_market_count"])
    candle_rows = int(source_metadata["candle_row_count"])
    target_rows = _int_or_zero(source_metadata["target_row_count"])
    rows_per_market = _int_or_zero(source_metadata["rows_per_market_target"])
    ideal_rows_for_selected = selected_count * rows_per_market
    row_shortfall_vs_selected = max(0, ideal_rows_for_selected - candle_rows)
    row_shortfall_vs_target = max(0, target_rows - candle_rows)
    quota_shortfalls = _quota_shortfalls(quotas, category_counts)
    has_category_shortfall = bool(limitations or quota_shortfalls)
    candidate_supported = bool(candidate_counts)
    true_scarcity_categories = []
    filter_or_candle_categories = []
    for category, quota in quotas.items():
        quota_int = _int_or_zero(quota)
        selected = _int_or_zero(category_counts.get(category))
        candidate = _int_or_none(candidate_counts.get(category))
        if selected >= quota_int or quota_int == 0:
            continue
        if candidate is not None and candidate < quota_int:
            true_scarcity_categories.append(category)
        elif candidate is not None and candidate >= quota_int:
            filter_or_candle_categories.append(category)

    mismatch_count = int(taxonomy_checks["suspected_category_mismatch_count"])
    catch_all_count = int(taxonomy_checks["public_event_catch_all_overuse_count"])
    mention_count = int(taxonomy_checks["topic_keyword_mention_market_count"])
    taxonomy_supported = mismatch_count > 0 or catch_all_count > 0 or mention_count > 0
    filter_counts_available = bool(
        source_metadata["resolved_finalized_binary_filter_counts"]
    )
    candle_attempts_available = bool(
        source_metadata["candle_attempt_summary"]["failure_count_available"]
    )

    if has_category_shortfall and taxonomy_supported:
        source_scarcity_status = "not_proven_taxonomy_mismatch_present"
    elif true_scarcity_categories and not taxonomy_supported:
        source_scarcity_status = "supported_by_candidate_category_counts"
    elif has_category_shortfall and not candidate_supported:
        source_scarcity_status = "not_proven_missing_candidate_category_counts"
    elif has_category_shortfall:
        source_scarcity_status = "possible_but_not_primary"
    else:
        source_scarcity_status = "not_detected"

    if taxonomy_supported:
        primary_blocker = "taxonomy_mismatch_or_keyword_mapping"
    elif filter_or_candle_categories:
        primary_blocker = "filter_or_candlestick_bottleneck"
    elif true_scarcity_categories:
        primary_blocker = "source_scarcity"
    elif has_category_shortfall:
        primary_blocker = "unknown_due_to_missing_logs"
    else:
        primary_blocker = "none_detected"

    warnings = []
    if source_metadata["missing_log_warnings"]:
        warnings.extend(source_metadata["missing_log_warnings"])
    if row_shortfall_vs_selected > 0:
        warnings.append(WARNING_ROW_COUNT_BOTTLENECK)
    if taxonomy_supported:
        warnings.append(WARNING_SUSPECTED_CATEGORY_MISMATCH)
    warnings = list(dict.fromkeys(warnings))

    return {
        "primary_blocker": primary_blocker,
        "true_source_scarcity": {
            "status": source_scarcity_status,
            "supported_categories": true_scarcity_categories,
            "candidate_category_counts_available": candidate_supported,
            "note": _source_scarcity_note(source_scarcity_status),
        },
        "taxonomy_mismatch": {
            "status": "supported" if taxonomy_supported else "not_detected",
            "suspected_category_mismatch_count": mismatch_count,
            "public_event_catch_all_overuse_count": catch_all_count,
            "topic_keyword_mention_market_count": mention_count,
            "heuristics_not_hard_truth": True,
        },
        "filter_bottleneck": {
            "status": "unknown" if not filter_counts_available else "inspect_counts",
            "filter_counts_available": filter_counts_available,
            "categories_with_candidates_but_shortfall": filter_or_candle_categories,
        },
        "candlestick_availability_bottleneck": {
            "status": "unknown" if not candle_attempts_available else "inspect_counts",
            "candle_attempt_failure_counts_available": candle_attempts_available,
            "attempt_budget": source_metadata["max_candle_market_attempts"],
            "selected_success_count": selected_count,
        },
        "row_count_bottleneck": {
            "status": "supported" if row_shortfall_vs_selected > 0 else "not_detected",
            "selected_market_count": selected_count,
            "rows_per_market_target": rows_per_market,
            "ideal_rows_for_selected_markets": ideal_rows_for_selected,
            "actual_rows": candle_rows,
            "row_shortfall_vs_selected_markets": row_shortfall_vs_selected,
            "row_shortfall_vs_target": row_shortfall_vs_target,
        },
        "unknown_due_to_missing_logs": {
            "status": bool(source_metadata["missing_log_warnings"]),
            "warnings": source_metadata["missing_log_warnings"],
        },
        "quota_shortfalls": quota_shortfalls,
        "interpretation": _diagnosis_interpretation(
            primary_blocker=primary_blocker,
            taxonomy_supported=taxonomy_supported,
            filter_counts_available=filter_counts_available,
            candle_attempts_available=candle_attempts_available,
            market_count=len(market_records),
        ),
        "warnings": warnings,
    }


def _market_warnings(
    *,
    source_category: str,
    collector_quota_category: str,
    semantic: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    semantic_category = str(semantic["category"])
    expected = _expected_source_categories(semantic_category)
    if expected and source_category not in expected:
        warnings.append(WARNING_SUSPECTED_CATEGORY_MISMATCH)
    if expected and collector_quota_category not in expected:
        warnings.append(WARNING_SUSPECTED_CATEGORY_MISMATCH)
    if (
        semantic_category == "sports"
        and source_category in {"weather", "fed_policy"}
    ):
        warnings.append(WARNING_SPORTS_ASSIGNED_TO_WEATHER_OR_FED)
    if semantic_category == "weather" and source_category != "weather":
        warnings.append(WARNING_WEATHER_ASSIGNED_ELSEWHERE)
    if semantic_category == "fed_policy" and source_category != "fed_policy":
        warnings.append(WARNING_FED_MACRO_ASSIGNED_ELSEWHERE)
    if (
        source_category == CATEGORY_PUBLIC_EVENT
        and semantic_category not in {CATEGORY_PUBLIC_EVENT, "unknown"}
    ):
        warnings.append(WARNING_PUBLIC_EVENT_CATCH_ALL_OVERUSE)
    if semantic["mention_market"] and source_category in {"weather", "fed_policy"}:
        warnings.append(WARNING_TOPIC_MENTION_MARKET)
    return list(dict.fromkeys(warnings))


def _expected_source_categories(semantic_category: str) -> set[str]:
    if semantic_category == "sports":
        return {"major_sports"}
    if semantic_category == "weather":
        return {"weather"}
    if semantic_category == "fed_policy":
        return {"fed_policy"}
    if semantic_category == CATEGORY_PUBLIC_EVENT:
        return {CATEGORY_PUBLIC_EVENT}
    return set()


def _reference_export_summary(reference_dir: Path | None) -> dict[str, Any]:
    if reference_dir is None:
        return {
            "status": "disabled",
            "source_export_dir": None,
        }
    markets_path = reference_dir / "markets.jsonl"
    if not markets_path.exists():
        return {
            "status": "missing",
            "source_export_dir": str(reference_dir),
        }
    markets = _load_jsonl_optional(markets_path)
    records = []
    for market in markets:
        source_category = _market_category(market)
        semantic = infer_semantic_category(market)
        warnings = _market_warnings(
            source_category=source_category,
            collector_quota_category=source_category,
            semantic=semantic,
        )
        records.append(
            {
                "ticker": _market_id(market),
                "title": _text(market.get("title")) or "missing",
                "source_category": source_category,
                "inferred_semantic_category": semantic["category"],
                "warnings": warnings,
            }
        )
    mismatch_count = sum(
        1
        for record in records
        if WARNING_SUSPECTED_CATEGORY_MISMATCH in record["warnings"]
    )
    catch_all_count = sum(
        1
        for record in records
        if WARNING_PUBLIC_EVENT_CATCH_ALL_OVERUSE in record["warnings"]
    )
    return {
        "status": "loaded",
        "source_export_dir": str(reference_dir),
        "market_count": len(markets),
        "source_category_distribution": dict(
            sorted(Counter(record["source_category"] for record in records).items())
        ),
        "semantic_category_distribution": dict(
            sorted(
                Counter(
                    str(record["inferred_semantic_category"]) for record in records
                ).items()
            )
        ),
        "suspected_category_mismatch_count": mismatch_count,
        "public_event_catch_all_overuse_count": catch_all_count,
        "sample_mismatches": [
            record
            for record in records
            if WARNING_SUSPECTED_CATEGORY_MISMATCH in record["warnings"]
        ][:10],
    }


def _load_jsonl_required(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        msg = f"{label} not found: {path}"
        raise ValueError(msg)
    return _load_jsonl_optional(path)


def _load_jsonl_optional(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            msg = f"JSONL line {line_number} in {path} is invalid JSON"
            raise ValueError(msg) from exc
        if not isinstance(payload, dict):
            msg = f"JSONL line {line_number} in {path} must be an object"
            raise ValueError(msg)
        rows.append(payload)
    return rows


def _load_json_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"JSON file is invalid: {path}"
        raise ValueError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"JSON file must contain an object: {path}"
        raise ValueError(msg)
    return payload


def _market_text(market: dict[str, Any]) -> str:
    fields = (
        "ticker",
        "title",
        "subtitle",
        "event_ticker",
        "series_ticker",
        "rules_primary",
        "rules_secondary",
    )
    values = [_text(market.get(field)) for field in fields]
    metadata = market.get("metadata")
    if isinstance(metadata, dict):
        values.extend(_text(metadata.get(field)) for field in fields)
    return " ".join(value.lower() for value in values if value)


def _matches(text: str, patterns: tuple[tuple[str, str], ...]) -> list[str]:
    return [name for name, pattern in patterns if re.search(pattern, text)]


def _market_id(market: dict[str, Any]) -> str:
    return _text(market.get("ticker")) or "missing"


def _row_market_id(row: dict[str, Any]) -> str:
    return _text(row.get("market_id")) or "missing"


def _market_category(market: dict[str, Any]) -> str:
    return (
        _text(_metadata_value(market, "calibration_category"))
        or _text(market.get("category"))
        or CATEGORY_MISSING
    )


def _metadata_value(row: dict[str, Any], key: str) -> Any:
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        return None
    return metadata.get(key)


def _dominant_metadata_value(rows: list[dict[str, Any]], key: str) -> str | None:
    counts: Counter[str] = Counter()
    for row in rows:
        value = _text(_metadata_value(row, key))
        if value:
            counts[value] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _collection_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    summary = manifest.get("collection_summary")
    return summary if isinstance(summary, dict) else {}


def _filter_counts(manifest: dict[str, Any]) -> dict[str, Any]:
    summary = _collection_summary(manifest)
    for key in (
        "filter_counts",
        "resolved_finalized_binary_filter_counts",
        "discovery_filter_counts",
    ):
        value = summary.get(key) or manifest.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _candidate_category_counts(manifest: dict[str, Any]) -> dict[str, Any]:
    summary = _collection_summary(manifest)
    for key in (
        "candidate_category_counts",
        "discovered_category_counts",
        "source_category_counts",
    ):
        value = summary.get(key) or manifest.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _candle_attempt_summary(collection_summary: dict[str, Any]) -> dict[str, Any]:
    attempts = collection_summary.get("candle_attempts")
    if isinstance(attempts, dict):
        return {
            "status": "loaded",
            "success_count": _int_or_none(attempts.get("success_count")),
            "failure_count": _int_or_none(attempts.get("failure_count")),
            "failure_count_available": attempts.get("failure_count") is not None,
            "raw": attempts,
        }
    return {
        "status": "missing",
        "success_count": _int_or_none(collection_summary.get("selected_count")),
        "failure_count": None,
        "failure_count_available": False,
        "raw": {},
    }


def _missing_log_warnings(
    manifest: dict[str, Any],
    collection_summary: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if not manifest:
        warnings.append(WARNING_SOURCE_LOGS_MISSING)
    if not _filter_counts(manifest):
        warnings.append(WARNING_FILTER_COUNTS_MISSING)
    if not _candle_attempt_summary(collection_summary)["failure_count_available"]:
        warnings.append(WARNING_CANDLE_ATTEMPT_LOGS_MISSING)
    return warnings


def _market_metadata_counter(markets: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(_text(_metadata_value(market, key)) or "missing" for market in markets)
    return dict(sorted(counts.items()))


def _series_distribution(markets: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(
        _text(market.get("series_ticker"))
        or _text(_metadata_value(market, "series_ticker"))
        or "missing"
        for market in markets
    )
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20])


def _target_row_count(collection_summary: dict[str, Any]) -> int | None:
    explicit = _int_or_none(collection_summary.get("target_rows"))
    if explicit is not None:
        return explicit
    target_markets = _int_or_none(collection_summary.get("target_markets"))
    rows_per_market = _int_or_none(collection_summary.get("rows_per_market"))
    if target_markets is None or rows_per_market is None:
        return None
    return target_markets * rows_per_market


def _quota_shortfalls(
    quotas: dict[str, Any],
    category_counts: dict[str, Any],
) -> list[dict[str, Any]]:
    shortfalls = []
    for category, quota in sorted(quotas.items()):
        quota_int = _int_or_zero(quota)
        selected = _int_or_zero(category_counts.get(category))
        if selected >= quota_int:
            continue
        shortfalls.append(
            {
                "category": category,
                "quota_markets": quota_int,
                "selected_markets": selected,
                "missing_markets": quota_int - selected,
            }
        )
    return shortfalls


def _warning_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": record["ticker"],
        "title": record["title"],
        "source_category": record["source_category"],
        "collector_quota_category": record["collector_quota_category"],
        "historical_enriched_category": record["historical_enriched_category"],
        "inferred_semantic_category": record["inferred_semantic_category"],
        "semantic_confidence": record["semantic_confidence"],
        "mention_market": record["mention_market"],
        "warnings": record["warnings"],
    }


def _source_scarcity_note(status: str) -> str:
    if status == "supported_by_candidate_category_counts":
        return (
            "Candidate category counts are available and show fewer candidates "
            "than the requested quota for at least one category."
        )
    if status == "not_proven_taxonomy_mismatch_present":
        return (
            "The selected export has taxonomy mismatch signals, so the observed "
            "shortfall cannot be interpreted as true source scarcity."
        )
    if status == "not_proven_missing_candidate_category_counts":
        return (
            "The manifest lacks candidate category counts before candle selection, "
            "so source scarcity is not proven by this export."
        )
    if status == "possible_but_not_primary":
        return (
            "A category shortfall remains, but available diagnostics point to a "
            "different primary blocker."
        )
    return "No quota shortfall was found."


def _diagnosis_interpretation(
    *,
    primary_blocker: str,
    taxonomy_supported: bool,
    filter_counts_available: bool,
    candle_attempts_available: bool,
    market_count: int,
) -> str:
    if market_count == 0:
        return "No selected source markets were available for taxonomy comparison."
    if taxonomy_supported:
        return (
            "The selected export supports a category taxonomy or keyword-mapping "
            "issue. True non-public source scarcity remains unproven without "
            "pre-candle candidate category counts and candle failure logs."
        )
    if primary_blocker == "source_scarcity":
        return (
            "Candidate category counts support source scarcity for at least one "
            "quota category. This still remains a source-availability finding, "
            "not a calibration category-effect finding."
        )
    if not filter_counts_available or not candle_attempts_available:
        return (
            "The export is missing enough filter or candle-attempt detail to "
            "separate source scarcity from filtering and candlestick bottlenecks."
        )
    return "No taxonomy or availability blocker was detected in the supplied export."


def _guardrails() -> dict[str, bool]:
    return {
        "calibration_taxonomy_audit_only": True,
        "local_only": True,
        "data_collection": False,
        "historical_dataset_built": False,
        "evidence_collection": False,
        "evidence_approval": False,
        "strategy_logic_changed": False,
        "acceptance_gate_changed": False,
        "phase8_started": False,
        "broker_or_live_trading_added": False,
        "scheduler_or_daemon_added": False,
        "paper_pnl_claim": False,
        "profitability_claim": False,
        "acceptance_ready_claim": False,
        "strategy_v2_superiority_claim": False,
        "trading_readiness_claim": False,
    }


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    return _int_or_none(value) or 0


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return safe or "category_taxonomy_audit"


def _format_pct(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.6f}%"


def _warnings(warnings: list[str]) -> str:
    return ", ".join(warnings) if warnings else "None"


def _render_markdown(report: dict[str, Any]) -> str:
    source = report["source_export"]
    checks = report["taxonomy_checks"]
    diagnosis = report["availability_diagnosis"]
    guardrails = report["guardrails"]
    lines = [
        "# Kalshi Category Taxonomy And Source Availability Audit",
        "",
        "Scope: PR-CAL-9 local-only calibration taxonomy and availability audit. "
        "This report reads existing local PR-CAL-8 artifacts only. It does not "
        "collect data, build a new historical dataset, collect or approve "
        "evidence, change strategy logic, change acceptance gates, start Phase 8, "
        "add broker/live trading, add scheduler behavior, or make paper-PnL, "
        "profitability, acceptance, Strategy v2 superiority, or live-readiness "
        "claims.",
        "",
        "## Inputs",
        "",
        f"- Source export dir: `{source['source_export_dir']}`",
        f"- Historical file: `{report['historical_file']}`",
        f"- Manifest status: `{source['manifest_status']}`",
        f"- Markets status: `{source['markets_status']}`",
        f"- Candlesticks status: `{source['candlesticks_status']}`",
        "",
        "## Source Metadata Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Discovered candidate markets | {source['discovered_market_count']} |",
        f"| Selected markets | {source['selected_market_count']} |",
        f"| Historical rows | {source['historical_row_count']} |",
        f"| Candlestick rows | {source['candle_row_count']} |",
        f"| Target markets | {source['target_market_count']} |",
        f"| Target rows | {source['target_row_count']} |",
        f"| Rows per market target | {source['rows_per_market_target']} |",
        f"| Max candle-market attempts | {source['max_candle_market_attempts']} |",
        "",
        "Raw source category distribution from selected market metadata:",
        "",
    ]
    lines.extend(_counter_lines(source["raw_source_category_distribution"]))
    lines.extend(
        [
            "",
            "Semantic category distribution from heuristic title/ticker/rules checks:",
            "",
        ]
    )
    lines.extend(_counter_lines(checks["semantic_category_distribution"]))
    lines.extend(
        [
            "",
            "## Label Comparison Findings",
            "",
            f"- Suspected category mismatches: {checks['suspected_category_mismatch_count']}",
            f"- Sports assigned to weather/fed-policy labels: {checks['sports_assigned_to_weather_or_fed_count']}",
            f"- Weather-looking markets assigned elsewhere: {checks['weather_assigned_elsewhere_count']}",
            f"- Fed/macro-looking markets assigned elsewhere: {checks['fed_macro_assigned_elsewhere_count']}",
            f"- Public-event catch-all overuse: {checks['public_event_catch_all_overuse_count']}",
            f"- Topic keyword mention markets: {checks['topic_keyword_mention_market_count']}",
            "",
            "Heuristic warnings are taxonomy QA signals, not hard truth.",
            "",
            "Sample suspected mismatches:",
            "",
        ]
    )
    lines.extend(_market_warning_lines(checks["suspected_category_mismatches"][:15]))
    lines.extend(
        [
            "",
            "Public-event catch-all samples:",
            "",
        ]
    )
    lines.extend(_market_warning_lines(checks["public_event_catch_all_overuse"][:15]))
    lines.extend(
        [
            "",
            "Topic keyword mention samples:",
            "",
        ]
    )
    lines.extend(_market_warning_lines(checks["topic_keyword_mention_markets"][:15]))
    lines.extend(
        [
            "",
            "## Availability Diagnosis",
            "",
            f"- Primary blocker: `{diagnosis['primary_blocker']}`",
            f"- True source scarcity: `{diagnosis['true_source_scarcity']['status']}`",
            f"- Taxonomy mismatch: `{diagnosis['taxonomy_mismatch']['status']}`",
            f"- Filter bottleneck: `{diagnosis['filter_bottleneck']['status']}`",
            f"- Candlestick bottleneck: `{diagnosis['candlestick_availability_bottleneck']['status']}`",
            f"- Row-count bottleneck: `{diagnosis['row_count_bottleneck']['status']}`",
            f"- Warnings: {_warnings(diagnosis['warnings'])}",
            "",
            diagnosis["interpretation"],
            "",
            "Quota shortfalls:",
            "",
        ]
    )
    if diagnosis["quota_shortfalls"]:
        lines.extend(
            "- "
            f"`{item['category']}` selected={item['selected_markets']} "
            f"quota={item['quota_markets']} missing={item['missing_markets']}"
            for item in diagnosis["quota_shortfalls"]
        )
    else:
        lines.append("None.")
    row_bottleneck = diagnosis["row_count_bottleneck"]
    lines.extend(
        [
            "",
            "Row-count bottleneck detail:",
            "",
            f"- Ideal rows for selected markets: {row_bottleneck['ideal_rows_for_selected_markets']}",
            f"- Actual rows: {row_bottleneck['actual_rows']}",
            f"- Shortfall versus selected-market target: {row_bottleneck['row_shortfall_vs_selected_markets']}",
            f"- Shortfall versus full target: {row_bottleneck['row_shortfall_vs_target']}",
            "",
            "## Reference Export",
            "",
        ]
    )
    reference = report["reference_export_summary"]
    lines.append(f"- Status: `{reference['status']}`")
    if reference.get("market_count") is not None:
        lines.append(f"- Markets: {reference['market_count']}")
        lines.append(
            f"- Suspected mismatches: {reference['suspected_category_mismatch_count']}"
        )
        lines.append(
            f"- Public-event catch-all overuse: {reference['public_event_catch_all_overuse_count']}"
        )
    lines.extend(
        [
            "",
            "## Recommended Next Step",
            "",
            "Before another category-balanced calibration-only retry, revise the "
            "category taxonomy and collector diagnostics: separate event-format "
            "mention markets from topic categories, add sports/tennis taxonomy "
            "coverage or an explicit non-major-sports bucket, and log pre-candle "
            "candidate category counts plus candle failure reasons. Do not infer "
            "true non-public scarcity or a category calibration effect from the "
            "PR-CAL-8 selected export alone.",
            "",
            "## Guardrails",
            "",
            "| Guardrail | Value |",
            "| --- | --- |",
        ]
    )
    for name, value in guardrails.items():
        lines.append(f"| `{name}` | `{value}` |")
    lines.append("")
    return "\n".join(lines)


def _counter_lines(counter: dict[str, Any]) -> list[str]:
    if not counter:
        return ["- none"]
    return [f"- `{name}`: {count}" for name, count in sorted(counter.items())]


def _market_warning_lines(markets: list[dict[str, Any]]) -> list[str]:
    if not markets:
        return ["None."]
    lines = [
        "| Ticker | Source | Inferred | Mention | Warnings | Title |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for market in markets:
        title = str(market["title"]).replace("|", "/")
        if len(title) > 110:
            title = f"{title[:107]}..."
        lines.append(
            f"| `{market['ticker']}` | `{market['source_category']}` | "
            f"`{market['inferred_semantic_category']}` | "
            f"`{market['mention_market']}` | "
            f"{_warnings(market['warnings'])} | {title} |"
        )
    return lines
