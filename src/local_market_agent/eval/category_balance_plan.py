from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from local_market_agent.eval.category_calibration import (
    CATEGORY_MISSING,
    CATEGORY_PUBLIC_EVENT,
    run_category_calibration_analysis,
)

DEFAULT_CATEGORY_REPORT_PATH = Path("docs/reports/kalshi_category_calibration_analysis.md")
DEFAULT_SOURCE_EXPORT_ROOT = Path("data/source_exports/kalshi")
DEFAULT_GAP_THRESHOLD = 0.15
PUBLIC_EVENT_MARKET_CAP_SHARE = 0.50
MAJOR_CATEGORY_MARKET_TARGET = 20
SMALL_CATEGORY_MARKET_THRESHOLD = 10
SMALL_CATEGORY_ROW_THRESHOLD = 100
ROWS_PER_MARKET_TARGET = 12

PLAN_TIERS = {
    "minimum": {
        "target_markets": 80,
        "target_rows": 960,
        "description": "Smallest useful category-balanced retry if four known categories are available.",
    },
    "preferred": {
        "target_markets": 120,
        "target_rows": 1440,
        "description": "Recommended retry target for less fragile cross-category calibration QA.",
    },
    "stretch": {
        "target_markets": 200,
        "target_rows": 2400,
        "description": "Higher-power calibration QA target while remaining calibration-only.",
    },
}

WARNING_PUBLIC_EVENT_OVERDOMINANCE = "public_event_overdominance_warning"
WARNING_SMALL_CATEGORY_SAMPLE = "small_category_sample_warning"
WARNING_SMALL_CATEGORY_MARKET_SAMPLE = "small_category_market_sample_warning"
WARNING_SMALL_CATEGORY_ROW_SAMPLE = "small_category_row_sample_warning"
WARNING_CATEGORY_METADATA_MISSING = "category_metadata_missing_warning"
WARNING_AVAILABLE_SOURCE_LIMITATION = "available_source_limitation_warning"


@dataclass(frozen=True)
class CategoryBalancePlanArtifacts:
    json_path: Path
    markdown_path: Path
    docs_markdown_path: Path | None = None


@dataclass(frozen=True)
class CategoryBalancePlanResult:
    report: dict[str, Any]

    @property
    def dataset_id(self) -> str:
        return str(self.report["dataset"]["dataset_id"])

    @property
    def target_plans(self) -> dict[str, dict[str, Any]]:
        plans = self.report["target_plans"]
        return plans if isinstance(plans, dict) else {}

    @property
    def recommended_plan(self) -> dict[str, Any]:
        recommended = self.report["recommended_plan"]
        return recommended if isinstance(recommended, dict) else {}

    @property
    def guardrails(self) -> dict[str, bool]:
        guardrails = self.report["guardrails"]
        return guardrails if isinstance(guardrails, dict) else {}

    def as_dict(self) -> dict[str, Any]:
        return self.report


def run_category_balance_plan(
    historical_file: str | Path,
    *,
    category_report_path: str | Path = DEFAULT_CATEGORY_REPORT_PATH,
    source_export_root: str | Path = DEFAULT_SOURCE_EXPORT_ROOT,
    gap_threshold: float = DEFAULT_GAP_THRESHOLD,
) -> CategoryBalancePlanResult:
    analysis = run_category_calibration_analysis(
        historical_file,
        source_export_root=source_export_root,
        gap_threshold=gap_threshold,
    ).as_dict()
    high_gap_from_report = _load_high_gap_shares(Path(category_report_path))
    current_distribution = _current_distribution(
        analysis,
        high_gap_report=high_gap_from_report,
    )
    target_plans = _target_plans(current_distribution)
    recommended_plan_name = "preferred"
    report = {
        "report_id": _report_id(Path(historical_file)),
        "phase": "PR-CAL-7",
        "created_at": datetime.now(UTC).isoformat(),
        "historical_file": str(Path(historical_file)),
        "category_report_path": str(Path(category_report_path)),
        "source_export_root": str(Path(source_export_root)),
        "dataset": _dataset_summary(analysis),
        "current_distribution": current_distribution,
        "target_plans": target_plans,
        "recommended_plan_name": recommended_plan_name,
        "recommended_plan": target_plans[recommended_plan_name],
        "recommended_target": _recommended_target(target_plans[recommended_plan_name]),
        "available_source_limitations": _available_source_limitations(
            current_distribution,
            target_plans[recommended_plan_name],
        ),
        "collector_constraints": _collector_constraints(target_plans[recommended_plan_name]),
        "interpretation_guardrails": _interpretation_guardrails(current_distribution),
        "guardrails": _guardrails(),
    }
    return CategoryBalancePlanResult(report=report)


def write_category_balance_plan_reports(
    result: CategoryBalancePlanResult,
    output_dir: str | Path,
    *,
    docs_markdown_path: str | Path | None = None,
) -> CategoryBalancePlanArtifacts:
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    safe_dataset_id = _safe_filename(result.dataset_id)
    json_path = report_dir / f"{safe_dataset_id}.category_balance_plan.json"
    markdown_path = report_dir / f"{safe_dataset_id}_category_balance_plan.md"
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

    return CategoryBalancePlanArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        docs_markdown_path=docs_path,
    )


def _dataset_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    dataset = analysis["dataset"]
    comparison = analysis["comparison"]
    return {
        "dataset_id": dataset["dataset_id"],
        "row_count": dataset["row_count"],
        "market_count": dataset["market_count"],
        "scored_row_count": dataset["scored_row_count"],
        "category_source_status": dataset["category_source_status"],
        "category_missing_row_count": dataset["category_missing_row_count"],
        "category_missing_market_count": dataset["category_missing_market_count"],
        "public_event_dominance_detected": comparison[
            "public_event_dominance_detected"
        ],
        "non_public_event_sparse": comparison["non_public_event_sparse"],
    }


def _current_distribution(
    analysis: dict[str, Any],
    *,
    high_gap_report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    categories = analysis["categories"]
    distribution: dict[str, dict[str, Any]] = {}
    for category, report in categories.items():
        high_gap = high_gap_report["categories"].get(category, {})
        high_gap_row_share = high_gap.get(
            "high_gap_bucket_row_contribution_share",
            report.get("high_gap_bucket_row_contribution_share"),
        )
        high_gap_brier_share = high_gap.get(
            "high_gap_bucket_brier_loss_contribution_share",
            report.get("high_gap_bucket_brier_loss_contribution_share"),
        )
        warnings = _category_warnings(category, report)
        distribution[category] = {
            "category": category,
            "market_count": report["market_count"],
            "row_count": report["row_count"],
            "row_share": report["row_share"],
            "market_share": report["market_share"],
            "brier_loss_share": report["brier_loss_contribution_share"],
            "high_gap_bucket_row_share": high_gap_row_share,
            "high_gap_bucket_brier_share": high_gap_brier_share,
            "high_gap_share_source": high_gap_report["status"]
            if high_gap
            else "computed_category_analysis",
            "warnings": warnings,
            "sample_size_warning": WARNING_SMALL_CATEGORY_SAMPLE in warnings,
            "available_source_limitation": _available_source_limited(report),
            "category_effect_claim_allowed": False,
        }
    return dict(
        sorted(
            distribution.items(),
            key=lambda item: (-item[1]["row_count"], item[0]),
        )
    )


def _target_plans(
    current_distribution: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    known_categories = [
        category
        for category in current_distribution
        if category != CATEGORY_MISSING
    ]
    if not known_categories:
        known_categories = [
            CATEGORY_PUBLIC_EVENT,
            "major_sports",
            "weather",
            "fed_policy",
        ]

    plans = {
        tier: _single_target_plan(
            tier=tier,
            target_markets=int(config["target_markets"]),
            target_rows=int(config["target_rows"]),
            description=str(config["description"]),
            categories=known_categories,
            current_distribution=current_distribution,
        )
        for tier, config in PLAN_TIERS.items()
    }
    return plans


def _single_target_plan(
    *,
    tier: str,
    target_markets: int,
    target_rows: int,
    description: str,
    categories: list[str],
    current_distribution: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    quotas = _balanced_quotas(categories, target_markets)
    public_event_quota = quotas.get(CATEGORY_PUBLIC_EVENT, 0)
    public_event_cap = math.floor(target_markets * PUBLIC_EVENT_MARKET_CAP_SHARE)
    if public_event_quota > public_event_cap:
        extra = public_event_quota - public_event_cap
        quotas[CATEGORY_PUBLIC_EVENT] = public_event_cap
        _redistribute_quota(quotas, extra, exclude={CATEGORY_PUBLIC_EVENT})

    rows_per_market = max(1, math.ceil(target_rows / target_markets))
    category_targets: dict[str, dict[str, Any]] = {}
    for category, market_quota in quotas.items():
        current = current_distribution.get(category, {})
        target_row_count = market_quota * rows_per_market
        current_markets = int(current.get("market_count", 0))
        current_rows = int(current.get("row_count", 0))
        category_targets[category] = {
            "target_market_count": market_quota,
            "target_row_count": target_row_count,
            "target_market_share": _rate(market_quota, target_markets),
            "target_row_share": _rate(target_row_count, target_markets * rows_per_market),
            "rows_per_market_target": rows_per_market,
            "current_market_count": current_markets,
            "current_row_count": current_rows,
            "additional_market_need_vs_current": max(0, market_quota - current_markets),
            "additional_row_need_vs_current": max(0, target_row_count - current_rows),
            "current_source_availability_observed": current_markets,
            "available_source_limitation": current_markets < market_quota,
            "availability_note": _availability_note(
                category=category,
                current_markets=current_markets,
                target_markets=market_quota,
            ),
        }
    warnings = _plan_warnings(category_targets, target_markets)
    return {
        "tier": tier,
        "description": description,
        "target_market_count": target_markets,
        "target_row_count": target_markets * rows_per_market,
        "configured_target_row_count": target_rows,
        "rows_per_market_target": rows_per_market,
        "public_event_market_cap": public_event_cap,
        "public_event_market_cap_share": PUBLIC_EVENT_MARKET_CAP_SHARE,
        "major_category_market_target": MAJOR_CATEGORY_MARKET_TARGET,
        "category_targets": category_targets,
        "warnings": warnings,
        "meets_public_event_cap": (
            category_targets.get(CATEGORY_PUBLIC_EVENT, {}).get(
                "target_market_count",
                0,
            )
            <= public_event_cap
        ),
        "collection_allowed": False,
    }


def _balanced_quotas(categories: list[str], target_markets: int) -> dict[str, int]:
    category_count = max(1, len(categories))
    base_quota = target_markets // category_count
    remainder = target_markets % category_count
    ordered = sorted(
        categories,
        key=lambda category: (category == CATEGORY_PUBLIC_EVENT, category),
    )
    quotas = {category: base_quota for category in ordered}
    for category in ordered[:remainder]:
        quotas[category] += 1
    for category in ordered:
        if target_markets >= MAJOR_CATEGORY_MARKET_TARGET * category_count:
            quotas[category] = max(quotas[category], MAJOR_CATEGORY_MARKET_TARGET)
    while sum(quotas.values()) > target_markets:
        reducible = [
            category
            for category in reversed(ordered)
            if quotas[category] > MAJOR_CATEGORY_MARKET_TARGET
        ]
        if not reducible:
            break
        quotas[reducible[0]] -= 1
    while sum(quotas.values()) < target_markets:
        for category in ordered:
            quotas[category] += 1
            if sum(quotas.values()) == target_markets:
                break
    return dict(sorted(quotas.items()))


def _redistribute_quota(
    quotas: dict[str, int],
    extra: int,
    *,
    exclude: set[str],
) -> None:
    targets = [category for category in sorted(quotas) if category not in exclude]
    if not targets:
        return
    while extra > 0:
        for category in targets:
            quotas[category] += 1
            extra -= 1
            if extra == 0:
                break


def _recommended_target(recommended_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan": recommended_plan["tier"],
        "target_market_count": recommended_plan["target_market_count"],
        "target_row_count": recommended_plan["target_row_count"],
        "public_event_market_cap": recommended_plan["public_event_market_cap"],
        "public_event_market_cap_share": recommended_plan[
            "public_event_market_cap_share"
        ],
        "minimum_markets_per_major_category_where_available": (
            MAJOR_CATEGORY_MARKET_TARGET
        ),
        "small_category_warning_thresholds": {
            "market_count": SMALL_CATEGORY_MARKET_THRESHOLD,
            "row_count": SMALL_CATEGORY_ROW_THRESHOLD,
        },
        "category_effect_claim_allowed": False,
    }


def _collector_constraints(recommended_plan: dict[str, Any]) -> dict[str, Any]:
    category_targets = recommended_plan["category_targets"]
    return {
        "do_not_implement_in_this_pr": True,
        "suggested_future_constraints_only": True,
        "max_public_event_markets": recommended_plan["public_event_market_cap"],
        "max_public_event_market_share": recommended_plan[
            "public_event_market_cap_share"
        ],
        "desired_category_quotas": {
            category: target["target_market_count"]
            for category, target in category_targets.items()
        },
        "per_category_rows_per_market_targets": {
            category: target["rows_per_market_target"]
            for category, target in category_targets.items()
        },
        "stop_conditions": [
            "stop when every available category quota is met",
            "stop if public_event reaches its cap before non-public quotas are met",
            "stop when target row count is reached with 100% scored settlement coverage",
            "stop with an availability-limited status if non-public categories cannot be found without broadening scope",
        ],
        "fallback_behavior_if_non_public_unavailable": [
            "do not fill missing non-public quotas with public_event beyond the cap",
            "emit available_source_limitation rather than category_effect evidence",
            "preserve calibration_only_last_price shape",
            "write a planning/collection-limitation report before any retry result is interpreted",
        ],
    }


def _available_source_limitations(
    current_distribution: dict[str, dict[str, Any]],
    recommended_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    limitations: list[dict[str, Any]] = []
    for category, target in recommended_plan["category_targets"].items():
        current = current_distribution.get(category, {})
        current_markets = int(current.get("market_count", 0))
        if current_markets >= target["target_market_count"]:
            continue
        limitations.append(
            {
                "category": category,
                "current_observed_markets": current_markets,
                "recommended_target_markets": target["target_market_count"],
                "additional_markets_needed": target[
                    "additional_market_need_vs_current"
                ],
                "classification": "available_source_limitation",
                "not_a_true_category_effect": True,
                "note": (
                    "Current source availability is insufficient for this target; "
                    "do not interpret the shortfall as a true category calibration effect."
                ),
            }
        )
    return limitations


def _interpretation_guardrails(
    current_distribution: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    public_event = current_distribution.get(CATEGORY_PUBLIC_EVENT, {})
    public_overdominance = (
        float(public_event.get("market_share", 0.0)) > PUBLIC_EVENT_MARKET_CAP_SHARE
    )
    sparse_categories = [
        category
        for category, stats in current_distribution.items()
        if stats["sample_size_warning"]
    ]
    return {
        "public_event_overdominance_detected": public_overdominance,
        "sparse_categories": sparse_categories,
        "available_source_limitation_is_not_category_effect": True,
        "category_effect_claim_allowed": False,
        "balanced_retry_required_before_broad_category_conclusions": True,
    }


def _category_warnings(category: str, report: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if category == CATEGORY_MISSING and report["row_count"] > 0:
        warnings.append(WARNING_CATEGORY_METADATA_MISSING)
    if category == CATEGORY_PUBLIC_EVENT and report["market_share"] > PUBLIC_EVENT_MARKET_CAP_SHARE:
        warnings.append(WARNING_PUBLIC_EVENT_OVERDOMINANCE)
    if _available_source_limited(report):
        warnings.append(WARNING_AVAILABLE_SOURCE_LIMITATION)
    if (
        report["market_count"] < SMALL_CATEGORY_MARKET_THRESHOLD
        or report["row_count"] < SMALL_CATEGORY_ROW_THRESHOLD
    ):
        warnings.append(WARNING_SMALL_CATEGORY_SAMPLE)
    if report["market_count"] < SMALL_CATEGORY_MARKET_THRESHOLD:
        warnings.append(WARNING_SMALL_CATEGORY_MARKET_SAMPLE)
    if report["row_count"] < SMALL_CATEGORY_ROW_THRESHOLD:
        warnings.append(WARNING_SMALL_CATEGORY_ROW_SAMPLE)
    return list(dict.fromkeys(warnings))


def _available_source_limited(report: dict[str, Any]) -> bool:
    return (
        report["category"] != CATEGORY_MISSING
        and report["market_count"] < MAJOR_CATEGORY_MARKET_TARGET
    )


def _plan_warnings(
    category_targets: dict[str, dict[str, Any]],
    target_markets: int,
) -> list[str]:
    warnings: list[str] = []
    public_event = category_targets.get(CATEGORY_PUBLIC_EVENT)
    if public_event and public_event["target_market_count"] > target_markets * PUBLIC_EVENT_MARKET_CAP_SHARE:
        warnings.append(WARNING_PUBLIC_EVENT_OVERDOMINANCE)
    if any(target["available_source_limitation"] for target in category_targets.values()):
        warnings.append(WARNING_AVAILABLE_SOURCE_LIMITATION)
    return list(dict.fromkeys(warnings))


def _load_high_gap_shares(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "status": "missing",
            "path": str(path),
            "categories": {},
        }
    categories: dict[str, dict[str, Any]] = {}
    in_table = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "Category contribution to high-gap category buckets:":
            in_table = True
            continue
        if in_table and stripped.startswith("## "):
            break
        if not in_table or not stripped.startswith("| `"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != 5:
            continue
        category = cells[0].strip("`")
        categories[category] = {
            "high_gap_bucket_row_count": _parse_int(cells[1]),
            "high_gap_bucket_brier_loss_sum": _parse_float(cells[2]),
            "high_gap_bucket_row_contribution_share": _parse_percent(cells[3]),
            "high_gap_bucket_brier_loss_contribution_share": _parse_percent(cells[4]),
        }
    status = "loaded" if categories else "unavailable"
    return {
        "status": status,
        "path": str(path),
        "categories": categories,
    }


def _availability_note(
    *,
    category: str,
    current_markets: int,
    target_markets: int,
) -> str:
    if category == CATEGORY_MISSING:
        return "Category metadata must be restored before a balanced retry can be assessed."
    if current_markets >= target_markets:
        return "Current observed source metadata has enough markets for this target."
    return (
        "Current observed source metadata is below the target. Treat this as an "
        "available-source limitation until a future collector or manual source review "
        "shows otherwise."
    )


def _guardrails() -> dict[str, bool]:
    return {
        "calibration_planning_only": True,
        "local_only": True,
        "data_collection": False,
        "collector_implemented": False,
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


def _parse_int(value: str) -> int | None:
    try:
        return int(value.replace(",", ""))
    except ValueError:
        return None


def _parse_float(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _parse_percent(value: str) -> float | None:
    match = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)%", value.strip())
    if match is None:
        return None
    return round(float(match.group(1)) / 100, 8)


def _rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator), 8)


def _report_id(historical_path: Path) -> str:
    return f"category_balance_plan_{_safe_filename(historical_path.stem)}"


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return safe or "category_balance_plan"


def _render_markdown(report: dict[str, Any]) -> str:
    dataset = report["dataset"]
    recommended = report["recommended_plan"]
    guardrails = report["guardrails"]
    lines = [
        "# Kalshi Category Balance Plan",
        "",
        "Scope: PR-CAL-7 local-only calibration planning. This report designs a "
        "category-balanced calibration-only retry, but it does not collect data, "
        "modify strategy logic, modify acceptance gates, start Phase 8, add "
        "broker/live trading, add scheduler behavior, or make profitability, "
        "acceptance, Strategy v2 superiority, paper-PnL, or live-readiness claims.",
        "",
        "## Inputs",
        "",
        f"- Historical file: `{report['historical_file']}`",
        f"- PR-CAL-6 category report: `{report['category_report_path']}`",
        f"- Source export root: `{report['source_export_root']}`",
        f"- Dataset id: `{dataset['dataset_id']}`",
        f"- Category source status: `{dataset['category_source_status']}`",
        "",
        "## Current Distribution",
        "",
        "| Category | Markets | Rows | Market share | Row share | Brier loss share | High-gap Brier share | Warnings |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for category, stats in report["current_distribution"].items():
        lines.append(
            f"| `{category}` | {stats['market_count']} | {stats['row_count']} | "
            f"{_format_pct(stats['market_share'])} | {_format_pct(stats['row_share'])} | "
            f"{_format_pct(stats['brier_loss_share'])} | "
            f"{_format_pct(stats['high_gap_bucket_brier_share'])} | "
            f"{_warnings(stats['warnings'])} |"
        )
    lines.extend(
        [
            "",
            "## Target Plans",
            "",
        ]
    )
    for plan_name, plan in report["target_plans"].items():
        lines.extend(_plan_lines(plan_name, plan))
    lines.extend(
        [
            "",
            "## Recommended Target",
            "",
            f"- Recommended plan: `{report['recommended_plan_name']}`",
            f"- Target markets: {recommended['target_market_count']}",
            f"- Target rows: {recommended['target_row_count']}",
            f"- Rows per market target: {recommended['rows_per_market_target']}",
            f"- Public-event cap: {recommended['public_event_market_cap']} markets "
            f"({_format_pct(recommended['public_event_market_cap_share'])})",
            f"- At least {MAJOR_CATEGORY_MARKET_TARGET} markets per major category where available.",
            f"- Small-category warnings: < {SMALL_CATEGORY_MARKET_THRESHOLD} markets or < {SMALL_CATEGORY_ROW_THRESHOLD} rows.",
            "",
            "The current PR-CAL-5 dataset should be treated as source-skewed, not as "
            "evidence of a true category effect. If future non-public categories are "
            "unavailable, record an available-source limitation instead of filling the "
            "gap with more public-event markets.",
            "",
            "## Suggested Future Collector Constraints",
            "",
        ]
    )
    constraints = report["collector_constraints"]
    lines.extend(
        [
            f"- Max public-event markets: {constraints['max_public_event_markets']}",
            f"- Max public-event market share: {_format_pct(constraints['max_public_event_market_share'])}",
            f"- Desired category quotas: `{constraints['desired_category_quotas']}`",
            f"- Per-category rows-per-market targets: `{constraints['per_category_rows_per_market_targets']}`",
            "",
            "Stop conditions:",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in constraints["stop_conditions"])
    lines.extend(["", "Fallback behavior if non-public categories are unavailable:", ""])
    lines.extend(f"- {item}" for item in constraints["fallback_behavior_if_non_public_unavailable"])
    lines.extend(["", "## Available-Source Limitations", ""])
    if report["available_source_limitations"]:
        for item in report["available_source_limitations"]:
            lines.append(
                "- "
                f"`{item['category']}` current={item['current_observed_markets']} "
                f"target={item['recommended_target_markets']} "
                f"additional_needed={item['additional_markets_needed']} "
                f"classification=`{item['classification']}`"
            )
    else:
        lines.append("None.")
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
            "Use this plan to scope a future category-balanced calibration-only retry. "
            "Do not implement collection, acceptance evaluation, Strategy v2 "
            "superiority evaluation, profitability analysis, live trading, or Phase 8 "
            "work from this PR.",
            "",
        ]
    )
    return "\n".join(lines)


def _plan_lines(plan_name: str, plan: dict[str, Any]) -> list[str]:
    lines = [
        f"### `{plan_name}`",
        "",
        f"- Target markets: {plan['target_market_count']}",
        f"- Target rows: {plan['target_row_count']}",
        f"- Rows per market target: {plan['rows_per_market_target']}",
        f"- Public-event cap: {plan['public_event_market_cap']}",
        f"- Warnings: {_warnings(plan['warnings'])}",
        "",
        "| Category | Target markets | Target rows | Market share | Current markets | Additional markets needed | Availability-limited |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for category, target in plan["category_targets"].items():
        lines.append(
            f"| `{category}` | {target['target_market_count']} | "
            f"{target['target_row_count']} | "
            f"{_format_pct(target['target_market_share'])} | "
            f"{target['current_market_count']} | "
            f"{target['additional_market_need_vs_current']} | "
            f"`{target['available_source_limitation']}` |"
        )
    lines.append("")
    return lines


def _warnings(warnings: list[str]) -> str:
    return ", ".join(warnings) if warnings else "None"


def _format_pct(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.6f}%"
    except (TypeError, ValueError):
        return str(value)
