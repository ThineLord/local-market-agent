#!/usr/bin/env python3
"""Collect a local normalized-category Kalshi calibration-only dataset.

This is a temporary PR-CAL-11 public-data helper, not production application
code. It uses only unauthenticated public/read-only Kalshi market and
candlestick endpoints already used by earlier local collectors. It writes a
local staged source export, imports it as calibration-only last-price rows, and
emits collector diagnostics. It does not collect evidence or make acceptance,
superiority, paper-PnL, profitability, or live-readiness claims.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import collect_kalshi_calibration_dataset as base_collector  # noqa: E402
import collect_kalshi_sprint1 as sprint1  # noqa: E402

from local_market_agent.data import import_kalshi_export  # noqa: E402
from local_market_agent.data.historical_validator import PROFILE_CALIBRATION_ONLY  # noqa: E402
from local_market_agent.eval import (  # noqa: E402
    audit_calibration_dataset,
    normalize_market_category,
    write_calibration_audit_reports,
)
from local_market_agent.eval.category_normalization import (  # noqa: E402
    NORMALIZED_FED_POLICY_MACRO,
    NORMALIZED_MENTION_MARKET,
    NORMALIZED_PUBLIC_EVENT_GENERIC,
    NORMALIZED_SPORTS_MAJOR,
    NORMALIZED_SPORTS_TENNIS,
    NORMALIZED_UNKNOWN,
    NORMALIZED_WEATHER,
    NormalizedCategoryResult,
)
from local_market_agent.eval.collector_diagnostics import (  # noqa: E402
    FILTER_LOSS_NON_BINARY,
    FILTER_LOSS_NOT_FINALIZED,
    FILTER_LOSS_OTHER,
    FILTER_LOSS_UNRESOLVED,
    CollectorDiagnostics,
)

SOURCE_NAME = "kalshi_public_market_and_candlestick_api"
SOURCE_TYPE = "public_research_export"
TERMS_REVIEW_DEFAULT = "pending_review"
DEFAULT_OUTPUT_ROOT = Path("data/source_exports/kalshi")
DEFAULT_HISTORICAL_OUTPUT_DIR = Path("data/historical")
DEFAULT_REPORT_DIR = Path("data/reports/calibration")
DEFAULT_EXPORT_ID = "kalshi_normalized_calibration_20260608_public_probe"
DEFAULT_TARGET_MARKETS = 100
DEFAULT_ROWS_PER_MARKET = 12
DEFAULT_MAX_CANDLE_MARKET_ATTEMPTS = 400
DEFAULT_PERIOD_INTERVAL = 60
DEFAULT_TIMEOUT_SECONDS = 4.0
NETWORK_FAILURE_EXIT_CODE = 2
MIN_CANDLES_PER_SELECTED_MARKET = 4
DEFAULT_QUOTAS = {
    NORMALIZED_SPORTS_TENNIS: 30,
    NORMALIZED_SPORTS_MAJOR: 20,
    NORMALIZED_MENTION_MARKET: 20,
    NORMALIZED_WEATHER: 10,
    NORMALIZED_FED_POLICY_MACRO: 10,
    NORMALIZED_PUBLIC_EVENT_GENERIC: 10,
    NORMALIZED_UNKNOWN: 0,
}


@dataclass(frozen=True)
class NormalizedCandidateMarket:
    market: sprint1.CandidateMarket
    normalization: NormalizedCategoryResult

    @property
    def category(self) -> str:
        return self.normalization.normalized_category


@dataclass(frozen=True)
class SelectedMarket:
    candidate: NormalizedCandidateMarket
    period_interval: int
    candles: tuple[dict[str, Any], ...]

    @property
    def market(self) -> sprint1.CandidateMarket:
        return self.candidate.market

    @property
    def category(self) -> str:
        return self.candidate.category


@dataclass(frozen=True)
class NormalizedCalibrationCollectionResult:
    export_id: str
    export_dir: Path
    historical_jsonl: Path | None
    audit_json: Path | None
    audit_markdown: Path | None
    diagnostics_json: Path | None
    diagnostics_markdown: Path | None
    discovered_count: int
    post_filter_count: int
    selected_count: int
    candle_count: int
    category_counts: dict[str, int]
    quotas: dict[str, int]
    target_markets: int
    rows_per_market: int
    availability_limitations: tuple[dict[str, Any], ...]
    non_quota_category_counts: dict[str, int]
    diagnostics: dict[str, Any]
    audit_classification: str | None
    claim_guardrails: dict[str, bool]
    target_status: str
    dry_run: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "export_id": self.export_id,
            "export_dir": str(self.export_dir),
            "historical_jsonl": str(self.historical_jsonl) if self.historical_jsonl else None,
            "audit_json": str(self.audit_json) if self.audit_json else None,
            "audit_markdown": str(self.audit_markdown) if self.audit_markdown else None,
            "diagnostics_json": str(self.diagnostics_json)
            if self.diagnostics_json
            else None,
            "diagnostics_markdown": str(self.diagnostics_markdown)
            if self.diagnostics_markdown
            else None,
            "discovered_count": self.discovered_count,
            "post_filter_count": self.post_filter_count,
            "selected_count": self.selected_count,
            "candle_count": self.candle_count,
            "category_counts": self.category_counts,
            "quotas": self.quotas,
            "target_markets": self.target_markets,
            "rows_per_market": self.rows_per_market,
            "availability_limitations": list(self.availability_limitations),
            "non_quota_category_counts": self.non_quota_category_counts,
            "diagnostics": self.diagnostics,
            "audit_classification": self.audit_classification,
            "claim_guardrails": self.claim_guardrails,
            "target_status": self.target_status,
            "dry_run": self.dry_run,
        }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    export_id = args.export_id or default_export_id()
    quotas = parse_quotas(args.quota)
    client = sprint1.KalshiPublicClient(timeout_seconds=args.timeout_seconds)
    try:
        result = collect_normalized_calibration(
            client=client,
            export_id=export_id,
            output_root=args.output_root,
            historical_output_dir=args.historical_output_dir,
            report_dir=args.report_dir,
            target_markets=args.target_markets,
            rows_per_market=args.rows_per_market,
            quotas=quotas,
            max_candle_market_attempts=args.max_candle_market_attempts,
            period_interval=args.period_interval,
            dry_run=args.dry_run,
        )
    except RuntimeError as exc:
        print(
            json.dumps(
                build_network_failure_diagnostic(
                    exc,
                    client=client,
                    export_id=export_id,
                    output_root=args.output_root,
                ),
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return NETWORK_FAILURE_EXIT_CODE
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect a local normalized-category Kalshi calibration-only dataset."
    )
    parser.add_argument("--export-id", default=DEFAULT_EXPORT_ID)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--historical-output-dir", type=Path, default=DEFAULT_HISTORICAL_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--target-markets", type=positive_int, default=DEFAULT_TARGET_MARKETS)
    parser.add_argument(
        "--rows-per-market",
        type=positive_int,
        default=DEFAULT_ROWS_PER_MARKET,
    )
    parser.add_argument(
        "--quota",
        action="append",
        default=[],
        help="Normalized category quota in the form category=count. May be repeated.",
    )
    parser.add_argument(
        "--max-candle-market-attempts",
        type=positive_int,
        default=DEFAULT_MAX_CANDLE_MARKET_ATTEMPTS,
    )
    parser.add_argument(
        "--period-interval",
        type=positive_int,
        default=DEFAULT_PERIOD_INTERVAL,
    )
    parser.add_argument(
        "--timeout-seconds",
        type=positive_float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def collect_normalized_calibration(
    *,
    client: sprint1.KalshiPublicClient,
    export_id: str,
    output_root: Path,
    historical_output_dir: Path,
    report_dir: Path,
    target_markets: int,
    rows_per_market: int,
    quotas: dict[str, int],
    max_candle_market_attempts: int,
    period_interval: int,
    dry_run: bool,
) -> NormalizedCalibrationCollectionResult:
    validate_collection_request(target_markets=target_markets, quotas=quotas)
    export_dir = output_root / export_id
    diagnostics = CollectorDiagnostics()
    diagnostics.set_quota_targets(quotas)
    discovery_target = max(
        max_candle_market_attempts * 2,
        target_markets * 10,
        max(1, sum(quotas.values())) * 10,
    )
    discovered = discover_normalized_candidate_markets(
        client,
        target_count=discovery_target,
        diagnostics=diagnostics,
    )
    grouped_markets, non_quota_category_counts = group_markets_by_normalized_category(
        discovered,
        quotas=quotas,
    )
    selected: list[SelectedMarket] = []
    selected_counts: Counter[str] = Counter()
    category_offsets: dict[str, int] = {category: 0 for category in quotas}
    attempts = 0

    while (
        len(selected) < target_markets
        and attempts < max_candle_market_attempts
        and not quotas_met(selected_counts, quotas)
    ):
        made_progress = False
        for category in category_cycle_order(quotas):
            if len(selected) >= target_markets or attempts >= max_candle_market_attempts:
                break
            if selected_counts[category] >= quotas[category] or quotas[category] <= 0:
                continue
            candidate = next_market_for_category(
                grouped_markets,
                category_offsets,
                category,
            )
            if candidate is None:
                continue
            made_progress = True
            attempts += 1
            selected_item = try_select_market(
                client=client,
                candidate=candidate,
                diagnostics=diagnostics,
                rows_per_market=rows_per_market,
                period_interval=period_interval,
            )
            if selected_item is None:
                continue
            selected.append(selected_item)
            selected_counts[category] += 1
            diagnostics.record_selected_category(category)
            time.sleep(0.03)
        if not made_progress:
            break

    selected_markets = [to_export_market(item) for item in selected]
    selected_candles = [candle for item in selected for candle in item.candles]
    category_counts = dict(Counter(item.category for item in selected))
    diagnostics_payload = diagnostics.as_dict()
    availability_limitations = tuple(diagnostics_payload["availability_limitations"])
    status = target_status(
        selected_count=len(selected),
        candle_count=len(selected_candles),
        target_markets=target_markets,
        target_rows=target_markets * rows_per_market,
        limitations=availability_limitations,
    )

    if dry_run:
        return NormalizedCalibrationCollectionResult(
            export_id=export_id,
            export_dir=export_dir,
            historical_jsonl=None,
            audit_json=None,
            audit_markdown=None,
            diagnostics_json=None,
            diagnostics_markdown=None,
            discovered_count=diagnostics.discovered_count,
            post_filter_count=len(discovered),
            selected_count=len(selected),
            candle_count=len(selected_candles),
            category_counts=category_counts,
            quotas=dict(sorted(quotas.items())),
            target_markets=target_markets,
            rows_per_market=rows_per_market,
            availability_limitations=availability_limitations,
            non_quota_category_counts=dict(sorted(non_quota_category_counts.items())),
            diagnostics=diagnostics_payload,
            audit_classification=None,
            claim_guardrails={},
            target_status=status,
            dry_run=True,
        )

    export_dir.mkdir(parents=True, exist_ok=True)
    sprint1.write_jsonl(export_dir / "markets.jsonl", selected_markets)
    sprint1.write_jsonl(export_dir / "candlesticks.jsonl", selected_candles)
    sprint1.write_jsonl(export_dir / "evidence.jsonl", [])
    manifest = build_manifest(
        export_id=export_id,
        export_dir=export_dir,
        selected=selected,
        diagnostics=diagnostics_payload,
        discovered_count=diagnostics.discovered_count,
        post_filter_count=len(discovered),
        period_interval=period_interval,
        rows_per_market=rows_per_market,
        target_markets=target_markets,
        quotas=quotas,
        max_candle_market_attempts=max_candle_market_attempts,
        availability_limitations=availability_limitations,
        non_quota_category_counts=dict(sorted(non_quota_category_counts.items())),
        target_status_value=status,
    )
    (export_dir / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    diagnostics_json, diagnostics_markdown = write_diagnostics_reports(
        export_id=export_id,
        export_dir=export_dir,
        report_dir=report_dir,
        diagnostics=diagnostics_payload,
    )
    (export_dir / "calibration_collection_report.md").write_text(
        render_export_report(
            export_id=export_id,
            export_dir=export_dir,
            discovered_count=diagnostics.discovered_count,
            post_filter_count=len(discovered),
            selected=selected,
            candle_count=len(selected_candles),
            quotas=quotas,
            availability_limitations=availability_limitations,
            target_status_value=status,
            diagnostics=diagnostics_payload,
        ),
        encoding="utf-8",
    )

    import_result = import_kalshi_export(
        export_dir,
        profile=PROFILE_CALIBRATION_ONLY,
        output_dir=historical_output_dir,
        report_dir=report_dir,
        source_audit_dir=report_dir,
        validate=True,
        allow_downgrade=False,
    )
    audit_result = audit_calibration_dataset(import_result.output_jsonl)
    audit_artifacts = write_calibration_audit_reports(audit_result, report_dir)

    return NormalizedCalibrationCollectionResult(
        export_id=export_id,
        export_dir=export_dir,
        historical_jsonl=import_result.output_jsonl,
        audit_json=audit_artifacts.json_path,
        audit_markdown=audit_artifacts.markdown_path,
        diagnostics_json=diagnostics_json,
        diagnostics_markdown=diagnostics_markdown,
        discovered_count=diagnostics.discovered_count,
        post_filter_count=len(discovered),
        selected_count=len(selected),
        candle_count=len(selected_candles),
        category_counts=category_counts,
        quotas=dict(sorted(quotas.items())),
        target_markets=target_markets,
        rows_per_market=rows_per_market,
        availability_limitations=availability_limitations,
        non_quota_category_counts=dict(sorted(non_quota_category_counts.items())),
        diagnostics=diagnostics_payload,
        audit_classification=audit_result.classification,
        claim_guardrails=audit_result.claim_guardrails,
        target_status=status,
        dry_run=False,
    )


def discover_normalized_candidate_markets(
    client: sprint1.KalshiPublicClient,
    *,
    target_count: int,
    diagnostics: CollectorDiagnostics,
) -> list[NormalizedCandidateMarket]:
    scanned: list[NormalizedCandidateMarket] = []
    seen: set[str] = set()
    page_limit = max(1, min(6, target_count * 2))
    per_page = min(1000, max(100, target_count * 80))

    for source_family in sprint1.DISCOVERY_FAMILIES:
        cursor: str | None = None
        for _ in range(page_limit):
            path, params = sprint1.discovery_request(
                source_family,
                limit=per_page,
                cursor=cursor,
            )
            payload = client.get_json(path, params)
            for raw in payload.get("markets", []):
                if not isinstance(raw, dict):
                    continue
                pre_normalization = normalize_market_category(raw)
                diagnostics.record_pre_filter_category(
                    pre_normalization.normalized_category
                )
                candidate = sprint1.normalize_candidate(source_family, raw)
                if candidate is None:
                    diagnostics.record_filter_loss(filter_loss_reason(raw))
                    continue
                if candidate.ticker in seen:
                    continue
                seen.add(candidate.ticker)
                normalization = normalize_market_category(candidate.raw)
                diagnostics.record_post_filter_category(
                    normalization.normalized_category
                )
                scanned.append(
                    NormalizedCandidateMarket(
                        market=candidate,
                        normalization=normalization,
                    )
                )
            cursor = sprint1.text_or_none(payload.get("cursor"))
            if not cursor:
                break

    scanned.sort(
        key=lambda item: (
            -item.market.volume,
            sprint1.parse_timestamp(item.market.settlement_ts)
            or datetime.min.replace(tzinfo=UTC),
            item.market.ticker,
        )
    )
    return scanned


def filter_loss_reason(raw: dict[str, Any]) -> str:
    status = (sprint1.text_or_none(raw.get("status")) or "").lower()
    market_type = (sprint1.text_or_none(raw.get("market_type")) or "binary").lower()
    result = sprint1.normalize_outcome(
        raw.get("result") or raw.get("settlement_value_dollars")
    )
    settlement_ts = sprint1.first_text(
        raw,
        (
            "settlement_ts",
            "latest_expiration_time",
            "expected_expiration_time",
            "close_time",
        ),
    )
    if market_type != "binary" or raw.get("mve_collection_ticker") or raw.get("mve_selected_legs"):
        return FILTER_LOSS_NON_BINARY
    if status not in sprint1.ALLOWED_STATUS:
        return FILTER_LOSS_NOT_FINALIZED
    if result not in sprint1.ALLOWED_OUTCOMES or not settlement_ts:
        return FILTER_LOSS_UNRESOLVED
    if sprint1.parse_timestamp(settlement_ts) is None:
        return FILTER_LOSS_UNRESOLVED
    return FILTER_LOSS_OTHER


def group_markets_by_normalized_category(
    markets: list[NormalizedCandidateMarket],
    *,
    quotas: dict[str, int],
) -> tuple[dict[str, list[NormalizedCandidateMarket]], Counter[str]]:
    grouped = {category: [] for category in quotas}
    non_quota_category_counts: Counter[str] = Counter()
    for candidate in markets:
        category = candidate.category
        if category not in quotas or quotas[category] <= 0:
            non_quota_category_counts[category] += 1
            continue
        grouped[category].append(candidate)
    for category_markets in grouped.values():
        category_markets.sort(
            key=lambda item: (
                -int(item.market.volume),
                item.market.settlement_ts,
                item.market.ticker,
            )
        )
    return grouped, non_quota_category_counts


def category_cycle_order(quotas: dict[str, int]) -> list[str]:
    return sorted(quotas, key=lambda category: (quotas[category] <= 0, category))


def next_market_for_category(
    grouped_markets: dict[str, list[NormalizedCandidateMarket]],
    category_offsets: dict[str, int],
    category: str,
) -> NormalizedCandidateMarket | None:
    offset = category_offsets[category]
    markets = grouped_markets.get(category, [])
    if offset >= len(markets):
        return None
    category_offsets[category] = offset + 1
    return markets[offset]


def try_select_market(
    *,
    client: sprint1.KalshiPublicClient,
    candidate: NormalizedCandidateMarket,
    diagnostics: CollectorDiagnostics,
    rows_per_market: int,
    period_interval: int,
) -> SelectedMarket | None:
    try:
        raw_candles = sprint1.fetch_candlesticks(
            client=client,
            market=candidate.market,
            period_interval=period_interval,
        )
    except RuntimeError:
        diagnostics.record_candle_attempt(
            success=False,
            failure_reason="candlestick_request_failed",
        )
        return None
    if not raw_candles:
        diagnostics.record_candle_attempt(success=False, failure_reason="no_candles_returned")
        return None
    sampled = sample_calibration_candles(
        candidate=candidate,
        candles=raw_candles,
        rows_per_market=rows_per_market,
        period_interval=period_interval,
    )
    if len(sampled) < min(MIN_CANDLES_PER_SELECTED_MARKET, rows_per_market):
        diagnostics.record_candle_attempt(
            success=False,
            failure_reason="insufficient_pre_settlement_last_price_candles",
        )
        return None
    diagnostics.record_candle_attempt(success=True)
    return SelectedMarket(
        candidate=candidate,
        period_interval=period_interval,
        candles=tuple(sampled),
    )


def sample_calibration_candles(
    *,
    candidate: NormalizedCandidateMarket,
    candles: list[dict[str, Any]],
    rows_per_market: int,
    period_interval: int,
) -> list[dict[str, Any]]:
    sampled = base_collector.sample_calibration_candles(
        market=candidate.market,
        candles=candles,
        rows_per_market=rows_per_market,
        period_interval=period_interval,
    )
    normalization = candidate.normalization.as_dict()
    return [
        {
            **row,
            "metadata": {
                **row.get("metadata", {}),
                "market_category": candidate.category,
                "normalized_category": candidate.category,
                "semantic_category": normalization["semantic_category"],
                "source_category": normalization["source_category"],
                "is_mention_market": normalization["is_mention_market"],
                "normalization_warnings": normalization["warnings"],
                "category_normalized_calibration_retry": True,
            },
        }
        for row in sampled
    ]


def to_export_market(item: SelectedMarket) -> dict[str, Any]:
    row = sprint1.to_export_market(item.market)
    normalization = item.candidate.normalization.as_dict()
    row.setdefault("metadata", {})
    row["metadata"] = {
        **row["metadata"],
        "calibration_category": item.category,
        "normalized_category": item.category,
        "semantic_category": normalization["semantic_category"],
        "source_category": normalization["source_category"],
        "is_mention_market": normalization["is_mention_market"],
        "normalization_confidence": normalization["confidence"],
        "normalization_matched_rules": normalization["matched_rules"],
        "normalization_warnings": normalization["warnings"],
        "temporary_calibration_collection_script": True,
        "temporary_normalized_calibration_collection_script": True,
        "evidence_friendly_filter_applied": False,
    }
    return row


def build_manifest(
    *,
    export_id: str,
    export_dir: Path,
    selected: list[SelectedMarket],
    diagnostics: dict[str, Any],
    discovered_count: int,
    post_filter_count: int,
    period_interval: int,
    rows_per_market: int,
    target_markets: int,
    quotas: dict[str, int],
    max_candle_market_attempts: int,
    availability_limitations: tuple[dict[str, Any], ...],
    non_quota_category_counts: dict[str, int],
    target_status_value: str,
) -> dict[str, Any]:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    selected_candles = [candle for item in selected for candle in item.candles]
    notes = (
        "Temporary PR-CAL-11 normalized-category calibration-only public-data "
        "collection helper. Evidence is intentionally not collected, "
        "evidence.jsonl is empty, bid/ask are not required for calibration "
        "output, and acceptance, Strategy v2 superiority, paper-PnL, "
        "profitability, and live-readiness claims are blocked. Terms review "
        "remains pending_review by default. Quota shortfalls are reported as "
        "availability limitations and are not backfilled from unrelated "
        "normalized categories by default."
    )
    return {
        "export_id": export_id,
        "dataset_id": f"phase7g_kalshi_calibration_{sprint1.slugify(export_id)}",
        "dataset_label": f"Kalshi normalized-category calibration-only temporary collection {export_id}",
        "source_name": SOURCE_NAME,
        "source_type": SOURCE_TYPE,
        "source_urls": [
            f"{sprint1.BASE_URL}/markets",
            f"{sprint1.BASE_URL}/historical/markets",
            f"{sprint1.BASE_URL}/markets/candlesticks",
            f"{sprint1.BASE_URL}/historical/markets/{{ticker}}/candlesticks",
        ],
        "retrieved_at": now,
        "exported_at": now,
        "terms_review": TERMS_REVIEW_DEFAULT,
        "terms_reviewed_by": "pending_review",
        "terms_reviewed_at": now,
        "private_or_authenticated_source": False,
        "network_used_by_adapter": False,
        "raw_file_sha256": {
            "markets.jsonl": sprint1.file_sha256(export_dir / "markets.jsonl"),
            "candlesticks.jsonl": sprint1.file_sha256(export_dir / "candlesticks.jsonl"),
            "evidence.jsonl": sprint1.file_sha256(export_dir / "evidence.jsonl"),
        },
        "notes": notes,
        "collection_script": "scripts/local_only/collect_kalshi_normalized_calibration.py",
        "collector_diagnostics": diagnostics,
        "collection_summary": {
            "discovered_count": discovered_count,
            "post_filter_count": post_filter_count,
            "selected_count": len(selected),
            "candle_count": len(selected_candles),
            "evidence_count": 0,
            "target_markets": target_markets,
            "rows_per_market": rows_per_market,
            "period_interval": period_interval,
            "quotas": dict(sorted(quotas.items())),
            "max_candle_market_attempts": max_candle_market_attempts,
            "category_counts": dict(Counter(item.category for item in selected)),
            "non_quota_category_counts": non_quota_category_counts,
            "availability_limitations": list(availability_limitations),
            "target_status": target_status_value,
            "unrelated_category_backfill": False,
        },
        "safety": {
            "local_only_output": True,
            "public_read_only_endpoints": True,
            "private_or_authenticated_source": False,
            "credentials_used": False,
            "cookies_or_browser_session_used": False,
            "evidence_collected": False,
            "evidence_approval_performed": False,
            "terms_review_mutated": False,
            "acceptance_claim": False,
            "strategy_v2_superiority_claim": False,
            "paper_pnl_claim": False,
            "profitability_claim": False,
            "live_readiness_claim": False,
        },
    }


def write_diagnostics_reports(
    *,
    export_id: str,
    export_dir: Path,
    report_dir: Path,
    diagnostics: dict[str, Any],
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    export_json = export_dir / "collector_diagnostics.json"
    export_markdown = export_dir / "collector_diagnostics.md"
    report_json = report_dir / f"{export_id}_collector_diagnostics.json"
    report_markdown = report_dir / f"{export_id}_collector_diagnostics.md"
    markdown = render_diagnostics_markdown(export_id=export_id, diagnostics=diagnostics)
    for path in (export_json, report_json):
        path.write_text(json.dumps(diagnostics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for path in (export_markdown, report_markdown):
        path.write_text(markdown, encoding="utf-8")
    return report_json, report_markdown


def render_diagnostics_markdown(*, export_id: str, diagnostics: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Normalized Calibration Collector Diagnostics",
            "",
            f"Export id: `{export_id}`",
            "",
            "## Counts",
            "",
            f"- discovered_count: {diagnostics['discovered_count']}",
            f"- candle_attempt_count: {diagnostics['candle_attempt_count']}",
            f"- candle_success_count: {diagnostics['candle_success_count']}",
            f"- candle_failure_count: {diagnostics['candle_failure_count']}",
            "",
            "## Category Counts",
            "",
            f"- pre_filter_category_counts: `{diagnostics['pre_filter_category_counts']}`",
            f"- post_filter_category_counts: `{diagnostics['post_filter_category_counts']}`",
            f"- selected_category_counts: `{diagnostics['selected_category_counts']}`",
            "",
            "## Quotas",
            "",
            f"- quota_targets: `{diagnostics['quota_targets']}`",
            f"- quota_filled: `{diagnostics['quota_filled']}`",
            f"- quota_shortfalls: `{diagnostics['quota_shortfalls']}`",
            "",
            "## Failures",
            "",
            f"- filter_losses: `{diagnostics['filter_losses']}`",
            f"- candle_failure_reasons: `{diagnostics['candle_failure_reasons']}`",
            "",
            "## Availability Limitations",
            "",
            *[
                "- "
                f"`{item['category']}` missing={item['missing_count']} "
                f"reasons=`{item['reasons']}`"
                for item in diagnostics["availability_limitations"]
            ],
            "",
        ]
    )


def render_export_report(
    *,
    export_id: str,
    export_dir: Path,
    discovered_count: int,
    post_filter_count: int,
    selected: list[SelectedMarket],
    candle_count: int,
    quotas: dict[str, int],
    availability_limitations: tuple[dict[str, Any], ...],
    target_status_value: str,
    diagnostics: dict[str, Any],
) -> str:
    category_counts = dict(Counter(item.category for item in selected))
    category_lines = [f"- `{name}`: {count}" for name, count in sorted(category_counts.items())]
    if not category_lines:
        category_lines = ["- none"]
    limitation_lines = [
        (
            f"- `{item['category']}` filled={item['quota_filled']} "
            f"target={item['quota_target']} missing={item['missing_count']} "
            f"reasons=`{item['reasons']}`"
        )
        for item in availability_limitations
    ] or ["- none"]
    return "\n".join(
        [
            "# Kalshi Normalized-Category Calibration Collection Local Report",
            "",
            f"Export id: `{export_id}`",
            f"Export directory: `{export_dir}`",
            "",
            "## Counts",
            "",
            f"- markets_discovered_pre_filter: {discovered_count}",
            f"- markets_post_filter_resolved_binary: {post_filter_count}",
            f"- markets_selected: {len(selected)}",
            f"- rows_collected: {candle_count}",
            "- evidence_rows: 0",
            f"- target_status: `{target_status_value}`",
            f"- quotas: `{dict(sorted(quotas.items()))}`",
            "",
            "## Normalized Categories",
            "",
            *category_lines,
            "",
            "## Collector Diagnostics",
            "",
            f"- candle_attempt_count: {diagnostics['candle_attempt_count']}",
            f"- candle_success_count: {diagnostics['candle_success_count']}",
            f"- candle_failure_count: {diagnostics['candle_failure_count']}",
            f"- quota_shortfalls: `{diagnostics['quota_shortfalls']}`",
            f"- candle_failure_reasons: `{diagnostics['candle_failure_reasons']}`",
            "",
            "## Availability Limitations",
            "",
            *limitation_lines,
            "",
            "## Claim Boundary",
            "",
            "- Profile after import: `calibration_only_last_price`",
            "- Bid/ask are intentionally discarded from Phase 7G calibration rows.",
            "- Evidence is intentionally empty.",
            "- Missing quotas are not backfilled from unrelated normalized categories by default.",
            "- Acceptance, Strategy v2 superiority, paper-PnL, profitability, and live-readiness claims are not allowed.",
            "",
        ]
    )


def quotas_met(selected_counts: Counter[str], quotas: dict[str, int]) -> bool:
    return all(selected_counts[category] >= quota for category, quota in quotas.items())


def target_status(
    *,
    selected_count: int,
    candle_count: int,
    target_markets: int,
    target_rows: int,
    limitations: tuple[dict[str, Any], ...],
) -> str:
    if selected_count >= target_markets and candle_count >= target_rows and not limitations:
        return "target_met"
    if selected_count >= 60 and candle_count >= 720:
        return "preferred_size_availability_limited"
    if selected_count >= 25 and candle_count >= 250:
        return "minimum_size_availability_limited"
    return "missed_availability_limited"


def validate_collection_request(*, target_markets: int, quotas: dict[str, int]) -> None:
    if not quotas:
        raise ValueError("at least one --quota is required")
    if sum(quotas.values()) > target_markets:
        raise ValueError("sum of quotas must be less than or equal to --target-markets")
    negative = [category for category, quota in quotas.items() if quota < 0]
    if negative:
        raise ValueError(f"quota cannot be negative: {negative}")


def parse_quotas(values: list[str]) -> dict[str, int]:
    if not values:
        return dict(DEFAULT_QUOTAS)
    quotas: dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise argparse.ArgumentTypeError("--quota must use category=count")
        category, raw_count = value.split("=", maxsplit=1)
        category = category.strip()
        if not category:
            raise argparse.ArgumentTypeError("--quota category cannot be blank")
        quotas[category] = non_negative_int(raw_count)
    return dict(sorted(quotas.items()))


def build_network_failure_diagnostic(
    error: RuntimeError,
    *,
    client: sprint1.KalshiPublicClient,
    export_id: str,
    output_root: Path,
) -> dict[str, object]:
    return {
        "export_id": export_id,
        "export_dir": str(output_root / export_id),
        "network_status": "network_blocked_or_public_endpoint_failure",
        "error": str(error),
        "requested_url_count": len(client.requested_urls),
        "sample_requested_urls": client.requested_urls[:5],
        "safety": {
            "private_or_authenticated_source": False,
            "credentials_used": False,
            "cookies_or_browser_session_used": False,
            "trading_endpoint_used": False,
            "acceptance_claim": False,
        },
    }


def default_export_id() -> str:
    now = datetime.now(UTC).strftime("%Y%m%d")
    return f"kalshi_normalized_calibration_{now}"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def encode_market_ticker(path: str) -> str:
    return urllib.parse.quote(path, safe="")


if __name__ == "__main__":
    sys.exit(main())
