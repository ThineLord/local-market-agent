from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from typer.testing import CliRunner

import local_market_agent.eval.category_calibration as category_calibration_module
from local_market_agent.cli import app
from local_market_agent.eval.category_calibration import (
    CATEGORY_MISSING,
    WARNING_NON_PUBLIC_EVENT_SPARSE,
    WARNING_PUBLIC_EVENT_DOMINANCE,
    WARNING_SMALL_CATEGORY_SAMPLE,
    run_category_calibration_analysis,
)


def test_category_enrichment_from_synthetic_manifest_works(tmp_path: Path):
    export_id = "synthetic_export"
    source_root = _write_manifest(
        tmp_path,
        export_id=export_id,
        market_categories={
            "MKT-PUBLIC": "public_event",
            "MKT-WEATHER": "weather",
        },
    )
    dataset_path = _write_dataset(
        tmp_path,
        export_id=export_id,
        rows=[
            ("MKT-PUBLIC", 0.25, "yes"),
            ("MKT-WEATHER", 0.75, "no"),
        ],
    )

    result = run_category_calibration_analysis(
        dataset_path,
        source_export_root=source_root,
    )

    assert result.report["dataset"]["category_source_status"] == "loaded"
    assert result.report["dataset"]["category_market_distribution"] == {
        "public_event": 1,
        "weather": 1,
    }
    assert result.category_reports["public_event"]["row_count"] == 1
    assert result.category_reports["weather"]["row_count"] == 1


def test_missing_category_manifest_is_handled_safely(tmp_path: Path):
    dataset_path = _write_dataset(
        tmp_path,
        export_id="missing_export",
        rows=[("MKT-A", 0.25, "yes"), ("MKT-B", 0.75, "no")],
    )

    result = run_category_calibration_analysis(
        dataset_path,
        source_export_root=tmp_path / "source_exports",
    )

    assert result.report["dataset"]["category_source_status"] == "missing"
    assert result.report["dataset"]["category_missing_row_count"] == 2
    assert set(result.category_reports) == {CATEGORY_MISSING}
    assert result.category_reports[CATEGORY_MISSING]["row_count"] == 2


def test_public_event_dominance_detected(tmp_path: Path):
    export_id = "dominance_export"
    market_categories = {
        **{f"MKT-PUBLIC-{index}": "public_event" for index in range(8)},
        "MKT-WEATHER": "weather",
        "MKT-SPORTS": "major_sports",
    }
    source_root = _write_manifest(
        tmp_path,
        export_id=export_id,
        market_categories=market_categories,
    )
    rows = [
        (market_id, 0.25, "yes")
        for market_id in market_categories
    ]
    dataset_path = _write_dataset(tmp_path, export_id=export_id, rows=rows)

    result = run_category_calibration_analysis(
        dataset_path,
        source_export_root=source_root,
    )

    assert result.comparison["public_event_dominance_detected"] is True
    assert WARNING_PUBLIC_EVENT_DOMINANCE in result.comparison["warnings"]
    assert WARNING_PUBLIC_EVENT_DOMINANCE in result.category_reports["public_event"]["warnings"]


def test_category_level_brier_and_log_loss_are_correct(tmp_path: Path):
    export_id = "metric_export"
    source_root = _write_manifest(
        tmp_path,
        export_id=export_id,
        market_categories={"MKT-A": "public_event", "MKT-B": "public_event"},
    )
    dataset_path = _write_dataset(
        tmp_path,
        export_id=export_id,
        rows=[
            ("MKT-A", 0.25, "yes"),
            ("MKT-B", 0.75, "no"),
        ],
    )

    result = run_category_calibration_analysis(
        dataset_path,
        source_export_root=source_root,
    )

    public_event = result.category_reports["public_event"]
    assert public_event["brier_score"] == 0.5625
    assert public_event["log_loss"] == 1.38629436
    assert public_event["brier_loss_sum"] == 1.125
    assert public_event["absolute_calibration_gap"] == 0.0


def test_high_gap_category_bucket_detected(tmp_path: Path):
    export_id = "high_gap_export"
    source_root = _write_manifest(
        tmp_path,
        export_id=export_id,
        market_categories={f"MKT-{index}": "weather" for index in range(10)},
    )
    dataset_path = _write_dataset(
        tmp_path,
        export_id=export_id,
        rows=[(f"MKT-{index}", 0.25, "yes") for index in range(10)],
    )

    result = run_category_calibration_analysis(
        dataset_path,
        source_export_root=source_root,
        gap_threshold=0.15,
    )

    weather = result.category_reports["weather"]
    assert [bucket["bucket"] for bucket in weather["high_gap_buckets"]] == ["0.20-0.30"]
    assert weather["high_gap_buckets"][0]["absolute_calibration_gap"] == 0.75
    assert weather["high_gap_bucket_brier_loss_contribution_share"] == 1.0


def test_small_category_warning_emitted(tmp_path: Path):
    export_id = "small_export"
    source_root = _write_manifest(
        tmp_path,
        export_id=export_id,
        market_categories={"MKT-SMALL": "fed_policy"},
    )
    dataset_path = _write_dataset(
        tmp_path,
        export_id=export_id,
        rows=[("MKT-SMALL", 0.55, "yes")],
    )

    result = run_category_calibration_analysis(
        dataset_path,
        source_export_root=source_root,
    )

    assert WARNING_SMALL_CATEGORY_SAMPLE in result.category_reports["fed_policy"]["warnings"]
    assert WARNING_NON_PUBLIC_EVENT_SPARSE in result.comparison["warnings"]


def test_category_calibration_cli_writes_json_and_markdown(tmp_path: Path):
    export_id = "cli_export"
    source_root = _write_manifest(
        tmp_path,
        export_id=export_id,
        market_categories={"MKT-A": "public_event", "MKT-B": "weather"},
    )
    dataset_path = _write_dataset(
        tmp_path,
        export_id=export_id,
        rows=[("MKT-A", 0.25, "yes"), ("MKT-B", 0.75, "no")],
    )

    result = CliRunner().invoke(
        app,
        [
            "category-calibration-analysis",
            "--historical-file",
            str(dataset_path),
            "--output-dir",
            str(tmp_path / "reports"),
            "--source-export-root",
            str(source_root),
            "--docs-report-path",
            str(tmp_path / "docs" / "category.md"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["category_market_distribution"] == {"public_event": 1, "weather": 1}
    assert payload["guardrails"]["calibration_qa_only"] is True
    assert Path(payload["json_path"]).exists()
    assert Path(payload["markdown_path"]).exists()
    assert Path(payload["docs_markdown_path"]).exists()
    markdown = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "Kalshi Category Calibration Analysis" in markdown
    assert "Strategy v2 superiority" in markdown


def test_category_calibration_adds_no_broker_live_or_order_api():
    source = inspect.getsource(category_calibration_module)
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
    rows: list[tuple[str, float, str]],
) -> Path:
    payloads = []
    for index, (market_id, probability, outcome) in enumerate(rows, start=1):
        payloads.append(
            {
                "dataset_id": "category_calibration_fixture",
                "row_id": f"row-{index}",
                "timestamp": f"2026-05-01T{index:02d}:00:00Z",
                "market_id": market_id,
                "title": f"Synthetic market {market_id}",
                "platform": "kalshi",
                "profile": "calibration_only_last_price",
                "last_price": probability,
                "implied_probability": probability,
                "paper_pnl_allowed": False,
                "acceptance_candidate": False,
                "evidence": [],
                "settlement": {
                    "outcome": outcome,
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
