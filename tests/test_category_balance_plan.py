from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from typer.testing import CliRunner

import local_market_agent.eval.category_balance_plan as category_balance_plan_module
from local_market_agent.cli import app
from local_market_agent.eval.category_balance_plan import (
    WARNING_CATEGORY_METADATA_MISSING,
    WARNING_PUBLIC_EVENT_OVERDOMINANCE,
    WARNING_SMALL_CATEGORY_SAMPLE,
    run_category_balance_plan,
)


def test_public_event_over_dominance_detected(tmp_path: Path):
    export_id = "dominance_export"
    market_categories = {
        **{f"PUBLIC-{index}": "public_event" for index in range(8)},
        "SPORTS-1": "major_sports",
        "WEATHER-1": "weather",
    }
    source_root = _write_manifest(
        tmp_path,
        export_id=export_id,
        market_categories=market_categories,
    )
    dataset_path = _write_dataset(
        tmp_path,
        export_id=export_id,
        market_categories=market_categories,
        rows_per_market=2,
    )

    result = run_category_balance_plan(
        dataset_path,
        category_report_path=_write_high_gap_report(tmp_path),
        source_export_root=source_root,
    )

    public_event = result.report["current_distribution"]["public_event"]
    assert WARNING_PUBLIC_EVENT_OVERDOMINANCE in public_event["warnings"]
    assert result.report["interpretation_guardrails"][
        "public_event_overdominance_detected"
    ] is True


def test_balanced_target_quotas_generated(tmp_path: Path):
    export_id = "quota_export"
    market_categories = {
        **{f"PUBLIC-{index}": "public_event" for index in range(4)},
        **{f"SPORTS-{index}": "major_sports" for index in range(4)},
        **{f"WEATHER-{index}": "weather" for index in range(2)},
        "FED-1": "fed_policy",
    }
    source_root = _write_manifest(
        tmp_path,
        export_id=export_id,
        market_categories=market_categories,
    )
    dataset_path = _write_dataset(
        tmp_path,
        export_id=export_id,
        market_categories=market_categories,
        rows_per_market=3,
    )

    result = run_category_balance_plan(
        dataset_path,
        category_report_path=_write_high_gap_report(tmp_path),
        source_export_root=source_root,
    )

    preferred = result.target_plans["preferred"]
    quotas = {
        category: target["target_market_count"]
        for category, target in preferred["category_targets"].items()
    }
    assert quotas == {
        "fed_policy": 30,
        "major_sports": 30,
        "public_event": 30,
        "weather": 30,
    }
    assert preferred["public_event_market_cap"] == 60
    assert preferred["meets_public_event_cap"] is True
    assert result.recommended_plan["tier"] == "preferred"


def test_small_category_warnings_generated(tmp_path: Path):
    export_id = "small_export"
    market_categories = {
        "PUBLIC-1": "public_event",
        "WEATHER-1": "weather",
    }
    source_root = _write_manifest(
        tmp_path,
        export_id=export_id,
        market_categories=market_categories,
    )
    dataset_path = _write_dataset(
        tmp_path,
        export_id=export_id,
        market_categories=market_categories,
        rows_per_market=1,
    )

    result = run_category_balance_plan(
        dataset_path,
        category_report_path=_write_high_gap_report(tmp_path),
        source_export_root=source_root,
    )

    weather = result.report["current_distribution"]["weather"]
    assert WARNING_SMALL_CATEGORY_SAMPLE in weather["warnings"]
    assert weather["sample_size_warning"] is True


def test_missing_category_metadata_handled_safely(tmp_path: Path):
    export_id = "missing_export"
    market_categories = {
        "MISSING-1": "public_event",
        "MISSING-2": "weather",
    }
    dataset_path = _write_dataset(
        tmp_path,
        export_id=export_id,
        market_categories=market_categories,
        rows_per_market=1,
    )

    result = run_category_balance_plan(
        dataset_path,
        category_report_path=tmp_path / "missing_report.md",
        source_export_root=tmp_path / "missing_source_root",
    )

    assert result.report["dataset"]["category_source_status"] == "missing"
    assert set(result.report["current_distribution"]) == {"missing"}
    assert (
        WARNING_CATEGORY_METADATA_MISSING
        in result.report["current_distribution"]["missing"]["warnings"]
    )
    assert result.report["guardrails"]["data_collection"] is False


def test_high_gap_share_loaded_from_pr_cal_6_markdown(tmp_path: Path):
    export_id = "high_gap_share_export"
    market_categories = {
        "PUBLIC-1": "public_event",
        "SPORTS-1": "major_sports",
    }
    source_root = _write_manifest(
        tmp_path,
        export_id=export_id,
        market_categories=market_categories,
    )
    dataset_path = _write_dataset(
        tmp_path,
        export_id=export_id,
        market_categories=market_categories,
        rows_per_market=1,
    )
    category_report = _write_high_gap_report(
        tmp_path,
        public_event_brier_share="80.000000%",
        major_sports_brier_share="20.000000%",
    )

    result = run_category_balance_plan(
        dataset_path,
        category_report_path=category_report,
        source_export_root=source_root,
    )

    assert (
        result.report["current_distribution"]["public_event"][
            "high_gap_bucket_brier_share"
        ]
        == 0.8
    )
    assert (
        result.report["current_distribution"]["major_sports"][
            "high_gap_bucket_brier_share"
        ]
        == 0.2
    )


def test_category_balance_plan_cli_writes_json_and_markdown(tmp_path: Path):
    export_id = "cli_export"
    market_categories = {
        "PUBLIC-1": "public_event",
        "SPORTS-1": "major_sports",
        "WEATHER-1": "weather",
    }
    source_root = _write_manifest(
        tmp_path,
        export_id=export_id,
        market_categories=market_categories,
    )
    dataset_path = _write_dataset(
        tmp_path,
        export_id=export_id,
        market_categories=market_categories,
        rows_per_market=2,
    )
    category_report = _write_high_gap_report(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "category-balance-plan",
            "--historical-file",
            str(dataset_path),
            "--output-dir",
            str(tmp_path / "reports"),
            "--category-report-path",
            str(category_report),
            "--source-export-root",
            str(source_root),
            "--docs-report-path",
            str(tmp_path / "docs" / "balance.md"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["recommended_plan_name"] == "preferred"
    assert payload["guardrails"]["calibration_planning_only"] is True
    assert payload["collector_constraints"]["do_not_implement_in_this_pr"] is True
    assert Path(payload["json_path"]).exists()
    assert Path(payload["markdown_path"]).exists()
    assert Path(payload["docs_markdown_path"]).exists()
    markdown = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "Kalshi Category Balance Plan" in markdown
    assert "Suggested Future Collector Constraints" in markdown


def test_category_balance_plan_adds_no_broker_live_or_order_api():
    source = inspect.getsource(category_balance_plan_module)
    tree = ast.parse(source)
    referenced_symbols = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    forbidden_symbols = {
        "PaperLedger",
        "PaperOrder",
        "PaperOrderIntent",
        "RiskEngine",
        "RiskGateEvaluator",
        "ExecutionMode.LIVE",
        "create_order",
        "open_position",
    }
    assert forbidden_symbols.isdisjoint(referenced_symbols)
    assert "local_market_agent.paper" not in source
    assert "local_market_agent.risk" not in source


def _write_manifest(
    tmp_path: Path,
    *,
    export_id: str,
    market_categories: dict[str, str],
) -> Path:
    source_root = tmp_path / "source_exports"
    export_dir = source_root / export_id
    export_dir.mkdir(parents=True)
    rows = [
        {
            "ticker": market_id,
            "title": f"Synthetic market {market_id}",
            "metadata": {
                "calibration_category": category,
            },
        }
        for market_id, category in market_categories.items()
    ]
    (export_dir / "markets.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    return source_root


def _write_dataset(
    tmp_path: Path,
    *,
    export_id: str,
    market_categories: dict[str, str],
    rows_per_market: int,
) -> Path:
    payloads = []
    for market_index, market_id in enumerate(market_categories, start=1):
        for row_index in range(1, rows_per_market + 1):
            absolute_index = len(payloads) + 1
            payloads.append(
                {
                    "dataset_id": "category_balance_fixture",
                    "row_id": f"row-{absolute_index}",
                    "timestamp": f"2026-05-{market_index:02d}T{row_index:02d}:00:00Z",
                    "market_id": market_id,
                    "title": f"Synthetic market {market_id}",
                    "platform": "kalshi",
                    "profile": "calibration_only_last_price",
                    "last_price": 0.25,
                    "implied_probability": 0.25,
                    "paper_pnl_allowed": False,
                    "acceptance_candidate": False,
                    "evidence": [],
                    "settlement": {
                        "outcome": "yes",
                        "ambiguous": False,
                    },
                    "metadata": {
                        "export_id": export_id,
                    },
                }
            )
    path = tmp_path / f"{export_id}.jsonl"
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in payloads) + "\n",
        encoding="utf-8",
    )
    return path


def _write_high_gap_report(
    tmp_path: Path,
    *,
    public_event_brier_share: str = "89.000000%",
    major_sports_brier_share: str = "11.000000%",
) -> Path:
    path = tmp_path / "category_report.md"
    path.write_text(
        "\n".join(
            [
                "# Synthetic PR-CAL-6 Report",
                "",
                "Category contribution to high-gap category buckets:",
                "",
                "| Category | High-gap rows | High-gap Brier loss sum | Row share | Brier share |",
                "| --- | ---: | ---: | ---: | ---: |",
                f"| `public_event` | 10 | 1.0 | 90.000000% | {public_event_brier_share} |",
                f"| `major_sports` | 1 | 0.1 | 10.000000% | {major_sports_brier_share} |",
                "",
                "## Next Section",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path
