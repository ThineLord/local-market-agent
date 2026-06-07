#!/usr/bin/env python3
"""Collect a local Kalshi calibration-only dataset.

This is a temporary public-data helper, not production application code. It uses
only unauthenticated public/read-only Kalshi market and candlestick endpoints,
writes local staged files, imports them as calibration-only historical rows,
and runs the calibration audit. It does not collect evidence or make acceptance
claims.
"""

from __future__ import annotations

import argparse
import json
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
DEFAULT_MIN_MARKETS = 25
DEFAULT_MAX_MARKETS = 60
DEFAULT_ROWS_PER_MARKET = 12
DEFAULT_MAX_CANDLE_MARKET_ATTEMPTS = 150
DEFAULT_PERIOD_INTERVAL = 60
DEFAULT_TIMEOUT_SECONDS = 4.0
NETWORK_FAILURE_EXIT_CODE = 2
MIN_CANDLES_PER_SELECTED_MARKET = 4

MACRO_TERMS = (
    "cpi",
    "inflation",
    "unemployment",
    "payroll",
    "jobs",
    "jobless",
    "gdp",
    "retail sales",
    "ppi",
)
FED_TERMS = ("fomc", "fed", "federal reserve", "interest rate")
WEATHER_TERMS = ("weather", "temperature", "rain", "snow", "hurricane", "noaa")
ELECTION_TERMS = ("election", "senate", "house", "governor", "mayor", "primary")
COMPANY_TERMS = ("earnings", "revenue", "eps", "sec filing")
MAJOR_SPORTS_TERMS = ("nfl", "nba", "mlb", "nhl", "champions league", "world cup")


@dataclass(frozen=True)
class SelectedMarket:
    market: sprint1.CandidateMarket
    category: str
    period_interval: int
    candles: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CalibrationCollectionResult:
    export_id: str
    export_dir: Path
    historical_jsonl: Path | None
    audit_json: Path | None
    audit_markdown: Path | None
    discovered_count: int
    selected_count: int
    candle_count: int
    category_counts: dict[str, int]
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
            "audit_classification": self.audit_classification,
            "claim_guardrails": self.claim_guardrails,
            "target_status": self.target_status,
            "dry_run": self.dry_run,
        }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    export_id = args.export_id or default_export_id()
    client = sprint1.KalshiPublicClient(timeout_seconds=args.timeout_seconds)
    try:
        result = collect_calibration_dataset(
            client=client,
            export_id=export_id,
            output_root=args.output_root,
            historical_output_dir=args.historical_output_dir,
            report_dir=args.report_dir,
            min_markets=args.min_markets,
            max_markets=args.max_markets,
            rows_per_market=args.rows_per_market,
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
        description="Collect a local Kalshi calibration-only dataset."
    )
    parser.add_argument("--export-id")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--historical-output-dir", type=Path, default=DEFAULT_HISTORICAL_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--min-markets", type=positive_int, default=DEFAULT_MIN_MARKETS)
    parser.add_argument("--max-markets", type=positive_int, default=DEFAULT_MAX_MARKETS)
    parser.add_argument(
        "--rows-per-market",
        type=positive_int,
        default=DEFAULT_ROWS_PER_MARKET,
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


def collect_calibration_dataset(
    *,
    client: sprint1.KalshiPublicClient,
    export_id: str,
    output_root: Path,
    historical_output_dir: Path,
    report_dir: Path,
    min_markets: int,
    max_markets: int,
    rows_per_market: int,
    max_candle_market_attempts: int,
    period_interval: int,
    dry_run: bool,
) -> CalibrationCollectionResult:
    if min_markets > max_markets:
        raise ValueError("--min-markets must be less than or equal to --max-markets")
    export_dir = output_root / export_id
    discovery_target = max(max_candle_market_attempts * 2, max_markets * 10)
    discovered = sprint1.discover_candidate_markets(client, target_count=discovery_target)
    selected: list[SelectedMarket] = []
    attempts = 0

    for market in sorted(discovered, key=calibration_market_sort_key):
        if len(selected) >= max_markets or attempts >= max_candle_market_attempts:
            break
        attempts += 1
        try:
            raw_candles = sprint1.fetch_candlesticks(
                client=client,
                market=market,
                period_interval=period_interval,
            )
        except RuntimeError:
            continue
        sampled = sample_calibration_candles(
            market=market,
            candles=raw_candles,
            rows_per_market=rows_per_market,
            period_interval=period_interval,
        )
        if len(sampled) < min(MIN_CANDLES_PER_SELECTED_MARKET, rows_per_market):
            continue
        selected.append(
            SelectedMarket(
                market=market,
                category=classify_category(market),
                period_interval=period_interval,
                candles=tuple(sampled),
            )
        )
        time.sleep(0.03)

    selected_markets = [to_export_market(item) for item in selected]
    selected_candles = [candle for item in selected for candle in item.candles]
    category_counts = dict(Counter(item.category for item in selected))

    if dry_run:
        return CalibrationCollectionResult(
            export_id=export_id,
            export_dir=export_dir,
            historical_jsonl=None,
            audit_json=None,
            audit_markdown=None,
            discovered_count=len(discovered),
            selected_count=len(selected),
            candle_count=len(selected_candles),
            category_counts=category_counts,
            audit_classification=None,
            claim_guardrails={},
            target_status=target_status(len(selected), len(selected_candles)),
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
        min_markets=min_markets,
        max_markets=max_markets,
        max_candle_market_attempts=max_candle_market_attempts,
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
            category_counts=category_counts,
            target_status_value=target_status(len(selected), len(selected_candles)),
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

    return CalibrationCollectionResult(
        export_id=export_id,
        export_dir=export_dir,
        historical_jsonl=import_result.output_jsonl,
        audit_json=audit_artifacts.json_path,
        audit_markdown=audit_artifacts.markdown_path,
        discovered_count=len(discovered),
        selected_count=len(selected),
        candle_count=len(selected_candles),
        category_counts=category_counts,
        audit_classification=audit_result.classification,
        claim_guardrails=audit_result.claim_guardrails,
        target_status=target_status(len(selected), len(selected_candles)),
        dry_run=False,
    )


def sample_calibration_candles(
    *,
    market: sprint1.CandidateMarket,
    candles: list[dict[str, Any]],
    rows_per_market: int,
    period_interval: int,
) -> list[dict[str, Any]]:
    cutoff = sprint1.market_cutoff(market)
    useful: list[dict[str, Any]] = []
    seen_timestamps: set[str] = set()
    for candle in candles:
        candle_dt = sprint1.parse_candle_timestamp(candle.get("end_period_ts"))
        if candle_dt is None or (cutoff is not None and candle_dt >= cutoff):
            continue
        last_price = sprint1.nested(candle, "price.close_dollars")
        if last_price is None:
            continue
        timestamp = sprint1.canonical_timestamp(candle_dt)
        if timestamp in seen_timestamps:
            continue
        seen_timestamps.add(timestamp)
        useful.append(
            {
                **candle,
                "market_ticker": market.ticker,
                "period_interval": period_interval,
                "end_period_ts": timestamp,
                "metadata": {
                    "source_family": market.source_family,
                    "market_category": classify_category(market),
                    "quote_source": "kalshi_candlestick_last_price_close",
                    "bid_ask_required_for_calibration": False,
                    "sampled_before": "earliest_of_close_or_settlement",
                },
            }
        )
    useful.sort(key=lambda row: row["end_period_ts"])
    return sprint1.evenly_sample(useful, rows_per_market)


def calibration_market_sort_key(market: sprint1.CandidateMarket) -> tuple[int, int, str, str]:
    category = classify_category(market)
    category_rank = {
        "economic_indicator": 0,
        "fed_policy": 1,
        "weather": 2,
        "election_public_policy": 3,
        "company_event": 4,
        "major_sports": 5,
        "public_event": 6,
        "unknown": 7,
    }.get(category, 8)
    return (-int(market.volume), category_rank, category, market.ticker)


def classify_category(market: sprint1.CandidateMarket | dict[str, Any]) -> str:
    raw = market.raw if isinstance(market, sprint1.CandidateMarket) else market
    text = " ".join(
        str(raw.get(field) or "").lower()
        for field in ("ticker", "title", "rules_primary", "rules_secondary")
    )
    if any(term in text for term in FED_TERMS):
        return "fed_policy"
    if any(term in text for term in MACRO_TERMS):
        return "economic_indicator"
    if any(term in text for term in WEATHER_TERMS):
        return "weather"
    if any(term in text for term in ELECTION_TERMS):
        return "election_public_policy"
    if any(term in text for term in COMPANY_TERMS):
        return "company_event"
    if any(term in text for term in MAJOR_SPORTS_TERMS):
        return "major_sports"
    if str(raw.get("title") or "").strip():
        return "public_event"
    return "unknown"


def to_export_market(item: SelectedMarket) -> dict[str, Any]:
    row = sprint1.to_export_market(item.market)
    row.setdefault("metadata", {})
    row["metadata"] = {
        **row["metadata"],
        "calibration_category": item.category,
        "temporary_calibration_collection_script": True,
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
    min_markets: int,
    max_markets: int,
    max_candle_market_attempts: int,
) -> dict[str, Any]:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    selected_candles = [candle for item in selected for candle in item.candles]
    notes = (
        "Temporary PR-CAL-2 calibration-only public-data collection helper. "
        "Evidence is intentionally not collected, evidence.jsonl is empty, "
        "bid/ask are not required for calibration output, and acceptance, "
        "superiority, and profitability claims are blocked by audit guardrails. "
        "Terms review remains pending_review by default."
    )
    return {
        "export_id": export_id,
        "dataset_id": f"phase7g_kalshi_calibration_{sprint1.slugify(export_id)}",
        "dataset_label": f"Kalshi calibration-only temporary collection {export_id}",
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
        "collection_script": "scripts/local_only/collect_kalshi_calibration_dataset.py",
        "collection_summary": {
            "discovered_count": discovered_count,
            "selected_count": len(selected),
            "candle_count": len(selected_candles),
            "evidence_count": 0,
            "min_markets": min_markets,
            "max_markets": max_markets,
            "rows_per_market": rows_per_market,
            "period_interval": period_interval,
            "max_candle_market_attempts": max_candle_market_attempts,
            "category_counts": dict(Counter(item.category for item in selected)),
            "target_status": target_status(len(selected), len(selected_candles)),
        },
        "safety": {
            "local_only_output": True,
            "public_read_only_endpoints": True,
            "private_or_authenticated_source": False,
            "evidence_approval_performed": False,
            "terms_review_mutated": False,
            "acceptance_claim": False,
            "strategy_v2_superiority_claim": False,
            "profitability_claim": False,
        },
    }


def render_export_report(
    *,
    export_id: str,
    export_dir: Path,
    discovered_count: int,
    selected: list[SelectedMarket],
    candle_count: int,
    category_counts: dict[str, int],
    target_status_value: str,
) -> str:
    category_lines = [f"- `{name}`: {count}" for name, count in sorted(category_counts.items())]
    if not category_lines:
        category_lines = ["- none"]
    return "\n".join(
        [
            "# Kalshi Calibration Collection Local Report",
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
            "",
            "## Categories",
            "",
            *category_lines,
            "",
            "## Claim Boundary",
            "",
            "- Profile after import: `calibration_only_last_price`",
            "- Bid/ask are intentionally discarded from Phase 7G calibration rows.",
            "- Evidence is intentionally empty.",
            "- Acceptance, Strategy v2 superiority, and profitability claims are not allowed.",
            "",
        ]
    )


def target_status(markets: int, rows: int) -> str:
    if markets >= 150 and rows >= 2000:
        return "stretch"
    if markets >= 60 and rows >= 720:
        return "preferred"
    if markets >= 25 and rows >= 250:
        return "minimum"
    return "missed"


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
            "trading_endpoint_used": False,
            "acceptance_claim": False,
        },
    }


def default_export_id() -> str:
    now = datetime.now(UTC).strftime("%Y%m%d")
    return f"kalshi_calibration_{now}"


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
