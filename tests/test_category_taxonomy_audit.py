from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from typer.testing import CliRunner

import local_market_agent.eval.category_taxonomy_audit as taxonomy_audit_module
from local_market_agent.cli import app
from local_market_agent.eval.category_taxonomy_audit import (
    WARNING_CANDLE_ATTEMPT_LOGS_MISSING,
    WARNING_FED_MACRO_ASSIGNED_ELSEWHERE,
    WARNING_FILTER_COUNTS_MISSING,
    WARNING_SOURCE_LOGS_MISSING,
    WARNING_SPORTS_ASSIGNED_TO_WEATHER_OR_FED,
    WARNING_WEATHER_ASSIGNED_ELSEWHERE,
    run_category_taxonomy_audit,
)


def test_detects_tennis_market_misclassified_as_weather_or_fed_policy(tmp_path: Path):
    export_dir = _write_export(
        tmp_path,
        markets=[
            _market(
                "KXWTAMATCH-26APR07VOLVEK-VEK",
                "weather",
                "Will Donna Vekic win the Volynets vs Vekic professional tennis match?",
            ),
            _market(
                "KXATPCHALLENGERMATCH-26APR07JONSEK-JON",
                "fed_policy",
                "Will Maximus Jones win the Jones vs Sekulic professional tennis match?",
            ),
        ],
    )
    historical_path = _write_historical(tmp_path, export_dir)

    result = run_category_taxonomy_audit(
        export_dir,
        historical_path,
        reference_export_dir=None,
    )

    checks = result.report["taxonomy_checks"]
    assert checks["sports_assigned_to_weather_or_fed_count"] == 2
    assert checks["suspected_category_mismatch_count"] == 2
    assert all(
        WARNING_SPORTS_ASSIGNED_TO_WEATHER_OR_FED in item["warnings"]
        for item in checks["sports_assigned_to_weather_or_fed"]
    )
    assert result.report["availability_diagnosis"]["taxonomy_mismatch"][
        "status"
    ] == "supported"


def test_detects_fed_macro_looking_market(tmp_path: Path):
    export_dir = _write_export(
        tmp_path,
        markets=[
            _market(
                "KXFOMCDECISION-26MAY-RATECUT",
                "public_event",
                "Will the Fed cut interest rates after the FOMC meeting?",
            )
        ],
    )
    historical_path = _write_historical(tmp_path, export_dir)

    result = run_category_taxonomy_audit(
        export_dir,
        historical_path,
        reference_export_dir=None,
    )

    checks = result.report["taxonomy_checks"]
    assert checks["fed_macro_assigned_elsewhere_count"] == 1
    assert WARNING_FED_MACRO_ASSIGNED_ELSEWHERE in checks[
        "fed_macro_assigned_elsewhere"
    ][0]["warnings"]


def test_detects_weather_looking_market(tmp_path: Path):
    export_dir = _write_export(
        tmp_path,
        markets=[
            _market(
                "KXNYCRAIN-26MAY",
                "public_event",
                "Will New York City receive rain tomorrow?",
            )
        ],
    )
    historical_path = _write_historical(tmp_path, export_dir)

    result = run_category_taxonomy_audit(
        export_dir,
        historical_path,
        reference_export_dir=None,
    )

    checks = result.report["taxonomy_checks"]
    assert checks["weather_assigned_elsewhere_count"] == 1
    assert WARNING_WEATHER_ASSIGNED_ELSEWHERE in checks["weather_assigned_elsewhere"][0][
        "warnings"
    ]


def test_handles_missing_source_logs_safely(tmp_path: Path):
    export_dir = _write_export(
        tmp_path,
        markets=[
            _market(
                "KXWEATHER-26MAY",
                "weather",
                "Will the high temperature exceed 80 degrees?",
            )
        ],
        write_manifest=False,
        write_candles=False,
    )
    historical_path = _write_historical(tmp_path, export_dir)

    result = run_category_taxonomy_audit(
        export_dir,
        historical_path,
        reference_export_dir=None,
    )

    source = result.report["source_export"]
    warnings = result.report["availability_diagnosis"]["warnings"]
    assert source["manifest_status"] == "missing"
    assert source["candlesticks_status"] == "missing"
    assert WARNING_SOURCE_LOGS_MISSING in warnings
    assert WARNING_FILTER_COUNTS_MISSING in warnings
    assert WARNING_CANDLE_ATTEMPT_LOGS_MISSING in warnings
    assert result.guardrails["data_collection"] is False


def test_distinguishes_source_scarcity_from_taxonomy_mismatch(tmp_path: Path):
    scarce_export = _write_export(
        tmp_path / "scarce",
        markets=[
            _market(
                "KXSEATTLEWEATHER-26MAY",
                "weather",
                "Will Seattle receive rain tomorrow?",
            )
        ],
        manifest_summary={
            "quotas": {"weather": 5},
            "category_counts": {"weather": 1},
            "candidate_category_counts": {"weather": 1},
            "target_markets": 5,
            "rows_per_market": 2,
        },
    )
    scarce_history = _write_historical(tmp_path / "scarce", scarce_export)

    scarce = run_category_taxonomy_audit(
        scarce_export,
        scarce_history,
        reference_export_dir=None,
    )

    assert scarce.report["availability_diagnosis"]["primary_blocker"] == "source_scarcity"
    assert scarce.report["availability_diagnosis"]["true_source_scarcity"][
        "status"
    ] == "supported_by_candidate_category_counts"

    mismatch_export = _write_export(
        tmp_path / "mismatch",
        markets=[
            _market(
                "KXWTAMATCH-26APR07VOLVEK-VEK",
                "weather",
                "Will Donna Vekic win the Volynets vs Vekic professional tennis match?",
            )
        ],
        manifest_summary={
            "quotas": {"weather": 5},
            "category_counts": {"weather": 1},
            "candidate_category_counts": {"weather": 1},
            "target_markets": 5,
            "rows_per_market": 2,
        },
    )
    mismatch_history = _write_historical(tmp_path / "mismatch", mismatch_export)

    mismatch = run_category_taxonomy_audit(
        mismatch_export,
        mismatch_history,
        reference_export_dir=None,
    )

    assert (
        mismatch.report["availability_diagnosis"]["primary_blocker"]
        == "taxonomy_mismatch_or_keyword_mapping"
    )
    assert mismatch.report["availability_diagnosis"]["true_source_scarcity"][
        "status"
    ] == "not_proven_taxonomy_mismatch_present"


def test_category_taxonomy_audit_cli_writes_json_and_markdown(tmp_path: Path):
    export_dir = _write_export(
        tmp_path,
        markets=[
            _market(
                "KXFOMCDECISION-26MAY-RATECUT",
                "public_event",
                "Will the Fed cut interest rates after the FOMC meeting?",
            )
        ],
    )
    historical_path = _write_historical(tmp_path, export_dir)

    result = CliRunner().invoke(
        app,
        [
            "category-taxonomy-audit",
            "--source-export-dir",
            str(export_dir),
            "--historical-file",
            str(historical_path),
            "--output-dir",
            str(tmp_path / "reports"),
            "--reference-export-dir",
            str(tmp_path / "missing-reference"),
            "--docs-report-path",
            str(tmp_path / "docs" / "taxonomy.md"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["export_id"] == "synthetic_taxonomy_export"
    assert payload["suspected_category_mismatch_count"] == 1
    assert payload["guardrails"]["calibration_taxonomy_audit_only"] is True
    assert Path(payload["json_path"]).exists()
    assert Path(payload["markdown_path"]).exists()
    assert Path(payload["docs_markdown_path"]).exists()
    markdown = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "Kalshi Category Taxonomy And Source Availability Audit" in markdown
    assert "Availability Diagnosis" in markdown


def test_category_taxonomy_audit_adds_no_broker_live_or_order_api():
    source = inspect.getsource(taxonomy_audit_module)
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


def _write_export(
    tmp_path: Path,
    *,
    markets: list[dict[str, object]],
    manifest_summary: dict[str, object] | None = None,
    write_manifest: bool = True,
    write_candles: bool = True,
) -> Path:
    export_dir = tmp_path / "source_exports" / "synthetic_taxonomy_export"
    export_dir.mkdir(parents=True)
    (export_dir / "markets.jsonl").write_text(
        "\n".join(json.dumps(market, sort_keys=True) for market in markets) + "\n",
        encoding="utf-8",
    )
    if write_candles:
        candle_rows = []
        for market in markets:
            ticker = str(market["ticker"])
            category = str(market["metadata"]["calibration_category"])
            for index in range(2):
                candle_rows.append(
                    {
                        "market_ticker": ticker,
                        "end_period_ts": f"2026-05-01T0{index}:00:00Z",
                        "period_interval": 60,
                        "price": {"close_dollars": "0.5000"},
                        "metadata": {"market_category": category},
                    }
                )
        (export_dir / "candlesticks.jsonl").write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in candle_rows) + "\n",
            encoding="utf-8",
        )
    if write_manifest:
        summary = {
            "discovered_count": len(markets),
            "selected_count": len(markets),
            "candle_count": len(markets) * 2 if write_candles else 0,
            "target_markets": len(markets),
            "rows_per_market": 2,
            "quotas": {},
            "category_counts": {},
            "availability_limitations": [],
            "target_status": "synthetic",
        }
        if manifest_summary:
            summary.update(manifest_summary)
        manifest = {
            "export_id": "synthetic_taxonomy_export",
            "collection_summary": summary,
        }
        (export_dir / "source_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return export_dir


def _write_historical(tmp_path: Path, export_dir: Path) -> Path:
    markets = [
        json.loads(line)
        for line in (export_dir / "markets.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = []
    for market in markets:
        for index in range(2):
            rows.append(
                {
                    "dataset_id": "synthetic_taxonomy_dataset",
                    "row_id": f"{market['ticker']}-{index}",
                    "timestamp": f"2026-05-01T0{index}:00:00Z",
                    "market_id": market["ticker"],
                    "title": market["title"],
                    "platform": "kalshi",
                    "profile": "calibration_only_last_price",
                    "last_price": 0.5,
                    "implied_probability": 0.5,
                    "paper_pnl_allowed": False,
                    "acceptance_candidate": False,
                    "evidence": [],
                    "settlement": {"outcome": "yes", "ambiguous": False},
                    "metadata": {"export_id": "synthetic_taxonomy_export"},
                }
            )
    historical_path = tmp_path / "historical.jsonl"
    historical_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    return historical_path


def _market(ticker: str, category: str, title: str) -> dict[str, object]:
    return {
        "ticker": ticker,
        "event_ticker": ticker.rsplit("-", maxsplit=1)[0],
        "series_ticker": ticker.split("-", maxsplit=1)[0],
        "title": title,
        "rules_primary": title,
        "status": "finalized",
        "market_type": "binary",
        "metadata": {
            "calibration_category": category,
            "market_type": "binary",
            "source_family": "synthetic",
        },
    }
