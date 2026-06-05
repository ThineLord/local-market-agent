#!/usr/bin/env python3
"""Temporary Kalshi Sprint 1 public data collector.

This is a local research helper, not production application code. It uses only
unauthenticated public/read-only market and candlestick endpoints and writes a
PR-DATA-3-shaped local export directory for manual validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
SOURCE_NAME = "kalshi_public_market_and_candlestick_api"
SOURCE_TYPE = "public_research_export"
TERMS_REVIEW_DEFAULT = "pending_review"
DISCOVERY_FAMILIES = ("live_settled_markets", "historical_markets")
ALLOWED_STATUS = {"settled", "finalized"}
ALLOWED_OUTCOMES = {"yes", "no"}


@dataclass(frozen=True)
class CandidateMarket:
    source_family: str
    raw: dict[str, Any]
    ticker: str
    series_ticker: str
    title: str
    status: str
    result: str
    settlement_ts: str
    volume: float


@dataclass(frozen=True)
class CollectionResult:
    export_id: str
    export_dir: Path
    discovered_count: int
    selected_count: int
    candle_count: int
    evidence_count: int
    dry_run: bool


class KalshiPublicClient:
    def __init__(self, base_url: str = BASE_URL, *, timeout_seconds: float = 20.0) -> None:
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
            headers={"User-Agent": "local-market-agent-kalshi-sprint1/temporary"},
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = collect_export(
        client=KalshiPublicClient(),
        export_id=args.export_id,
        output_root=args.output_root,
        max_markets=args.max_markets,
        rows_per_market=args.rows_per_market,
        period_interval=args.period_interval,
        terms_review=args.terms_review,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "export_id": result.export_id,
                "export_dir": str(result.export_dir),
                "discovered_count": result.discovered_count,
                "selected_count": result.selected_count,
                "candle_count": result.candle_count,
                "evidence_count": result.evidence_count,
                "dry_run": result.dry_run,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect a small local Kalshi Sprint 1 public data export."
    )
    parser.add_argument("--export-id", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/source_exports/kalshi"),
    )
    parser.add_argument("--max-markets", type=positive_int, default=10)
    parser.add_argument("--rows-per-market", type=positive_int, default=10)
    parser.add_argument("--period-interval", type=positive_int, default=60)
    parser.add_argument("--terms-review", default=TERMS_REVIEW_DEFAULT)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def collect_export(
    *,
    client: KalshiPublicClient,
    export_id: str,
    output_root: Path,
    max_markets: int,
    rows_per_market: int,
    period_interval: int,
    terms_review: str,
    dry_run: bool,
) -> CollectionResult:
    export_dir = output_root / export_id
    markets = discover_candidate_markets(client, target_count=max_markets)
    selected_markets: list[dict[str, Any]] = []
    selected_candles: list[dict[str, Any]] = []

    for market in markets:
        raw_candles = fetch_candlesticks(
            client=client,
            market=market,
            period_interval=period_interval,
        )
        sampled = sample_pre_settlement_candles(
            market=market,
            candles=raw_candles,
            rows_per_market=rows_per_market,
            period_interval=period_interval,
        )
        if not sampled:
            continue
        selected_markets.append(to_export_market(market))
        selected_candles.extend(sampled)
        if len(selected_markets) >= max_markets:
            break
        time.sleep(0.05)

    if dry_run:
        return CollectionResult(
            export_id=export_id,
            export_dir=export_dir,
            discovered_count=len(markets),
            selected_count=len(selected_markets),
            candle_count=len(selected_candles),
            evidence_count=0,
            dry_run=True,
        )

    export_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(export_dir / "markets.jsonl", selected_markets)
    write_jsonl(export_dir / "candlesticks.jsonl", selected_candles)
    write_jsonl(export_dir / "evidence.jsonl", [])
    manifest = build_manifest(
        export_id=export_id,
        export_dir=export_dir,
        selected_count=len(selected_markets),
        candle_count=len(selected_candles),
        discovered_count=len(markets),
        period_interval=period_interval,
        rows_per_market=rows_per_market,
        max_markets=max_markets,
        terms_review=terms_review,
    )
    (export_dir / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return CollectionResult(
        export_id=export_id,
        export_dir=export_dir,
        discovered_count=len(markets),
        selected_count=len(selected_markets),
        candle_count=len(selected_candles),
        evidence_count=0,
        dry_run=False,
    )


def discover_candidate_markets(
    client: KalshiPublicClient,
    *,
    target_count: int,
) -> list[CandidateMarket]:
    scanned: list[CandidateMarket] = []
    seen: set[str] = set()
    page_limit = max(1, min(6, target_count * 2))
    per_page = min(1000, max(100, target_count * 80))

    for source_family in DISCOVERY_FAMILIES:
        cursor: str | None = None
        for _ in range(page_limit):
            path, params = discovery_request(source_family, limit=per_page, cursor=cursor)
            payload = client.get_json(path, params)
            for raw in payload.get("markets", []):
                if not isinstance(raw, dict):
                    continue
                candidate = normalize_candidate(source_family, raw)
                if candidate is None or candidate.ticker in seen:
                    continue
                seen.add(candidate.ticker)
                scanned.append(candidate)
            cursor = text_or_none(payload.get("cursor"))
            if not cursor:
                break

    scanned.sort(
        key=lambda item: (
            -item.volume,
            parse_timestamp(item.settlement_ts) or datetime.min.replace(tzinfo=UTC),
            item.ticker,
        )
    )
    return scanned


def discovery_request(
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


def normalize_candidate(source_family: str, raw: dict[str, Any]) -> CandidateMarket | None:
    ticker = text_or_none(raw.get("ticker"))
    event_ticker = text_or_none(raw.get("event_ticker"))
    series_ticker = text_or_none(raw.get("series_ticker")) or derive_series_ticker(
        event_ticker or ticker
    )
    title = text_or_none(raw.get("title"))
    status = (text_or_none(raw.get("status")) or "").lower()
    result = normalize_outcome(raw.get("result") or raw.get("settlement_value_dollars"))
    settlement_ts = first_text(
        raw,
        (
            "settlement_ts",
            "latest_expiration_time",
            "expected_expiration_time",
            "close_time",
        ),
    )
    market_type = (text_or_none(raw.get("market_type")) or "binary").lower()
    if (
        not ticker
        or not series_ticker
        or not title
        or status not in ALLOWED_STATUS
        or result not in ALLOWED_OUTCOMES
        or not settlement_ts
        or market_type != "binary"
    ):
        return None
    if raw.get("mve_collection_ticker") or raw.get("mve_selected_legs"):
        return None
    if parse_timestamp(settlement_ts) is None:
        return None
    return CandidateMarket(
        source_family=source_family,
        raw=raw,
        ticker=ticker,
        series_ticker=series_ticker,
        title=title,
        status=status,
        result=result,
        settlement_ts=canonical_timestamp(settlement_ts),
        volume=float_or_zero(raw.get("volume_fp")),
    )


def fetch_candlesticks(
    *,
    client: KalshiPublicClient,
    market: CandidateMarket,
    period_interval: int,
) -> list[dict[str, Any]]:
    start_ts, end_ts = candle_window(market, period_interval=period_interval)
    if start_ts >= end_ts:
        return []
    params = {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "period_interval": period_interval,
    }
    if market.source_family == "historical_markets":
        payload = client.get_json(
            f"/historical/markets/{urllib.parse.quote(market.ticker)}/candlesticks",
            params,
        )
        raw_candles = payload.get("candlesticks", [])
    else:
        payload = client.get_json(
            "/markets/candlesticks",
            {"market_tickers": market.ticker, **params},
        )
        market_payloads = payload.get("markets", [])
        raw_candles = []
        for item in market_payloads:
            if isinstance(item, dict) and item.get("market_ticker") == market.ticker:
                raw_candles = item.get("candlesticks", [])
                break
    return [normalize_candle(row) for row in raw_candles if isinstance(row, dict)]


def candle_window(market: CandidateMarket, *, period_interval: int) -> tuple[int, int]:
    settlement_dt = parse_timestamp(market.settlement_ts)
    if settlement_dt is None:
        return 0, 0
    open_dt = parse_timestamp(first_text(market.raw, ("open_time", "created_time")) or "")
    lookback_days = max(2, int((period_interval * 12) / 1440) + 2)
    start_dt = open_dt or settlement_dt - timedelta(days=lookback_days)
    start_dt -= timedelta(minutes=period_interval)
    return int(start_dt.timestamp()), int(settlement_dt.timestamp())


def sample_pre_settlement_candles(
    *,
    market: CandidateMarket,
    candles: list[dict[str, Any]],
    rows_per_market: int,
    period_interval: int,
) -> list[dict[str, Any]]:
    cutoff = market_cutoff(market)
    useful: list[dict[str, Any]] = []
    for candle in candles:
        candle_dt = parse_candle_timestamp(candle.get("end_period_ts"))
        if candle_dt is None or (cutoff is not None and candle_dt >= cutoff):
            continue
        if nested(candle, "yes_bid.close_dollars") is None:
            continue
        if nested(candle, "yes_ask.close_dollars") is None:
            continue
        if nested(candle, "price.close_dollars") is None:
            continue
        useful.append(
            {
                **candle,
                "market_ticker": market.ticker,
                "period_interval": period_interval,
                "end_period_ts": canonical_timestamp(candle_dt),
                "metadata": {
                    "source_family": market.source_family,
                    "quote_source": "kalshi_candlestick_close_bid_ask",
                    "sampled_before": "earliest_of_close_or_settlement",
                },
            }
        )
    useful.sort(key=lambda row: row["end_period_ts"])
    return evenly_sample(useful, rows_per_market)


def market_cutoff(market: CandidateMarket) -> datetime | None:
    values = [
        parse_timestamp(value)
        for value in (
            first_text(market.raw, ("close_time",)),
            market.settlement_ts,
            first_text(market.raw, ("latest_expiration_time", "expected_expiration_time")),
        )
    ]
    valid = [value for value in values if value is not None]
    return min(valid) if valid else None


def normalize_candle(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "end_period_ts": raw.get("end_period_ts"),
        "yes_bid": normalize_price_block(raw.get("yes_bid")),
        "yes_ask": normalize_price_block(raw.get("yes_ask")),
        "price": normalize_price_block(raw.get("price")),
        "volume_fp": raw.get("volume_fp", raw.get("volume")),
        "open_interest_fp": raw.get("open_interest_fp", raw.get("open_interest")),
    }


def normalize_price_block(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, Any] = {}
    for key in (
        "open",
        "low",
        "high",
        "close",
        "mean",
        "previous",
        "min",
        "max",
    ):
        value = raw.get(f"{key}_dollars", raw.get(key))
        if value is not None:
            result[f"{key}_dollars"] = value
    return result


def evenly_sample(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return rows
    if limit == 1:
        return [rows[-1]]
    positions = {
        round(index * (len(rows) - 1) / (limit - 1))
        for index in range(limit)
    }
    return [rows[index] for index in sorted(positions)]


def to_export_market(market: CandidateMarket) -> dict[str, Any]:
    raw = market.raw
    event_ticker = text_or_none(raw.get("event_ticker"))
    return {
        "ticker": market.ticker,
        "series_ticker": market.series_ticker,
        "event_ticker": event_ticker,
        "title": market.title,
        "subtitle": text_or_none(raw.get("subtitle")),
        "status": market.status,
        "result": market.result,
        "open_time": canonical_or_none(raw.get("open_time")),
        "close_time": canonical_or_none(raw.get("close_time")),
        "expected_expiration_time": canonical_or_none(raw.get("expected_expiration_time")),
        "latest_expiration_time": canonical_or_none(raw.get("latest_expiration_time")),
        "settlement_ts": market.settlement_ts,
        "settlement_value_dollars": raw.get("settlement_value_dollars"),
        "rules_primary": text_or_none(raw.get("rules_primary")),
        "rules_secondary": text_or_none(raw.get("rules_secondary")),
        "can_close_early": raw.get("can_close_early"),
        "volume_fp": raw.get("volume_fp"),
        "liquidity_dollars": raw.get("liquidity_dollars"),
        "metadata": {
            "source_family": market.source_family,
            "market_type": raw.get("market_type"),
            "event_ticker": event_ticker,
            "series_ticker_inferred": raw.get("series_ticker") in (None, ""),
            "temporary_collection_script": True,
        },
    }


def build_manifest(
    *,
    export_id: str,
    export_dir: Path,
    selected_count: int,
    candle_count: int,
    discovered_count: int,
    period_interval: int,
    rows_per_market: int,
    max_markets: int,
    terms_review: str,
) -> dict[str, Any]:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    notes = (
        "Temporary DATA-SCRIPT-1 local public-data collection helper. "
        "Evidence was not collected; evidence.jsonl is intentionally empty and "
        "manual evidence curation remains required. Terms review defaults to "
        "pending_review unless explicitly overridden by CLI. This export is not "
        "production data and should not be committed as raw data."
    )
    return {
        "export_id": export_id,
        "dataset_id": f"phase7g_kalshi_sprint1_{slugify(export_id)}",
        "dataset_label": f"Kalshi Sprint 1 temporary collection {export_id}",
        "source_name": SOURCE_NAME,
        "source_type": SOURCE_TYPE,
        "source_urls": [
            f"{BASE_URL}/markets",
            f"{BASE_URL}/historical/markets",
            f"{BASE_URL}/markets/candlesticks",
            f"{BASE_URL}/historical/markets/{{ticker}}/candlesticks",
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
        },
        "notes": notes,
        "collection_script": "scripts/local_only/collect_kalshi_sprint1.py",
        "collection_summary": {
            "discovered_count": discovered_count,
            "selected_count": selected_count,
            "candle_count": candle_count,
            "evidence_count": 0,
            "max_markets": max_markets,
            "rows_per_market": rows_per_market,
            "period_interval": period_interval,
            "endpoint_families_used": list(DISCOVERY_FAMILIES)
            + ["live_market_candlesticks", "historical_market_candlesticks"],
        },
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def derive_series_ticker(value: str | None) -> str | None:
    if not value:
        return None
    return value.split("-", maxsplit=1)[0]


def normalize_outcome(value: object) -> str | None:
    text = text_or_none(value)
    if text is None:
        return None
    lower = text.lower()
    if lower in {"yes", "y", "true", "1", "1.0", "1.0000"}:
        return "yes"
    if lower in {"no", "n", "false", "0", "0.0", "0.0000"}:
        return "no"
    return lower


def parse_candle_timestamp(value: object) -> datetime | None:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC).replace(microsecond=0)
    text = text_or_none(value)
    if text is not None and text.isdigit():
        return datetime.fromtimestamp(int(text), UTC).replace(microsecond=0)
    return parse_timestamp(text or "")


def parse_timestamp(value: object) -> datetime | None:
    text = text_or_none(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC).replace(microsecond=0)


def canonical_or_none(value: object) -> str | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    return canonical_timestamp(parsed)


def canonical_timestamp(value: object) -> str:
    parsed = value if isinstance(value, datetime) else parse_timestamp(value)
    if parsed is None:
        raise ValueError(f"invalid timestamp: {value}")
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def first_text(row: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = text_or_none(row.get(field))
        if value is not None:
            return value
    return None


def text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def float_or_zero(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def nested(row: dict[str, Any], dotted_key: str) -> object:
    current: object = row
    for part in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def slugify(value: str) -> str:
    normalized = []
    for char in value.lower():
        if char.isalnum():
            normalized.append(char)
        elif char in {"-", "_"}:
            normalized.append("_")
    slug = "".join(normalized).strip("_")
    return slug or "export"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    sys.exit(main())
