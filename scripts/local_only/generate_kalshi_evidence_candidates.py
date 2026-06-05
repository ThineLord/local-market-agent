#!/usr/bin/env python3
"""Generate public evidence candidates for a local Kalshi export.

This helper creates candidates for human review only. It reads local export
files, optionally queries public web search without credentials or cookies, and
writes evidence_candidates.jsonl. It does not approve evidence, write
evidence.jsonl, mutate source_manifest.json, or integrate with production paths.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

DEFAULT_EXPORT_ROOT = Path("data/source_exports/kalshi")
DEFAULT_EXPORT_ID = "kalshi_sprint1_20260605_public_probe"
GENERATOR_VERSION = "data_evidence_4_candidate_generator.v1"
DEFAULT_USER_AGENT = "lma-data-evidence-4-public-candidate-generator/1.0"
EVIDENCE_CANDIDATES_JSONL = "evidence_candidates.jsonl"
GENERATION_REPORT_MD = "evidence_candidate_generation_report.md"
UI_REVIEW_STATUS = "needs_more_review"
METADATA_REVIEW_STATUS = "needs_human_review"
MAX_FETCH_BYTES = 256_000

PRIVATE_HOSTS = {
    "0.0.0.0",
    "127.0.0.1",
    "::1",
    "localhost",
}
PRIVATE_URL_MARKERS = (
    "/account",
    "/accounts",
    "/admin",
    "/dashboard",
    "/login",
    "/logout",
    "/signin",
    "/sign-in",
    "/signup",
    "/user/",
    "/users/",
)
PRIVATE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "code",
    "cookie",
    "key",
    "session",
    "token",
}
OFFICIAL_DOMAINS = {
    "cfbenchmarks.com",
    "docs.cfbenchmarks.com",
    "itftennis.com",
    "www.cfbenchmarks.com",
    "www.itftennis.com",
}
REPUTABLE_PUBLIC_DOMAINS = {
    "apnews.com",
    "bbc.com",
    "betexplorer.com",
    "cmegroup.com",
    "coretennis.net",
    "espn.com",
    "reuters.com",
    "sofascore.com",
    "www.betexplorer.com",
    "www.cmegroup.com",
    "www.coretennis.net",
    "www.sofascore.com",
}
WEAK_SOURCE_DOMAINS = {
    "polymarket.com",
    "reddit.com",
    "www.reddit.com",
}


@dataclass(frozen=True)
class MarketContext:
    ticker: str
    title: str
    subtitle: str
    rules_primary: str
    rules_secondary: str
    result: str
    settlement_ts: str
    earliest_candle_ts: str
    latest_candle_ts: str
    required_evidence_before_ts: str
    candle_count: int
    worksheet_queries: tuple[str, ...]
    suggested_primary_source_type: str


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    published_at: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class SourceCandidate:
    title: str
    url: str
    source: str
    snippet: str
    search_query_used: str
    retrieval_method: str
    published_at: str | None = None


@dataclass(frozen=True)
class PageMetadata:
    title: str | None
    description: str | None
    published_at: str | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class GenerationResult:
    export_dir: Path
    candidates_path: Path
    report_path: Path
    market_count: int
    candidate_count: int
    markets_covered: int
    timestamp_coverage_estimate: float
    warnings: tuple[str, ...]


class FixtureSearchClient:
    def __init__(self, fixtures: dict[str, list[SearchResult]]) -> None:
        self.fixtures = fixtures

    def search(self, query: str, max_results: int) -> tuple[list[SearchResult], str | None]:
        return self.fixtures.get(query, [])[:max_results], None


class DuckDuckGoSearchClient:
    def __init__(self, *, timeout_seconds: float, user_agent: str) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def search(self, query: str, max_results: int) -> tuple[list[SearchResult], str | None]:
        params = urlencode({"q": query})
        url = f"https://html.duckduckgo.com/html/?{params}"
        request = Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read(MAX_FETCH_BYTES).decode("utf-8", "replace")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            return [], f"search_failed:{type(exc).__name__}"
        if "anomaly-modal" in body or "Unfortunately, bots use DuckDuckGo too" in body:
            return [], "search_challenge"
        return parse_duckduckgo_html(body)[:max_results], None


class DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture_title = False
        self._capture_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        classes = set(attrs_dict.get("class", "").split())
        if tag == "a" and "result__a" in classes:
            href = attrs_dict.get("href", "")
            self._current = {"url": unwrap_duckduckgo_url(href), "title": "", "snippet": ""}
            self._capture_title = True
        elif self._current is not None and "result__snippet" in classes:
            self._capture_snippet = True

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        text = clean_text(data)
        if not text:
            return
        if self._capture_title:
            self._current["title"] = clean_text(
                f"{self._current.get('title', '')} {text}"
            )
        elif self._capture_snippet:
            self._current["snippet"] = clean_text(
                f"{self._current.get('snippet', '')} {text}"
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title:
            self._capture_title = False
            if self._current and self._current.get("url") and self._current.get("title"):
                self.results.append(self._current)
        elif self._capture_snippet and tag in {"a", "div"}:
            self._capture_snippet = False


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.description: str | None = None
        self.published_at: str | None = None
        self.time_values: list[str] = []
        self._capture_title = False
        self._json_ld_chunks: list[str] = []
        self._capture_json_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag == "title":
            self._capture_title = True
        elif tag == "meta":
            key = (
                attrs_dict.get("property")
                or attrs_dict.get("name")
                or attrs_dict.get("itemprop")
                or ""
            ).lower()
            content = attrs_dict.get("content", "")
            if key in {
                "article:published_time",
                "datepublished",
                "dc.date",
                "dc.date.issued",
                "pubdate",
                "publishdate",
            }:
                self.published_at = self.published_at or content
            elif key in {"description", "og:description", "twitter:description"}:
                self.description = self.description or clean_text(content)
        elif tag == "time":
            value = attrs_dict.get("datetime") or attrs_dict.get("title")
            if value:
                self.time_values.append(value)
        elif tag == "script" and "ld+json" in attrs_dict.get("type", "").lower():
            self._capture_json_ld = True

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self.title_parts.append(data)
        elif self._capture_json_ld:
            self._json_ld_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._capture_title = False
        elif tag == "script" and self._capture_json_ld:
            self._capture_json_ld = False

    def finish(self) -> PageMetadata:
        published_at = self.published_at or first_json_ld_date(self._json_ld_chunks)
        if not published_at and self.time_values:
            published_at = self.time_values[0]
        return PageMetadata(
            title=clean_text(" ".join(self.title_parts)) or None,
            description=self.description,
            published_at=published_at,
            warnings=(),
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    export_dir = resolve_export_dir(
        export_id=args.export_id,
        export_root=args.export_root,
        export_dir=args.export_dir,
    )
    search_client = (
        FixtureSearchClient(load_search_fixtures(args.search_fixtures))
        if args.search_fixtures
        else None
    )
    result = generate_candidates(
        export_dir=export_dir,
        output_file=args.output_file,
        report_file=args.report_file,
        search_client=search_client,
        skip_network=args.skip_network,
        use_seed_sources=not args.no_seed_sources,
        include_future_candidates=args.include_future_candidates,
        max_results_per_query=args.max_results_per_query,
        max_candidates_per_market=args.max_candidates_per_market,
        timeout_seconds=args.timeout_seconds,
    )
    print(
        json.dumps(
            {
                "candidate_count": result.candidate_count,
                "candidates_path": str(result.candidates_path),
                "export_dir": str(result.export_dir),
                "market_count": result.market_count,
                "markets_covered": result.markets_covered,
                "report_path": str(result.report_path),
                "timestamp_coverage_estimate": result.timestamp_coverage_estimate,
                "warnings": result.warnings,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate public Kalshi evidence candidates for human review."
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--export-id", default=DEFAULT_EXPORT_ID)
    target.add_argument("--export-dir", type=Path)
    parser.add_argument("--export-root", type=Path, default=DEFAULT_EXPORT_ROOT)
    parser.add_argument("--output-file", default=EVIDENCE_CANDIDATES_JSONL)
    parser.add_argument("--report-file", default=GENERATION_REPORT_MD)
    parser.add_argument(
        "--search-fixtures",
        type=Path,
        help="Optional JSON fixture mapping queries to public search results.",
    )
    parser.add_argument(
        "--skip-network",
        action="store_true",
        help="Do not perform live public search or page metadata fetches.",
    )
    parser.add_argument(
        "--no-seed-sources",
        action="store_true",
        help="Disable built-in official/public seed URLs.",
    )
    parser.add_argument(
        "--include-future-candidates",
        action="store_true",
        help="Keep useful candidates with published_at after the required timestamp.",
    )
    parser.add_argument("--max-results-per-query", type=positive_int, default=2)
    parser.add_argument("--max-candidates-per-market", type=positive_int, default=4)
    parser.add_argument("--timeout-seconds", type=positive_float, default=10.0)
    return parser.parse_args(argv)


def generate_candidates(
    *,
    export_dir: Path,
    output_file: str | Path = EVIDENCE_CANDIDATES_JSONL,
    report_file: str | Path = GENERATION_REPORT_MD,
    search_client: FixtureSearchClient | DuckDuckGoSearchClient | None = None,
    skip_network: bool = False,
    use_seed_sources: bool = True,
    include_future_candidates: bool = False,
    max_results_per_query: int = 2,
    max_candidates_per_market: int = 4,
    timeout_seconds: float = 10.0,
) -> GenerationResult:
    manifest_path = export_dir / "source_manifest.json"
    manifest_before = manifest_path.read_text(encoding="utf-8")
    manifest = load_json_object(manifest_path)
    markets = load_jsonl(export_dir / "markets.jsonl")
    candles = load_jsonl(export_dir / "candlesticks.jsonl")
    worksheet_rows = load_worksheet_rows(export_dir)
    contexts = build_market_contexts(
        markets=markets,
        candles=candles,
        worksheet_rows=worksheet_rows,
    )
    client = search_client
    if client is None and not skip_network:
        client = DuckDuckGoSearchClient(
            timeout_seconds=timeout_seconds,
            user_agent=DEFAULT_USER_AGENT,
        )
    retrieved_at = canonical_timestamp(utc_now())
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    search_errors: dict[str, list[str]] = {}

    for context in contexts:
        source_candidates: list[SourceCandidate] = []
        if use_seed_sources:
            source_candidates.extend(seed_sources_for_market(context))
        for query in generate_search_queries(context):
            if client is None:
                continue
            results, search_error = client.search(query, max_results_per_query)
            if search_error:
                warnings.append(f"{context.ticker}: {query}: {search_error}")
                search_errors.setdefault(context.ticker, []).append(search_error)
                continue
            source_candidates.extend(
                source_candidate_from_search_result(
                    result,
                    search_query_used=query,
                )
                for result in results
            )

        market_rows = build_candidate_rows_for_market(
            context=context,
            source_candidates=source_candidates,
            retrieved_at=retrieved_at,
            include_future_candidates=include_future_candidates,
            skip_page_fetch=skip_network,
            timeout_seconds=timeout_seconds,
        )
        rows.extend(dedupe_candidate_rows(market_rows)[:max_candidates_per_market])

    output_path = export_dir / output_file
    report_path = export_dir / report_file
    write_jsonl(output_path, rows)
    report_path.write_text(
        render_generation_report(
            export_dir=export_dir,
            manifest=manifest,
            contexts=contexts,
            candidates=rows,
            warnings=warnings,
            search_errors=search_errors,
            output_path=output_path,
            report_path=report_path,
        ),
        encoding="utf-8",
    )
    if manifest_path.read_text(encoding="utf-8") != manifest_before:
        msg = "source_manifest.json was modified unexpectedly"
        raise RuntimeError(msg)
    evidence_path = export_dir / "evidence.jsonl"
    if evidence_path.exists() and evidence_path.stat().st_size > 0:
        warnings.append("existing_nonempty_evidence_jsonl_left_untouched")

    market_count = len(contexts)
    covered_markets = {str(row["market_ticker"]) for row in rows}
    timestamp_coverage_estimate = estimate_timestamp_coverage(contexts, rows)
    return GenerationResult(
        export_dir=export_dir,
        candidates_path=output_path,
        report_path=report_path,
        market_count=market_count,
        candidate_count=len(rows),
        markets_covered=len(covered_markets),
        timestamp_coverage_estimate=timestamp_coverage_estimate,
        warnings=tuple(dedupe(warnings)),
    )


def build_candidate_rows_for_market(
    *,
    context: MarketContext,
    source_candidates: list[SourceCandidate],
    retrieved_at: str,
    include_future_candidates: bool,
    skip_page_fetch: bool,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, source_candidate in enumerate(source_candidates, start=1):
        url = source_candidate.url
        public_check = public_url_check(url)
        if not public_check[0]:
            continue
        metadata = (
            PageMetadata(None, None, None, ())
            if skip_page_fetch
            else fetch_page_metadata(url, timeout_seconds=timeout_seconds)
        )
        published_at = source_candidate.published_at or metadata.published_at
        timestamp_status = classify_timestamp_status(published_at)
        warnings = candidate_warnings(
            context=context,
            source_candidate=source_candidate,
            metadata=metadata,
            published_at=published_at,
        )
        future = published_after_required(
            published_at,
            context.required_evidence_before_ts,
        )
        if future:
            warnings.append("future_evidence_candidate")
            if not include_future_candidates and not useful_future_candidate(
                source_candidate
            ):
                continue
        evidence_type = classify_evidence_type(url, context, source_candidate.title)
        supports_side = classify_supports_side(context, evidence_type, source_candidate.title)
        domain = domain_from_url(url)
        title = clean_text(metadata.title or source_candidate.title)
        summary = candidate_summary(
            context=context,
            source_candidate=source_candidate,
            metadata=metadata,
            evidence_type=evidence_type,
        )
        source = source_candidate.source or source_name_from_domain(domain)
        relevance_score, credibility_score = score_candidate(
            context=context,
            domain=domain,
            evidence_type=evidence_type,
            title=title,
        )
        evidence_id = stable_evidence_id(
            context.ticker,
            domain or "unknown",
            title,
            index,
        )
        warnings = dedupe(warnings)
        row = {
            "market_ticker": context.ticker,
            "evidence_id": evidence_id,
            "source": source,
            "title": title,
            "url": url,
            "published_at": published_at,
            "retrieved_at": retrieved_at,
            "summary": summary,
            "relevance_score": relevance_score,
            "credibility_score": credibility_score,
            "reviewer_status": UI_REVIEW_STATUS,
            "timestamp_status": timestamp_status,
            "evidence_type": evidence_type,
            "supports_side": supports_side,
            "curator_notes": (
                "Candidate generated for human review only; verify public access, "
                "timestamp safety, relevance, and source terms before approval."
            ),
            "metadata": {
                "reviewer_status": METADATA_REVIEW_STATUS,
                "generated_by": "data_evidence_4_candidate_generator",
                "generator_version": GENERATOR_VERSION,
                "timestamp_status": timestamp_status,
                "evidence_type": evidence_type,
                "supports_side": supports_side,
                "source_public": True,
                "private_or_authenticated_source": False,
                "required_evidence_before_ts": context.required_evidence_before_ts,
                "candidate_warnings": warnings,
                "search_query_used": source_candidate.search_query_used,
                "source_domain": domain,
                "retrieval_method": source_candidate.retrieval_method,
            },
        }
        rows.append(row)
    return rows


def seed_sources_for_market(context: MarketContext) -> list[SourceCandidate]:
    title_and_rules = f"{context.title} {context.rules_primary} {context.rules_secondary}"
    text = title_and_rules.lower()
    if "btc" in text or "brti" in text or "bitcoin" in text:
        return [
            SourceCandidate(
                title="CME CF Bitcoin Real Time Index (BRTI)",
                url="https://www.cfbenchmarks.com/data/indices/BRTI",
                source="CF Benchmarks",
                snippet=(
                    "Official CF Benchmarks public BRTI page describing the "
                    "Bitcoin Real Time Index referenced by the market rule."
                ),
                search_query_used='seed: official CF Benchmarks BRTI page',
                retrieval_method="seed_public_url",
            ),
            SourceCandidate(
                title="CME CF Real Time Indices Methodology",
                url="https://docs.cfbenchmarks.com/CME%20CF%20Real%20Time%20Indices%20Methodology.pdf",
                source="CF Benchmarks",
                snippet=(
                    "Official public methodology document for CME CF real-time "
                    "indices, useful for rule and reference-price context."
                ),
                search_query_used='seed: official CF Benchmarks methodology',
                retrieval_method="seed_public_url",
            ),
        ]
    if "m15 harmon" in text:
        return itf_seed_sources(
            tournament_title="M15 Harmon 2026 Tennis Tournament",
            base_url="https://www.itftennis.com/en/tournament/m15-harmon/gum/2026/m-itf-gum-2026-002/",
            context=context,
        )
    if "m15 luan" in text or "zeng vs huang" in text:
        return itf_seed_sources(
            tournament_title="M15 Luan 2026 Tennis Tournament",
            base_url="https://www.itftennis.com/en/tournament/m15-luan/chn/2026/m-itf-chn-2026-010/",
            context=context,
        )
    if "w50 wuning" in text or "saigo" in text or "yang vs ren" in text:
        return itf_seed_sources(
            tournament_title="W50 Wuning 2026 Tennis Tournament",
            base_url="https://www.itftennis.com/en/tournament/w50-wuning/chn/2026/w-itf-chn-2026-019/",
            context=context,
        )
    return []


def itf_seed_sources(
    *,
    tournament_title: str,
    base_url: str,
    context: MarketContext,
) -> list[SourceCandidate]:
    return [
        SourceCandidate(
            title=tournament_title,
            url=base_url,
            source="International Tennis Federation",
            snippet=(
                "Official public ITF tournament page for the event referenced by "
                f"{context.ticker}."
            ),
            search_query_used=f"seed: official ITF tournament page for {context.ticker}",
            retrieval_method="seed_public_url",
        ),
        SourceCandidate(
            title=f"{tournament_title} Draws and Results",
            url=base_url.rstrip("/") + "/draws-and-results/",
            source="International Tennis Federation",
            snippet=(
                "Official public ITF draws/results page for human timestamp and "
                "event-context review."
            ),
            search_query_used=f"seed: official ITF draws/results page for {context.ticker}",
            retrieval_method="seed_public_url",
        ),
    ]


def generate_search_queries(context: MarketContext) -> tuple[str, ...]:
    queries = list(context.worksheet_queries)
    text = f"{context.title} {context.rules_primary} {context.rules_secondary}"
    lowered = text.lower()
    if "btc" in lowered or "bitcoin" in lowered or "brti" in lowered:
        queries.extend(
            [
                "CF Benchmarks BRTI Bitcoin Real Time Index official page",
                "CME CF Bitcoin Real Time Index methodology BRTI",
            ]
        )
    elif "tennis" in lowered or "quarterfinal" in lowered:
        players = tennis_player_query_text(context.title)
        tournament = tournament_query_text(context.title)
        if tournament:
            queries.append(f'site:itftennis.com "{tournament}" {players}'.strip())
        queries.append(f'official ITF "{players}" "{tournament}"'.strip())
    return tuple(dedupe([query for query in queries if query]))


def source_candidate_from_search_result(
    result: SearchResult,
    *,
    search_query_used: str,
) -> SourceCandidate:
    domain = domain_from_url(result.url)
    return SourceCandidate(
        title=result.title or source_name_from_domain(domain),
        url=result.url,
        source=result.source or source_name_from_domain(domain),
        snippet=result.snippet,
        published_at=result.published_at,
        search_query_used=search_query_used,
        retrieval_method="public_search_result",
    )


def load_search_fixtures(path: Path) -> dict[str, list[SearchResult]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_queries = payload.get("queries", payload)
    fixtures: dict[str, list[SearchResult]] = {}
    for query, rows in raw_queries.items():
        fixtures[str(query)] = [
            SearchResult(
                title=str(row.get("title") or ""),
                url=str(row.get("url") or ""),
                snippet=str(row.get("snippet") or ""),
                published_at=row.get("published_at"),
                source=row.get("source"),
            )
            for row in rows
            if isinstance(row, dict)
        ]
    return fixtures


def fetch_page_metadata(url: str, *, timeout_seconds: float) -> PageMetadata:
    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get("content-type", "")
            body = response.read(MAX_FETCH_BYTES)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return PageMetadata(None, None, None, (f"metadata_fetch_failed:{type(exc).__name__}",))
    if "html" not in content_type.lower():
        return PageMetadata(None, None, None, ("metadata_fetch_non_html",))
    parser = MetadataParser()
    parser.feed(body.decode("utf-8", "replace"))
    metadata = parser.finish()
    return PageMetadata(
        metadata.title,
        metadata.description,
        metadata.published_at,
        metadata.warnings,
    )


def candidate_warnings(
    *,
    context: MarketContext,
    source_candidate: SourceCandidate,
    metadata: PageMetadata,
    published_at: str | None,
) -> list[str]:
    warnings = list(metadata.warnings)
    domain = domain_from_url(source_candidate.url)
    if not published_at:
        warnings.append("missing_published_at")
    elif classify_timestamp_status(published_at) == "explicit_date_only":
        warnings.append("date_only_timestamp")
    elif classify_timestamp_status(published_at) == "missing":
        warnings.append("ambiguous_published_at")
    if domain is None:
        warnings.append("source_domain_unknown")
    elif domain in WEAK_SOURCE_DOMAINS:
        warnings.append("weak_source")
    if domain and domain not in OFFICIAL_DOMAINS:
        warnings.append("not_primary_source")
    text = " ".join(
        [
            source_candidate.title,
            source_candidate.snippet,
            metadata.description or "",
        ]
    ).lower()
    if "login" in text or "sign in" in text or "signin" in text:
        warnings.append("source_mentions_login_for_full_details")
    if "result" in text or "score" in text or "settlement" in text:
        warnings.append("possible_settlement_or_final_result_context")
    if published_after_required(published_at, context.required_evidence_before_ts):
        warnings.append("published_after_required_evidence_before_ts")
    return warnings


def candidate_summary(
    *,
    context: MarketContext,
    source_candidate: SourceCandidate,
    metadata: PageMetadata,
    evidence_type: str,
) -> str:
    base = metadata.description or source_candidate.snippet
    if not base:
        if evidence_type == "price_reference":
            base = (
                "Public official reference-price page or methodology relevant to "
                "the BTC BRTI rule."
            )
        elif evidence_type == "sports_event_reference":
            base = (
                "Public official sports event page relevant to the tennis match "
                "named in the market rule."
            )
        else:
            base = "Public candidate source generated for human evidence review."
    return clean_text(
        f"{base} Candidate for {context.ticker}; reviewer must verify timestamp "
        "safety before approval."
    )


def classify_evidence_type(url: str, context: MarketContext, title: str) -> str:
    domain = domain_from_url(url) or ""
    text = f"{url} {context.title} {context.rules_primary} {title}".lower()
    if "cfbenchmarks" in domain or "brti" in text or "bitcoin real time index" in text:
        return "price_reference"
    if "itftennis" in domain or "tennis" in text or "quarterfinal" in text:
        return "sports_event_reference"
    if domain in OFFICIAL_DOMAINS:
        return "official_public_source"
    if domain in REPUTABLE_PUBLIC_DOMAINS:
        return "reputable_public_news"
    if "market" in text or "prediction" in text:
        return "market_context"
    return "unknown"


def classify_supports_side(context: MarketContext, evidence_type: str, title: str) -> str:
    text = f"{context.title} {context.rules_primary} {title}".lower()
    if evidence_type in {"price_reference", "sports_event_reference", "official_public_source"}:
        return "context_or_rule"
    result = context.result.lower()
    if result == "yes" and any(word in text for word in ("yes", "win", "higher", "up")):
        return "yes"
    if result == "no" and any(word in text for word in ("no", "lost", "lower", "down")):
        return "no"
    return "unknown"


def classify_timestamp_status(value: str | None) -> str:
    if not value:
        return "missing"
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return "explicit_date_only"
    parsed = parse_timestamp(text)
    if parsed is not None:
        return "explicit_timezone"
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", text):
        return "inferred_from_page"
    return "missing"


def score_candidate(
    *,
    context: MarketContext,
    domain: str | None,
    evidence_type: str,
    title: str,
) -> tuple[float, float]:
    credibility = 0.55
    if domain in OFFICIAL_DOMAINS:
        credibility = 0.9
    elif domain in REPUTABLE_PUBLIC_DOMAINS:
        credibility = 0.7
    elif domain in WEAK_SOURCE_DOMAINS:
        credibility = 0.4
    relevance = 0.5
    if evidence_type in {"price_reference", "sports_event_reference"}:
        relevance = 0.84
    elif evidence_type == "official_public_source":
        relevance = 0.78
    elif evidence_type == "reputable_public_news":
        relevance = 0.65
    market_terms = set(tokenize(context.title))
    title_terms = set(tokenize(title))
    if market_terms and len(market_terms & title_terms) >= 2:
        relevance = min(0.95, relevance + 0.08)
    return round(relevance, 2), round(credibility, 2)


def public_url_check(url: str) -> tuple[bool, str | None]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, "not_http_public_url"
    host = (parsed.hostname or "").lower()
    if not host or host in PRIVATE_HOSTS or is_private_ipv4(host):
        return False, "private_or_local_host"
    path_lower = parsed.path.lower()
    if any(marker in path_lower for marker in PRIVATE_URL_MARKERS):
        return False, "private_or_authenticated_path"
    query_keys = {key.lower() for key in parse_qs(parsed.query)}
    if query_keys & PRIVATE_QUERY_KEYS:
        return False, "private_or_authenticated_query"
    return True, None


def useful_future_candidate(source_candidate: SourceCandidate) -> bool:
    domain = domain_from_url(source_candidate.url)
    if domain in OFFICIAL_DOMAINS:
        return True
    title = source_candidate.title.lower()
    return "official" in title or "methodology" in title


def published_after_required(published_at: str | None, required_ts: str) -> bool:
    published = parse_timestamp(published_at)
    required = parse_timestamp(required_ts)
    return published is not None and required is not None and published > required


def estimate_timestamp_coverage(
    contexts: list[MarketContext],
    candidates: list[dict[str, Any]],
) -> float:
    if not contexts:
        return 0.0
    covered = set()
    for row in candidates:
        published_at = row.get("published_at")
        if classify_timestamp_status(published_at) != "explicit_timezone":
            continue
        context = next(
            (item for item in contexts if item.ticker == row.get("market_ticker")),
            None,
        )
        if context and not published_after_required(
            str(published_at),
            context.required_evidence_before_ts,
        ):
            covered.add(context.ticker)
    return round(len(covered) / len(contexts), 4)


def render_generation_report(
    *,
    export_dir: Path,
    manifest: dict[str, Any],
    contexts: list[MarketContext],
    candidates: list[dict[str, Any]],
    warnings: list[str],
    search_errors: dict[str, list[str]],
    output_path: Path,
    report_path: Path,
) -> str:
    by_market: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        by_market.setdefault(str(row["market_ticker"]), []).append(row)
    timestamp_coverage = estimate_timestamp_coverage(contexts, candidates)
    warning_counts: dict[str, int] = {}
    for row in candidates:
        for warning in row.get("metadata", {}).get("candidate_warnings", []):
            warning_counts[warning] = warning_counts.get(warning, 0) + 1
    lines = [
        "# Kalshi Sprint 1 Evidence Candidate Generation",
        "",
        f"Date: {canonical_timestamp(utc_now())}",
        "",
        "Scope: DATA-EVIDENCE-4 public evidence candidate generation for human review.",
        "",
        "This helper generated candidate evidence only. It did not approve evidence, "
        "write approved `evidence.jsonl`, clear terms review, change acceptance gates, "
        "or add trading/order/account logic.",
        "",
        "## Commands",
        "",
        "```bash",
        "PYTHONPATH=src .venv/bin/python scripts/local_only/generate_kalshi_evidence_candidates.py \\",
        "  --export-id kalshi_sprint1_20260605_public_probe \\",
        "  --export-root data/source_exports/kalshi",
        "```",
        "",
        "Launch review UI after generation:",
        "",
        "```bash",
        "PYTHONPATH=src .venv/bin/streamlit run scripts/local_only/review_kalshi_evidence.py -- \\",
        "  --export-id kalshi_sprint1_20260605_public_probe \\",
        "  --export-root data/source_exports/kalshi \\",
        "  --candidates-file evidence_candidates.jsonl \\",
        "  --overwrite",
        "```",
        "",
        "## Outputs",
        "",
        f"- Export directory: `{export_dir}`",
        f"- Candidate file: `{output_path}`",
        f"- Generation report: `{report_path}`",
        f"- Manifest terms_review remains: `{manifest.get('terms_review')}`",
        "",
        "## Summary",
        "",
        f"- Markets processed: {len(contexts)}",
        f"- Candidates generated: {len(candidates)}",
        f"- Markets covered by at least one candidate: {len(by_market)}",
        f"- Timestamp coverage estimate: {timestamp_coverage:.2%}",
        "",
        "## Markets Processed",
        "",
        "| Market | Required before | Candidates | Explicit timestamp candidates |",
        "|---|---:|---:|---:|",
    ]
    for context in contexts:
        rows = by_market.get(context.ticker, [])
        explicit = sum(
            1
            for row in rows
            if row.get("metadata", {}).get("timestamp_status") == "explicit_timezone"
        )
        lines.append(
            f"| `{context.ticker}` | `{context.required_evidence_before_ts}` | "
            f"{len(rows)} | {explicit} |"
        )
    lines.extend(["", "## Warning Counts", ""])
    if warning_counts:
        for warning, count in sorted(warning_counts.items()):
            lines.append(f"- {warning}: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "## Search Warnings", ""])
    if warnings:
        for warning in dedupe(warnings):
            lines.append(f"- {warning}")
    else:
        lines.append("- none")
    lines.extend(["", "## Search Error Summary", ""])
    if search_errors:
        for ticker, errors in sorted(search_errors.items()):
            lines.append(f"- `{ticker}`: {', '.join(dedupe(errors))}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Remaining Manual Review Steps",
            "",
            "- Open the Streamlit review UI with `evidence_candidates.jsonl`.",
            "- Reject candidates with missing or unsafe timestamps unless a human can verify them.",
            "- Do not approve final result or settlement pages as forecast-time evidence.",
            "- Keep `terms_review=pending_review` until a separate human/legal review is complete.",
            "- Export approved evidence only after the human review pass.",
            "",
            "## Limitations",
            "",
            "- Candidate timestamps may be missing when public pages do not expose a reliable publication time.",
            "- Search result snippets are discovery aids, not approved evidence.",
            "- Official source pages can still require human terms and timestamp review.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_market_contexts(
    *,
    markets: list[dict[str, Any]],
    candles: list[dict[str, Any]],
    worksheet_rows: dict[str, dict[str, str]],
) -> list[MarketContext]:
    candles_by_market = group_candles_by_market(candles)
    contexts: list[MarketContext] = []
    for market in sorted(markets, key=lambda item: required_text(item, "ticker")):
        ticker = required_text(market, "ticker")
        worksheet = worksheet_rows.get(ticker, {})
        candle_timestamps = sorted(
            timestamp
            for timestamp in (
                canonical_or_none(candle.get("end_period_ts"))
                for candle in candles_by_market.get(ticker, [])
            )
            if timestamp is not None
        )
        earliest = candle_timestamps[0] if candle_timestamps else ""
        latest = candle_timestamps[-1] if candle_timestamps else ""
        contexts.append(
            MarketContext(
                ticker=ticker,
                title=text_or_empty(market.get("title")),
                subtitle=text_or_empty(market.get("subtitle")),
                rules_primary=text_or_empty(market.get("rules_primary")),
                rules_secondary=text_or_empty(market.get("rules_secondary")),
                result=text_or_empty(market.get("result")),
                settlement_ts=canonical_or_none(market.get("settlement_ts")) or "",
                earliest_candle_ts=worksheet.get("earliest_candle_ts") or earliest,
                latest_candle_ts=worksheet.get("latest_candle_ts") or latest,
                required_evidence_before_ts=worksheet.get("required_evidence_before_ts")
                or earliest,
                candle_count=int(worksheet.get("number_of_candles") or len(candle_timestamps)),
                worksheet_queries=tuple(
                    query
                    for query in (
                        worksheet.get("suggested_evidence_query_1"),
                        worksheet.get("suggested_evidence_query_2"),
                    )
                    if query
                ),
                suggested_primary_source_type=worksheet.get(
                    "suggested_primary_source_type",
                    "",
                ),
            )
        )
    return contexts


def load_worksheet_rows(export_dir: Path) -> dict[str, dict[str, str]]:
    csv_path = export_dir / "evidence_worksheet.csv"
    if not csv_path.exists():
        return {}
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {
        str(row.get("market_ticker") or ""): dict(row)
        for row in rows
        if row.get("market_ticker")
    }


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path} must contain a JSON object"
        raise ValueError(msg)
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                msg = f"{path}:{line_number} must contain a JSON object"
                raise ValueError(msg)
            rows.append(payload)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def group_candles_by_market(candles: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candle in candles:
        ticker = text_or_empty(candle.get("market_ticker"))
        if ticker:
            grouped.setdefault(ticker, []).append(candle)
    return grouped


def parse_duckduckgo_html(body: str) -> list[SearchResult]:
    parser = DuckDuckGoParser()
    parser.feed(body)
    return [
        SearchResult(
            title=html.unescape(item["title"]),
            url=item["url"],
            snippet=html.unescape(item.get("snippet", "")),
        )
        for item in parser.results
        if item.get("url")
    ]


def unwrap_duckduckgo_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if "duckduckgo.com" in (parsed.hostname or "") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target)
    return url


def first_json_ld_date(chunks: list[str]) -> str | None:
    for chunk in chunks:
        try:
            payload = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        found = find_json_date(payload)
        if found:
            return found
    return None


def find_json_date(value: object) -> str | None:
    if isinstance(value, dict):
        for key in ("datePublished", "dateCreated", "uploadDate"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        for item in value.values():
            found = find_json_date(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_json_date(item)
            if found:
                return found
    return None


def resolve_export_dir(
    *,
    export_id: str | None,
    export_root: Path,
    export_dir: Path | None,
) -> Path:
    if export_dir is not None:
        return export_dir
    if not export_id:
        msg = "--export-id is required when --export-dir is not provided"
        raise ValueError(msg)
    return export_root / export_id


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


def required_text(row: dict[str, Any], field: str) -> str:
    value = text_or_empty(row.get(field))
    if not value:
        msg = f"missing required field {field}"
        raise ValueError(msg)
    return value


def text_or_empty(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clean_text(value: object) -> str:
    text = html.unescape(text_or_empty(value))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def canonical_or_none(value: object) -> str | None:
    parsed = parse_timestamp(value)
    return canonical_timestamp(parsed) if parsed is not None else None


def parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def canonical_timestamp(value: datetime) -> str:
    return (
        value.astimezone(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def utc_now() -> datetime:
    return datetime.now(UTC)


def stable_evidence_id(ticker: str, domain: str, title: str, index: int) -> str:
    digest = sha256(f"{ticker}|{domain}|{title}|{index}".encode()).hexdigest()[:10]
    return f"ev_{safe_id(ticker)}_{safe_id(domain)}_{digest}"


def safe_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return normalized[:80] or "unknown"


def domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(str(url))
    host = (parsed.hostname or "").lower()
    return host or None


def source_name_from_domain(domain: str | None) -> str:
    if not domain:
        return "Unknown public source"
    parts = domain.split(".")
    if len(parts) >= 2:
        return parts[-2].replace("-", " ").title()
    return domain.title()


def is_private_ipv4(host: str) -> bool:
    parts = host.split(".")
    if len(parts) != 4 or not all(part.isdigit() for part in parts):
        return False
    nums = [int(part) for part in parts]
    return (
        nums[0] == 10
        or nums[0] == 127
        or (nums[0] == 172 and 16 <= nums[1] <= 31)
        or (nums[0] == 192 and nums[1] == 168)
    )


def tennis_player_query_text(title: str) -> str:
    text = title
    match = re.search(r"Will\s+(.+?)\s+win\s+the\s+(.+?):", text, re.IGNORECASE)
    if match:
        player = match.group(1)
        matchup = match.group(2).replace("vs", " ")
        return compact_query_text(f"{player} {matchup}")
    return compact_query_text(title)


def tournament_query_text(title: str) -> str:
    match = re.search(r":\s*([^?]+?)\s+Quarterfinal", title, re.IGNORECASE)
    if match:
        return compact_query_text(match.group(1))
    for phrase in ("M15 Harmon", "M15 Luan", "W50 Wuning"):
        if phrase.lower() in title.lower():
            return phrase
    return ""


def compact_query_text(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9'-]+", text)
    return " ".join(words[:12])


def tokenize(text: str) -> list[str]:
    stop = {"the", "will", "win", "match", "vs", "and", "price", "next"}
    return [
        word.lower()
        for word in re.findall(r"[A-Za-z0-9]+", text)
        if len(word) > 2 and word.lower() not in stop
    ]


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def dedupe_candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row.get("market_ticker")), str(row.get("url")))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


if __name__ == "__main__":
    sys.exit(main())
