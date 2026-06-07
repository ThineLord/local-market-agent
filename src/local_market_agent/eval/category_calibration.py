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
CATEGORY_MISSING = "missing"
CATEGORY_PUBLIC_EVENT = "public_event"
SMALL_CATEGORY_ROW_THRESHOLD = 30
SMALL_CATEGORY_MARKET_THRESHOLD = 5
CALIBRATION_MINIMUM_ROWS = 250
CALIBRATION_MINIMUM_MARKETS = 25
CATEGORY_DOMINANCE_THRESHOLD = 0.75
MARKET_CONCENTRATION_THRESHOLD = 0.25
TOP_THREE_MARKET_CONCENTRATION_THRESHOLD = 0.50

WARNING_CATEGORY_MISSING = "category_missing_warning"
WARNING_PUBLIC_EVENT_DOMINANCE = "public_event_dominance_warning"
WARNING_SMALL_CATEGORY_SAMPLE = "small_category_sample_warning"
WARNING_SMALL_CATEGORY_ROW_SAMPLE = "small_category_row_sample_warning"
WARNING_SMALL_CATEGORY_MARKET_SAMPLE = "small_category_market_sample_warning"
WARNING_MARKET_CONCENTRATION = "market_concentration_warning"
WARNING_TOP_THREE_MARKET_CONCENTRATION = "top_three_market_concentration_warning"
WARNING_NON_PUBLIC_EVENT_SPARSE = "non_public_event_sparse_warning"


@dataclass(frozen=True)
class CategoryCalibrationArtifacts:
    json_path: Path
    markdown_path: Path
    docs_markdown_path: Path | None = None


@dataclass(frozen=True)
class CategoryCalibrationResult:
    report: dict[str, Any]

    @property
    def dataset_id(self) -> str:
        return str(self.report["dataset"]["dataset_id"])

    @property
    def category_reports(self) -> dict[str, dict[str, Any]]:
        categories = self.report["categories"]
        return categories if isinstance(categories, dict) else {}

    @property
    def comparison(self) -> dict[str, Any]:
        comparison = self.report["comparison"]
        return comparison if isinstance(comparison, dict) else {}

    @property
    def guardrails(self) -> dict[str, bool]:
        guardrails = self.report["guardrails"]
        return guardrails if isinstance(guardrails, dict) else {}

    def as_dict(self) -> dict[str, Any]:
        return self.report


def run_category_calibration_analysis(
    historical_file: str | Path,
    *,
    source_export_root: str | Path = Path("data/source_exports/kalshi"),
    gap_threshold: float = DEFAULT_GAP_THRESHOLD,
) -> CategoryCalibrationResult:
    historical_path = Path(historical_file)
    rows = _load_rows(historical_path)
    if not rows:
        msg = "category calibration analysis requires at least one historical row"
        raise ValueError(msg)

    category_lookup, category_source = _load_category_lookup(
        rows,
        source_export_root=Path(source_export_root),
    )
    enriched_rows = _enrich_rows(rows, category_lookup=category_lookup)
    categories = _category_reports(enriched_rows, gap_threshold=gap_threshold)
    overall = _segment_report(
        name="all_categories",
        rows=enriched_rows,
        total_rows=len(enriched_rows),
        total_markets=len({row["market_id"] for row in enriched_rows}),
        total_brier_loss=_brier_loss_sum(enriched_rows),
        gap_threshold=gap_threshold,
    )
    comparison = _comparison_report(
        enriched_rows,
        categories=categories,
        overall=overall,
        gap_threshold=gap_threshold,
    )
    report = {
        "report_id": _report_id(historical_path, gap_threshold),
        "phase": "PR-CAL-6",
        "created_at": datetime.now(UTC).isoformat(),
        "historical_file": str(historical_path),
        "gap_threshold": gap_threshold,
        "dataset": _dataset_summary(
            rows=enriched_rows,
            category_source=category_source,
        ),
        "overall": overall,
        "categories": categories,
        "comparison": comparison,
        "guardrails": _guardrails(),
    }
    return CategoryCalibrationResult(report=report)


def write_category_calibration_reports(
    result: CategoryCalibrationResult,
    output_dir: str | Path,
    *,
    docs_markdown_path: str | Path | None = None,
) -> CategoryCalibrationArtifacts:
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    safe_dataset_id = _safe_filename(result.dataset_id)
    json_path = report_dir / f"{safe_dataset_id}.category_calibration.json"
    markdown_path = report_dir / f"{safe_dataset_id}_category_calibration.md"
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

    return CategoryCalibrationArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        docs_markdown_path=docs_path,
    )


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


def _load_category_lookup(
    rows: list[dict[str, Any]],
    *,
    source_export_root: Path,
) -> tuple[dict[str, str], dict[str, Any]]:
    export_ids = sorted(
        {
            str(export_id)
            for row in rows
            if (export_id := _metadata_value(row, "export_id"))
        }
    )
    if not export_ids:
        return {}, {
            "status": "missing",
            "source_export_root": str(source_export_root),
            "export_ids": [],
            "loaded_paths": [],
            "missing_paths": [],
        }

    lookup: dict[str, str] = {}
    loaded_paths: list[str] = []
    missing_paths: list[str] = []
    for export_id in export_ids:
        markets_path = source_export_root / export_id / "markets.jsonl"
        if not markets_path.exists():
            missing_paths.append(str(markets_path))
            continue
        loaded_paths.append(str(markets_path))
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

    if loaded_paths and missing_paths:
        status = "partial"
    elif loaded_paths:
        status = "loaded"
    else:
        status = "missing"
    return lookup, {
        "status": status,
        "source_export_root": str(source_export_root),
        "export_ids": export_ids,
        "loaded_paths": loaded_paths,
        "missing_paths": missing_paths,
    }


def _enrich_rows(
    rows: list[dict[str, Any]],
    *,
    category_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        market_id = _text(row.get("market_id")) or "missing"
        forecast = _forecast_probability(row)
        outcome = _settlement_outcome(row)
        category = category_lookup.get(market_id) or CATEGORY_MISSING
        brier_loss = _brier_loss(forecast, outcome)
        enriched.append(
            {
                "row_index": index,
                "row_id": _text(row.get("row_id")) or f"row_{index}",
                "market_id": market_id,
                "title": _text(row.get("title")),
                "timestamp": _text(row.get("timestamp")) or "missing",
                "category": category,
                "forecast": forecast,
                "bucket": assign_calibration_bucket(forecast) or "missing",
                "settlement_outcome": outcome,
                "observed_yes": _outcome_yes(outcome)
                if outcome in {"yes", "no"}
                else None,
                "brier_loss": brier_loss,
                "log_loss": _log_loss(forecast, outcome),
                "scored": forecast is not None and outcome in {"yes", "no"},
                "raw": row,
            }
        )
    return enriched


def _category_reports(
    rows: list[dict[str, Any]],
    *,
    gap_threshold: float,
) -> dict[str, dict[str, Any]]:
    total_rows = len(rows)
    total_markets = len({row["market_id"] for row in rows})
    total_brier_loss = _brier_loss_sum(rows)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row)
    reports = {
        category: _segment_report(
            name=category,
            rows=category_rows,
            total_rows=total_rows,
            total_markets=total_markets,
            total_brier_loss=total_brier_loss,
            gap_threshold=gap_threshold,
        )
        for category, category_rows in sorted(grouped.items())
    }
    total_high_gap_rows = sum(
        report["high_gap_bucket_row_count"] for report in reports.values()
    )
    total_high_gap_brier = sum(
        report["high_gap_bucket_brier_loss_sum"] for report in reports.values()
    )
    for report in reports.values():
        report["high_gap_bucket_row_contribution_share"] = _rate(
            report["high_gap_bucket_row_count"],
            total_high_gap_rows,
        )
        report["high_gap_bucket_brier_loss_contribution_share"] = _rate(
            report["high_gap_bucket_brier_loss_sum"],
            total_high_gap_brier,
        )
    return dict(
        sorted(
            reports.items(),
            key=lambda item: (-item[1]["row_count"], item[0]),
        )
    )


def _segment_report(
    *,
    name: str,
    rows: list[dict[str, Any]],
    total_rows: int,
    total_markets: int,
    total_brier_loss: float,
    gap_threshold: float,
) -> dict[str, Any]:
    market_ids = {row["market_id"] for row in rows}
    scored_rows = [row for row in rows if row["scored"]]
    brier_losses = [row["brier_loss"] for row in scored_rows if row["brier_loss"] is not None]
    log_losses = [row["log_loss"] for row in scored_rows if row["log_loss"] is not None]
    brier_loss_sum = round(sum(brier_losses), 8)
    bucket_table = _bucket_table(rows)
    high_gap_buckets = [
        bucket
        for bucket in bucket_table
        if bucket["rows"] > 0
        and bucket["absolute_calibration_gap"] is not None
        and bucket["absolute_calibration_gap"] >= gap_threshold
    ]
    high_gap_row_count = sum(bucket["rows"] for bucket in high_gap_buckets)
    high_gap_brier_loss_sum = round(
        sum(bucket["brier_loss_sum"] for bucket in high_gap_buckets),
        8,
    )
    dominance = _market_dominance(rows)
    warnings = _segment_warnings(
        name=name,
        row_count=len(rows),
        market_count=len(market_ids),
        row_share=_rate(len(rows), total_rows),
        market_share=_rate(len(market_ids), total_markets),
        dominance=dominance,
    )
    return {
        "category": name,
        "market_count": len(market_ids),
        "row_count": len(rows),
        "scored_row_count": len(scored_rows),
        "row_share": _rate(len(rows), total_rows),
        "market_share": _rate(len(market_ids), total_markets),
        "mean_forecast": _mean(
            [row["forecast"] for row in scored_rows if row["forecast"] is not None]
        ),
        "observed_yes_rate": _mean(
            [
                row["observed_yes"]
                for row in scored_rows
                if row["observed_yes"] is not None
            ]
        ),
        "absolute_calibration_gap": _absolute_gap(scored_rows),
        "brier_score": _mean(brier_losses),
        "log_loss": _mean(log_losses),
        "brier_loss_sum": brier_loss_sum,
        "brier_loss_contribution_share": _rate(brier_loss_sum, total_brier_loss),
        "bucket_table": bucket_table,
        "high_gap_buckets": high_gap_buckets,
        "high_gap_bucket_count": len(high_gap_buckets),
        "high_gap_bucket_row_count": high_gap_row_count,
        "high_gap_bucket_brier_loss_sum": high_gap_brier_loss_sum,
        "high_gap_bucket_brier_loss_share_within_category": _rate(
            high_gap_brier_loss_sum,
            brier_loss_sum,
        ),
        "high_gap_bucket_row_contribution_share": 0.0,
        "high_gap_bucket_brier_loss_contribution_share": 0.0,
        "top_markets_by_row_count": _top_markets(rows, sort_by="rows"),
        "top_markets_by_brier_loss": _top_markets(rows, sort_by="brier_loss"),
        "concentration": dominance,
        "concentration_warnings": [
            warning
            for warning in warnings
            if warning
            in {
                WARNING_MARKET_CONCENTRATION,
                WARNING_TOP_THREE_MARKET_CONCENTRATION,
                WARNING_PUBLIC_EVENT_DOMINANCE,
            }
        ],
        "sample_size_warnings": [
            warning
            for warning in warnings
            if warning
            in {
                WARNING_SMALL_CATEGORY_SAMPLE,
                WARNING_SMALL_CATEGORY_ROW_SAMPLE,
                WARNING_SMALL_CATEGORY_MARKET_SAMPLE,
            }
        ],
        "warnings": warnings,
    }


def _bucket_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = [f"{index / 10:.2f}-{(index + 1) / 10:.2f}" for index in range(10)]
    grouped: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in buckets}
    for row in rows:
        if row["scored"] and row["bucket"] in grouped:
            grouped[row["bucket"]].append(row)
    return [_bucket_stats(bucket, grouped[bucket]) for bucket in buckets]


def _bucket_stats(bucket: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    brier_losses = [row["brier_loss"] for row in rows if row["brier_loss"] is not None]
    log_losses = [row["log_loss"] for row in rows if row["log_loss"] is not None]
    brier_loss_sum = round(sum(brier_losses), 8)
    return {
        "bucket": bucket,
        "rows": len(rows),
        "markets": len({row["market_id"] for row in rows}),
        "mean_forecast": _mean(
            [row["forecast"] for row in rows if row["forecast"] is not None]
        ),
        "observed_yes_rate": _mean(
            [row["observed_yes"] for row in rows if row["observed_yes"] is not None]
        ),
        "absolute_calibration_gap": _absolute_gap(rows),
        "brier_score": _mean(brier_losses),
        "log_loss": _mean(log_losses),
        "brier_loss_sum": brier_loss_sum,
        "top_markets_by_row_count": _top_markets(rows, sort_by="rows", limit=5),
        "top_markets_by_brier_loss": _top_markets(rows, sort_by="brier_loss", limit=5),
    }


def _comparison_report(
    rows: list[dict[str, Any]],
    *,
    categories: dict[str, dict[str, Any]],
    overall: dict[str, Any],
    gap_threshold: float,
) -> dict[str, Any]:
    public_rows = [row for row in rows if row["category"] == CATEGORY_PUBLIC_EVENT]
    non_public_rows = [
        row
        for row in rows
        if row["category"] not in {CATEGORY_PUBLIC_EVENT, CATEGORY_MISSING}
    ]
    missing_rows = [row for row in rows if row["category"] == CATEGORY_MISSING]
    total_rows = len(rows)
    total_markets = len({row["market_id"] for row in rows})
    total_brier_loss = _brier_loss_sum(rows)
    public_event = _segment_report(
        name=CATEGORY_PUBLIC_EVENT,
        rows=public_rows,
        total_rows=total_rows,
        total_markets=total_markets,
        total_brier_loss=total_brier_loss,
        gap_threshold=gap_threshold,
    )
    non_public_event = _segment_report(
        name="non_public_event",
        rows=non_public_rows,
        total_rows=total_rows,
        total_markets=total_markets,
        total_brier_loss=total_brier_loss,
        gap_threshold=gap_threshold,
    )
    missing_category = _segment_report(
        name=CATEGORY_MISSING,
        rows=missing_rows,
        total_rows=total_rows,
        total_markets=total_markets,
        total_brier_loss=total_brier_loss,
        gap_threshold=gap_threshold,
    )
    total_high_gap_rows = sum(
        report["high_gap_bucket_row_count"] for report in categories.values()
    )
    total_high_gap_brier = sum(
        report["high_gap_bucket_brier_loss_sum"] for report in categories.values()
    )
    for segment in (public_event, non_public_event, missing_category):
        segment["high_gap_bucket_row_contribution_share"] = _rate(
            segment["high_gap_bucket_row_count"],
            total_high_gap_rows,
        )
        segment["high_gap_bucket_brier_loss_contribution_share"] = _rate(
            segment["high_gap_bucket_brier_loss_sum"],
            total_high_gap_brier,
        )

    public_dominance = (
        public_event["row_share"] >= CATEGORY_DOMINANCE_THRESHOLD
        and public_event["market_share"] >= CATEGORY_DOMINANCE_THRESHOLD
    )
    non_public_sparse = (
        non_public_event["row_count"] < CALIBRATION_MINIMUM_ROWS
        or non_public_event["market_count"] < CALIBRATION_MINIMUM_MARKETS
    )
    non_public_high_gap = bool(non_public_event["high_gap_buckets"])
    public_loss_dominance = (
        public_event["brier_loss_contribution_share"] >= CATEGORY_DOMINANCE_THRESHOLD
    )

    warnings: list[str] = []
    if public_dominance:
        warnings.append(WARNING_PUBLIC_EVENT_DOMINANCE)
    if non_public_sparse:
        warnings.append(WARNING_NON_PUBLIC_EVENT_SPARSE)
    if missing_category["row_count"] > 0:
        warnings.append(WARNING_CATEGORY_MISSING)

    return {
        "public_event": public_event,
        "non_public_event": non_public_event,
        "missing_category": missing_category,
        "category_brier_loss_contributions": [
            {
                "category": category,
                "row_count": report["row_count"],
                "market_count": report["market_count"],
                "brier_loss_sum": report["brier_loss_sum"],
                "brier_loss_contribution_share": report[
                    "brier_loss_contribution_share"
                ],
            }
            for category, report in sorted(
                categories.items(),
                key=lambda item: (-item[1]["brier_loss_sum"], item[0]),
            )
        ],
        "category_high_gap_bucket_contributions": [
            {
                "category": category,
                "high_gap_bucket_row_count": report["high_gap_bucket_row_count"],
                "high_gap_bucket_brier_loss_sum": report[
                    "high_gap_bucket_brier_loss_sum"
                ],
                "high_gap_bucket_row_contribution_share": report[
                    "high_gap_bucket_row_contribution_share"
                ],
                "high_gap_bucket_brier_loss_contribution_share": report[
                    "high_gap_bucket_brier_loss_contribution_share"
                ],
            }
            for category, report in sorted(
                categories.items(),
                key=lambda item: (-item[1]["high_gap_bucket_brier_loss_sum"], item[0]),
            )
        ],
        "public_event_dominance_detected": public_dominance,
        "public_event_loss_dominance_detected": public_loss_dominance,
        "non_public_event_sparse": non_public_sparse,
        "non_public_event_high_gap_detected": non_public_high_gap,
        "aggregate_high_gap_bucket_count": overall["high_gap_bucket_count"],
        "public_event_explanation": {
            "aggregate_weight_explained_by_public_event_dominance": public_dominance
            and public_loss_dominance,
            "gap_origin_explained_by_public_event": False,
            "assessment": _public_event_assessment(
                public_dominance=public_dominance,
                public_loss_dominance=public_loss_dominance,
                non_public_sparse=non_public_sparse,
                non_public_high_gap=non_public_high_gap,
                missing_rows=missing_category["row_count"],
            ),
        },
        "warnings": list(dict.fromkeys(warnings)),
    }


def _dataset_summary(
    *,
    rows: list[dict[str, Any]],
    category_source: dict[str, Any],
) -> dict[str, Any]:
    dataset_ids = Counter(_text(row["raw"].get("dataset_id")) or "missing" for row in rows)
    market_ids = {row["market_id"] for row in rows}
    categories_by_market: dict[str, str] = {}
    for row in rows:
        categories_by_market[row["market_id"]] = row["category"]
    category_market_distribution = Counter(categories_by_market.values())
    return {
        "dataset_id": dataset_ids.most_common(1)[0][0],
        "row_count": len(rows),
        "market_count": len(market_ids),
        "scored_row_count": sum(1 for row in rows if row["scored"]),
        "category_source": category_source,
        "category_source_status": category_source["status"],
        "category_missing_row_count": sum(
            1 for row in rows if row["category"] == CATEGORY_MISSING
        ),
        "category_missing_market_count": sum(
            1 for category in categories_by_market.values() if category == CATEGORY_MISSING
        ),
        "category_row_distribution": dict(
            sorted(Counter(row["category"] for row in rows).items())
        ),
        "category_market_distribution": dict(
            sorted(category_market_distribution.items())
        ),
        "profile_distribution": dict(
            sorted(
                Counter(
                    _text(row["raw"].get("profile")) or "missing" for row in rows
                ).items()
            )
        ),
        "platform_distribution": dict(
            sorted(
                Counter(
                    _text(row["raw"].get("platform")) or "missing" for row in rows
                ).items()
            )
        ),
    }


def _segment_warnings(
    *,
    name: str,
    row_count: int,
    market_count: int,
    row_share: float,
    market_share: float,
    dominance: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if name == CATEGORY_MISSING and row_count > 0:
        warnings.append(WARNING_CATEGORY_MISSING)
    if row_count < SMALL_CATEGORY_ROW_THRESHOLD or market_count < SMALL_CATEGORY_MARKET_THRESHOLD:
        warnings.append(WARNING_SMALL_CATEGORY_SAMPLE)
    if row_count < SMALL_CATEGORY_ROW_THRESHOLD:
        warnings.append(WARNING_SMALL_CATEGORY_ROW_SAMPLE)
    if market_count < SMALL_CATEGORY_MARKET_THRESHOLD:
        warnings.append(WARNING_SMALL_CATEGORY_MARKET_SAMPLE)
    if dominance["top_market_row_share"] >= MARKET_CONCENTRATION_THRESHOLD:
        warnings.append(WARNING_MARKET_CONCENTRATION)
    if dominance["top_three_market_row_share"] >= TOP_THREE_MARKET_CONCENTRATION_THRESHOLD:
        warnings.append(WARNING_TOP_THREE_MARKET_CONCENTRATION)
    if (
        name == CATEGORY_PUBLIC_EVENT
        and row_share >= CATEGORY_DOMINANCE_THRESHOLD
        and market_share >= CATEGORY_DOMINANCE_THRESHOLD
    ):
        warnings.append(WARNING_PUBLIC_EVENT_DOMINANCE)
    return list(dict.fromkeys(warnings))


def _market_dominance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["market_id"] for row in rows)
    ordered = counts.most_common()
    top_count = ordered[0][1] if ordered else 0
    top_three = sum(count for _market, count in ordered[:3])
    return {
        "top_market_id": ordered[0][0] if ordered else None,
        "top_market_row_count": top_count,
        "top_market_row_share": _rate(top_count, len(rows)),
        "top_three_market_row_share": _rate(top_three, len(rows)),
        "dominated_by_few_markets": (
            _rate(top_count, len(rows)) >= MARKET_CONCENTRATION_THRESHOLD
            or _rate(top_three, len(rows)) >= TOP_THREE_MARKET_CONCENTRATION_THRESHOLD
        ),
    }


def _top_markets(
    rows: list[dict[str, Any]],
    *,
    sort_by: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["market_id"]].append(row)
    entries = []
    for market_id, market_rows in grouped.items():
        scored = [row for row in market_rows if row["scored"]]
        brier_loss_sum = round(
            sum(row["brier_loss"] or 0.0 for row in scored),
            8,
        )
        entries.append(
            {
                "market_id": market_id,
                "title": market_rows[0]["title"],
                "rows": len(market_rows),
                "row_share": _rate(len(market_rows), len(rows)),
                "brier_loss_sum": brier_loss_sum,
                "brier_score": _mean(
                    [row["brier_loss"] for row in scored if row["brier_loss"] is not None]
                ),
                "mean_forecast": _mean(
                    [row["forecast"] for row in scored if row["forecast"] is not None]
                ),
                "observed_yes_rate": _mean(
                    [
                        row["observed_yes"]
                        for row in scored
                        if row["observed_yes"] is not None
                    ]
                ),
                "category": market_rows[0]["category"],
            }
        )
    if sort_by == "brier_loss":
        return sorted(
            entries,
            key=lambda item: (-item["brier_loss_sum"], -item["rows"], item["market_id"]),
        )[:limit]
    return sorted(
        entries,
        key=lambda item: (-item["rows"], -item["brier_loss_sum"], item["market_id"]),
    )[:limit]


def _public_event_assessment(
    *,
    public_dominance: bool,
    public_loss_dominance: bool,
    non_public_sparse: bool,
    non_public_high_gap: bool,
    missing_rows: int,
) -> str:
    if missing_rows:
        return (
            "Category source metadata is incomplete, so public-event attribution is "
            "not reliable for this run."
        )
    if public_dominance and public_loss_dominance and non_public_sparse and non_public_high_gap:
        return (
            "Public-event dominance explains most aggregate weighting, but it does "
            "not prove the gaps are public-event-specific because sparse non-public "
            "categories also show high-gap buckets."
        )
    if public_dominance and public_loss_dominance and non_public_sparse:
        return (
            "Public-event dominance explains most aggregate weighting, while "
            "non-public evidence is too sparse for a category-level conclusion."
        )
    if public_dominance and public_loss_dominance:
        return (
            "Public-event dominance explains most aggregate weighting, but category "
            "balance still needs review before treating the gap as category-specific."
        )
    if non_public_high_gap:
        return (
            "Calibration gaps appear outside public-event rows too, so public-event "
            "dominance alone does not explain the pattern."
        )
    return (
        "This run does not isolate public-event dominance as the sole explanation "
        "for aggregate calibration gaps."
    )


def _guardrails() -> dict[str, bool]:
    return {
        "calibration_qa_only": True,
        "local_only": True,
        "data_collection": False,
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


def _optional_probability(value: object) -> float | None:
    parsed = _optional_float(value)
    if parsed is None or not 0 <= parsed <= 1:
        return None
    return parsed


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


def _brier_loss_sum(rows: list[dict[str, Any]]) -> float:
    return round(
        sum(row["brier_loss"] or 0.0 for row in rows if row.get("brier_loss") is not None),
        8,
    )


def _mean(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 8)


def _absolute_gap(rows: list[dict[str, Any]]) -> float | None:
    mean_forecast = _mean([row["forecast"] for row in rows])
    observed = _mean([row["observed_yes"] for row in rows])
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
    return f"category_calibration_{_safe_filename(historical_path.stem)}_{gap_threshold:g}"


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return safe or "category_calibration"


def _render_markdown(report: dict[str, Any]) -> str:
    dataset = report["dataset"]
    overall = report["overall"]
    comparison = report["comparison"]
    guardrails = report["guardrails"]
    public = comparison["public_event"]
    non_public = comparison["non_public_event"]
    explanation = comparison["public_event_explanation"]
    lines = [
        "# Kalshi Category Calibration Analysis",
        "",
        "Scope: PR-CAL-6 local-only calibration QA. This report does not collect data, "
        "modify strategy logic, modify acceptance gates, start Phase 8, add broker/live "
        "trading, add scheduler behavior, or make profitability, acceptance, Strategy v2 "
        "superiority, paper-PnL, or live-readiness claims.",
        "",
        "## Report Inputs",
        "",
        f"- Report id: `{report['report_id']}`",
        f"- Historical file: `{report['historical_file']}`",
        f"- Gap threshold: {report['gap_threshold']}",
        f"- Dataset id: `{dataset['dataset_id']}`",
        f"- Category source status: `{dataset['category_source_status']}`",
        f"- Category source paths: {_format_paths(dataset['category_source']['loaded_paths'])}",
        "",
        "## Dataset Summary",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Rows | {dataset['row_count']} |",
        f"| Markets | {dataset['market_count']} |",
        f"| Scored rows | {dataset['scored_row_count']} |",
        f"| Overall Brier | {_format_metric(overall['brier_score'])} |",
        f"| Overall log loss | {_format_metric(overall['log_loss'])} |",
        f"| Overall mean forecast | {_format_metric(overall['mean_forecast'])} |",
        f"| Overall observed YES rate | {_format_metric(overall['observed_yes_rate'])} |",
        f"| Overall absolute gap | {_format_metric(overall['absolute_calibration_gap'])} |",
        "",
        "Category market distribution:",
        "",
    ]
    lines.extend(_distribution_lines(dataset["category_market_distribution"]))
    lines.extend(
        [
            "",
            "Category row distribution:",
            "",
        ]
    )
    lines.extend(_distribution_lines(dataset["category_row_distribution"]))
    lines.extend(["", "## Category Metrics", ""])
    lines.extend(_category_table_lines(report["categories"]))
    lines.extend(["", "## High-Gap Category Buckets", ""])
    lines.extend(_high_gap_lines(report["categories"]))
    lines.extend(["", "## Public Event Versus Non-Public Event", ""])
    lines.extend(
        [
            "| Segment | Rows | Markets | Row share | Market share | Brier | Log loss | Gap | Brier loss share | High-gap Brier share |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            _segment_table_line("public_event", public),
            _segment_table_line("non_public_event", non_public),
            "",
            f"- Public-event dominance detected: `{comparison['public_event_dominance_detected']}`",
            f"- Public-event Brier-loss dominance detected: `{comparison['public_event_loss_dominance_detected']}`",
            f"- Non-public-event evidence sparse: `{comparison['non_public_event_sparse']}`",
            f"- Non-public-event high-gap bucket detected: `{comparison['non_public_event_high_gap_detected']}`",
            f"- Public-event aggregate-weight explanation: `{explanation['aggregate_weight_explained_by_public_event_dominance']}`",
            f"- Public-event gap-origin explanation: `{explanation['gap_origin_explained_by_public_event']}`",
            f"- Assessment: {explanation['assessment']}",
            "",
            "Category contribution to total Brier loss:",
            "",
            "| Category | Rows | Markets | Brier loss sum | Share |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in comparison["category_brier_loss_contributions"]:
        lines.append(
            f"| `{item['category']}` | {item['row_count']} | {item['market_count']} | "
            f"{_format_metric(item['brier_loss_sum'])} | "
            f"{_format_pct(item['brier_loss_contribution_share'])} |"
        )
    lines.extend(
        [
            "",
            "Category contribution to high-gap category buckets:",
            "",
            "| Category | High-gap rows | High-gap Brier loss sum | Row share | Brier share |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in comparison["category_high_gap_bucket_contributions"]:
        lines.append(
            f"| `{item['category']}` | {item['high_gap_bucket_row_count']} | "
            f"{_format_metric(item['high_gap_bucket_brier_loss_sum'])} | "
            f"{_format_pct(item['high_gap_bucket_row_contribution_share'])} | "
            f"{_format_pct(item['high_gap_bucket_brier_loss_contribution_share'])} |"
        )
    lines.extend(["", "## Top Markets By Category", ""])
    lines.extend(_top_market_lines(report["categories"]))
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "| Guardrail | Value |",
            "| --- | --- |",
        ]
    )
    for name, value in guardrails.items():
        lines.append(f"| `{name}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Recommended Next Step",
            "",
            "Treat this as evidence that PR-CAL-5 is too category-skewed for broad "
            "category conclusions. The next useful step is a category-balance or "
            "metadata-visibility QA task, or a separate manually targeted "
            "acceptance-evidence pilot. Do not use this report for acceptance, "
            "profitability, Strategy v2 superiority, paper-PnL, live-trading, or "
            "Phase 8 readiness claims.",
            "",
        ]
    )
    return "\n".join(lines)


def _category_table_lines(categories: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "| Category | Rows | Markets | Row share | Market share | Mean forecast | Observed YES | Gap | Brier | Log loss | Brier loss share | Warnings |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for category, report in categories.items():
        warnings = ", ".join(report["warnings"]) if report["warnings"] else "None"
        lines.append(
            f"| `{category}` | {report['row_count']} | {report['market_count']} | "
            f"{_format_pct(report['row_share'])} | {_format_pct(report['market_share'])} | "
            f"{_format_metric(report['mean_forecast'])} | "
            f"{_format_metric(report['observed_yes_rate'])} | "
            f"{_format_metric(report['absolute_calibration_gap'])} | "
            f"{_format_metric(report['brier_score'])} | "
            f"{_format_metric(report['log_loss'])} | "
            f"{_format_pct(report['brier_loss_contribution_share'])} | {warnings} |"
        )
    return lines


def _high_gap_lines(categories: dict[str, dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    any_bucket = False
    for category, report in categories.items():
        high_gap_buckets = report["high_gap_buckets"]
        if not high_gap_buckets:
            continue
        any_bucket = True
        lines.extend(
            [
                f"### `{category}`",
                "",
                "| Bucket | Rows | Markets | Mean forecast | Observed YES | Gap | Brier | Brier loss sum |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for bucket in high_gap_buckets:
            lines.append(
                f"| `{bucket['bucket']}` | {bucket['rows']} | {bucket['markets']} | "
                f"{_format_metric(bucket['mean_forecast'])} | "
                f"{_format_metric(bucket['observed_yes_rate'])} | "
                f"{_format_metric(bucket['absolute_calibration_gap'])} | "
                f"{_format_metric(bucket['brier_score'])} | "
                f"{_format_metric(bucket['brier_loss_sum'])} |"
            )
        lines.append("")
    if not any_bucket:
        return ["None."]
    return lines


def _top_market_lines(categories: dict[str, dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for category, report in categories.items():
        lines.extend([f"### `{category}`", "", "Top by row count:"])
        lines.extend(_market_lines(report["top_markets_by_row_count"][:5]))
        lines.extend(["", "Top by Brier loss:"])
        lines.extend(_market_lines(report["top_markets_by_brier_loss"][:5]))
        lines.append("")
    return lines


def _market_lines(markets: list[dict[str, Any]]) -> list[str]:
    if not markets:
        return ["- None"]
    return [
        "- "
        f"`{market['market_id']}` rows={market['rows']} "
        f"row_share={_format_pct(market['row_share'])} "
        f"brier_loss_sum={_format_metric(market['brier_loss_sum'])} "
        f"brier={_format_metric(market['brier_score'])}"
        for market in markets
    ]


def _segment_table_line(label: str, segment: dict[str, Any]) -> str:
    return (
        f"| `{label}` | {segment['row_count']} | {segment['market_count']} | "
        f"{_format_pct(segment['row_share'])} | {_format_pct(segment['market_share'])} | "
        f"{_format_metric(segment['brier_score'])} | {_format_metric(segment['log_loss'])} | "
        f"{_format_metric(segment['absolute_calibration_gap'])} | "
        f"{_format_pct(segment['brier_loss_contribution_share'])} | "
        f"{_format_pct(segment['high_gap_bucket_brier_loss_contribution_share'])} |"
    )


def _distribution_lines(distribution: dict[str, int]) -> list[str]:
    if not distribution:
        return ["- None"]
    return [f"- `{key}`: {value}" for key, value in sorted(distribution.items())]


def _format_paths(paths: list[str]) -> str:
    if not paths:
        return "`none`"
    return ", ".join(f"`{path}`" for path in paths)


def _format_metric(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.8f}"
    return str(value)


def _format_pct(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.6f}%"
    except (TypeError, ValueError):
        return str(value)
