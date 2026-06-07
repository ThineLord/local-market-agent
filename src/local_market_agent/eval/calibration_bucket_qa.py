from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from local_market_agent.eval.forecast_assessment import assign_calibration_bucket

LOG_LOSS_EPSILON = 1e-6
DEFAULT_GAP_THRESHOLD = 0.15
SMALL_BUCKET_ROW_THRESHOLD = 30
MARKET_CONCENTRATION_THRESHOLD = 0.25
TOP_MARKET_CONCENTRATION_THRESHOLD = 0.50
SETTLEMENT_IMBALANCE_THRESHOLD = 0.80
REPEATED_MARKET_AVERAGE_ROWS_THRESHOLD = 8.0

WARNING_SMALL_SAMPLE = "small_sample_warning"
WARNING_MARKET_CONCENTRATION = "market_concentration_warning"
WARNING_CATEGORY_MISSING = "category_missing_warning"
WARNING_LIQUIDITY_MISSING = "liquidity_missing_warning"
WARNING_THIN_LIQUIDITY = "thin_liquidity_warning"
WARNING_EVIDENCE_MISSING = "evidence_missing_warning"
WARNING_BID_ASK_MISSING = "bid_ask_missing_warning"
WARNING_SETTLEMENT_IMBALANCE = "settlement_imbalance_warning"
WARNING_REPEATED_MARKET_SAMPLING = "repeated_market_sampling_warning"

SEGMENT_DIMENSIONS = (
    "market_id",
    "platform",
    "source",
    "profile",
    "settlement_outcome",
    "timestamp_date",
    "hour_of_day",
    "price_decile",
    "row_recency_within_market",
    "source_manifest_category",
    "liquidity_segment",
    "volume_segment",
)


@dataclass(frozen=True)
class CalibrationBucketQAArtifacts:
    json_path: Path
    markdown_path: Path


@dataclass(frozen=True)
class CalibrationBucketQAResult:
    report: dict[str, Any]

    @property
    def dataset_id(self) -> str:
        return str(self.report["dataset"]["dataset_id"])

    @property
    def high_gap_buckets(self) -> list[dict[str, Any]]:
        buckets = self.report["high_gap_buckets"]
        return buckets if isinstance(buckets, list) else []

    @property
    def guardrails(self) -> dict[str, bool]:
        guardrails = self.report["guardrails"]
        return guardrails if isinstance(guardrails, dict) else {}

    def as_dict(self) -> dict[str, Any]:
        return self.report


def run_calibration_bucket_qa(
    historical_file: str | Path,
    *,
    gap_threshold: float = DEFAULT_GAP_THRESHOLD,
) -> CalibrationBucketQAResult:
    historical_path = Path(historical_file)
    rows = _load_rows(historical_path)
    if not rows:
        msg = "calibration bucket QA requires at least one historical row"
        raise ValueError(msg)
    enriched_rows = _enrich_rows(rows)
    category_lookup, category_source = _load_category_lookup(enriched_rows)
    if category_lookup:
        for row in enriched_rows:
            row["source_manifest_category"] = category_lookup.get(row["market_id"])
    else:
        for row in enriched_rows:
            row["source_manifest_category"] = None
    _attach_row_recency(enriched_rows)
    bucket_stats = _bucket_stats(enriched_rows)
    high_gap_buckets = [
        _bucket_qa(
            bucket=stats,
            rows=[row for row in enriched_rows if row["bucket"] == stats["bucket"]],
        )
        for stats in bucket_stats
        if stats["rows"] > 0 and stats["absolute_gap"] is not None
        and stats["absolute_gap"] >= gap_threshold
    ]
    report = {
        "report_id": _report_id(historical_path, gap_threshold),
        "created_at": datetime.now(UTC).isoformat(),
        "historical_file": str(historical_path),
        "gap_threshold": gap_threshold,
        "dataset": _dataset_summary(enriched_rows, category_source),
        "bucket_stats": bucket_stats,
        "high_gap_buckets": high_gap_buckets,
        "segment_dimensions": list(SEGMENT_DIMENSIONS),
        "guardrails": _guardrails(),
    }
    return CalibrationBucketQAResult(report=report)


def write_calibration_bucket_qa_reports(
    result: CalibrationBucketQAResult,
    output_dir: str | Path,
) -> CalibrationBucketQAArtifacts:
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    safe_dataset_id = _safe_filename(result.dataset_id)
    json_path = report_dir / f"{safe_dataset_id}.calibration_bucket_qa.json"
    markdown_path = report_dir / f"{safe_dataset_id}_calibration_bucket_qa.md"
    json_path.write_text(
        json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(result.as_dict()), encoding="utf-8")
    return CalibrationBucketQAArtifacts(json_path=json_path, markdown_path=markdown_path)


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        msg = f"historical file not found: {path}"
        raise ValueError(msg)
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            msg = f"historical JSONL line {line_number} is invalid JSON"
            raise ValueError(msg) from exc
        if not isinstance(payload, dict):
            msg = f"historical JSONL line {line_number} must be an object"
            raise ValueError(msg)
        rows.append(payload)
    return rows


def _enrich_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        forecast = _forecast_probability(row)
        outcome = _settlement_outcome(row)
        timestamp = _parse_timestamp(row.get("timestamp"))
        brier_loss = _brier_loss(forecast, outcome)
        enriched.append(
            {
                "row_index": index,
                "row_id": _text(row.get("row_id")) or f"row_{index}",
                "market_id": _text(row.get("market_id")) or "missing",
                "timestamp": _canonical_timestamp(timestamp),
                "timestamp_date": timestamp.date().isoformat() if timestamp else "missing",
                "hour_of_day": f"{timestamp.hour:02d}" if timestamp else "missing",
                "platform": _text(row.get("platform")) or "missing",
                "source": _source_name(row) or "missing",
                "profile": _text(row.get("profile")) or "missing",
                "settlement_outcome": outcome,
                "forecast": forecast,
                "bucket": assign_calibration_bucket(forecast) or "missing",
                "price_decile": assign_calibration_bucket(forecast) or "missing",
                "brier_loss": brier_loss,
                "log_loss": _log_loss(forecast, outcome),
                "has_bid_ask": _valid_probability(row.get("bid"))
                and _valid_probability(row.get("ask")),
                "has_evidence": bool(row.get("evidence")),
                "row_category": _row_category(row),
                "liquidity": _optional_float(row.get("liquidity")),
                "volume": _optional_float(row.get("volume")),
                "metadata_open_interest": _metadata_float(row, "open_interest_fp"),
                "raw": row,
            }
        )
    return enriched


def _load_category_lookup(rows: list[dict[str, Any]]) -> tuple[dict[str, str], str]:
    export_ids = sorted(
        {
            str(export_id)
            for row in rows
            if (export_id := _metadata_value(row["raw"], "export_id"))
        }
    )
    if not export_ids:
        return {}, "not_available"
    lookup: dict[str, str] = {}
    sources: list[str] = []
    for export_id in export_ids:
        markets_path = Path("data/source_exports/kalshi") / export_id / "markets.jsonl"
        if not markets_path.exists():
            continue
        sources.append(str(markets_path))
        for line in markets_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                market = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(market, dict):
                continue
            market_id = _text(market.get("ticker"))
            category = _market_category(market)
            if market_id and category:
                lookup[market_id] = category
    if not sources:
        return {}, "not_available"
    return lookup, ",".join(sources)


def _attach_row_recency(rows: list[dict[str, Any]]) -> None:
    by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_market[row["market_id"]].append(row)
    for market_rows in by_market.values():
        market_rows.sort(key=lambda item: (item["timestamp"], item["row_index"]))
        total = len(market_rows)
        for index, row in enumerate(market_rows, start=1):
            row["row_recency_index"] = index
            row["row_recency_count"] = total
            if total <= 1:
                row["row_recency_within_market"] = "single"
            elif index == 1:
                row["row_recency_within_market"] = "first"
            elif index == total:
                row["row_recency_within_market"] = "last"
            elif index <= math.ceil(total / 3):
                row["row_recency_within_market"] = "early"
            elif index > math.floor((2 * total) / 3):
                row["row_recency_within_market"] = "late"
            else:
                row["row_recency_within_market"] = "middle"
            row["liquidity_segment"] = _numeric_segment(row["liquidity"])
            row["volume_segment"] = _numeric_segment(row["volume"])


def _bucket_stats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = [f"{index / 10:.2f}-{(index + 1) / 10:.2f}" for index in range(10)]
    grouped: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in buckets}
    for row in rows:
        if row["bucket"] in grouped:
            grouped[row["bucket"]].append(row)
    return [_stats_for_rows(bucket, grouped[bucket]) for bucket in buckets]


def _stats_for_rows(bucket: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    forecasts = [row["forecast"] for row in rows if row["forecast"] is not None]
    outcomes = [_outcome_yes(row["settlement_outcome"]) for row in rows if row["settlement_outcome"] in {"yes", "no"}]
    scored = [
        row for row in rows if row["forecast"] is not None and row["settlement_outcome"] in {"yes", "no"}
    ]
    return {
        "bucket": bucket,
        "rows": len(rows),
        "markets": len({row["market_id"] for row in rows}),
        "mean_forecast": _mean(forecasts),
        "observed_yes_rate": _mean(outcomes),
        "absolute_gap": _absolute_gap(forecasts, outcomes),
        "brier": _mean([row["brier_loss"] for row in scored if row["brier_loss"] is not None]),
        "log_loss": _mean([row["log_loss"] for row in scored if row["log_loss"] is not None]),
    }


def _bucket_qa(*, bucket: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    warnings = _bucket_warnings(bucket, rows)
    return {
        **bucket,
        "warnings": warnings,
        "top_markets_by_rows": _top_market_rows(rows),
        "top_markets_by_brier_loss": _top_market_brier(rows),
        "outcome_split": dict(sorted(Counter(row["settlement_outcome"] for row in rows).items())),
        "dominance": _market_dominance(rows),
        "row_count_too_small": WARNING_SMALL_SAMPLE in warnings,
        "all_rows_calibration_only_last_price": all(
            row["profile"] == "calibration_only_last_price" for row in rows
        ),
        "row_category_missing_count": sum(1 for row in rows if not row["row_category"]),
        "source_manifest_category_missing_count": sum(
            1 for row in rows if not row.get("source_manifest_category")
        ),
        "evidence_missing_count": sum(1 for row in rows if not row["has_evidence"]),
        "bid_ask_missing_count": sum(1 for row in rows if not row["has_bid_ask"]),
        "liquidity_missing_count": sum(1 for row in rows if row["liquidity"] is None),
        "thin_liquidity_count": sum(
            1 for row in rows if row["liquidity"] is not None and row["liquidity"] <= 0
        ),
        "segments": _segment_summary(rows),
        "representative_rows": _representative_rows(rows),
    }


def _bucket_warnings(bucket: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if bucket["rows"] < SMALL_BUCKET_ROW_THRESHOLD:
        warnings.append(WARNING_SMALL_SAMPLE)
    dominance = _market_dominance(rows)
    if dominance["top_market_row_share"] >= MARKET_CONCENTRATION_THRESHOLD or (
        dominance["top_three_market_row_share"] >= TOP_MARKET_CONCENTRATION_THRESHOLD
    ):
        warnings.append(WARNING_MARKET_CONCENTRATION)
    if any(not row["row_category"] for row in rows) or any(
        not row.get("source_manifest_category") for row in rows
    ):
        warnings.append(WARNING_CATEGORY_MISSING)
    if any(row["liquidity"] is None for row in rows):
        warnings.append(WARNING_LIQUIDITY_MISSING)
    if rows and all(row["liquidity"] is not None and row["liquidity"] <= 0 for row in rows):
        warnings.append(WARNING_THIN_LIQUIDITY)
    if any(not row["has_evidence"] for row in rows):
        warnings.append(WARNING_EVIDENCE_MISSING)
    if any(not row["has_bid_ask"] for row in rows):
        warnings.append(WARNING_BID_ASK_MISSING)
    observed = bucket.get("observed_yes_rate")
    if observed is not None and (observed >= SETTLEMENT_IMBALANCE_THRESHOLD or observed <= 1 - SETTLEMENT_IMBALANCE_THRESHOLD):
        warnings.append(WARNING_SETTLEMENT_IMBALANCE)
    market_count = max(1, int(bucket["markets"]))
    if bucket["rows"] / market_count >= REPEATED_MARKET_AVERAGE_ROWS_THRESHOLD:
        warnings.append(WARNING_REPEATED_MARKET_SAMPLING)
    return list(dict.fromkeys(warnings))


def _segment_summary(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        dimension: _segment_dimension(rows, dimension)
        for dimension in SEGMENT_DIMENSIONS
    }


def _segment_dimension(rows: list[dict[str, Any]], dimension: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        value = row.get(dimension)
        grouped[str(value) if value not in (None, "") else "missing"].append(row)
    entries = [
        {
            "value": value,
            "rows": len(segment_rows),
            "markets": len({row["market_id"] for row in segment_rows}),
            "brier_loss_sum": round(
                sum(row["brier_loss"] or 0.0 for row in segment_rows),
                8,
            ),
            "observed_yes_rate": _mean(
                [
                    _outcome_yes(row["settlement_outcome"])
                    for row in segment_rows
                    if row["settlement_outcome"] in {"yes", "no"}
                ]
            ),
            "mean_forecast": _mean(
                [
                    row["forecast"]
                    for row in segment_rows
                    if row["forecast"] is not None
                ]
            ),
        }
        for value, segment_rows in grouped.items()
    ]
    return sorted(entries, key=lambda item: (-item["rows"], -item["brier_loss_sum"], item["value"]))[:10]


def _top_market_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["market_id"]].append(row)
    entries = [
        {
            "market_id": market_id,
            "rows": len(market_rows),
            "row_share": _rate(len(market_rows), len(rows)),
            "brier_loss_sum": round(sum(row["brier_loss"] or 0.0 for row in market_rows), 8),
            "observed_yes_rate": _mean(
                [
                    _outcome_yes(row["settlement_outcome"])
                    for row in market_rows
                    if row["settlement_outcome"] in {"yes", "no"}
                ]
            ),
            "source_manifest_category": market_rows[0].get("source_manifest_category"),
        }
        for market_id, market_rows in grouped.items()
    ]
    return sorted(entries, key=lambda item: (-item["rows"], -item["brier_loss_sum"], item["market_id"]))[:10]


def _top_market_brier(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries = _top_market_rows(rows)
    return sorted(entries, key=lambda item: (-item["brier_loss_sum"], -item["rows"], item["market_id"]))[:10]


def _market_dominance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["market_id"] for row in rows)
    ordered = counts.most_common()
    top_count = ordered[0][1] if ordered else 0
    top_three = sum(count for _market, count in ordered[:3])
    return {
        "top_market_row_share": _rate(top_count, len(rows)),
        "top_three_market_row_share": _rate(top_three, len(rows)),
        "top_market_id": ordered[0][0] if ordered else None,
        "dominated_by_few_markets": _rate(top_count, len(rows)) >= MARKET_CONCENTRATION_THRESHOLD
        or _rate(top_three, len(rows)) >= TOP_MARKET_CONCENTRATION_THRESHOLD,
    }


def _representative_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: (-(row["brier_loss"] or 0.0), row["market_id"], row["timestamp"]))
    return [
        {
            "row_id": row["row_id"],
            "market_id": row["market_id"],
            "timestamp": row["timestamp"],
            "forecast": row["forecast"],
            "settlement_outcome": row["settlement_outcome"],
            "brier_loss": row["brier_loss"],
            "log_loss": row["log_loss"],
            "source_manifest_category": row.get("source_manifest_category"),
            "volume": row["volume"],
            "liquidity": row["liquidity"],
        }
        for row in ordered[:10]
    ]


def _dataset_summary(rows: list[dict[str, Any]], category_source: str) -> dict[str, Any]:
    dataset_ids = Counter(_text(row["raw"].get("dataset_id")) or "missing" for row in rows)
    return {
        "dataset_id": dataset_ids.most_common(1)[0][0],
        "row_count": len(rows),
        "market_count": len({row["market_id"] for row in rows}),
        "scored_row_count": sum(
            1 for row in rows if row["forecast"] is not None and row["settlement_outcome"] in {"yes", "no"}
        ),
        "profile_distribution": dict(sorted(Counter(row["profile"] for row in rows).items())),
        "platform_distribution": dict(sorted(Counter(row["platform"] for row in rows).items())),
        "source_distribution": dict(sorted(Counter(row["source"] for row in rows).items())),
        "category_source": category_source,
        "row_category_missing_count": sum(1 for row in rows if not row["row_category"]),
        "source_manifest_category_missing_count": sum(
            1 for row in rows if not row.get("source_manifest_category")
        ),
        "bid_ask_missing_count": sum(1 for row in rows if not row["has_bid_ask"]),
        "evidence_missing_count": sum(1 for row in rows if not row["has_evidence"]),
        "liquidity_missing_count": sum(1 for row in rows if row["liquidity"] is None),
        "thin_liquidity_count": sum(
            1 for row in rows if row["liquidity"] is not None and row["liquidity"] <= 0
        ),
    }


def _guardrails() -> dict[str, bool]:
    return {
        "forecast_calibration_diagnostics": True,
        "acceptance_gate_pass": False,
        "strategy_v2_superiority": False,
        "profitability_claim": False,
        "acceptance_ready_claim": False,
        "trading_readiness_claim": False,
    }


def _forecast_probability(row: dict[str, Any]) -> float | None:
    implied = _optional_probability(row.get("implied_probability"))
    if implied is not None:
        return implied
    return _optional_probability(row.get("last_price"))


def _settlement_outcome(row: dict[str, Any]) -> str | None:
    settlement = row.get("settlement")
    if isinstance(settlement, dict):
        value = settlement.get("outcome")
    else:
        value = row.get("settlement_outcome", row.get("outcome"))
    text = _text(value)
    return text if text in {"yes", "no"} else None


def _source_name(row: dict[str, Any]) -> str | None:
    source = row.get("source_provenance")
    if not isinstance(source, dict):
        return None
    return _text(source.get("source_name"))


def _row_category(row: dict[str, Any]) -> str | None:
    for key in ("category", "market_category", "event_category"):
        if category := _text(row.get(key)):
            return category
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        return _text(metadata.get("category"))
    return None


def _market_category(market: dict[str, Any]) -> str | None:
    metadata = market.get("metadata")
    if isinstance(metadata, dict):
        return _text(metadata.get("calibration_category"))
    return None


def _metadata_value(row: dict[str, Any], key: str) -> object:
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        return None
    return metadata.get(key)


def _metadata_float(row: dict[str, Any], key: str) -> float | None:
    return _optional_float(_metadata_value(row, key))


def _optional_probability(value: object) -> float | None:
    parsed = _optional_float(value)
    if parsed is None or not 0 <= parsed <= 1:
        return None
    return parsed


def _valid_probability(value: object) -> bool:
    return _optional_probability(value) is not None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _parse_timestamp(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _canonical_timestamp(value: datetime | None) -> str:
    if value is None:
        return "missing"
    return value.isoformat().replace("+00:00", "Z")


def _brier_loss(forecast: float | None, outcome: str | None) -> float | None:
    if forecast is None or outcome not in {"yes", "no"}:
        return None
    observed = _outcome_yes(outcome)
    return round((forecast - observed) ** 2, 8)


def _log_loss(forecast: float | None, outcome: str | None) -> float | None:
    if forecast is None or outcome not in {"yes", "no"}:
        return None
    observed = _outcome_yes(outcome)
    probability = min(1 - LOG_LOSS_EPSILON, max(LOG_LOSS_EPSILON, forecast))
    return round(
        -observed * math.log(probability)
        - (1 - observed) * math.log(1 - probability),
        8,
    )


def _outcome_yes(outcome: str | None) -> float:
    return 1.0 if outcome == "yes" else 0.0


def _numeric_segment(value: float | None) -> str:
    if value is None:
        return "missing"
    if value <= 0:
        return "zero_or_negative"
    if value < 100:
        return "0-100"
    if value < 1_000:
        return "100-1k"
    if value < 10_000:
        return "1k-10k"
    if value < 100_000:
        return "10k-100k"
    return "100k_plus"


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 8)


def _absolute_gap(forecasts: list[float], outcomes: list[float]) -> float | None:
    mean_forecast = _mean(forecasts)
    observed = _mean(outcomes)
    if mean_forecast is None or observed is None:
        return None
    return round(abs(mean_forecast - observed), 8)


def _rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator), 8)


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _report_id(historical_path: Path, gap_threshold: float) -> str:
    return f"calibration_bucket_qa_{_safe_filename(historical_path.stem)}_{gap_threshold:g}"


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return safe or "calibration_bucket_qa"


def _render_markdown(report: dict[str, Any]) -> str:
    dataset = report["dataset"]
    high_gap_buckets = report["high_gap_buckets"]
    guardrails = report["guardrails"]
    lines = [
        "# Calibration Bucket QA Report",
        "",
        f"Report id: `{report['report_id']}`",
        f"Historical file: `{report['historical_file']}`",
        f"Gap threshold: {report['gap_threshold']}",
        "",
        "## Dataset",
        "",
        f"- Dataset id: `{dataset['dataset_id']}`",
        f"- Rows: {dataset['row_count']}",
        f"- Markets: {dataset['market_count']}",
        f"- Scored rows: {dataset['scored_row_count']}",
        f"- Category source: `{dataset['category_source']}`",
        f"- Row category missing count: {dataset['row_category_missing_count']}",
        f"- Source-manifest category missing count: {dataset['source_manifest_category_missing_count']}",
        f"- Evidence missing count: {dataset['evidence_missing_count']}",
        f"- Bid/ask missing count: {dataset['bid_ask_missing_count']}",
        "",
        "## Bucket Stats",
        "",
        "| Bucket | Rows | Markets | Mean forecast | Observed YES rate | Absolute gap | Brier | Log loss |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for bucket in report["bucket_stats"]:
        lines.append(
            f"| `{bucket['bucket']}` | {bucket['rows']} | {bucket['markets']} | "
            f"{_format_metric(bucket['mean_forecast'])} | "
            f"{_format_metric(bucket['observed_yes_rate'])} | "
            f"{_format_metric(bucket['absolute_gap'])} | "
            f"{_format_metric(bucket['brier'])} | "
            f"{_format_metric(bucket['log_loss'])} |"
        )
    lines.extend(["", "## High-Gap Buckets", ""])
    if not high_gap_buckets:
        lines.append("None.")
    for bucket in high_gap_buckets:
        lines.extend(
            [
                f"### `{bucket['bucket']}`",
                "",
                f"- Rows: {bucket['rows']}",
                f"- Markets: {bucket['markets']}",
                f"- Absolute gap: {_format_metric(bucket['absolute_gap'])}",
                f"- Brier: {_format_metric(bucket['brier'])}",
                f"- Log loss: {_format_metric(bucket['log_loss'])}",
                f"- Outcome split: {bucket['outcome_split']}",
                f"- Dominated by few markets: {bucket['dominance']['dominated_by_few_markets']}",
                f"- All rows calibration-only last price: {bucket['all_rows_calibration_only_last_price']}",
                f"- Warnings: {', '.join(bucket['warnings']) if bucket['warnings'] else 'None'}",
                "",
                "Top markets by rows:",
                "",
            ]
        )
        lines.extend(_market_lines(bucket["top_markets_by_rows"]))
        lines.extend(["", "Top markets by Brier loss:", ""])
        lines.extend(_market_lines(bucket["top_markets_by_brier_loss"]))
        lines.extend(["", "Representative rows:", ""])
        lines.extend(_representative_lines(bucket["representative_rows"]))
        lines.append("")
    lines.extend(
        [
            "## Guardrails",
            "",
            "| Claim | Allowed |",
            "| --- | --- |",
            f"| Forecast calibration diagnostics | {guardrails['forecast_calibration_diagnostics']} |",
            f"| Acceptance gate pass | {guardrails['acceptance_gate_pass']} |",
            f"| Strategy v2 superiority | {guardrails['strategy_v2_superiority']} |",
            f"| Profitability claim | {guardrails['profitability_claim']} |",
            f"| Acceptance-ready claim | {guardrails['acceptance_ready_claim']} |",
            f"| Trading readiness claim | {guardrails['trading_readiness_claim']} |",
            "",
            "This report is calibration QA only. It does not make acceptance, "
            "Strategy v2 superiority, profitability, or trading-readiness claims.",
            "",
        ]
    )
    return "\n".join(lines)


def _market_lines(markets: list[dict[str, Any]]) -> list[str]:
    if not markets:
        return ["- None"]
    return [
        "- "
        f"`{market['market_id']}` rows={market['rows']} "
        f"share={market['row_share']} "
        f"brier_loss_sum={market['brier_loss_sum']} "
        f"category={market['source_manifest_category']}"
        for market in markets
    ]


def _representative_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- None"]
    return [
        "- "
        f"`{row['row_id']}` market=`{row['market_id']}` "
        f"timestamp=`{row['timestamp']}` forecast={row['forecast']} "
        f"outcome={row['settlement_outcome']} brier={row['brier_loss']} "
        f"category={row['source_manifest_category']}"
        for row in rows
    ]


def _format_metric(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.8f}"
    return str(value)
