#!/usr/bin/env python3
"""Prepare a local evidence curation worksheet for a Kalshi export.

This helper reads only local PR-DATA-3 export files. It does not fetch URLs,
scrape websites, automate browser access, or call source APIs.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WORKSHEET_COLUMNS = (
    "market_ticker",
    "title",
    "subtitle",
    "rules_primary",
    "rules_secondary",
    "result",
    "settlement_ts",
    "earliest_candle_ts",
    "latest_candle_ts",
    "number_of_candles",
    "required_evidence_before_ts",
    "suggested_evidence_query_1",
    "suggested_evidence_query_2",
    "suggested_primary_source_type",
    "evidence_needed_count",
    "notes",
)
EVIDENCE_TEMPLATE_FIELDS = (
    "market_ticker",
    "evidence_id",
    "source",
    "title",
    "url",
    "published_at",
    "retrieved_at",
    "summary",
    "relevance_score",
    "credibility_score",
    "metadata",
)
DEFAULT_EVIDENCE_NEEDED_COUNT = 2


@dataclass(frozen=True)
class WorksheetResult:
    export_dir: Path
    csv_path: Path
    markdown_path: Path
    template_path: Path
    market_count: int
    template_row_count: int


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    export_dir = resolve_export_dir(
        export_id=args.export_id,
        export_root=args.export_root,
        export_dir=args.export_dir,
    )
    result = prepare_worksheet(
        export_dir,
        evidence_needed_count=args.evidence_needed_count,
    )
    print(
        json.dumps(
            {
                "export_dir": str(result.export_dir),
                "evidence_worksheet_csv": str(result.csv_path),
                "evidence_worksheet_md": str(result.markdown_path),
                "evidence_template_jsonl": str(result.template_path),
                "market_count": result.market_count,
                "template_row_count": result.template_row_count,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare local Kalshi evidence curation worksheet files."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--export-id")
    target.add_argument("--export-dir", type=Path)
    parser.add_argument(
        "--export-root",
        type=Path,
        default=Path("data/source_exports/kalshi"),
    )
    parser.add_argument(
        "--evidence-needed-count",
        type=positive_int,
        default=DEFAULT_EVIDENCE_NEEDED_COUNT,
        help="Placeholder evidence rows to create per market.",
    )
    return parser.parse_args(argv)


def prepare_worksheet(
    export_dir: Path,
    *,
    evidence_needed_count: int = DEFAULT_EVIDENCE_NEEDED_COUNT,
) -> WorksheetResult:
    manifest = load_json_object(export_dir / "source_manifest.json")
    markets = load_jsonl(export_dir / "markets.jsonl")
    candles = load_jsonl(export_dir / "candlesticks.jsonl")
    candles_by_market = group_candles_by_market(candles)

    rows = [
        build_worksheet_row(
            market=market,
            candles=candles_by_market.get(required_text(market, "ticker"), []),
            evidence_needed_count=evidence_needed_count,
        )
        for market in sorted(markets, key=lambda item: required_text(item, "ticker"))
    ]
    template_rows = build_evidence_template_rows(rows)

    csv_path = export_dir / "evidence_worksheet.csv"
    markdown_path = export_dir / "evidence_worksheet.md"
    template_path = export_dir / "evidence_template.jsonl"

    write_csv(csv_path, rows)
    markdown_path.write_text(
        render_markdown(
            rows=rows,
            manifest=manifest,
            template_row_count=len(template_rows),
        ),
        encoding="utf-8",
    )
    write_jsonl(template_path, template_rows)

    return WorksheetResult(
        export_dir=export_dir,
        csv_path=csv_path,
        markdown_path=markdown_path,
        template_path=template_path,
        market_count=len(rows),
        template_row_count=len(template_rows),
    )


def build_worksheet_row(
    *,
    market: dict[str, Any],
    candles: list[dict[str, Any]],
    evidence_needed_count: int,
) -> dict[str, object]:
    ticker = required_text(market, "ticker")
    candle_timestamps = sorted(
        timestamp
        for timestamp in (canonical_or_none(candle.get("end_period_ts")) for candle in candles)
        if timestamp is not None
    )
    earliest_candle_ts = candle_timestamps[0] if candle_timestamps else ""
    latest_candle_ts = candle_timestamps[-1] if candle_timestamps else ""
    title = text_or_empty(market.get("title"))
    rules_primary = text_or_empty(market.get("rules_primary"))
    rules_secondary = text_or_empty(market.get("rules_secondary"))
    result = text_or_empty(market.get("result"))
    source_type = suggest_primary_source_type(
        " ".join([title, rules_primary, rules_secondary])
    )
    query_1, query_2 = suggested_queries(
        title=title,
        rules_primary=rules_primary,
        rules_secondary=rules_secondary,
        result=result,
        source_type=source_type,
    )
    return {
        "market_ticker": ticker,
        "title": title,
        "subtitle": text_or_empty(market.get("subtitle")),
        "rules_primary": rules_primary,
        "rules_secondary": rules_secondary,
        "result": result,
        "settlement_ts": canonical_or_none(market.get("settlement_ts")) or "",
        "earliest_candle_ts": earliest_candle_ts,
        "latest_candle_ts": latest_candle_ts,
        "number_of_candles": len(candle_timestamps),
        "required_evidence_before_ts": earliest_candle_ts,
        "suggested_evidence_query_1": query_1,
        "suggested_evidence_query_2": query_2,
        "suggested_primary_source_type": source_type,
        "evidence_needed_count": evidence_needed_count,
        "notes": worksheet_notes(earliest_candle_ts),
    }


def build_evidence_template_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    template_rows: list[dict[str, object]] = []
    for row in rows:
        ticker = str(row["market_ticker"])
        needed_count = int(row["evidence_needed_count"])
        for index in range(1, needed_count + 1):
            template_rows.append(
                {
                    "market_ticker": ticker,
                    "evidence_id": f"TODO_{safe_id(ticker)}_evidence_{index}",
                    "source": "TODO_public_source_name",
                    "title": "TODO_public_evidence_title",
                    "url": "TODO_public_url",
                    "published_at": "TODO_published_at_UTC_must_be_on_or_before_required_ts",
                    "retrieved_at": "TODO_retrieved_at_UTC",
                    "summary": "TODO_brief_public_evidence_summary_no_model_claims",
                    "relevance_score": 0.0,
                    "credibility_score": 0.0,
                    "metadata": {
                        "placeholder": True,
                        "replace_before_import": True,
                        "required_published_at_lte": row["required_evidence_before_ts"],
                        "suggested_query": row["suggested_evidence_query_1"]
                        if index == 1
                        else row["suggested_evidence_query_2"],
                        "suggested_primary_source_type": row[
                            "suggested_primary_source_type"
                        ],
                        "notes": (
                            "Do not copy this row into evidence.jsonl until all TODO "
                            "values are replaced with real public timestamped evidence."
                        ),
                    },
                }
            )
    return template_rows


def suggested_queries(
    *,
    title: str,
    rules_primary: str,
    rules_secondary: str,
    result: str,
    source_type: str,
) -> tuple[str, str]:
    compact_title = compact_query_text(title)
    keyword_text = keyword_query_text(" ".join([rules_primary, rules_secondary]))
    result_context = f" result {result}" if result else ""
    query_1 = f'official source "{compact_title}"'
    if source_type == "government/statistics release":
        query_2 = f'government statistics source "{compact_title}" {keyword_text}'.strip()
    elif source_type == "official weather agency record":
        query_2 = f'official weather record "{compact_title}" {keyword_text}'.strip()
    elif source_type == "election authority or official result":
        query_2 = f'election authority official result "{compact_title}"'
    elif source_type == "company filing or official press release":
        query_2 = f'company filing press release "{compact_title}" {keyword_text}'.strip()
    elif source_type == "official event result page":
        query_2 = f'official event result "{compact_title}" {keyword_text}'.strip()
    elif source_type == "market/reference price source":
        query_2 = f'reference price source "{compact_title}" {keyword_text}'.strip()
    else:
        query_2 = f'settlement source "{compact_title}"{result_context}'.strip()
    return query_1, collapse_spaces(query_2)


def suggest_primary_source_type(text: str) -> str:
    normalized = text.lower()
    if any(
        token in normalized
        for token in (
            "government",
            "bureau",
            "census",
            "statistics",
            "inflation",
            "unemployment",
            "cpi",
            "treasury",
            "federal reserve",
            "department of",
        )
    ):
        return "government/statistics release"
    if any(
        token in normalized
        for token in ("weather", "temperature", "rain", "snow", "hurricane", "tornado")
    ):
        return "official weather agency record"
    if any(token in normalized for token in ("election", "vote", "ballot", "senate")):
        return "election authority or official result"
    if any(
        token in normalized
        for token in ("sec filing", "earnings", "revenue", "company", "stock")
    ):
        return "company filing or official press release"
    if any(
        token in normalized
        for token in (
            "match",
            "game",
            "set ",
            "tennis",
            "baseball",
            "basketball",
            "football",
            "score",
            "win ",
            "wins ",
        )
    ):
        return "official event result page"
    if any(
        token in normalized
        for token in ("btc", "bitcoin", "eth", "ethereum", "crypto", "price")
    ):
        return "market/reference price source"
    return "public primary or authoritative source"


def worksheet_notes(required_ts: str) -> str:
    if not required_ts:
        return (
            "No candle timestamps found. Inspect the local export before evidence "
            "curation."
        )
    return (
        "Find public timestamped evidence published at or before "
        f"{required_ts}. Settlement labels and post-result reports are not "
        "forecast-time evidence."
    )


def render_markdown(
    *,
    rows: list[dict[str, object]],
    manifest: dict[str, Any],
    template_row_count: int,
) -> str:
    export_id = text_or_empty(manifest.get("export_id"))
    dataset_id = text_or_empty(manifest.get("dataset_id"))
    lines = [
        "# Kalshi Sprint 1 Evidence Worksheet",
        "",
        f"Export id: `{export_id}`",
        f"Dataset id: `{dataset_id}`",
        f"Markets requiring evidence: {len(rows)}",
        f"Template rows written: {template_row_count}",
        "",
        "Use this worksheet to find public timestamped evidence. Do not treat "
        "settlement labels as forecast-time evidence.",
        "",
        "| Market | Result | Candles | Required evidence before | Suggested source |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(str(row["market_ticker"])),
                    markdown_cell(str(row["result"])),
                    str(row["number_of_candles"]),
                    markdown_cell(str(row["required_evidence_before_ts"])),
                    markdown_cell(str(row["suggested_primary_source_type"])),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Per-Market Prompts", ""])
    for row in rows:
        lines.extend(
            [
                f"### {row['market_ticker']}",
                "",
                f"- Title: {row['title']}",
                f"- Result: `{row['result']}`",
                f"- Settlement timestamp: `{row['settlement_ts']}`",
                f"- Candle window: `{row['earliest_candle_ts']}` to "
                f"`{row['latest_candle_ts']}`",
                f"- Required evidence before: `{row['required_evidence_before_ts']}`",
                f"- Query 1: `{row['suggested_evidence_query_1']}`",
                f"- Query 2: `{row['suggested_evidence_query_2']}`",
                f"- Notes: {row['notes']}",
                "",
            ]
        )
    return "\n".join(lines)


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path} line {line_number} must contain a JSON object")
        rows.append(payload)
    return rows


def group_candles_by_market(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ticker = required_text(row, "market_ticker")
        grouped.setdefault(ticker, []).append(row)
    return grouped


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=WORKSHEET_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def resolve_export_dir(
    *,
    export_id: str | None,
    export_root: Path,
    export_dir: Path | None,
) -> Path:
    if export_dir is not None:
        return export_dir
    if export_id is None:
        raise ValueError("export_id is required when export_dir is not provided")
    return export_root / export_id


def canonical_or_none(value: object) -> str | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC).replace(microsecond=0)
    text = text_or_none(value)
    if text is None:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text), UTC).replace(microsecond=0)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC).replace(microsecond=0)


def compact_query_text(value: str) -> str:
    return collapse_spaces(value.replace("?", ""))


def keyword_query_text(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value.lower())
    keepers = [
        word
        for word in words
        if len(word) >= 4
        and word
        not in {
            "then",
            "market",
            "resolves",
            "will",
            "with",
            "that",
            "this",
            "from",
            "originally",
            "scheduled",
        }
    ]
    return " ".join(keepers[:6])


def collapse_spaces(value: str) -> str:
    return " ".join(value.split())


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|")


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")


def required_text(row: dict[str, Any], field: str) -> str:
    value = text_or_none(row.get(field))
    if value is None:
        raise ValueError(f"missing required field: {field}")
    return value


def text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def text_or_empty(value: object) -> str:
    return text_or_none(value) or ""


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


if __name__ == "__main__":
    sys.exit(main())
