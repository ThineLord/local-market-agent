from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

NORMALIZED_SPORTS_TENNIS = "sports_tennis"
NORMALIZED_SPORTS_MAJOR = "sports_major"
NORMALIZED_WEATHER = "weather"
NORMALIZED_FED_POLICY_MACRO = "fed_policy_macro"
NORMALIZED_PUBLIC_EVENT_GENERIC = "public_event_generic"
NORMALIZED_MENTION_MARKET = "mention_market"
NORMALIZED_CRYPTO = "crypto"
NORMALIZED_POLITICS_GOVERNMENT = "politics_government"
NORMALIZED_ENTERTAINMENT = "entertainment"
NORMALIZED_ECONOMICS_OTHER = "economics_other"
NORMALIZED_UNKNOWN = "unknown"

NORMALIZED_CATEGORIES = (
    NORMALIZED_SPORTS_TENNIS,
    NORMALIZED_SPORTS_MAJOR,
    NORMALIZED_WEATHER,
    NORMALIZED_FED_POLICY_MACRO,
    NORMALIZED_PUBLIC_EVENT_GENERIC,
    NORMALIZED_MENTION_MARKET,
    NORMALIZED_CRYPTO,
    NORMALIZED_POLITICS_GOVERNMENT,
    NORMALIZED_ENTERTAINMENT,
    NORMALIZED_ECONOMICS_OTHER,
    NORMALIZED_UNKNOWN,
)

WARNING_SOURCE_SEMANTIC_MISMATCH = "source_semantic_mismatch_warning"
WARNING_PUBLIC_EVENT_SOURCE_OVERRIDDEN = "public_event_source_label_overridden_warning"
WARNING_MENTION_MARKET_FORMAT = "mention_market_format_warning"
WARNING_UNKNOWN_CATEGORY = "unknown_category_warning"

DEFAULT_DOCS_REPORT_PATH = Path("docs/reports/kalshi_category_normalization_result.md")

MENTION_RULES = (
    ("mention_ticker", r"kx(?:person|fedgov|fedgovmention|speaker).*mention"),
    ("mention_title_what_will_say", r"\bwhat will\b.+\bsay\b"),
    ("mention_rule_says_as_part", r"\bsays?\b.+\bas part of\b"),
    ("mention_rule_phrase", r"\bthe exact phrase\b|\bexact phrase/word\b"),
)
TENNIS_RULES = (
    ("tennis_ticker_itf", r"kxitfwmatch|kxitfmatch"),
    ("tennis_ticker_wta", r"kxwtamatch|kxwtachallengermatch"),
    ("tennis_ticker_atp", r"kxatpchallengermatch|kxatpmatch"),
    ("tennis_title", r"\bprofessional tennis match\b"),
    ("tennis_tour", r"\b(?:atp|wta|itf)\b"),
    ("tennis_round", r"\bw100\b|\bm25\b|\bchallenger\b"),
)
MAJOR_SPORTS_RULES = (
    ("major_sports_ticker", r"kx(?:nfl|nba|mlb|nhl|ncaamb|ncaafb|ucl)"),
    ("nfl", r"\bnfl\b|\bfootball game\b"),
    ("nba", r"\bnba\b|\bbasketball game\b"),
    ("mlb", r"\bmlb\b|\bbaseball game\b"),
    ("nhl", r"\bnhl\b|\bhockey game\b"),
    ("soccer", r"\bchampions league\b|\bworld cup\b|\bsoccer game\b"),
    ("college_basketball", r"\bcollege basketball\b|\bncaamb\b"),
)
WEATHER_RULES = (
    ("weather_ticker", r"kx(?:weather|rain|snow|temp|hurricane|tornado)"),
    ("weather_keyword", r"\bweather\b"),
    ("temperature", r"\btemperatures?\b|\bhigh temp\b|\blow temp\b"),
    ("precipitation", r"\brain\b|\bsnow\b|\bprecipitation\b"),
    ("storm", r"\bhurricane\b|\btornado\b|\bstorm\b"),
    ("weather_agency", r"\bnoaa\b|\bnational weather service\b"),
)
FED_POLICY_RULES = (
    ("fed_ticker", r"kx(?:fed|fomc)"),
    ("fed_keyword", r"\bfed\b|\bfederal reserve\b|\bfomc\b"),
    ("rates", r"\binterest rates?\b|\brate cut\b|\brate hike\b|\bcut rate\b"),
    ("inflation", r"\bcpi\b|\bppi\b|\binflation\b"),
    ("monetary_policy", r"\bmonetary policy\b"),
    ("fed_speaker", r"\bpowell\b|\bgoolsbee\b|\bbowman\b|\bwaller\b"),
)
CRYPTO_RULES = (
    ("crypto_ticker", r"kx(?:btc|bitcoin|eth|ethereum|crypto)"),
    ("bitcoin", r"\bbitcoin\b|\bbtc\b"),
    ("ethereum", r"\bethereum\b|\beth\b"),
    ("crypto_keyword", r"\bcrypto(?:currency)?\b"),
)
POLITICS_GOVERNMENT_RULES = (
    ("election", r"\belection\b|\bprimary\b|\bballot\b"),
    ("government", r"\bcongress\b|\bsenate\b|\bhouse\b|\bgovernor\b"),
    ("president", r"\bpresident\b|\bwhite house\b"),
    ("court", r"\bsupreme court\b|\bscotus\b"),
)
ENTERTAINMENT_RULES = (
    ("awards", r"\boscars?\b|\bgrammys?\b|\bemmys?\b"),
    ("media", r"\bbox office\b|\bmovie\b|\bfilm\b|\balbum\b|\bsong\b"),
    ("celebrity", r"\bcelebrity\b|\bactor\b|\bartist\b"),
)
ECONOMICS_OTHER_RULES = (
    ("labor", r"\bunemployment\b|\bjobs report\b|\bpayrolls?\b"),
    ("growth", r"\bgdp\b|\bretail sales\b"),
    ("market_prices", r"\boil price\b|\bgas prices?\b|\btreasury yield\b"),
    ("recession", r"\brecession\b"),
)

SEMANTIC_RULE_GROUPS = (
    (NORMALIZED_SPORTS_TENNIS, TENNIS_RULES, "high"),
    (NORMALIZED_SPORTS_MAJOR, MAJOR_SPORTS_RULES, "high"),
    (NORMALIZED_WEATHER, WEATHER_RULES, "high"),
    (NORMALIZED_FED_POLICY_MACRO, FED_POLICY_RULES, "high"),
    (NORMALIZED_CRYPTO, CRYPTO_RULES, "high"),
    (NORMALIZED_POLITICS_GOVERNMENT, POLITICS_GOVERNMENT_RULES, "medium"),
    (NORMALIZED_ENTERTAINMENT, ENTERTAINMENT_RULES, "medium"),
    (NORMALIZED_ECONOMICS_OTHER, ECONOMICS_OTHER_RULES, "medium"),
)

SOURCE_CATEGORY_MAP = {
    "major_sports": NORMALIZED_SPORTS_MAJOR,
    "weather": NORMALIZED_WEATHER,
    "fed_policy": NORMALIZED_FED_POLICY_MACRO,
    "public_event": NORMALIZED_PUBLIC_EVENT_GENERIC,
    "crypto": NORMALIZED_CRYPTO,
    "politics_government": NORMALIZED_POLITICS_GOVERNMENT,
    "entertainment": NORMALIZED_ENTERTAINMENT,
    "economics_other": NORMALIZED_ECONOMICS_OTHER,
}


@dataclass(frozen=True)
class NormalizedCategoryResult:
    source_category: str
    normalized_category: str
    semantic_category: str
    is_mention_market: bool
    confidence: str
    matched_rules: tuple[str, ...]
    warnings: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_category": self.source_category,
            "normalized_category": self.normalized_category,
            "semantic_category": self.semantic_category,
            "is_mention_market": self.is_mention_market,
            "confidence": self.confidence,
            "matched_rules": list(self.matched_rules),
            "warnings": list(self.warnings),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CategoryNormalizationArtifacts:
    json_path: Path
    markdown_path: Path
    docs_markdown_path: Path | None = None


@dataclass(frozen=True)
class CategoryNormalizationExportResult:
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


def normalize_market_category(market: Mapping[str, Any]) -> NormalizedCategoryResult:
    source_category = _source_category(market)
    text = _market_text(market)
    mention_rules = _matched_rule_names(text, MENTION_RULES)
    semantic_category, semantic_rules, semantic_confidence = _semantic_category(text)
    is_mention_market = bool(mention_rules)

    if is_mention_market:
        normalized_category = NORMALIZED_MENTION_MARKET
        confidence = "medium" if semantic_category != NORMALIZED_UNKNOWN else "low"
    elif semantic_category != NORMALIZED_UNKNOWN:
        normalized_category = semantic_category
        confidence = semantic_confidence
    elif source_category == "public_event":
        normalized_category = NORMALIZED_PUBLIC_EVENT_GENERIC
        confidence = "low"
    else:
        normalized_category = SOURCE_CATEGORY_MAP.get(source_category, NORMALIZED_UNKNOWN)
        confidence = "low" if normalized_category == NORMALIZED_UNKNOWN else "medium"

    warnings = _normalization_warnings(
        source_category=source_category,
        normalized_category=normalized_category,
        semantic_category=semantic_category,
        is_mention_market=is_mention_market,
    )
    matched_rules = tuple([*mention_rules, *semantic_rules])
    return NormalizedCategoryResult(
        source_category=source_category,
        normalized_category=normalized_category,
        semantic_category=semantic_category,
        is_mention_market=is_mention_market,
        confidence=confidence,
        matched_rules=matched_rules,
        warnings=tuple(warnings),
        reason=_normalization_reason(
            source_category=source_category,
            normalized_category=normalized_category,
            semantic_category=semantic_category,
            is_mention_market=is_mention_market,
            matched_rules=matched_rules,
        ),
    )


def run_category_normalization_export(
    source_export_dir: str | Path,
) -> CategoryNormalizationExportResult:
    export_dir = Path(source_export_dir)
    markets_path = export_dir / "markets.jsonl"
    markets = _load_markets(markets_path)
    normalized_markets = []
    for market in markets:
        result = normalize_market_category(market)
        normalized_markets.append(
            {
                "ticker": _text(market.get("ticker")) or "missing",
                "title": _text(market.get("title")) or "missing",
                "event_ticker": _text(market.get("event_ticker"))
                or _metadata_text(market, "event_ticker")
                or "missing",
                "series_ticker": _text(market.get("series_ticker")) or "missing",
                **result.as_dict(),
            }
        )
    summary = _normalization_summary(normalized_markets)
    report = {
        "report_id": f"category_normalization_{_safe_filename(export_dir.name)}",
        "phase": "PR-CAL-10",
        "created_at": datetime.now(UTC).isoformat(),
        "source_export": {
            "export_id": export_dir.name,
            "source_export_dir": str(export_dir),
            "markets_path": str(markets_path),
            "market_count": len(markets),
        },
        "normalized_categories": list(NORMALIZED_CATEGORIES),
        "summary": summary,
        "markets": normalized_markets,
        "guardrails": _guardrails(),
    }
    return CategoryNormalizationExportResult(report=report)


def write_category_normalization_reports(
    result: CategoryNormalizationExportResult,
    output_dir: str | Path,
    *,
    docs_markdown_path: str | Path | None = DEFAULT_DOCS_REPORT_PATH,
) -> CategoryNormalizationArtifacts:
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    safe_export_id = _safe_filename(result.export_id)
    json_path = report_dir / f"{safe_export_id}.category_normalization.json"
    markdown_path = report_dir / f"{safe_export_id}_category_normalization.md"
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

    return CategoryNormalizationArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        docs_markdown_path=docs_path,
    )


def _semantic_category(text: str) -> tuple[str, tuple[str, ...], str]:
    for category, rules, confidence in SEMANTIC_RULE_GROUPS:
        matched = _matched_rule_names(text, rules)
        if matched:
            return category, tuple(matched), confidence
    return NORMALIZED_UNKNOWN, (), "low"


def _normalization_warnings(
    *,
    source_category: str,
    normalized_category: str,
    semantic_category: str,
    is_mention_market: bool,
) -> list[str]:
    warnings: list[str] = []
    source_normalized = SOURCE_CATEGORY_MAP.get(source_category)
    comparison_category = (
        semantic_category if semantic_category != NORMALIZED_UNKNOWN else normalized_category
    )
    if source_normalized and comparison_category != source_normalized:
        warnings.append(WARNING_SOURCE_SEMANTIC_MISMATCH)
    if (
        source_category == "public_event"
        and comparison_category
        not in {NORMALIZED_PUBLIC_EVENT_GENERIC, NORMALIZED_UNKNOWN}
    ):
        warnings.append(WARNING_PUBLIC_EVENT_SOURCE_OVERRIDDEN)
    if is_mention_market:
        warnings.append(WARNING_MENTION_MARKET_FORMAT)
    if normalized_category == NORMALIZED_UNKNOWN:
        warnings.append(WARNING_UNKNOWN_CATEGORY)
    return list(dict.fromkeys(warnings))


def _normalization_reason(
    *,
    source_category: str,
    normalized_category: str,
    semantic_category: str,
    is_mention_market: bool,
    matched_rules: tuple[str, ...],
) -> str:
    if is_mention_market:
        return (
            "Mention-market format detected; normalized category is separated "
            f"from topical semantic category `{semantic_category}`."
        )
    if matched_rules:
        return (
            f"Deterministic semantic rules mapped source `{source_category}` "
            f"to normalized `{normalized_category}`."
        )
    if source_category == "public_event":
        return "No specific semantic signal found; public_event retained as generic source label."
    if normalized_category == NORMALIZED_UNKNOWN:
        return "No source or semantic rule mapped this market to a known normalized category."
    return f"Source category `{source_category}` mapped to normalized `{normalized_category}`."


def _normalization_summary(markets: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts = Counter(str(market["source_category"]) for market in markets)
    normalized_counts = Counter(str(market["normalized_category"]) for market in markets)
    semantic_counts = Counter(str(market["semantic_category"]) for market in markets)
    warning_counts: Counter[str] = Counter()
    for market in markets:
        warning_counts.update(str(warning) for warning in market["warnings"])
    public_event_mismatches = [
        market
        for market in markets
        if market["source_category"] == "public_event"
        and market["normalized_category"] != NORMALIZED_PUBLIC_EVENT_GENERIC
    ]
    mention_markets = [market for market in markets if market["is_mention_market"]]
    return {
        "market_count": len(markets),
        "source_category_counts": dict(sorted(source_counts.items())),
        "normalized_category_counts": dict(sorted(normalized_counts.items())),
        "semantic_category_counts": dict(sorted(semantic_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "public_event_mismatch_count": len(public_event_mismatches),
        "mention_market_count": len(mention_markets),
        "unknown_count": normalized_counts.get(NORMALIZED_UNKNOWN, 0),
        "public_event_mismatch_samples": _sample_markets(public_event_mismatches),
        "mention_market_samples": _sample_markets(mention_markets),
        "normalization_usable_for_future_retry": True,
        "taxonomy_is_deterministic_and_local": True,
    }


def _sample_markets(markets: list[dict[str, Any]], *, limit: int = 15) -> list[dict[str, Any]]:
    return [
        {
            "ticker": market["ticker"],
            "title": market["title"],
            "source_category": market["source_category"],
            "normalized_category": market["normalized_category"],
            "semantic_category": market["semantic_category"],
            "is_mention_market": market["is_mention_market"],
            "warnings": market["warnings"],
        }
        for market in markets[:limit]
    ]


def _load_markets(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        msg = f"markets.jsonl not found: {path}"
        raise ValueError(msg)
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            msg = f"markets JSONL line {line_number} is invalid JSON"
            raise ValueError(msg) from exc
        if not isinstance(payload, dict):
            msg = f"markets JSONL line {line_number} must be an object"
            raise ValueError(msg)
        rows.append(payload)
    return rows


def _source_category(market: Mapping[str, Any]) -> str:
    return (
        _metadata_text(market, "calibration_category")
        or _text(market.get("category"))
        or NORMALIZED_UNKNOWN
    )


def _market_text(market: Mapping[str, Any]) -> str:
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
    if isinstance(metadata, Mapping):
        values.extend(_text(metadata.get(field)) for field in fields)
    return " ".join(value.lower() for value in values if value)


def _matched_rule_names(text: str, rules: tuple[tuple[str, str], ...]) -> list[str]:
    return [name for name, pattern in rules if re.search(pattern, text)]


def _metadata_text(market: Mapping[str, Any], key: str) -> str | None:
    metadata = market.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    return _text(metadata.get(key))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return safe or "category_normalization"


def _format_pct(value: int | float, total: int | float) -> str:
    if total == 0:
        return "0.000000%"
    return f"{float(value) / float(total) * 100:.6f}%"


def _warnings(warnings: list[str]) -> str:
    return ", ".join(warnings) if warnings else "None"


def _guardrails() -> dict[str, bool]:
    return {
        "taxonomy_infrastructure_only": True,
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


def _render_markdown(report: dict[str, Any]) -> str:
    source = report["source_export"]
    summary = report["summary"]
    market_count = int(summary["market_count"])
    lines = [
        "# Kalshi Category Normalization Result",
        "",
        "Scope: PR-CAL-10 taxonomy/diagnostics infrastructure only. This report "
        "normalizes an existing local source export and does not collect data, "
        "build a new historical dataset, collect or approve evidence, modify "
        "strategy logic, modify acceptance gates, start Phase 8, add broker/live "
        "trading, add scheduler behavior, or make paper-PnL, profitability, "
        "acceptance, Strategy v2 superiority, or live-readiness claims.",
        "",
        "## Inputs",
        "",
        f"- Source export dir: `{source['source_export_dir']}`",
        f"- Markets path: `{source['markets_path']}`",
        f"- Market count: {market_count}",
        "",
        "## Normalized Category Findings",
        "",
        "| Category | Count | Share |",
        "| --- | ---: | ---: |",
    ]
    for category in report["normalized_categories"]:
        count = int(summary["normalized_category_counts"].get(category, 0))
        lines.append(f"| `{category}` | {count} | {_format_pct(count, market_count)} |")
    lines.extend(
        [
            "",
            "Source category counts:",
            "",
            *_counter_lines(summary["source_category_counts"]),
            "",
            "Semantic category counts:",
            "",
            *_counter_lines(summary["semantic_category_counts"]),
            "",
            "## Public Event And Mention Diagnostics",
            "",
            f"- Public-event mismatch count: {summary['public_event_mismatch_count']}",
            f"- Mention-market count: {summary['mention_market_count']}",
            f"- Unknown normalized count: {summary['unknown_count']}",
            f"- Future retry taxonomy usable: `{summary['normalization_usable_for_future_retry']}`",
            "",
            "Public-event mismatch samples:",
            "",
        ]
    )
    lines.extend(_sample_lines(summary["public_event_mismatch_samples"]))
    lines.extend(["", "Mention-market samples:", ""])
    lines.extend(_sample_lines(summary["mention_market_samples"]))
    lines.extend(
        [
            "",
            "## Warning Counts",
            "",
            *_counter_lines(summary["warning_counts"]),
            "",
            "## Collector Diagnostics Schema",
            "",
            "PR-CAL-10 also adds a reusable collector diagnostics schema for "
            "future local calibration collectors. It records discovered counts, "
            "pre-filter, post-filter, and selected normalized category counts, "
            "resolved/finalized/binary filter losses, candle attempt success and "
            "failure counts, candle failure reasons, quota targets, quota fills, "
            "quota shortfalls, and availability-limitation reasons. The schema is "
            "not wired into a new collection run in this PR.",
            "",
            "## Recommended Next Step",
            "",
            "Use the normalized taxonomy and diagnostics schema to prepare the next "
            "calibration-only retry design. Future collection should quota on "
            "normalized categories rather than raw Kalshi `public_event`, and "
            "should log pre-candle candidate counts plus candle failure reasons "
            "before interpreting any availability shortfall.",
            "",
            "## Guardrails",
            "",
            "| Guardrail | Value |",
            "| --- | --- |",
        ]
    )
    for name, value in report["guardrails"].items():
        lines.append(f"| `{name}` | `{value}` |")
    lines.append("")
    return "\n".join(lines)


def _counter_lines(counter: dict[str, Any]) -> list[str]:
    if not counter:
        return ["- none"]
    return [f"- `{name}`: {count}" for name, count in sorted(counter.items())]


def _sample_lines(markets: list[dict[str, Any]]) -> list[str]:
    if not markets:
        return ["None."]
    lines = [
        "| Ticker | Source | Normalized | Semantic | Mention | Warnings | Title |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for market in markets:
        title = str(market["title"]).replace("|", "/")
        if len(title) > 110:
            title = f"{title[:107]}..."
        lines.append(
            f"| `{market['ticker']}` | `{market['source_category']}` | "
            f"`{market['normalized_category']}` | "
            f"`{market['semantic_category']}` | "
            f"`{market['is_mention_market']}` | "
            f"{_warnings(market['warnings'])} | {title} |"
        )
    return lines
