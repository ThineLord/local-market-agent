from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from local_market_agent.eval.category_normalization import (
    NORMALIZED_ECONOMICS_OTHER,
    NORMALIZED_FED_POLICY_MACRO,
    NORMALIZED_UNKNOWN,
    NORMALIZED_WEATHER,
    normalize_market_category,
)

DEFAULT_DOCS_REPORT_PATH = Path("docs/reports/kalshi_normalized_availability_audit.md")
BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
DISCOVERY_FAMILIES = ("live_settled_markets", "historical_markets")
ALLOWED_STATUS = {"settled", "finalized"}
ALLOWED_OUTCOMES = {"yes", "no"}
MIN_PROBE_CANDLES_PER_MARKET = 4
DEFAULT_PROBE_CATEGORY = NORMALIZED_WEATHER
DEFAULT_PROBE_LIMIT = 50
DEFAULT_TIMEOUT_SECONDS = 4.0
DEFAULT_PERIOD_INTERVAL = 60

WARNING_DIAGNOSTICS_MISSING = "collector_diagnostics_missing_warning"
WARNING_UNSELECTED_CANDIDATES_NOT_PERSISTED = "unselected_candidate_examples_missing_warning"
WARNING_WEATHER_CANDLE_OR_ALLOCATION = "weather_candle_sparsity_or_allocation_warning"
WARNING_FED_MACRO_TAXONOMY_GAP = "fed_macro_taxonomy_coverage_gap_warning"

FED_MACRO_DIAGNOSTIC_RULES = (
    ("fed", r"\bfed\b|\bfederal reserve\b|\bfomc\b"),
    ("rates", r"\binterest rates?\b|\brate cut\b|\brate hike\b|\bcut rates?\b"),
    ("inflation", r"\bcpi\b|\bppi\b|\bpce\b|\binflation\b"),
    ("treasury", r"\btreasury\b|\byields?\b"),
    ("labor", r"\bunemployment\b|\bjobless claims\b|\bjobs report\b|\bpayrolls?\b"),
    ("growth", r"\bgdp\b|\bretail sales\b"),
    ("fed_speaker", r"\bpowell\b|\bgoolsbee\b|\bbowman\b|\bwaller\b"),
)
FED_POLICY_DIAGNOSTIC_RULE_NAMES = frozenset(
    {"fed", "rates", "inflation", "fed_speaker"}
)


@dataclass(frozen=True)
class NormalizedAvailabilityAuditArtifacts:
    json_path: Path
    markdown_path: Path
    docs_markdown_path: Path | None = None


@dataclass(frozen=True)
class NormalizedAvailabilityAuditResult:
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


@dataclass(frozen=True)
class ProbeCandidate:
    ticker: str
    title: str
    source_family: str
    raw: dict[str, Any]
    settlement_ts: str
    volume: float
    normalized_category: str
    semantic_category: str
    source_category: str


class KalshiPublicProbeClient:
    def __init__(self, base_url: str = BASE_URL, *, timeout_seconds: float = 4.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.requested_urls: list[str] = []

    def get_json(self, path: str, params: dict[str, object]) -> dict[str, Any]:
        encoded_params = urllib.parse.urlencode(params)
        url = f"{self.base_url}{path}"
        if encoded_params:
            url = f"{url}?{encoded_params}"
        self.requested_urls.append(url)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "local-market-agent-pr-cal-12-audit/temporary"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Kalshi public GET failed {exc.code} for {url}: {details}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Kalshi public GET failed for {url}: {exc}") from exc
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise RuntimeError(f"Kalshi public GET returned non-object JSON for {url}")
        return parsed


def run_normalized_availability_audit(
    source_export_dir: str | Path,
    *,
    probe_candles: bool = False,
    probe_category: str = DEFAULT_PROBE_CATEGORY,
    probe_limit: int = DEFAULT_PROBE_LIMIT,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    period_interval: int = DEFAULT_PERIOD_INTERVAL,
    probe_client: Any | None = None,
) -> NormalizedAvailabilityAuditResult:
    export_dir = Path(source_export_dir)
    if not export_dir.exists():
        msg = f"source export directory not found: {export_dir}"
        raise ValueError(msg)

    manifest_path = export_dir / "source_manifest.json"
    markets_path = export_dir / "markets.jsonl"
    candlesticks_path = export_dir / "candlesticks.jsonl"
    diagnostics_path = export_dir / "collector_diagnostics.json"
    unselected_path = export_dir / "unselected_candidates.jsonl"
    unselected_summary_path = export_dir / "unselected_candidates_summary.md"

    manifest = _load_json_optional(manifest_path)
    markets = _load_jsonl_optional(markets_path)
    candles = _load_jsonl_optional(candlesticks_path)
    unselected_candidates = _load_jsonl_optional(unselected_path)
    diagnostics, diagnostics_status = _load_collector_diagnostics(
        manifest=manifest,
        diagnostics_path=diagnostics_path,
    )

    selected_records = _selected_market_records(markets=markets, candles=candles)
    unselected_records = _unselected_candidate_records(unselected_candidates)
    combined_candidate_records = [*selected_records, *unselected_records]
    category_analysis = _category_analysis(
        diagnostics=diagnostics,
        selected_records=selected_records,
        candles=candles,
        unselected_records=unselected_records,
    )
    selected_summary = _selected_summary(selected_records)
    weather_examples = _category_examples(
        combined_candidate_records,
        NORMALIZED_WEATHER,
        limit=10,
    )
    fed_false_negatives = _fed_macro_false_negative_candidates(combined_candidate_records)

    probe = _empty_probe_result(
        enabled=probe_candles,
        probe_category=probe_category,
        probe_limit=probe_limit,
    )
    if probe_candles:
        client = probe_client or KalshiPublicProbeClient(timeout_seconds=timeout_seconds)
        probe = _run_probe(
            client=client,
            probe_category=probe_category,
            probe_limit=probe_limit,
            period_interval=period_interval,
        )

    weather_diagnosis = _weather_diagnosis(
        category_analysis=category_analysis,
        diagnostics=diagnostics,
        probe=probe,
        weather_example_count=len(weather_examples),
    )
    fed_macro_diagnosis = _fed_macro_diagnosis(
        category_analysis=category_analysis,
        fed_false_negatives=fed_false_negatives,
        unselected_candidate_count=len(unselected_records),
    )
    conclusions = _conclusions(
        weather_diagnosis=weather_diagnosis,
        fed_macro_diagnosis=fed_macro_diagnosis,
        diagnostics_status=diagnostics_status,
    )

    report = {
        "report_id": f"normalized_availability_audit_{_safe_filename(export_dir.name)}",
        "phase": "PR-CAL-12",
        "created_at": datetime.now(UTC).isoformat(),
        "source_export": {
            "export_id": _text(manifest.get("export_id")) or export_dir.name,
            "source_export_dir": str(export_dir),
            "manifest_path": str(manifest_path),
            "markets_path": str(markets_path),
            "candlesticks_path": str(candlesticks_path),
            "collector_diagnostics_path": str(diagnostics_path),
            "unselected_candidates_path": str(unselected_path),
            "unselected_candidates_summary_path": str(unselected_summary_path),
            "manifest_status": "loaded" if manifest else "missing",
            "markets_status": "loaded" if markets else "missing",
            "candlesticks_status": "loaded" if candles else "missing",
            "collector_diagnostics_status": diagnostics_status,
            "unselected_candidates_status": "loaded"
            if unselected_path.exists()
            else "missing",
            "unselected_candidates_summary_status": "loaded"
            if unselected_summary_path.exists()
            else "missing",
            "selected_market_count": len(markets),
            "unselected_candidate_count": len(unselected_candidates),
            "candlestick_row_count": len(candles),
            "collection_summary": _dict(manifest.get("collection_summary")),
            "safety": _dict(manifest.get("safety")),
        },
        "diagnostics_summary": _diagnostics_summary(diagnostics, diagnostics_status),
        "selected_category_summary": selected_summary,
        "unselected_candidate_summary": _unselected_summary(unselected_records),
        "category_availability": category_analysis,
        "weather_candidate_examples": weather_examples,
        "fed_macro_false_negative_candidates": fed_false_negatives,
        "weather_availability_diagnosis": weather_diagnosis,
        "fed_macro_taxonomy_diagnosis": fed_macro_diagnosis,
        "probe": probe,
        "conclusions": conclusions,
        "guardrails": _guardrails(probe_candles=probe_candles),
    }
    return NormalizedAvailabilityAuditResult(report=report)


def write_normalized_availability_audit_reports(
    result: NormalizedAvailabilityAuditResult,
    output_dir: str | Path,
    *,
    docs_markdown_path: str | Path | None = DEFAULT_DOCS_REPORT_PATH,
) -> NormalizedAvailabilityAuditArtifacts:
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    safe_export_id = _safe_filename(result.export_id)
    json_path = report_dir / f"{safe_export_id}.normalized_availability_audit.json"
    markdown_path = report_dir / f"{safe_export_id}_normalized_availability_audit.md"
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

    return NormalizedAvailabilityAuditArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        docs_markdown_path=docs_path,
    )


def _load_collector_diagnostics(
    *,
    manifest: dict[str, Any],
    diagnostics_path: Path,
) -> tuple[dict[str, Any], str]:
    if diagnostics_path.exists():
        payload = _load_json_optional(diagnostics_path)
        if payload:
            return payload, "loaded_from_export_json"
    manifest_diagnostics = manifest.get("collector_diagnostics")
    if isinstance(manifest_diagnostics, dict) and manifest_diagnostics:
        return manifest_diagnostics, "loaded_from_manifest"
    return {}, "missing"


def _selected_market_records(
    *,
    markets: list[dict[str, Any]],
    candles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candles_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candle in candles:
        candles_by_market[_text(candle.get("market_ticker")) or "missing"].append(candle)

    records = []
    for market in markets:
        ticker = _market_ticker(market)
        normalization = normalize_market_category(market)
        metadata = _dict(market.get("metadata"))
        normalized_category = (
            _text(metadata.get("normalized_category"))
            or _text(metadata.get("calibration_category"))
            or normalization.normalized_category
        )
        semantic_category = _text(metadata.get("semantic_category")) or normalization.semantic_category
        source_category = _text(metadata.get("source_category")) or normalization.source_category
        rows = candles_by_market.get(ticker, [])
        fed_macro_rules = _matched_rule_names(_market_text(market), FED_MACRO_DIAGNOSTIC_RULES)
        records.append(
            {
                "ticker": ticker,
                "title": _text(market.get("title")) or "missing",
                "event_ticker": _text(market.get("event_ticker"))
                or _text(metadata.get("event_ticker"))
                or "missing",
                "series_ticker": _text(market.get("series_ticker")) or "missing",
                "source_family": _text(metadata.get("source_family")) or "missing",
                "source_category": source_category,
                "normalized_category": normalized_category,
                "semantic_category": semantic_category,
                "is_mention_market": bool(metadata.get("is_mention_market"))
                or normalization.is_mention_market,
                "normalization_warnings": _list(metadata.get("normalization_warnings"))
                or list(normalization.warnings),
                "row_count": len(rows),
                "fed_macro_diagnostic_rules": fed_macro_rules,
                "status": _text(market.get("status")) or "missing",
                "market_type": _text(metadata.get("market_type"))
                or _text(market.get("market_type"))
                or "missing",
            }
        )
    return sorted(records, key=lambda row: (row["normalized_category"], row["ticker"]))


def _unselected_candidate_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for row in rows:
        ticker = _text(row.get("ticker")) or "missing"
        title = _text(row.get("title")) or "missing"
        normalized_category = _text(row.get("normalized_category")) or "unknown"
        semantic_category = _text(row.get("semantic_category")) or "unknown"
        source_category = _text(row.get("source_category")) or "unknown"
        records.append(
            {
                "ticker": ticker,
                "title": title,
                "event_ticker": _text(row.get("event_ticker")) or "missing",
                "series_ticker": _text(row.get("series_ticker")) or "missing",
                "source_family": _text(row.get("source_family")) or "missing",
                "source_category": source_category,
                "normalized_category": normalized_category,
                "semantic_category": semantic_category,
                "is_mention_market": bool(row.get("is_mention_market")),
                "normalization_warnings": _list(row.get("warnings")),
                "row_count": 0,
                "fed_macro_diagnostic_rules": _matched_rule_names(
                    " ".join(
                        text
                        for text in (
                            ticker,
                            title,
                            _text(row.get("reason")) or "",
                        )
                        if text
                    ),
                    FED_MACRO_DIAGNOSTIC_RULES,
                ),
                "status": "unselected_candidate",
                "market_type": "diagnostic_only",
                "candidate_selection_status": "unselected",
            }
        )
    return sorted(records, key=lambda row: (row["normalized_category"], row["ticker"]))


def _selected_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_category[str(record["normalized_category"])].append(record)

    summary = {}
    for category, items in sorted(by_category.items()):
        row_counts = [int(item["row_count"]) for item in items]
        summary[category] = {
            "market_count": len(items),
            "row_count": sum(row_counts),
            "rows_per_market_min": min(row_counts) if row_counts else 0,
            "rows_per_market_max": max(row_counts) if row_counts else 0,
            "rows_per_market_mean": _safe_div(sum(row_counts), len(row_counts)),
            "top_markets_by_rows": [
                {
                    "ticker": item["ticker"],
                    "title": item["title"],
                    "row_count": item["row_count"],
                }
                for item in sorted(items, key=lambda row: (-int(row["row_count"]), row["ticker"]))[:10]
            ],
        }
    return summary


def _unselected_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(record["normalized_category"]) for record in records)
    return {
        "candidate_count": len(records),
        "category_counts": dict(sorted(counts.items())),
        "samples": [
            {
                "ticker": record["ticker"],
                "title": record["title"],
                "normalized_category": record["normalized_category"],
                "semantic_category": record["semantic_category"],
            }
            for record in records[:25]
        ],
        "diagnostics_only": True,
        "not_imported_as_historical_rows": True,
    }


def _category_analysis(
    *,
    diagnostics: dict[str, Any],
    selected_records: list[dict[str, Any]],
    candles: list[dict[str, Any]],
    unselected_records: list[dict[str, Any]],
) -> dict[str, Any]:
    pre_counts = _counter_dict(diagnostics.get("pre_filter_category_counts"))
    post_counts = _counter_dict(diagnostics.get("post_filter_category_counts"))
    selected_counts = _counter_dict(diagnostics.get("selected_category_counts"))
    quota_targets = _counter_dict(diagnostics.get("quota_targets"))
    quota_shortfalls = _counter_dict(diagnostics.get("quota_shortfalls"))
    quota_filled = _counter_dict(diagnostics.get("quota_filled"))
    per_category = _dict(diagnostics.get("per_category"))
    per_category_selected_rows = _counter_dict(
        diagnostics.get("per_category_selected_row_counts")
    )
    selected_from_markets = Counter(str(record["normalized_category"]) for record in selected_records)
    unselected_counts = Counter(str(record["normalized_category"]) for record in unselected_records)
    rows_by_market = Counter(_text(candle.get("market_ticker")) or "missing" for candle in candles)
    category_by_market = {
        str(record["ticker"]): str(record["normalized_category"])
        for record in selected_records
    }
    row_counts: Counter[str] = Counter()
    market_row_counts: dict[str, list[int]] = defaultdict(list)
    for ticker, count in rows_by_market.items():
        category = category_by_market.get(ticker)
        if not category:
            continue
        row_counts[category] += count
        market_row_counts[category].append(count)

    categories = set(pre_counts) | set(post_counts) | set(selected_counts) | set(quota_targets)
    categories.update(unselected_counts)
    categories.update({NORMALIZED_WEATHER, NORMALIZED_FED_POLICY_MACRO, NORMALIZED_ECONOMICS_OTHER, NORMALIZED_UNKNOWN})
    analysis: dict[str, Any] = {}
    for category in sorted(categories):
        quota = quota_targets.get(category, 0)
        selected = selected_counts.get(category, selected_from_markets.get(category, 0))
        post = post_counts.get(category, 0)
        pre = pre_counts.get(category, 0)
        row_total = row_counts.get(category, 0)
        row_values = market_row_counts.get(category, [])
        analysis[category] = {
            "category": category,
            "quota_target": quota,
            "quota_filled": quota_filled.get(category, selected),
            "quota_shortfall": quota_shortfalls.get(category, max(0, quota - selected)),
            "pre_filter_count": pre,
            "post_filter_count": post,
            "selected_market_count": selected,
            "selected_row_count": per_category_selected_rows.get(category, row_total),
            "unselected_example_count": unselected_counts.get(category, 0),
            "per_category_diagnostics": _dict(per_category.get(category))
            if isinstance(per_category, dict)
            else {},
            "rows_per_selected_market_mean": _safe_div(row_total, selected),
            "rows_per_selected_market_min": min(row_values) if row_values else 0,
            "rows_per_selected_market_max": max(row_values) if row_values else 0,
            "post_filter_to_quota_ratio": _safe_div(post, quota),
            "selected_to_post_filter_ratio": _safe_div(selected, post),
            "candidate_count_available": bool(pre_counts or post_counts),
        }
    return analysis


def _diagnostics_summary(
    diagnostics: dict[str, Any],
    diagnostics_status: str,
) -> dict[str, Any]:
    attempts = _int_or_zero(diagnostics.get("candle_attempt_count"))
    successes = _int_or_zero(diagnostics.get("candle_success_count"))
    failures = _int_or_zero(diagnostics.get("candle_failure_count"))
    return {
        "status": diagnostics_status,
        "discovered_count": _int_or_zero(diagnostics.get("discovered_count")),
        "pre_filter_category_counts": _counter_dict(diagnostics.get("pre_filter_category_counts")),
        "post_filter_category_counts": _counter_dict(diagnostics.get("post_filter_category_counts")),
        "selected_category_counts": _counter_dict(diagnostics.get("selected_category_counts")),
        "quota_targets": _counter_dict(diagnostics.get("quota_targets")),
        "quota_filled": _counter_dict(diagnostics.get("quota_filled")),
        "quota_shortfalls": _counter_dict(diagnostics.get("quota_shortfalls")),
        "candle_attempt_count": attempts,
        "candle_success_count": successes,
        "candle_failure_count": failures,
        "candle_success_rate": _safe_div(successes, attempts),
        "candle_failure_rate": _safe_div(failures, attempts),
        "candle_failure_reasons": _counter_dict(diagnostics.get("candle_failure_reasons")),
        "per_category": _dict(diagnostics.get("per_category")),
        "per_category_candle_attempt_counts": _counter_dict(
            diagnostics.get("per_category_candle_attempt_counts")
        ),
        "per_category_candle_success_counts": _counter_dict(
            diagnostics.get("per_category_candle_success_counts")
        ),
        "per_category_candle_failure_counts": _counter_dict(
            diagnostics.get("per_category_candle_failure_counts")
        ),
        "per_category_candle_failure_reasons": _dict(
            diagnostics.get("per_category_candle_failure_reasons")
        ),
        "filter_losses": _dict(diagnostics.get("filter_losses")),
        "warnings": [] if diagnostics else [WARNING_DIAGNOSTICS_MISSING],
    }


def _weather_diagnosis(
    *,
    category_analysis: dict[str, Any],
    diagnostics: dict[str, Any],
    probe: dict[str, Any],
    weather_example_count: int,
) -> dict[str, Any]:
    weather = category_analysis.get(NORMALIZED_WEATHER, {})
    quota = _int_or_zero(weather.get("quota_target"))
    post_count = _int_or_zero(weather.get("post_filter_count"))
    selected_count = _int_or_zero(weather.get("selected_market_count"))
    shortfall = _int_or_zero(weather.get("quota_shortfall"))
    attempts = _int_or_zero(diagnostics.get("candle_attempt_count"))
    failures = _int_or_zero(diagnostics.get("candle_failure_count"))
    failure_rate = _safe_div(failures, attempts)
    category_diagnostics = _dict(weather.get("per_category_diagnostics"))
    category_attempts = _int_or_zero(category_diagnostics.get("candle_attempt_count"))
    category_failures = _int_or_zero(category_diagnostics.get("candle_failure_count"))
    category_successes = _int_or_zero(category_diagnostics.get("candle_success_count"))

    if shortfall <= 0:
        primary = "no_weather_shortfall_detected"
    elif category_attempts > 0 and category_successes == 0 and category_failures:
        primary = "weather_candle_sparsity_supported_by_per_category_diagnostics"
    elif post_count >= quota and selected_count < quota and failure_rate >= 0.5:
        primary = "candle_sparsity_or_attempt_allocation"
    elif post_count >= quota and selected_count < quota:
        primary = "selection_or_candle_allocation"
    elif post_count < quota:
        primary = "source_or_filter_availability"
    else:
        primary = "unknown"

    if probe.get("enabled") and probe.get("probe_category") == NORMALIZED_WEATHER:
        success_rate = float(probe.get("success_rate") or 0.0)
        if success_rate == 0.0 and _int_or_zero(probe.get("attempted_markets")):
            primary = "weather_candle_sparsity_supported_by_probe"
        elif success_rate < 0.2 and _int_or_zero(probe.get("attempted_markets")):
            primary = "weather_candle_sparsity_likely"
        elif _int_or_zero(probe.get("successful_markets")) >= shortfall:
            primary = "weather_allocation_budget_likely"

    warnings = []
    if shortfall > 0 and post_count >= quota:
        warnings.append(WARNING_WEATHER_CANDLE_OR_ALLOCATION)
    if (
        weather_example_count == 0
        and not _category_examples_from_probe_or_selected(probe, NORMALIZED_WEATHER)
    ):
        warnings.append(WARNING_UNSELECTED_CANDIDATES_NOT_PERSISTED)

    return {
        "primary_diagnosis": primary,
        "quota_target": quota,
        "selected_market_count": selected_count,
        "quota_shortfall": shortfall,
        "pre_filter_count": _int_or_zero(weather.get("pre_filter_count")),
        "post_filter_count": post_count,
        "global_candle_attempt_count": attempts,
        "global_candle_failure_count": failures,
        "global_candle_failure_rate": failure_rate,
        "weather_candle_attempt_count": category_attempts,
        "weather_candle_success_count": category_successes,
        "weather_candle_failure_count": category_failures,
        "weather_candle_failure_reasons": _dict(
            category_diagnostics.get("candle_failure_reasons")
        ),
        "per_category_failure_logs_available": bool(category_diagnostics)
        or bool(probe.get("enabled")),
        "probe_summary": _probe_brief(probe) if probe.get("enabled") else {},
        "true_weather_source_scarcity_proven": False,
        "interpretation": _weather_interpretation(primary),
        "warnings": list(dict.fromkeys(warnings)),
    }


def _fed_macro_diagnosis(
    *,
    category_analysis: dict[str, Any],
    fed_false_negatives: list[dict[str, Any]],
    unselected_candidate_count: int,
) -> dict[str, Any]:
    fed = category_analysis.get(NORMALIZED_FED_POLICY_MACRO, {})
    economics = category_analysis.get(NORMALIZED_ECONOMICS_OTHER, {})
    unknown = category_analysis.get(NORMALIZED_UNKNOWN, {})
    quota = _int_or_zero(fed.get("quota_target"))
    pre_count = _int_or_zero(fed.get("pre_filter_count"))
    post_count = _int_or_zero(fed.get("post_filter_count"))
    selected_count = _int_or_zero(fed.get("selected_market_count"))
    shortfall = _int_or_zero(fed.get("quota_shortfall"))
    adjacent_count = _int_or_zero(economics.get("post_filter_count")) + _int_or_zero(
        unknown.get("post_filter_count")
    )

    if shortfall <= 0:
        primary = "no_fed_macro_shortfall_detected"
    elif fed_false_negatives:
        primary = (
            "taxonomy_false_negatives_supported"
            if _fed_policy_candidate_count(fed_false_negatives)
            else "taxonomy_boundary_review_supported"
        )
    elif pre_count == 0 and post_count == 0 and adjacent_count > 0:
        primary = (
            "fed_policy_candidates_absent_in_retained_diagnostics"
            if unselected_candidate_count
            else "taxonomy_coverage_or_candidate_persistence_gap"
        )
    elif post_count < quota:
        primary = "source_availability_or_discovery_gap"
    elif selected_count < quota:
        primary = "candle_or_allocation_gap"
    else:
        primary = "unknown"

    suggested_rules = _suggested_fed_rule_additions(fed_false_negatives)
    if not suggested_rules and shortfall > 0 and unselected_candidate_count == 0:
        suggested_rules = [
            "persist unselected economics_other and unknown candidate examples before changing rules",
            "keep fed_policy_macro separate from generic economics_other unless deterministic Fed/rate/CPI/FOMC signals are present",
        ]
    elif not suggested_rules and shortfall > 0:
        suggested_rules = [
            "review retained economics_other and unknown examples before changing rules",
            "keep fed_policy_macro separate from generic economics_other unless deterministic Fed/rate/CPI/FOMC signals are present",
        ]

    warnings = []
    if shortfall > 0:
        warnings.append(WARNING_FED_MACRO_TAXONOMY_GAP)
    if adjacent_count > 0 and not fed_false_negatives and unselected_candidate_count == 0:
        warnings.append(WARNING_UNSELECTED_CANDIDATES_NOT_PERSISTED)

    return {
        "primary_diagnosis": primary,
        "quota_target": quota,
        "selected_market_count": selected_count,
        "quota_shortfall": shortfall,
        "pre_filter_count": pre_count,
        "post_filter_count": post_count,
        "economics_other_post_filter_count": _int_or_zero(economics.get("post_filter_count")),
        "unknown_post_filter_count": _int_or_zero(unknown.get("post_filter_count")),
        "adjacent_macro_or_unknown_post_filter_count": adjacent_count,
        "false_negative_candidate_count": _fed_policy_candidate_count(
            fed_false_negatives
        ),
        "macro_boundary_candidate_count": len(fed_false_negatives),
        "source_scarcity_proven": False if adjacent_count or fed_false_negatives else post_count < quota,
        "semantic_rule_gap_supported": bool(_fed_policy_candidate_count(fed_false_negatives)),
        "suggested_normalization_rule_additions": suggested_rules,
        "interpretation": _fed_interpretation(primary),
        "warnings": list(dict.fromkeys(warnings)),
    }


def _conclusions(
    *,
    weather_diagnosis: dict[str, Any],
    fed_macro_diagnosis: dict[str, Any],
    diagnostics_status: str,
) -> dict[str, Any]:
    weather_primary = str(weather_diagnosis["primary_diagnosis"])
    fed_primary = str(fed_macro_diagnosis["primary_diagnosis"])
    larger_retry = (
        weather_primary
        in {
            "weather_allocation_budget_likely",
            "selection_or_candle_allocation",
            "candle_sparsity_or_attempt_allocation",
        }
        and fed_primary
        in {
            "taxonomy_false_negatives_supported",
            "taxonomy_boundary_review_supported",
            "taxonomy_coverage_or_candidate_persistence_gap",
            "source_availability_or_discovery_gap",
        }
    )
    return {
        "weather_failure_explained_by": weather_primary,
        "fed_macro_failure_explained_by": fed_primary,
        "diagnostics_complete_enough_for_true_scarcity_claim": False,
        "diagnostics_status": diagnostics_status,
        "larger_retry_justified": bool(larger_retry),
        "larger_retry_condition": (
            "Justified only after PR-CAL-13 adds candidate persistence and "
            "per-category candle allocation diagnostics; do not interpret this "
            "audit as category-effect evidence."
        ),
        "recommended_pr_cal_13_action": (
            "Add candidate-level normalized discovery persistence, per-category "
            "candle attempt/failure logging, and deterministic fed/macro rule "
            "tests before a larger calibration-only retry."
        ),
    }


def _fed_macro_false_negative_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for record in records:
        category = str(record["normalized_category"])
        if category not in {NORMALIZED_ECONOMICS_OTHER, NORMALIZED_UNKNOWN}:
            continue
        matches = list(record["fed_macro_diagnostic_rules"])
        if not matches:
            continue
        candidates.append(
            {
                "ticker": record["ticker"],
                "title": record["title"],
                "normalized_category": category,
                "semantic_category": record["semantic_category"],
                "matched_fed_macro_rules": matches,
                "suggested_normalized_category": _suggested_candidate_category(
                    matches
                ),
                "boundary_type": _candidate_boundary_type(matches),
                "heuristic_not_hard_truth": True,
            }
        )
    return sorted(candidates, key=lambda item: (item["normalized_category"], item["ticker"]))[:25]


def _fed_policy_candidate_count(candidates: list[dict[str, Any]]) -> int:
    return sum(
        1
        for candidate in candidates
        if candidate.get("suggested_normalized_category") == NORMALIZED_FED_POLICY_MACRO
    )


def _suggested_candidate_category(matches: list[str]) -> str:
    if any(match in FED_POLICY_DIAGNOSTIC_RULE_NAMES for match in matches):
        return NORMALIZED_FED_POLICY_MACRO
    return NORMALIZED_ECONOMICS_OTHER


def _candidate_boundary_type(matches: list[str]) -> str:
    if any(match in FED_POLICY_DIAGNOSTIC_RULE_NAMES for match in matches):
        return "fed_policy_macro_candidate"
    return "generic_economics_other_candidate"


def _category_examples(
    records: list[dict[str, Any]],
    category: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    return [
        {
            "ticker": record["ticker"],
            "title": record["title"],
            "normalized_category": record["normalized_category"],
            "semantic_category": record["semantic_category"],
            "row_count": record["row_count"],
        }
        for record in records
        if record["normalized_category"] == category
    ][:limit]


def _run_probe(
    *,
    client: Any,
    probe_category: str,
    probe_limit: int,
    period_interval: int,
) -> dict[str, Any]:
    if probe_limit <= 0:
        msg = "probe_limit must be positive when probe_candles is enabled"
        raise ValueError(msg)
    candidates, discovery_summary = _discover_probe_candidates(
        client,
        probe_category=probe_category,
        probe_limit=probe_limit,
    )
    attempted = []
    success_count = 0
    failure_reasons: Counter[str] = Counter()
    for candidate in candidates[:probe_limit]:
        try:
            raw_candles = _fetch_probe_candlesticks(
                client=client,
                candidate=candidate,
                period_interval=period_interval,
            )
        except RuntimeError as exc:
            failure_reasons["candlestick_request_failed"] += 1
            attempted.append(_probe_attempt(candidate, "request_failed", 0, 0, str(exc)))
            continue
        useful_count = _useful_probe_candle_count(candidate, raw_candles)
        if useful_count < MIN_PROBE_CANDLES_PER_MARKET:
            failure_reasons["insufficient_pre_settlement_last_price_candles"] += 1
            attempted.append(
                _probe_attempt(
                    candidate,
                    "insufficient_pre_settlement_last_price_candles",
                    len(raw_candles),
                    useful_count,
                    None,
                )
            )
            continue
        success_count += 1
        attempted.append(_probe_attempt(candidate, "success", len(raw_candles), useful_count, None))
    attempted_count = len(attempted)
    failure_count = attempted_count - success_count
    return {
        "enabled": True,
        "network_used": True,
        "historical_dataset_written": False,
        "historical_rows_imported": False,
        "probe_category": probe_category,
        "probe_limit": probe_limit,
        "period_interval": period_interval,
        "discovery": discovery_summary,
        "attempted_markets": attempted_count,
        "successful_markets": success_count,
        "insufficient_candle_failures": failure_reasons.get(
            "insufficient_pre_settlement_last_price_candles",
            0,
        ),
        "request_failures": failure_reasons.get("candlestick_request_failed", 0),
        "failure_count": failure_count,
        "success_rate": _safe_div(success_count, attempted_count),
        "failure_reasons": dict(sorted(failure_reasons.items())),
        "sample_attempts": attempted[:20],
        "requested_url_count": len(getattr(client, "requested_urls", [])),
        "sample_requested_urls": list(getattr(client, "requested_urls", [])[:5]),
    }


def _empty_probe_result(
    *,
    enabled: bool,
    probe_category: str,
    probe_limit: int,
) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "network_used": False,
        "historical_dataset_written": False,
        "historical_rows_imported": False,
        "probe_category": probe_category,
        "probe_limit": probe_limit,
        "attempted_markets": 0,
        "successful_markets": 0,
        "insufficient_candle_failures": 0,
        "request_failures": 0,
        "failure_count": 0,
        "success_rate": None,
        "failure_reasons": {},
        "sample_attempts": [],
    }


def _discover_probe_candidates(
    client: Any,
    *,
    probe_category: str,
    probe_limit: int,
) -> tuple[list[ProbeCandidate], dict[str, Any]]:
    candidates: list[ProbeCandidate] = []
    seen: set[str] = set()
    scanned = 0
    filtered_out = 0
    normalized_counts: Counter[str] = Counter()
    page_limit = max(1, min(6, probe_limit * 2))
    per_page = min(1000, max(100, probe_limit * 80))
    for source_family in DISCOVERY_FAMILIES:
        cursor: str | None = None
        for _ in range(page_limit):
            payload = client.get_json(
                *_discovery_request(source_family, limit=per_page, cursor=cursor)
            )
            for raw in payload.get("markets", []):
                if not isinstance(raw, dict):
                    continue
                scanned += 1
                normalization = normalize_market_category(raw)
                normalized_counts[normalization.normalized_category] += 1
                candidate = _normalize_probe_candidate(
                    raw,
                    source_family=source_family,
                    normalization_category=normalization.normalized_category,
                    semantic_category=normalization.semantic_category,
                    source_category=normalization.source_category,
                )
                if candidate is None:
                    filtered_out += 1
                    continue
                if candidate.ticker in seen:
                    continue
                seen.add(candidate.ticker)
                if candidate.normalized_category == probe_category:
                    candidates.append(candidate)
            cursor = _text(payload.get("cursor"))
            if not cursor or len(candidates) >= probe_limit:
                break
        if len(candidates) >= probe_limit:
            break
    candidates.sort(
        key=lambda item: (
            -item.volume,
            _parse_timestamp(item.settlement_ts) or datetime.min.replace(tzinfo=UTC),
            item.ticker,
        )
    )
    return candidates[:probe_limit], {
        "scanned_raw_markets": scanned,
        "filtered_out_markets": filtered_out,
        "candidate_count_for_probe_category": len(candidates),
        "normalized_category_counts_seen": dict(sorted(normalized_counts.items())),
        "endpoint_families": list(DISCOVERY_FAMILIES),
        "bounded_probe_not_dataset_collection": True,
    }


def _normalize_probe_candidate(
    raw: dict[str, Any],
    *,
    source_family: str,
    normalization_category: str,
    semantic_category: str,
    source_category: str,
) -> ProbeCandidate | None:
    ticker = _text(raw.get("ticker"))
    title = _text(raw.get("title"))
    status = (_text(raw.get("status")) or "").lower()
    market_type = (_text(raw.get("market_type")) or "binary").lower()
    result = _normalize_outcome(raw.get("result") or raw.get("settlement_value_dollars"))
    settlement_ts = _first_text(
        raw,
        (
            "settlement_ts",
            "latest_expiration_time",
            "expected_expiration_time",
            "close_time",
        ),
    )
    if not ticker or not title:
        return None
    if market_type != "binary" or raw.get("mve_collection_ticker") or raw.get("mve_selected_legs"):
        return None
    if status not in ALLOWED_STATUS:
        return None
    if result not in ALLOWED_OUTCOMES or not settlement_ts:
        return None
    canonical = _canonical_timestamp(settlement_ts)
    if canonical is None:
        return None
    return ProbeCandidate(
        ticker=ticker,
        title=title,
        source_family=source_family,
        raw=raw,
        settlement_ts=canonical,
        volume=_float_or_zero(raw.get("volume_fp") or raw.get("volume")),
        normalized_category=normalization_category,
        semantic_category=semantic_category,
        source_category=source_category,
    )


def _fetch_probe_candlesticks(
    *,
    client: Any,
    candidate: ProbeCandidate,
    period_interval: int,
) -> list[dict[str, Any]]:
    start_ts, end_ts = _candle_window(candidate, period_interval=period_interval)
    if start_ts >= end_ts:
        return []
    params = {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "period_interval": period_interval,
    }
    if candidate.source_family == "historical_markets":
        payload = client.get_json(
            f"/historical/markets/{urllib.parse.quote(candidate.ticker)}/candlesticks",
            params,
        )
        raw_candles = payload.get("candlesticks", [])
    else:
        payload = client.get_json(
            "/markets/candlesticks",
            {"market_tickers": candidate.ticker, **params},
        )
        raw_candles = []
        for item in payload.get("markets", []):
            if isinstance(item, dict) and item.get("market_ticker") == candidate.ticker:
                raw_candles = item.get("candlesticks", [])
                break
    return [row for row in raw_candles if isinstance(row, dict)]


def _useful_probe_candle_count(candidate: ProbeCandidate, candles: list[dict[str, Any]]) -> int:
    cutoff = _market_cutoff(candidate.raw, candidate.settlement_ts)
    seen: set[str] = set()
    useful = 0
    for candle in candles:
        candle_dt = _parse_timestamp(_text(candle.get("end_period_ts")) or "")
        if candle_dt is None or (cutoff is not None and candle_dt >= cutoff):
            continue
        if _nested(candle, "price.close_dollars") is None:
            continue
        canonical = _canonical_timestamp(candle_dt)
        if canonical is None or canonical in seen:
            continue
        seen.add(canonical)
        useful += 1
    return useful


def _probe_attempt(
    candidate: ProbeCandidate,
    status: str,
    raw_candle_count: int,
    useful_candle_count: int,
    error: str | None,
) -> dict[str, Any]:
    return {
        "ticker": candidate.ticker,
        "title": candidate.title,
        "normalized_category": candidate.normalized_category,
        "semantic_category": candidate.semantic_category,
        "source_category": candidate.source_category,
        "source_family": candidate.source_family,
        "status": status,
        "raw_candle_count": raw_candle_count,
        "useful_pre_settlement_last_price_candle_count": useful_candle_count,
        "error": error,
    }


def _discovery_request(
    source_family: str,
    *,
    limit: int,
    cursor: str | None,
) -> tuple[str, dict[str, object]]:
    params: dict[str, object] = {"limit": limit, "mve_filter": "exclude"}
    if cursor:
        params["cursor"] = cursor
    if source_family == "live_settled_markets":
        params["status"] = "settled"
        return "/markets", params
    if source_family == "historical_markets":
        return "/historical/markets", params
    raise ValueError(f"unsupported discovery family: {source_family}")


def _candle_window(candidate: ProbeCandidate, *, period_interval: int) -> tuple[int, int]:
    settlement_dt = _parse_timestamp(candidate.settlement_ts)
    if settlement_dt is None:
        return 0, 0
    open_dt = _parse_timestamp(_first_text(candidate.raw, ("open_time", "created_time")) or "")
    lookback_days = max(2, int((period_interval * 12) / 1440) + 2)
    start_dt = open_dt or settlement_dt - timedelta(days=lookback_days)
    start_dt -= timedelta(minutes=period_interval)
    return int(start_dt.timestamp()), int(settlement_dt.timestamp())


def _market_cutoff(raw: dict[str, Any], settlement_ts: str) -> datetime | None:
    close_dt = _parse_timestamp(_first_text(raw, ("close_time", "expected_expiration_time")) or "")
    settlement_dt = _parse_timestamp(settlement_ts)
    if close_dt is None:
        return settlement_dt
    if settlement_dt is None:
        return close_dt
    return min(close_dt, settlement_dt)


def _suggested_fed_rule_additions(candidates: list[dict[str, Any]]) -> list[str]:
    matched = Counter(
        rule
        for candidate in candidates
        for rule in candidate.get("matched_fed_macro_rules", [])
    )
    suggestions = []
    for rule in sorted(matched):
        if rule in {"fed", "rates", "inflation"}:
            suggestions.append(f"promote clear `{rule}` false negatives to fed_policy_macro")
        else:
            suggestions.append(
                f"review whether `{rule}` should stay economics_other or become fed_policy_macro"
            )
    return suggestions


def _weather_interpretation(primary: str) -> str:
    if primary == "weather_candle_sparsity_supported_by_per_category_diagnostics":
        return (
            "Weather had normalized candidates, and per-category diagnostics show "
            "weather candle attempts failed without any successful selected weather "
            "markets. This supports candle sparsity for the bounded retry."
        )
    if primary == "weather_candle_sparsity_supported_by_probe":
        return (
            "Weather candidates can be discovered, but the bounded probe found "
            "no markets with enough usable pre-settlement last-price candles."
        )
    if primary == "weather_allocation_budget_likely":
        return (
            "Weather candidates with enough candles exist, so the PR-CAL-11 "
            "shortfall is more likely allocation/order budget than true source scarcity."
        )
    if primary in {"candle_sparsity_or_attempt_allocation", "selection_or_candle_allocation"}:
        return (
            "Weather had enough normalized pre/post-filter candidates for the quota, "
            "but PR-CAL-11 selected none while global candle failures were high. "
            "Offline diagnostics point to candle sparsity or attempt allocation, "
            "not proven source scarcity."
        )
    if primary == "source_or_filter_availability":
        return "Weather post-filter candidates were below quota, so source/filter limits remain possible."
    return "No weather shortfall was detected or the supplied logs are insufficient."


def _fed_interpretation(primary: str) -> str:
    if primary == "taxonomy_false_negatives_supported":
        return (
            "Local examples in economics_other/unknown matched Fed or macro keywords, "
            "so deterministic normalization rules should be reviewed before another retry."
        )
    if primary == "taxonomy_boundary_review_supported":
        return (
            "Local economics_other/unknown examples matched generic macro keywords, "
            "but not clear Fed-policy rules. Keep these separate unless deterministic "
            "Fed/rate/CPI/FOMC signals are present."
        )
    if primary == "taxonomy_coverage_or_candidate_persistence_gap":
        return (
            "PR-CAL-11 reported zero fed_policy_macro candidates but many adjacent "
            "economics_other/unknown candidates. Because unselected examples were "
            "not persisted, true source scarcity is not proven."
        )
    if primary == "fed_policy_candidates_absent_in_retained_diagnostics":
        return (
            "Retained unselected candidate diagnostics did not surface deterministic "
            "Fed/rate/CPI/FOMC examples, while normalized fed_policy_macro candidate "
            "counts were zero. This supports clear absence in the bounded discovery "
            "diagnostics, not a calibration category-effect claim."
        )
    if primary == "source_availability_or_discovery_gap":
        return (
            "Fed/macro candidates were below quota in normalized diagnostics. This "
            "may be source availability, discovery coverage, or overly narrow rules."
        )
    if primary == "candle_or_allocation_gap":
        return "Fed/macro candidates existed but were not selected, pointing to candle or allocation limits."
    return "No fed/macro shortfall was detected or the supplied logs are insufficient."


def _probe_brief(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "probe_category": probe.get("probe_category"),
        "attempted_markets": probe.get("attempted_markets"),
        "successful_markets": probe.get("successful_markets"),
        "success_rate": probe.get("success_rate"),
        "insufficient_candle_failures": probe.get("insufficient_candle_failures"),
        "request_failures": probe.get("request_failures"),
    }


def _category_examples_from_probe_or_selected(probe: dict[str, Any], category: str) -> bool:
    if probe.get("probe_category") != category:
        return False
    return bool(probe.get("sample_attempts"))


def _guardrails(*, probe_candles: bool) -> dict[str, bool]:
    return {
        "normalized_availability_audit_only": True,
        "offline_by_default": True,
        "network_used_only_when_probe_enabled": probe_candles,
        "historical_dataset_built": False,
        "historical_rows_imported": False,
        "evidence_collection": False,
        "evidence_approval": False,
        "bid_ask_invention": False,
        "strategy_logic_changed": False,
        "acceptance_gate_changed": False,
        "phase8_started": False,
        "broker_or_live_trading_added": False,
        "scheduler_or_daemon_added": False,
        "paper_pnl_claim": False,
        "profitability_claim": False,
        "acceptance_claim": False,
        "strategy_v2_superiority_claim": False,
        "live_readiness_claim": False,
    }


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


def _market_ticker(market: dict[str, Any]) -> str:
    return _text(market.get("ticker")) or "missing"


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


def _matched_rule_names(text: str, rules: tuple[tuple[str, str], ...]) -> list[str]:
    return [name for name, pattern in rules if re.search(pattern, text.lower())]


def _first_text(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return None


def _normalize_outcome(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    normalized = text.lower()
    if normalized in {"yes", "y", "true", "1", "yes_win", "settled_yes"}:
        return "yes"
    if normalized in {"no", "n", "false", "0", "no_win", "settled_no"}:
        return "no"
    try:
        numeric = float(normalized)
    except ValueError:
        return normalized
    if numeric == 1.0:
        return "yes"
    if numeric == 0.0:
        return "no"
    return None


def _parse_timestamp(value: str | None) -> datetime | None:
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _canonical_timestamp(value: str | datetime | None) -> str | None:
    parsed = value if isinstance(value, datetime) else _parse_timestamp(value)
    if parsed is None:
        return None
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _nested(row: dict[str, Any], dotted_path: str) -> Any:
    current: Any = row
    for key in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _counter_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    items = []
    for key, raw in value.items():
        parsed = _int_or_zero(raw)
        items.append((str(key), parsed))
    return dict(sorted(items))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_zero(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float_or_zero(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_div(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return safe or "normalized_availability_audit"


def _format_pct(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.6f}%"


def _counter_lines(counter: dict[str, Any]) -> list[str]:
    if not counter:
        return ["- none"]
    return [f"- `{key}`: {value}" for key, value in sorted(counter.items())]


def _render_markdown(report: dict[str, Any]) -> str:
    source = report["source_export"]
    diagnostics = report["diagnostics_summary"]
    weather = report["weather_availability_diagnosis"]
    fed = report["fed_macro_taxonomy_diagnosis"]
    probe = report["probe"]
    conclusions = report["conclusions"]
    guardrails = report["guardrails"]
    lines = [
        "# Kalshi Normalized Availability Audit",
        "",
        "Scope: PR-CAL-12 local-only normalized availability and candle allocation "
        "audit. Default mode reads existing local PR-CAL-11 artifacts only. "
        "Optional probe mode may perform bounded public/read-only metadata and "
        "candlestick checks, but it does not build a historical dataset, import "
        "rows, collect or approve evidence, invent bid/ask, change strategy logic, "
        "change acceptance gates, start Phase 8, add broker/live trading, add "
        "scheduler behavior, or make paper-PnL, profitability, acceptance, "
        "Strategy v2 superiority, or live-readiness claims.",
        "",
        "## Inputs",
        "",
        f"- Source export dir: `{source['source_export_dir']}`",
        f"- Manifest status: `{source['manifest_status']}`",
        f"- Markets status: `{source['markets_status']}`",
        f"- Candlesticks status: `{source['candlesticks_status']}`",
        f"- Collector diagnostics status: `{source['collector_diagnostics_status']}`",
        f"- Unselected candidates status: `{source['unselected_candidates_status']}`",
        f"- Unselected candidate count: {source['unselected_candidate_count']}",
        "",
        "## PR-CAL-11 Counts",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Discovered markets | {diagnostics['discovered_count']} |",
        f"| Selected markets | {source['selected_market_count']} |",
        f"| Candlestick rows | {source['candlestick_row_count']} |",
        f"| Candle attempts | {diagnostics['candle_attempt_count']} |",
        f"| Candle successes | {diagnostics['candle_success_count']} |",
        f"| Candle failures | {diagnostics['candle_failure_count']} |",
        f"| Candle success rate | {_format_pct(diagnostics['candle_success_rate'])} |",
        f"| Candle failure rate | {_format_pct(diagnostics['candle_failure_rate'])} |",
        "",
        "Pre-filter normalized category counts:",
        "",
    ]
    lines.extend(_counter_lines(diagnostics["pre_filter_category_counts"]))
    lines.extend(["", "Post-filter normalized category counts:", ""])
    lines.extend(_counter_lines(diagnostics["post_filter_category_counts"]))
    lines.extend(["", "Selected normalized category counts:", ""])
    lines.extend(_counter_lines(diagnostics["selected_category_counts"]))
    lines.extend(["", "Quota shortfalls:", ""])
    lines.extend(_counter_lines(diagnostics["quota_shortfalls"]))
    lines.extend(["", "Candle failure reasons:", ""])
    lines.extend(_counter_lines(diagnostics["candle_failure_reasons"]))

    lines.extend(
        [
            "",
            "## Category Availability",
            "",
            "| Category | Quota | Pre-filter | Post-filter | Selected | Shortfall | Rows | Unselected examples |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for category, stats in sorted(report["category_availability"].items()):
        if category not in {
            NORMALIZED_WEATHER,
            NORMALIZED_FED_POLICY_MACRO,
            NORMALIZED_ECONOMICS_OTHER,
            NORMALIZED_UNKNOWN,
        } and not stats["quota_target"]:
            continue
        lines.append(
            f"| `{category}` | {stats['quota_target']} | {stats['pre_filter_count']} | "
            f"{stats['post_filter_count']} | {stats['selected_market_count']} | "
            f"{stats['quota_shortfall']} | {stats['selected_row_count']} | "
            f"{stats['unselected_example_count']} |"
        )

    unselected = report["unselected_candidate_summary"]
    lines.extend(
        [
            "",
            "## Unselected Candidate Diagnostics",
            "",
            f"- Candidate count: {unselected['candidate_count']}",
            f"- Diagnostics only: {unselected['diagnostics_only']}",
            f"- Not imported as historical rows: {unselected['not_imported_as_historical_rows']}",
            "",
            "Unselected candidate category counts:",
            "",
        ]
    )
    lines.extend(_counter_lines(unselected["category_counts"]))
    lines.extend(["", "Unselected candidate samples:", ""])
    lines.extend(_example_lines(unselected["samples"]))

    lines.extend(
        [
            "",
            "## Weather Diagnosis",
            "",
            f"- Primary diagnosis: `{weather['primary_diagnosis']}`",
            f"- Weather quota target: {weather['quota_target']}",
            f"- Weather post-filter candidates: {weather['post_filter_count']}",
            f"- Weather selected markets: {weather['selected_market_count']}",
            f"- Weather shortfall: {weather['quota_shortfall']}",
            f"- Weather candle attempts: {weather['weather_candle_attempt_count']}",
            f"- Weather candle successes: {weather['weather_candle_success_count']}",
            f"- Weather candle failures: {weather['weather_candle_failure_count']}",
            f"- Interpretation: {weather['interpretation']}",
            f"- True weather source scarcity proven: {weather['true_weather_source_scarcity_proven']}",
            "",
            "Weather selected examples:",
            "",
        ]
    )
    lines.extend(_example_lines(report["weather_candidate_examples"]))

    lines.extend(
        [
            "",
            "## Fed/Macro Diagnosis",
            "",
            f"- Primary diagnosis: `{fed['primary_diagnosis']}`",
            f"- Fed/macro quota target: {fed['quota_target']}",
            f"- Fed/macro pre-filter candidates: {fed['pre_filter_count']}",
            f"- Fed/macro post-filter candidates: {fed['post_filter_count']}",
            f"- Economics-other post-filter candidates: {fed['economics_other_post_filter_count']}",
            f"- Unknown post-filter candidates: {fed['unknown_post_filter_count']}",
            f"- False-negative examples surfaced from selected local metadata: {fed['false_negative_candidate_count']}",
            f"- Source scarcity proven: {fed['source_scarcity_proven']}",
            f"- Interpretation: {fed['interpretation']}",
            "",
            "Fed/macro false-negative examples:",
            "",
        ]
    )
    lines.extend(_example_lines(report["fed_macro_false_negative_candidates"]))
    lines.extend(["", "Suggested normalization diagnostics:", ""])
    lines.extend(f"- {item}" for item in fed["suggested_normalization_rule_additions"])

    lines.extend(
        [
            "",
            "## Optional Probe",
            "",
            f"- Probe enabled: {probe['enabled']}",
            f"- Probe category: `{probe['probe_category']}`",
            f"- Network used: {probe['network_used']}",
            f"- Attempted markets: {probe['attempted_markets']}",
            f"- Successful markets: {probe['successful_markets']}",
            f"- Success rate: {_format_pct(probe['success_rate'])}",
            f"- Insufficient-candle failures: {probe['insufficient_candle_failures']}",
            f"- Request failures: {probe['request_failures']}",
            f"- Historical dataset written: {probe['historical_dataset_written']}",
            f"- Historical rows imported: {probe['historical_rows_imported']}",
            "",
            "Probe sample attempts:",
            "",
        ]
    )
    lines.extend(_example_lines(probe.get("sample_attempts", [])))

    lines.extend(
        [
            "",
            "## Conclusions",
            "",
            f"- Weather failure explained by: `{conclusions['weather_failure_explained_by']}`",
            f"- Fed/macro failure explained by: `{conclusions['fed_macro_failure_explained_by']}`",
            f"- Larger retry justified: {conclusions['larger_retry_justified']}",
            f"- Larger retry condition: {conclusions['larger_retry_condition']}",
            f"- Recommended PR-CAL-13 action: {conclusions['recommended_pr_cal_13_action']}",
            "",
            "## Guardrails",
            "",
        ]
    )
    for key, value in sorted(guardrails.items()):
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    return "\n".join(lines)


def _example_lines(examples: list[dict[str, Any]]) -> list[str]:
    if not examples:
        return ["- none retained in the local selected export/probe output"]
    lines = []
    for example in examples[:10]:
        ticker = example.get("ticker", "missing")
        title = example.get("title", "missing")
        category = example.get("normalized_category") or example.get("status") or "missing"
        lines.append(f"- `{ticker}` ({category}): {title}")
    return lines
