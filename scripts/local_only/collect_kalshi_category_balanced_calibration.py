#!/usr/bin/env python3
"""Collect a local category-balanced Kalshi calibration-only dataset.

This is a temporary PR-CAL-8 public-data helper, not production application
code. It uses only unauthenticated public/read-only Kalshi market and
candlestick endpoints, writes local staged files, imports them as
calibration-only historical rows, and runs the calibration audit. It does not
collect evidence or make acceptance, superiority, paper-PnL, profitability, or
live-readiness claims.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
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
    write_calibration_audit_reports,
)

SOURCE_NAME = "kalshi_public_market_and_candlestick_api"
SOURCE_TYPE = "public_research_export"
TERMS_REVIEW_DEFAULT = "pending_review"
DEFAULT_OUTPUT_ROOT = Path("data/source_exports/kalshi")
DEFAULT_HISTORICAL_OUTPUT_DIR = Path("data/historical")
DEFAULT_REPORT_DIR = Path("data/reports/calibration")
DEFAULT_EXPORT_ID = "kalshi_category_balanced_calibration_20260607_public_probe"
DEFAULT_TARGET_MARKETS = 120
DEFAULT_ROWS_PER_MARKET = 12
DEFAULT_MAX_CANDLE_MARKET_ATTEMPTS = 300
DEFAULT_PERIOD_INTERVAL = 60
DEFAULT_TIMEOUT_SECONDS = 4.0
DEFAULT_PUBLIC_EVENT_CAP = 60
NETWORK_FAILURE_EXIT_CODE = 2
MIN_CANDLES_PER_SELECTED_MARKET = 4
DEFAULT_QUOTAS = {
    "public_event": 30,
    "major_sports": 30,
    "weather": 30,
    "fed_policy": 30,
}

FED_PATTERNS = (
    r"\bfomc\b",
    r"\bfed\b",
    r"\bfederal reserve\b",
    r"\binterest rate\b",
    r"\brate cut\b",
    r"\brate hike\b",
)
WEATHER_PATTERNS = (
    r"\bweather\b",
    r"\btemperature\b",
    r"\brain\b",
    r"\bsnow\b",
    r"\bhurricane\b",
    r"\bnoaa\b",
)
MAJOR_SPORTS_PATTERNS = (
    r"\bnfl\b",
    r"\bnba\b",
    r"\bmlb\b",
    r"\bnhl\b",
    r"\bchampions league\b",
    r"\bworld cup\b",
)


@dataclass(frozen=True)
class SelectedMarket:
    market: sprint1.CandidateMarket
    category: str
    period_interval: int
    candles: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CategoryBalancedCollectionResult:
    export_id: str
    export_dir: Path
    historical_jsonl: Path | None
    audit_json: Path | None
    audit_markdown: Path | None
    discovered_count: int
    selected_count: int
    candle_count: int
    category_counts: dict[str, int]
    quotas: dict[str, int]
    public_event_cap: int
    target_markets: int
    rows_per_market: int
    availability_limitations: tuple[dict[str, Any], ...]
    non_quota_category_counts: dict[str, int]
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
            "discovered_count": self.discovered_count,
            "selected_count": self.selected_count,
            "candle_count": self.candle_count,
            "category_counts": self.category_counts,
            "quotas": self.quotas,
            "public_event_cap": self.public_event_cap,
            "target_markets": self.target_markets,
            "rows_per_market": self.rows_per_market,
            "availability_limitations": list(self.availability_limitations),
            "non_quota_category_counts": self.non_quota_category_counts,
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
        result = collect_category_balanced_calibration(
            client=client,
            export_id=export_id,
            output_root=args.output_root,
            historical_output_dir=args.historical_output_dir,
            report_dir=args.report_dir,
            target_markets=args.target_markets,
            rows_per_market=args.rows_per_market,
            quotas=quotas,
            public_event_cap=args.public_event_cap,
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
        description="Collect a local category-balanced Kalshi calibration-only dataset."
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
        help="Category quota in the form category=count. May be repeated.",
    )
    parser.add_argument(
        "--public-event-cap",
        type=positive_int,
        default=DEFAULT_PUBLIC_EVENT_CAP,
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


def collect_category_balanced_calibration(
    *,
    client: sprint1.KalshiPublicClient,
    export_id: str,
    output_root: Path,
    historical_output_dir: Path,
    report_dir: Path,
    target_markets: int,
    rows_per_market: int,
    quotas: dict[str, int],
    public_event_cap: int,
    max_candle_market_attempts: int,
    period_interval: int,
    dry_run: bool,
) -> CategoryBalancedCollectionResult:
    validate_collection_request(
        target_markets=target_markets,
        quotas=quotas,
        public_event_cap=public_event_cap,
    )
    export_dir = output_root / export_id
    discovery_target = max(max_candle_market_attempts * 2, target_markets * 10, sum(quotas.values()) * 10)
    discovered = sprint1.discover_candidate_markets(client, target_count=discovery_target)
    selected: list[SelectedMarket] = []
    selected_counts: Counter[str] = Counter()
    grouped_markets, non_quota_category_counts = group_markets_by_quota_category(
        discovered,
        quotas=quotas,
    )
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
            if selected_counts[category] >= quotas[category]:
                continue
            if category == "public_event" and selected_counts[category] >= public_event_cap:
                continue
            market = next_market_for_category(
                grouped_markets,
                category_offsets,
                category,
            )
            if market is None:
                continue
            made_progress = True
            attempts += 1
            selected_item = try_select_market(
                client=client,
                market=market,
                category=category,
                rows_per_market=rows_per_market,
                period_interval=period_interval,
            )
            if selected_item is None:
                continue
            selected.append(selected_item)
            selected_counts[category] += 1
            time.sleep(0.03)
        if not made_progress:
            break

    selected_markets = [to_export_market(item) for item in selected]
    selected_candles = [candle for item in selected for candle in item.candles]
    category_counts = dict(Counter(item.category for item in selected))
    availability_limitations = tuple(
        build_availability_limitations(
            selected_counts=selected_counts,
            quotas=quotas,
        )
    )
    status = target_status(
        selected_count=len(selected),
        candle_count=len(selected_candles),
        target_markets=target_markets,
        target_rows=target_markets * rows_per_market,
        limitations=availability_limitations,
    )

    if dry_run:
        return CategoryBalancedCollectionResult(
            export_id=export_id,
            export_dir=export_dir,
            historical_jsonl=None,
            audit_json=None,
            audit_markdown=None,
            discovered_count=len(discovered),
            selected_count=len(selected),
            candle_count=len(selected_candles),
            category_counts=category_counts,
            quotas=dict(sorted(quotas.items())),
            public_event_cap=public_event_cap,
            target_markets=target_markets,
            rows_per_market=rows_per_market,
            availability_limitations=availability_limitations,
            non_quota_category_counts=dict(sorted(non_quota_category_counts.items())),
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
        discovered_count=len(discovered),
        period_interval=period_interval,
        rows_per_market=rows_per_market,
        target_markets=target_markets,
        quotas=quotas,
        public_event_cap=public_event_cap,
        max_candle_market_attempts=max_candle_market_attempts,
        availability_limitations=availability_limitations,
        non_quota_category_counts=dict(sorted(non_quota_category_counts.items())),
        target_status_value=status,
    )
    (export_dir / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (export_dir / "calibration_collection_report.md").write_text(
        render_export_report(
            export_id=export_id,
            export_dir=export_dir,
            discovered_count=len(discovered),
            selected=selected,
            candle_count=len(selected_candles),
            quotas=quotas,
            public_event_cap=public_event_cap,
            availability_limitations=availability_limitations,
            target_status_value=status,
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

    return CategoryBalancedCollectionResult(
        export_id=export_id,
        export_dir=export_dir,
        historical_jsonl=import_result.output_jsonl,
        audit_json=audit_artifacts.json_path,
        audit_markdown=audit_artifacts.markdown_path,
        discovered_count=len(discovered),
        selected_count=len(selected),
        candle_count=len(selected_candles),
        category_counts=category_counts,
        quotas=dict(sorted(quotas.items())),
        public_event_cap=public_event_cap,
        target_markets=target_markets,
        rows_per_market=rows_per_market,
        availability_limitations=availability_limitations,
        non_quota_category_counts=dict(sorted(non_quota_category_counts.items())),
        audit_classification=audit_result.classification,
        claim_guardrails=audit_result.claim_guardrails,
        target_status=status,
        dry_run=False,
    )


def try_select_market(
    *,
    client: sprint1.KalshiPublicClient,
    market: sprint1.CandidateMarket,
    category: str,
    rows_per_market: int,
    period_interval: int,
) -> SelectedMarket | None:
    try:
        raw_candles = sprint1.fetch_candlesticks(
            client=client,
            market=market,
            period_interval=period_interval,
        )
    except RuntimeError:
        return None
    sampled = sample_calibration_candles(
        market=market,
        category=category,
        candles=raw_candles,
        rows_per_market=rows_per_market,
        period_interval=period_interval,
    )
    if len(sampled) < min(MIN_CANDLES_PER_SELECTED_MARKET, rows_per_market):
        return None
    return SelectedMarket(
        market=market,
        category=category,
        period_interval=period_interval,
        candles=tuple(sampled),
    )


def group_markets_by_quota_category(
    markets: list[sprint1.CandidateMarket],
    *,
    quotas: dict[str, int],
) -> tuple[dict[str, list[sprint1.CandidateMarket]], Counter[str]]:
    grouped = {category: [] for category in quotas}
    non_quota_category_counts: Counter[str] = Counter()
    for market in markets:
        category = classify_category(market)
        if category not in quotas:
            non_quota_category_counts[category] += 1
            continue
        grouped[category].append(market)
    for _category, category_markets in grouped.items():
        category_markets.sort(
            key=lambda market: (-int(market.volume), market.settlement_ts, market.ticker)
        )
    return grouped, non_quota_category_counts


def category_cycle_order(quotas: dict[str, int]) -> list[str]:
    return sorted(quotas, key=lambda category: (category == "public_event", category))


def next_market_for_category(
    grouped_markets: dict[str, list[sprint1.CandidateMarket]],
    category_offsets: dict[str, int],
    category: str,
) -> sprint1.CandidateMarket | None:
    offset = category_offsets[category]
    markets = grouped_markets.get(category, [])
    if offset >= len(markets):
        return None
    category_offsets[category] = offset + 1
    return markets[offset]


def sample_calibration_candles(
    *,
    market: sprint1.CandidateMarket,
    category: str,
    candles: list[dict[str, Any]],
    rows_per_market: int,
    period_interval: int,
) -> list[dict[str, Any]]:
    sampled = base_collector.sample_calibration_candles(
        market=market,
        candles=candles,
        rows_per_market=rows_per_market,
        period_interval=period_interval,
    )
    return [
        {
            **row,
            "metadata": {
                **row.get("metadata", {}),
                "market_category": category,
                "category_balanced_calibration_retry": True,
            },
        }
        for row in sampled
    ]


def balanced_market_sort_key(market: sprint1.CandidateMarket) -> tuple[int, int, str, str]:
    category = classify_category(market)
    category_rank = {
        "fed_policy": 0,
        "weather": 1,
        "major_sports": 2,
        "public_event": 3,
    }.get(category, 4)
    return (category_rank, -int(market.volume), category, market.ticker)


def classify_category(market: sprint1.CandidateMarket | dict[str, Any]) -> str:
    raw = market.raw if isinstance(market, sprint1.CandidateMarket) else market
    text = " ".join(
        str(raw.get(field) or "").lower()
        for field in ("ticker", "title", "rules_primary", "rules_secondary")
    )
    if matches_any(text, FED_PATTERNS):
        return "fed_policy"
    if matches_any(text, WEATHER_PATTERNS):
        return "weather"
    if matches_any(text, MAJOR_SPORTS_PATTERNS):
        return "major_sports"
    if str(raw.get("title") or "").strip():
        return "public_event"
    return "unknown"


def matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def to_export_market(item: SelectedMarket) -> dict[str, Any]:
    row = sprint1.to_export_market(item.market)
    row.setdefault("metadata", {})
    row["metadata"] = {
        **row["metadata"],
        "calibration_category": item.category,
        "temporary_calibration_collection_script": True,
        "temporary_category_balanced_calibration_collection_script": True,
        "evidence_friendly_filter_applied": False,
    }
    return row


def build_manifest(
    *,
    export_id: str,
    export_dir: Path,
    selected: list[SelectedMarket],
    discovered_count: int,
    period_interval: int,
    rows_per_market: int,
    target_markets: int,
    quotas: dict[str, int],
    public_event_cap: int,
    max_candle_market_attempts: int,
    availability_limitations: tuple[dict[str, Any], ...],
    non_quota_category_counts: dict[str, int],
    target_status_value: str,
) -> dict[str, Any]:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    selected_candles = [candle for item in selected for candle in item.candles]
    notes = (
        "Temporary PR-CAL-8 category-balanced calibration-only public-data "
        "collection helper. Evidence is intentionally not collected, "
        "evidence.jsonl is empty, bid/ask are not required for calibration "
        "output, and acceptance, Strategy v2 superiority, paper-PnL, "
        "profitability, and live-readiness claims are blocked. Terms review "
        "remains pending_review by default. Unmet non-public quotas are "
        "reported as available_source_limitation and are not backfilled with "
        "extra public_event markets."
    )
    return {
        "export_id": export_id,
        "dataset_id": f"phase7g_kalshi_calibration_{sprint1.slugify(export_id)}",
        "dataset_label": f"Kalshi category-balanced calibration-only temporary collection {export_id}",
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
        "collection_script": "scripts/local_only/collect_kalshi_category_balanced_calibration.py",
        "collection_summary": {
            "discovered_count": discovered_count,
            "selected_count": len(selected),
            "candle_count": len(selected_candles),
            "evidence_count": 0,
            "target_markets": target_markets,
            "rows_per_market": rows_per_market,
            "period_interval": period_interval,
            "quotas": dict(sorted(quotas.items())),
            "public_event_cap": public_event_cap,
            "max_candle_market_attempts": max_candle_market_attempts,
            "category_counts": dict(Counter(item.category for item in selected)),
            "non_quota_category_counts": non_quota_category_counts,
            "availability_limitations": list(availability_limitations),
            "target_status": target_status_value,
            "public_event_backfill_beyond_cap": False,
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


def render_export_report(
    *,
    export_id: str,
    export_dir: Path,
    discovered_count: int,
    selected: list[SelectedMarket],
    candle_count: int,
    quotas: dict[str, int],
    public_event_cap: int,
    availability_limitations: tuple[dict[str, Any], ...],
    target_status_value: str,
) -> str:
    category_counts = dict(Counter(item.category for item in selected))
    category_lines = [f"- `{name}`: {count}" for name, count in sorted(category_counts.items())]
    if not category_lines:
        category_lines = ["- none"]
    limitation_lines = [
        (
            f"- `{item['category']}` selected={item['selected_markets']} "
            f"quota={item['quota_markets']} missing={item['missing_markets']}"
        )
        for item in availability_limitations
    ] or ["- none"]
    return "\n".join(
        [
            "# Kalshi Category-Balanced Calibration Collection Local Report",
            "",
            f"Export id: `{export_id}`",
            f"Export directory: `{export_dir}`",
            "",
            "## Counts",
            "",
            f"- markets_discovered: {discovered_count}",
            f"- markets_selected: {len(selected)}",
            f"- rows_collected: {candle_count}",
            "- evidence_rows: 0",
            f"- target_status: `{target_status_value}`",
            f"- public_event_cap: {public_event_cap}",
            f"- quotas: `{dict(sorted(quotas.items()))}`",
            "",
            "## Categories",
            "",
            *category_lines,
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
            "- Unavailable non-public quotas are not backfilled with extra public-event markets.",
            "- Acceptance, Strategy v2 superiority, paper-PnL, profitability, and live-readiness claims are not allowed.",
            "",
        ]
    )


def build_availability_limitations(
    *,
    selected_counts: Counter[str],
    quotas: dict[str, int],
) -> list[dict[str, Any]]:
    limitations: list[dict[str, Any]] = []
    for category, quota in sorted(quotas.items()):
        selected = selected_counts[category]
        if selected >= quota:
            continue
        limitations.append(
            {
                "category": category,
                "selected_markets": selected,
                "quota_markets": quota,
                "missing_markets": quota - selected,
                "classification": "available_source_limitation",
                "not_a_true_category_effect": True,
                "public_event_backfilled": False,
            }
        )
    return limitations


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


def validate_collection_request(
    *,
    target_markets: int,
    quotas: dict[str, int],
    public_event_cap: int,
) -> None:
    if not quotas:
        raise ValueError("at least one --quota is required")
    if sum(quotas.values()) > target_markets:
        raise ValueError("sum of quotas must be less than or equal to --target-markets")
    if quotas.get("public_event", 0) > public_event_cap:
        raise ValueError("public_event quota must be less than or equal to --public-event-cap")


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
        count = positive_int(raw_count)
        quotas[category] = count
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
    return f"kalshi_category_balanced_calibration_{now}"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


if __name__ == "__main__":
    sys.exit(main())
