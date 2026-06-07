#!/usr/bin/env python3
"""Collect a local Kalshi Sprint 2 export biased toward reviewable evidence.

This is a temporary public-data collection helper, not production code. It uses
only unauthenticated public/read-only Kalshi market and candlestick endpoints,
generates evidence candidates for human review, and writes a PR-DATA-3-shaped
local export directory. It does not approve evidence or mutate terms review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import collect_kalshi_sprint1 as sprint1  # noqa: E402
import generate_kalshi_evidence_candidates as evidence_gen  # noqa: E402

SOURCE_NAME = "kalshi_public_market_and_candlestick_api"
SOURCE_TYPE = "public_research_export"
TERMS_REVIEW_DEFAULT = "pending_review"
DEFAULT_OUTPUT_ROOT = Path("data/source_exports/kalshi")
DEFAULT_MAX_MARKETS = 10
DEFAULT_ROWS_PER_MARKET = 12
DEFAULT_DISCOVERY_TARGET = 500
DEFAULT_PERIOD_INTERVALS = (60,)
DEFAULT_TIMEOUT_SECONDS = 4.0
GENERATOR = "data_collect_2_evidence_friendly_sprint2_collector"
NETWORK_FAILURE_EXIT_CODE = 2
MIN_CANDLES_PER_SELECTED_MARKET = 4
MIN_EVIDENCE_FRIENDLY_SCORE = 24

FRIENDLY_CATEGORY_SCORES = {
    "economic_indicator": 54,
    "fed_policy": 54,
    "weather": 44,
    "election_public_policy": 38,
    "company_event": 32,
    "major_sports": 28,
    "public_event": 24,
    "unknown": 0,
}

MACRO_TERMS = (
    "cpi",
    "core cpi",
    "pce",
    "inflation",
    "unemployment",
    "nonfarm",
    "payroll",
    "jobs report",
    "jobless claims",
    "initial claims",
    "gdp",
    "retail sales",
    "consumer price",
    "producer price",
    "ppi",
)
FED_TERMS = ("fomc", "fed", "federal reserve", "interest rate", "rate decision")
WEATHER_TERMS = (
    "weather",
    "temperature",
    "high temp",
    "low temp",
    "rain",
    "snow",
    "hurricane",
    "tropical storm",
    "noaa",
    "national weather service",
)
ELECTION_TERMS = (
    "election",
    "president",
    "senate",
    "house election",
    "house of representatives",
    "u.s. house",
    "governor",
    "mayor",
    "primary",
    "ballot",
)
COMPANY_TERMS = (
    "earnings",
    "revenue",
    "eps",
    "quarterly results",
    "10-k",
    "10-q",
    "sec filing",
)
MAJOR_SPORTS_TERMS = (
    "nfl",
    "nba",
    "mlb",
    "nhl",
    "champions league",
    "world cup",
    "super bowl",
    "nba finals",
    "stanley cup",
    "world series",
)
PUBLIC_EVENT_TERMS = (
    "academy awards",
    "oscars",
    "nobel",
    "government shutdown",
    "supreme court",
)
MICRO_MARKET_TERMS = (
    "15 mins",
    "15 minutes",
    "next 15",
    "next hour",
    "in 1 hour",
    "price up",
    "price down",
    "above or below",
    "bitcoin",
    "btc",
    "ethereum",
    "eth",
)
LOW_INFO_SPORTS_TERMS = (
    "m15",
    "w15",
    "w35",
    "w50",
    "itf",
    "challenger",
    "college baseball",
    "college softball",
    "quarterfinal match",
    "harmon",
    "wuning",
    "luan",
)
MENTION_MARKET_TERMS = (
    "what will",
    "say during",
    "will any",
    "mention",
    "mentions",
    "transcript",
)


@dataclass(frozen=True)
class MarketScore:
    ticker: str
    category: str
    score: int
    hard_exclude: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SelectedMarket:
    market: sprint1.CandidateMarket
    score: MarketScore
    period_interval: int
    candles: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class Sprint2CollectionResult:
    export_id: str
    export_dir: Path
    discovered_count: int
    scored_count: int
    rejected_count: int
    selected_count: int
    candle_count: int
    candidate_count: int
    categories: tuple[str, ...]
    timestamp_status_counts: dict[str, int]
    dry_run: bool


class RetryingKalshiPublicClient(sprint1.KalshiPublicClient):
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        max_attempts: int = 1,
        retry_delay_seconds: float = 0.5,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.max_attempts = max_attempts
        self.retry_delay_seconds = retry_delay_seconds

    def get_json(self, path: str, params: dict[str, object]) -> dict[str, Any]:
        last_error: RuntimeError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return super().get_json(path, params)
            except RuntimeError as exc:
                last_error = exc
                if attempt >= self.max_attempts:
                    break
                time.sleep(self.retry_delay_seconds * attempt)
        assert last_error is not None
        raise last_error


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    export_id = args.export_id or default_export_id()
    client = RetryingKalshiPublicClient(timeout_seconds=args.timeout_seconds)
    try:
        result = collect_export(
            client=client,
            export_id=export_id,
            output_root=args.output_root,
            max_markets=args.max_markets,
            rows_per_market=args.rows_per_market,
        period_intervals=parse_intervals(args.period_intervals),
        discovery_target=args.discovery_target,
        max_candle_market_attempts=args.max_candle_market_attempts,
        terms_review=args.terms_review,
        dry_run=args.dry_run,
        skip_candidate_metadata=args.skip_candidate_metadata,
        )
    except RuntimeError as exc:
        if is_public_kalshi_get_failure(exc):
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
        raise
    print(
        json.dumps(
            {
                "candidate_count": result.candidate_count,
                "candle_count": result.candle_count,
                "categories": result.categories,
                "discovered_count": result.discovered_count,
                "dry_run": result.dry_run,
                "export_dir": str(result.export_dir),
                "export_id": result.export_id,
                "rejected_count": result.rejected_count,
                "scored_count": result.scored_count,
                "selected_count": result.selected_count,
                "timestamp_status_counts": result.timestamp_status_counts,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect a local evidence-friendly Kalshi Sprint 2 export."
    )
    parser.add_argument("--export-id")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--max-markets", type=positive_int, default=DEFAULT_MAX_MARKETS)
    parser.add_argument(
        "--rows-per-market",
        type=positive_int,
        default=DEFAULT_ROWS_PER_MARKET,
    )
    parser.add_argument(
        "--period-intervals",
        default=",".join(str(value) for value in DEFAULT_PERIOD_INTERVALS),
        help="Comma-separated Kalshi candle intervals to try, in minutes.",
    )
    parser.add_argument(
        "--discovery-target",
        type=positive_int,
        default=DEFAULT_DISCOVERY_TARGET,
    )
    parser.add_argument("--terms-review", default=TERMS_REVIEW_DEFAULT)
    parser.add_argument(
        "--timeout-seconds",
        type=positive_float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument("--skip-candidate-metadata", action="store_true")
    parser.add_argument(
        "--max-candle-market-attempts",
        type=positive_int,
        help="Maximum scored markets to try for candlestick collection.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def collect_export(
    *,
    client: sprint1.KalshiPublicClient,
    export_id: str,
    output_root: Path,
    max_markets: int,
    rows_per_market: int,
    period_intervals: tuple[int, ...],
    discovery_target: int,
    max_candle_market_attempts: int | None,
    terms_review: str,
    dry_run: bool,
    skip_candidate_metadata: bool = False,
) -> Sprint2CollectionResult:
    export_dir = output_root / export_id
    discovered = sprint1.discover_candidate_markets(
        client,
        target_count=discovery_target,
    )
    scored = [score_candidate_market(market) for market in discovered]
    score_by_ticker = {score.ticker: score for score in scored}
    selected: list[SelectedMarket] = []
    candle_attempt_limit = max_candle_market_attempts or market_candle_attempt_limit(
        max_markets
    )
    candle_attempts = 0

    for market in sorted(
        discovered,
        key=lambda item: (
            -score_by_ticker[item.ticker].score,
            score_by_ticker[item.ticker].category,
            -item.volume,
            item.ticker,
        ),
    ):
        score = score_by_ticker[market.ticker]
        if score.hard_exclude:
            continue
        if not is_selectable_score(score):
            continue
        if not category_allowed(selected, score.category, max_markets=max_markets):
            continue
        if candle_attempts >= candle_attempt_limit:
            break
        candle_attempts += 1
        candle_result = fetch_best_candles(
            client=client,
            market=market,
            rows_per_market=rows_per_market,
            period_intervals=period_intervals,
        )
        if candle_result is None:
            continue
        selected.append(
            SelectedMarket(
                market=market,
                score=score,
                period_interval=candle_result[0],
                candles=tuple(candle_result[1]),
            )
        )
        if len(selected) >= max_markets and has_category_diversity(selected):
            break
        time.sleep(0.05)

    if len(selected) < max_markets:
        selected = fill_selection_without_category_cap(
            client=client,
            discovered=discovered,
            score_by_ticker=score_by_ticker,
            already_selected=selected,
            max_markets=max_markets,
            rows_per_market=rows_per_market,
            period_intervals=period_intervals,
            attempt_limit=candle_attempt_limit,
        )

    selected_markets = [to_export_market(item) for item in selected]
    selected_candles = [candle for item in selected for candle in item.candles]
    candidates = build_evidence_candidates(
        selected,
        skip_metadata_fetch=skip_candidate_metadata,
    )
    rejected = [score for score in scored if score.hard_exclude]
    timestamp_counts = timestamp_status_counts(candidates)

    if not dry_run:
        export_dir.mkdir(parents=True, exist_ok=True)
        sprint1.write_jsonl(export_dir / "markets.jsonl", selected_markets)
        sprint1.write_jsonl(export_dir / "candlesticks.jsonl", selected_candles)
        sprint1.write_jsonl(export_dir / "evidence.jsonl", [])
        sprint1.write_jsonl(export_dir / "evidence_candidates.jsonl", candidates)
        manifest = build_manifest(
            export_id=export_id,
            export_dir=export_dir,
            selected=selected,
            discovered_count=len(discovered),
            scored_count=len(scored),
            rejected_count=len(rejected),
            candidate_count=len(candidates),
            terms_review=terms_review,
        )
        (export_dir / "source_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (export_dir / "evidence_candidate_generation_report.md").write_text(
            render_local_candidate_report(
                export_id=export_id,
                export_dir=export_dir,
                selected=selected,
                candidates=candidates,
                timestamp_counts=timestamp_counts,
            ),
            encoding="utf-8",
        )

    return Sprint2CollectionResult(
        export_id=export_id,
        export_dir=export_dir,
        discovered_count=len(discovered),
        scored_count=len(scored),
        rejected_count=len(rejected),
        selected_count=len(selected),
        candle_count=len(selected_candles),
        candidate_count=len(candidates),
        categories=tuple(sorted({item.score.category for item in selected})),
        timestamp_status_counts=timestamp_counts,
        dry_run=dry_run,
    )


def score_candidate_market(market: sprint1.CandidateMarket | dict[str, Any]) -> MarketScore:
    raw = market.raw if isinstance(market, sprint1.CandidateMarket) else market
    ticker = sprint1.text_or_none(raw.get("ticker")) or ""
    title = sprint1.text_or_none(raw.get("title")) or ""
    rules_primary = sprint1.text_or_none(raw.get("rules_primary")) or ""
    rules_secondary = sprint1.text_or_none(raw.get("rules_secondary")) or ""
    text = normalized_text(" ".join([ticker, title, rules_primary, rules_secondary]))
    category = classify_market_category(text)
    score = FRIENDLY_CATEGORY_SCORES[category]
    reasons: list[str] = [f"category:{category}"]
    hard_exclude = False

    status = (sprint1.text_or_none(raw.get("status")) or "").lower()
    outcome = sprint1.normalize_outcome(raw.get("result") or raw.get("settlement_value_dollars"))
    if status in sprint1.ALLOWED_STATUS:
        score += 10
        reasons.append("resolved_or_finalized")
    else:
        score -= 20
        reasons.append("not_resolved")
    if outcome in sprint1.ALLOWED_OUTCOMES:
        score += 5
        reasons.append("clear_binary_outcome")
    if rules_primary or rules_secondary:
        score += 8
        reasons.append("rules_present")
    else:
        score -= 35
        reasons.append("missing_rules")
    if contains_any(text, ("official", "source", "according to", "reported by", "released by")):
        score += 18
        reasons.append("rules_reference_public_source")
    if contains_any(text, ("bureau", "department", "federal reserve", "national weather service", "noaa")):
        score += 12
        reasons.append("primary_source_named")

    duration_hours = market_duration_hours(raw)
    if duration_hours is not None:
        if duration_hours < 2:
            score -= 55
            hard_exclude = True
            reasons.append("ultra_short_market_window")
        elif duration_hours < 24:
            score -= 25
            reasons.append("intraday_market_window")
        elif duration_hours >= 24 * 7:
            score += 18
            reasons.append("multi_day_review_window")
        elif duration_hours >= 24:
            score += 10
            reasons.append("day_plus_review_window")

    if is_micro_price_market(text):
        score -= 90
        hard_exclude = True
        reasons.append("excluded_micro_price_market")
    if is_mention_market(text):
        score -= 80
        hard_exclude = True
        reasons.append("excluded_mention_or_transcript_market")
    if is_obscure_low_info_sports_market(text):
        score -= 75
        hard_exclude = True
        reasons.append("excluded_obscure_low_info_sports")
    if title and not contains_any(
        text,
        MACRO_TERMS
        + FED_TERMS
        + WEATHER_TERMS
        + ELECTION_TERMS
        + COMPANY_TERMS
        + MAJOR_SPORTS_TERMS
        + PUBLIC_EVENT_TERMS,
    ):
        score -= 8
        reasons.append("no_strong_public_reference_keyword")

    return MarketScore(
        ticker=ticker,
        category=category,
        score=score,
        hard_exclude=hard_exclude,
        reasons=tuple(reasons),
    )


def classify_market_category(text: str) -> str:
    if contains_any(text, FED_TERMS):
        return "fed_policy"
    if contains_any(text, MACRO_TERMS):
        return "economic_indicator"
    if contains_any(text, WEATHER_TERMS):
        return "weather"
    if contains_any(text, ELECTION_TERMS):
        return "election_public_policy"
    if contains_any(text, COMPANY_TERMS):
        return "company_event"
    if contains_any(text, MAJOR_SPORTS_TERMS):
        return "major_sports"
    if contains_any(text, PUBLIC_EVENT_TERMS):
        return "public_event"
    return "unknown"


def fetch_best_candles(
    *,
    client: sprint1.KalshiPublicClient,
    market: sprint1.CandidateMarket,
    rows_per_market: int,
    period_intervals: tuple[int, ...],
) -> tuple[int, list[dict[str, Any]]] | None:
    best: tuple[int, list[dict[str, Any]]] | None = None
    for interval in period_intervals:
        try:
            raw_candles = sprint1.fetch_candlesticks(
                client=client,
                market=market,
                period_interval=interval,
            )
        except RuntimeError:
            continue
        sampled = sprint1.sample_pre_settlement_candles(
            market=market,
            candles=raw_candles,
            rows_per_market=rows_per_market,
            period_interval=interval,
        )
        if len(sampled) >= min(MIN_CANDLES_PER_SELECTED_MARKET, rows_per_market):
            return interval, sampled
        if sampled and (best is None or len(sampled) > len(best[1])):
            best = (interval, sampled)
    if best is not None and len(best[1]) >= min(
        MIN_CANDLES_PER_SELECTED_MARKET,
        rows_per_market,
    ):
        return best
    return None


def fill_selection_without_category_cap(
    *,
    client: sprint1.KalshiPublicClient,
    discovered: list[sprint1.CandidateMarket],
    score_by_ticker: dict[str, MarketScore],
    already_selected: list[SelectedMarket],
    max_markets: int,
    rows_per_market: int,
    period_intervals: tuple[int, ...],
    attempt_limit: int,
) -> list[SelectedMarket]:
    selected = list(already_selected)
    selected_tickers = {item.market.ticker for item in selected}
    candle_attempts = 0
    for market in sorted(
        discovered,
        key=lambda item: (-score_by_ticker[item.ticker].score, -item.volume, item.ticker),
    ):
        if len(selected) >= max_markets:
            break
        score = score_by_ticker[market.ticker]
        if score.hard_exclude or market.ticker in selected_tickers:
            continue
        if not is_selectable_score(score):
            continue
        if candle_attempts >= attempt_limit:
            break
        candle_attempts += 1
        candle_result = fetch_best_candles(
            client=client,
            market=market,
            rows_per_market=rows_per_market,
            period_intervals=period_intervals,
        )
        if candle_result is None:
            continue
        selected.append(
            SelectedMarket(
                market=market,
                score=score,
                period_interval=candle_result[0],
                candles=tuple(candle_result[1]),
            )
        )
        selected_tickers.add(market.ticker)
        time.sleep(0.05)
    return selected


def category_allowed(
    selected: list[SelectedMarket],
    category: str,
    *,
    max_markets: int,
) -> bool:
    if len(selected) < 3 and category not in {item.score.category for item in selected}:
        return True
    category_cap = max(2, math.ceil(max_markets * 0.4))
    count = sum(1 for item in selected if item.score.category == category)
    return count < category_cap


def has_category_diversity(selected: list[SelectedMarket]) -> bool:
    return len({item.score.category for item in selected}) >= min(3, len(selected))


def market_candle_attempt_limit(max_markets: int) -> int:
    return max(20, max_markets * 2)


def is_selectable_score(score: MarketScore) -> bool:
    return (
        score.category != "unknown"
        and not score.hard_exclude
        and score.score >= MIN_EVIDENCE_FRIENDLY_SCORE
    )


def build_evidence_candidates(
    selected: list[SelectedMarket],
    *,
    skip_metadata_fetch: bool,
) -> list[dict[str, Any]]:
    retrieved_at = evidence_gen.canonical_timestamp(evidence_gen.utc_now())
    rows: list[dict[str, Any]] = []
    for item in selected:
        seeds = seed_sources_for_selected_market(item)
        for index, seed in enumerate(seeds[:2], start=1):
            url = str(seed["url"])
            public_ok, public_reason = evidence_gen.public_url_check(url)
            if not public_ok:
                continue
            metadata = (
                evidence_gen.PageMetadata(None, None, None, ())
                if skip_metadata_fetch
                else evidence_gen.fetch_page_metadata(url, timeout_seconds=10.0)
            )
            published_at = metadata.published_at
            timestamp_status = evidence_gen.classify_timestamp_status(published_at)
            warnings = list(metadata.warnings)
            if not published_at:
                warnings.append("missing_published_at")
            if public_reason:
                warnings.append(public_reason)
            warnings.append("needs_human_timestamp_review")
            if seed.get("warning"):
                warnings.append(str(seed["warning"]))
            domain = evidence_gen.domain_from_url(url)
            title = evidence_gen.clean_text(metadata.title or seed["title"])
            evidence_type = str(seed["evidence_type"])
            row = {
                "market_ticker": item.market.ticker,
                "evidence_id": evidence_gen.stable_evidence_id(
                    item.market.ticker,
                    domain or "unknown",
                    title,
                    index,
                ),
                "source": seed["source"],
                "title": title,
                "url": url,
                "published_at": published_at,
                "retrieved_at": retrieved_at,
                "summary": evidence_gen.clean_text(
                    f"{seed['summary']} Candidate generated for human review only; "
                    "verify timestamp safety before approval."
                ),
                "relevance_score": float(seed["relevance_score"]),
                "credibility_score": float(seed["credibility_score"]),
                "reviewer_status": "needs_more_review",
                "timestamp_status": timestamp_status,
                "evidence_type": evidence_type,
                "supports_side": "context_or_rule",
                "curator_notes": (
                    "Sprint 2 evidence-friendly seed candidate. Human reviewer must "
                    "verify public timestamp, source terms, and relevance before approval."
                ),
                "metadata": {
                    "reviewer_status": "needs_human_review",
                    "generated_by": GENERATOR,
                    "timestamp_status": timestamp_status,
                    "evidence_type": evidence_type,
                    "supports_side": "context_or_rule",
                    "source_public": True,
                    "private_or_authenticated_source": False,
                    "required_evidence_before_ts": earliest_candle_timestamp(item),
                    "candidate_warnings": evidence_gen.dedupe(warnings),
                    "search_query_used": seed["search_query_used"],
                    "source_domain": domain,
                    "retrieval_method": "sprint2_official_seed_source",
                    "market_category": item.score.category,
                },
            }
            rows.append(row)
    return rows


def seed_sources_for_selected_market(item: SelectedMarket) -> list[dict[str, object]]:
    category = item.score.category
    text = normalized_text(
        " ".join(
            [
                item.market.title,
                sprint1.text_or_none(item.market.raw.get("rules_primary")) or "",
                sprint1.text_or_none(item.market.raw.get("rules_secondary")) or "",
            ]
        )
    )
    if category == "fed_policy":
        return [
            official_seed(
                "Federal Reserve FOMC calendars",
                "Federal Reserve",
                "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                "Official Federal Reserve FOMC calendar page for policy decision timing.",
                "official Fed FOMC calendar",
                "official_public_source",
            ),
            official_seed(
                "Federal Reserve monetary policy press releases",
                "Federal Reserve",
                "https://www.federalreserve.gov/newsevents/pressreleases/monetary.htm",
                "Official Federal Reserve monetary policy press release index.",
                "official Fed monetary policy press releases",
                "official_public_source",
            ),
        ]
    if category == "economic_indicator":
        if contains_any(text, ("cpi", "consumer price", "inflation")):
            return [
                official_seed(
                    "BLS Consumer Price Index",
                    "U.S. Bureau of Labor Statistics",
                    "https://www.bls.gov/cpi/",
                    "Official BLS Consumer Price Index page and release access point.",
                    "official BLS CPI release calendar data",
                    "official_public_source",
                ),
                official_seed(
                    "BLS Economic News Release Schedule",
                    "U.S. Bureau of Labor Statistics",
                    "https://www.bls.gov/schedule/news_release/",
                    "Official BLS economic release schedule for timestamp review.",
                    "official BLS release schedule",
                    "official_public_source",
                ),
            ]
        if contains_any(text, ("unemployment", "nonfarm", "payroll", "jobs")):
            return [
                official_seed(
                    "BLS Employment Situation",
                    "U.S. Bureau of Labor Statistics",
                    "https://www.bls.gov/news.release/empsit.htm",
                    "Official BLS Employment Situation release page.",
                    "official BLS Employment Situation release",
                    "official_public_source",
                ),
                official_seed(
                    "BLS Economic News Release Schedule",
                    "U.S. Bureau of Labor Statistics",
                    "https://www.bls.gov/schedule/news_release/",
                    "Official BLS economic release schedule for timestamp review.",
                    "official BLS release schedule",
                    "official_public_source",
                ),
            ]
        if contains_any(text, ("jobless", "initial claims", "claims")):
            return [
                official_seed(
                    "Department of Labor Unemployment Insurance Weekly Claims",
                    "U.S. Department of Labor",
                    "https://www.dol.gov/ui/data.pdf",
                    "Official Department of Labor weekly unemployment insurance claims release.",
                    "official DOL weekly jobless claims release",
                    "official_public_source",
                    warning="pdf_or_non_html_timestamp_review_required",
                ),
                official_seed(
                    "Department of Labor unemployment insurance data",
                    "U.S. Department of Labor",
                    "https://oui.doleta.gov/unemploy/claims.asp",
                    "Official Department of Labor unemployment claims data page.",
                    "official DOL unemployment claims data",
                    "official_public_source",
                ),
            ]
        return [
            official_seed(
                "BLS Economic News Release Schedule",
                "U.S. Bureau of Labor Statistics",
                "https://www.bls.gov/schedule/news_release/",
                "Official BLS economic release schedule for timestamp review.",
                "official BLS economic release schedule",
                "official_public_source",
            ),
            official_seed(
                "BEA News Release Schedule",
                "U.S. Bureau of Economic Analysis",
                "https://www.bea.gov/news/schedule",
                "Official BEA news release schedule for economic indicator timing.",
                "official BEA release schedule",
                "official_public_source",
            ),
        ]
    if category == "weather":
        return [
            official_seed(
                "National Weather Service",
                "National Weather Service",
                "https://www.weather.gov/",
                "Official National Weather Service public weather information page.",
                "official National Weather Service forecast observation",
                "official_public_source",
            ),
            official_seed(
                "National Hurricane Center",
                "NOAA National Hurricane Center",
                "https://www.nhc.noaa.gov/",
                "Official NOAA National Hurricane Center public advisory page.",
                "official NOAA NHC advisory",
                "official_public_source",
            ),
        ]
    if category == "major_sports":
        return major_sports_seeds(text)
    if category == "election_public_policy":
        return [
            official_seed(
                "Federal Election Commission",
                "Federal Election Commission",
                "https://www.fec.gov/",
                "Official FEC public election information source.",
                "official election source",
                "official_public_source",
            ),
            official_seed(
                "USA.gov voting and elections",
                "USA.gov",
                "https://www.usa.gov/voting-and-elections",
                "Official U.S. government voting and elections information page.",
                "official government election information",
                "official_public_source",
            ),
        ]
    if category == "company_event":
        return [
            official_seed(
                "SEC EDGAR Company Search",
                "U.S. Securities and Exchange Commission",
                "https://www.sec.gov/edgar/search/",
                "Official SEC EDGAR search page for public company filings.",
                "official SEC EDGAR filing",
                "official_public_source",
            ),
            official_seed(
                "SEC Current Reports",
                "U.S. Securities and Exchange Commission",
                "https://www.sec.gov/edgar/browse/",
                "Official SEC company filing browser.",
                "official SEC company filing browser",
                "official_public_source",
            ),
        ]
    return [
        official_seed(
            "Kalshi market rule context source needed",
            "Public source TBD",
            "https://kalshi.com/",
            "Public candidate placeholder for source discovery; human review required.",
            "public source discovery needed",
            "market_context",
            relevance_score=0.35,
            credibility_score=0.45,
            warning="weak_generic_seed_source",
        ),
        official_seed(
            "Public source search needed",
            "Public source TBD",
            "https://www.usa.gov/",
            "Generic public source discovery seed; human review required.",
            "public source search needed",
            "unknown",
            relevance_score=0.25,
            credibility_score=0.45,
            warning="weak_generic_seed_source",
        ),
    ]


def major_sports_seeds(text: str) -> list[dict[str, object]]:
    if "nfl" in text or "super bowl" in text:
        league = ("NFL Schedules", "NFL", "https://www.nfl.com/schedules/")
    elif "nba" in text:
        league = ("NBA Schedule", "NBA", "https://www.nba.com/schedule")
    elif "mlb" in text or "world series" in text:
        league = ("MLB Schedule", "MLB", "https://www.mlb.com/schedule")
    elif "nhl" in text or "stanley cup" in text:
        league = ("NHL Schedule", "NHL", "https://www.nhl.com/schedule")
    else:
        league = ("Official league schedule", "Official sports league", "https://www.espn.com/")
    return [
        official_seed(
            league[0],
            league[1],
            league[2],
            "Official or widely available public league schedule page.",
            f"official {league[1]} schedule",
            "sports_event_reference",
            relevance_score=0.72,
            credibility_score=0.75,
        ),
        official_seed(
            "ESPN Scores and Schedules",
            "ESPN",
            "https://www.espn.com/",
            "Reputable public sports schedule and score context page.",
            "reputable public sports schedule",
            "reputable_public_news",
            relevance_score=0.6,
            credibility_score=0.65,
        ),
    ]


def official_seed(
    title: str,
    source: str,
    url: str,
    summary: str,
    search_query_used: str,
    evidence_type: str,
    *,
    relevance_score: float = 0.82,
    credibility_score: float = 0.9,
    warning: str | None = None,
) -> dict[str, object]:
    return {
        "title": title,
        "source": source,
        "url": url,
        "summary": summary,
        "search_query_used": search_query_used,
        "evidence_type": evidence_type,
        "relevance_score": relevance_score,
        "credibility_score": credibility_score,
        "warning": warning,
    }


def to_export_market(item: SelectedMarket) -> dict[str, Any]:
    row = sprint1.to_export_market(item.market)
    row["metadata"] = {
        **row.get("metadata", {}),
        "evidence_friendly_score": item.score.score,
        "evidence_friendly_category": item.score.category,
        "evidence_friendly_reasons": list(item.score.reasons),
        "period_interval_selected": item.period_interval,
        "temporary_collection_script": "DATA-COLLECT-2",
    }
    return row


def build_manifest(
    *,
    export_id: str,
    export_dir: Path,
    selected: list[SelectedMarket],
    discovered_count: int,
    scored_count: int,
    rejected_count: int,
    candidate_count: int,
    terms_review: str,
) -> dict[str, Any]:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    categories = sorted({item.score.category for item in selected})
    notes = (
        "Temporary DATA-COLLECT-2 evidence-friendly public Kalshi collection helper. "
        "Evidence candidates are generated for human review only; evidence.jsonl is "
        "intentionally empty until review approval. Terms review remains pending by "
        "default. This export is local research data and should not be committed."
    )
    return {
        "export_id": export_id,
        "dataset_id": f"phase7g_kalshi_sprint2_evidence_friendly_{slugify(export_id)}",
        "dataset_label": f"Kalshi Sprint 2 evidence-friendly pilot {export_id}",
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
        "terms_review": terms_review,
        "terms_reviewed_by": "pending_review"
        if terms_review == TERMS_REVIEW_DEFAULT
        else "explicit_cli_override",
        "terms_reviewed_at": now,
        "private_or_authenticated_source": False,
        "network_used_by_adapter": False,
        "raw_file_sha256": {
            "markets.jsonl": file_sha256(export_dir / "markets.jsonl"),
            "candlesticks.jsonl": file_sha256(export_dir / "candlesticks.jsonl"),
            "evidence.jsonl": file_sha256(export_dir / "evidence.jsonl"),
            "evidence_candidates.jsonl": file_sha256(
                export_dir / "evidence_candidates.jsonl"
            ),
        },
        "notes": notes,
        "collection_script": "scripts/local_only/collect_kalshi_sprint2_evidence_friendly.py",
        "collection_summary": {
            "discovered_count": discovered_count,
            "scored_count": scored_count,
            "heuristic_rejected_count": rejected_count,
            "selected_count": len(selected),
            "candle_count": sum(len(item.candles) for item in selected),
            "evidence_count": 0,
            "evidence_candidate_count": candidate_count,
            "categories": categories,
            "market_selection": [
                {
                    "ticker": item.market.ticker,
                    "category": item.score.category,
                    "score": item.score.score,
                    "period_interval": item.period_interval,
                    "candle_count": len(item.candles),
                }
                for item in selected
            ],
            "endpoint_families_used": list(sprint1.DISCOVERY_FAMILIES)
            + ["live_market_candlesticks", "historical_market_candlesticks"],
        },
    }


def render_local_candidate_report(
    *,
    export_id: str,
    export_dir: Path,
    selected: list[SelectedMarket],
    candidates: list[dict[str, Any]],
    timestamp_counts: dict[str, int],
) -> str:
    lines = [
        "# Kalshi Sprint 2 Evidence Candidate Generation Report",
        "",
        f"Export id: `{export_id}`",
        f"Export dir: `{export_dir}`",
        "",
        "All candidates are for human review only. No evidence was approved.",
        "",
        "## Summary",
        "",
        f"- Markets selected: {len(selected)}",
        f"- Candidates generated: {len(candidates)}",
        f"- Timestamp status distribution: {timestamp_counts}",
        "",
        "## Markets",
        "",
        "| Market | Category | Score | Candles | Candidates |",
        "|---|---:|---:|---:|---:|",
    ]
    candidate_counts: dict[str, int] = {}
    for row in candidates:
        ticker = str(row["market_ticker"])
        candidate_counts[ticker] = candidate_counts.get(ticker, 0) + 1
    for item in selected:
        lines.append(
            f"| `{item.market.ticker}` | {item.score.category} | {item.score.score} | "
            f"{len(item.candles)} | {candidate_counts.get(item.market.ticker, 0)} |"
        )
    lines.extend(
        [
            "",
            "## Review UI",
            "",
            "```bash",
            "PYTHONPATH=src .venv/bin/streamlit run scripts/local_only/review_kalshi_evidence.py -- \\",
            f"  --export-id {export_id} \\",
            "  --export-root data/source_exports/kalshi \\",
            "  --candidates-file evidence_candidates.jsonl \\",
            "  --overwrite",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def timestamp_status_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in candidates:
        status = str(row.get("metadata", {}).get("timestamp_status") or "missing")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def is_public_kalshi_get_failure(exc: RuntimeError) -> bool:
    return "kalshi public get failed" in str(exc).lower()


def build_network_failure_diagnostic(
    exc: RuntimeError,
    *,
    client: sprint1.KalshiPublicClient,
    export_id: str,
    output_root: Path,
) -> dict[str, Any]:
    return {
        "export_id": export_id,
        "export_dir": str(output_root / export_id),
        "network_status": classify_public_get_failure(exc),
        "endpoint_families_attempted": endpoint_families_from_urls(
            client.requested_urls
        ),
        "failure_message": str(exc),
        "safety": {
            "public_read_only": True,
            "private_or_authenticated_source": False,
            "credentials_used": False,
            "cookies_or_browser_session_used": False,
            "tls_verification_disabled": False,
        },
        "rerun_command": (
            "PYTHONPATH=src .venv/bin/python "
            "scripts/local_only/collect_kalshi_sprint2_evidence_friendly.py "
            f"--export-id {export_id}"
        ),
    }


def classify_public_get_failure(exc: RuntimeError) -> str:
    message = str(exc).lower()
    tls_markers = (
        "ssl",
        "tls",
        "certificate",
        "unexpected_eof",
        "unexpected eof",
        "connection reset",
        "connection refused",
        "connection aborted",
        "network is unreachable",
    )
    timeout_markers = ("timed out", "timeout")
    if contains_any(message, tls_markers):
        return "network_blocked_or_tls_failure"
    if contains_any(message, timeout_markers):
        return "network_timeout"
    if "http error" in message or "failed " in message:
        return "public_endpoint_http_failure"
    return "network_blocked_or_tls_failure"


def endpoint_families_from_urls(urls: list[str]) -> list[str]:
    families: set[str] = set()
    for url in urls:
        if "/historical/markets/" in url and "/candlesticks" in url:
            families.add("historical_market_candlesticks")
        elif "/markets/candlesticks" in url:
            families.add("live_market_candlesticks")
        elif "/historical/markets" in url:
            families.add("historical_markets")
        elif "/markets" in url:
            families.add("live_settled_markets")
    return sorted(families)


def market_duration_hours(raw: dict[str, Any]) -> float | None:
    open_dt = sprint1.parse_timestamp(raw.get("open_time") or raw.get("created_time"))
    close_dt = sprint1.parse_timestamp(
        raw.get("close_time")
        or raw.get("expected_expiration_time")
        or raw.get("latest_expiration_time")
        or raw.get("settlement_ts")
    )
    if open_dt is None or close_dt is None:
        return None
    return max(0.0, (close_dt - open_dt).total_seconds() / 3600)


def earliest_candle_timestamp(item: SelectedMarket) -> str:
    timestamps = [
        str(candle["end_period_ts"])
        for candle in item.candles
        if candle.get("end_period_ts")
    ]
    return min(timestamps) if timestamps else ""


def is_micro_price_market(text: str) -> bool:
    if contains_any(text, ("price up", "price down", "above or below")) and contains_any(
        text,
        ("next 15", "15 mins", "15 minutes", "next hour", "bitcoin", "btc", "ethereum", "eth"),
    ):
        return True
    return "kxbtc15m" in text or "kxeth15m" in text


def is_obscure_low_info_sports_market(text: str) -> bool:
    return contains_any(text, LOW_INFO_SPORTS_TERMS) and contains_any(
        text,
        (
            "tennis",
            "match",
            "quarterfinal",
            "college baseball",
            "college softball",
        ),
    )


def is_mention_market(text: str) -> bool:
    return contains_any(text, MENTION_MARKET_TERMS)


def normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term_matches(text, term) for term in terms)


def term_matches(text: str, term: str) -> bool:
    return term_pattern(term).search(text) is not None


@lru_cache(maxsize=256)
def term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term.lower()).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")


def parse_intervals(value: str) -> tuple[int, ...]:
    intervals = tuple(
        int(part.strip())
        for part in value.split(",")
        if part.strip()
    )
    if not intervals or any(item <= 0 for item in intervals):
        msg = "period intervals must be positive integers"
        raise argparse.ArgumentTypeError(msg)
    return intervals


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        msg = "value must be positive"
        raise argparse.ArgumentTypeError(msg)
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        msg = "value must be positive"
        raise argparse.ArgumentTypeError(msg)
    return parsed


def default_export_id() -> str:
    date = datetime.now(UTC).strftime("%Y%m%d")
    return f"kalshi_sprint2_evidence_friendly_{date}"


def slugify(value: str) -> str:
    return sprint1.slugify(value)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    sys.exit(main())
