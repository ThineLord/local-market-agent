from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

import local_market_agent.eval.normalized_availability_audit as audit_module
from local_market_agent.cli import app
from local_market_agent.eval.category_normalization import (
    NORMALIZED_ECONOMICS_OTHER,
    NORMALIZED_FED_POLICY_MACRO,
    NORMALIZED_MENTION_MARKET,
    NORMALIZED_SPORTS_TENNIS,
    NORMALIZED_UNKNOWN,
    NORMALIZED_WEATHER,
)
from local_market_agent.eval.normalized_availability_audit import (
    run_normalized_availability_audit,
    write_normalized_availability_audit_reports,
)


def test_offline_audit_works_with_synthetic_diagnostics(tmp_path: Path):
    export_dir = _write_export(tmp_path, diagnostics=_diagnostics())

    result = run_normalized_availability_audit(export_dir)
    report = result.as_dict()

    assert report["source_export"]["collector_diagnostics_status"] == (
        "loaded_from_export_json"
    )
    assert report["diagnostics_summary"]["discovered_count"] == 10
    assert report["guardrails"]["offline_by_default"] is True
    assert report["guardrails"]["network_used_only_when_probe_enabled"] is False
    assert report["probe"]["enabled"] is False


def test_weather_candidate_availability_and_shortfall_diagnosed(tmp_path: Path):
    diagnostics = _diagnostics(
        pre_filter={NORMALIZED_WEATHER: 12, NORMALIZED_SPORTS_TENNIS: 2},
        post_filter={NORMALIZED_WEATHER: 12, NORMALIZED_SPORTS_TENNIS: 2},
        selected={NORMALIZED_SPORTS_TENNIS: 2},
        quotas={NORMALIZED_WEATHER: 10, NORMALIZED_SPORTS_TENNIS: 2},
        shortfalls={NORMALIZED_WEATHER: 10},
        candle_attempts=20,
        candle_successes=2,
        candle_failures=18,
    )
    export_dir = _write_export(tmp_path, diagnostics=diagnostics)

    result = run_normalized_availability_audit(export_dir)
    weather = result.report["weather_availability_diagnosis"]

    assert weather["primary_diagnosis"] == "candle_sparsity_or_attempt_allocation"
    assert weather["post_filter_count"] == 12
    assert weather["quota_shortfall"] == 10
    assert weather["true_weather_source_scarcity_proven"] is False


def test_fed_macro_false_negative_candidates_surfaced_from_adjacent_categories(
    tmp_path: Path,
):
    export_dir = _write_export(
        tmp_path,
        diagnostics=_diagnostics(
            pre_filter={
                NORMALIZED_ECONOMICS_OTHER: 1,
                NORMALIZED_UNKNOWN: 1,
                NORMALIZED_FED_POLICY_MACRO: 0,
            },
            post_filter={
                NORMALIZED_ECONOMICS_OTHER: 1,
                NORMALIZED_UNKNOWN: 1,
                NORMALIZED_FED_POLICY_MACRO: 0,
            },
            selected={NORMALIZED_ECONOMICS_OTHER: 1, NORMALIZED_UNKNOWN: 1},
            quotas={NORMALIZED_FED_POLICY_MACRO: 2},
            shortfalls={NORMALIZED_FED_POLICY_MACRO: 2},
        ),
        markets=[
            _market(
                "KXJOBS-26MAY",
                NORMALIZED_ECONOMICS_OTHER,
                "Will unemployment be above 5% after the jobs report?",
            ),
            _market(
                "KXPCE-26MAY",
                NORMALIZED_UNKNOWN,
                "Will core PCE inflation be above forecast?",
            ),
        ],
    )

    result = run_normalized_availability_audit(export_dir)
    diagnosis = result.report["fed_macro_taxonomy_diagnosis"]
    false_negatives = result.report["fed_macro_false_negative_candidates"]

    assert diagnosis["primary_diagnosis"] == "taxonomy_false_negatives_supported"
    assert diagnosis["semantic_rule_gap_supported"] is True
    assert diagnosis["false_negative_candidate_count"] == 1
    assert diagnosis["macro_boundary_candidate_count"] == 2
    suggested = {
        item["ticker"]: item["suggested_normalized_category"]
        for item in false_negatives
    }
    assert suggested["KXPCE-26MAY"] == NORMALIZED_FED_POLICY_MACRO
    assert suggested["KXJOBS-26MAY"] == NORMALIZED_ECONOMICS_OTHER


def test_unselected_candidate_diagnostics_loaded_when_present(tmp_path: Path):
    export_dir = _write_export(
        tmp_path,
        diagnostics=_diagnostics(
            pre_filter={
                NORMALIZED_ECONOMICS_OTHER: 1,
                NORMALIZED_FED_POLICY_MACRO: 0,
                NORMALIZED_WEATHER: 1,
            },
            post_filter={
                NORMALIZED_ECONOMICS_OTHER: 1,
                NORMALIZED_FED_POLICY_MACRO: 0,
                NORMALIZED_WEATHER: 1,
            },
            selected={NORMALIZED_SPORTS_TENNIS: 1},
            quotas={NORMALIZED_FED_POLICY_MACRO: 1, NORMALIZED_WEATHER: 1},
            shortfalls={NORMALIZED_FED_POLICY_MACRO: 1, NORMALIZED_WEATHER: 1},
        ),
        unselected_candidates=[
            {
                "ticker": "KXFEDRATE-26MAY",
                "title": "Will the Federal Reserve announce a rate cut?",
                "source_category": "unknown",
                "normalized_category": NORMALIZED_UNKNOWN,
                "semantic_category": NORMALIZED_UNKNOWN,
                "warnings": [],
            },
            {
                "ticker": "KXRAIN-26MAY",
                "title": "Will New York City receive rain tomorrow?",
                "source_category": "weather",
                "normalized_category": NORMALIZED_WEATHER,
                "semantic_category": NORMALIZED_WEATHER,
                "warnings": [],
            },
        ],
    )

    result = run_normalized_availability_audit(export_dir)

    assert result.report["source_export"]["unselected_candidates_status"] == "loaded"
    assert result.report["unselected_candidate_summary"]["candidate_count"] == 2
    assert result.report["category_availability"][NORMALIZED_WEATHER][
        "unselected_example_count"
    ] == 1
    assert result.report["weather_candidate_examples"][0]["ticker"] == "KXRAIN-26MAY"
    fed = result.report["fed_macro_taxonomy_diagnosis"]
    assert fed["primary_diagnosis"] == "taxonomy_false_negatives_supported"
    assert fed["false_negative_candidate_count"] == 1


def test_per_category_weather_failures_drive_weather_diagnosis(tmp_path: Path):
    diagnostics = _diagnostics(
        pre_filter={NORMALIZED_WEATHER: 20},
        post_filter={NORMALIZED_WEATHER: 20},
        selected={},
        quotas={NORMALIZED_WEATHER: 10},
        shortfalls={NORMALIZED_WEATHER: 10},
        candle_attempts=20,
        candle_successes=0,
        candle_failures=20,
    )
    diagnostics["per_category"] = {
        NORMALIZED_WEATHER: {
            "candle_attempt_count": 20,
            "candle_success_count": 0,
            "candle_failure_count": 20,
            "candle_failure_reasons": {
                "insufficient_pre_settlement_last_price_candles": 20
            },
            "selected_market_count": 0,
            "selected_row_count": 0,
        }
    }
    diagnostics["per_category_candle_attempt_counts"] = {NORMALIZED_WEATHER: 20}
    diagnostics["per_category_candle_success_counts"] = {}
    diagnostics["per_category_candle_failure_counts"] = {NORMALIZED_WEATHER: 20}
    diagnostics["per_category_candle_failure_reasons"] = {
        NORMALIZED_WEATHER: {"insufficient_pre_settlement_last_price_candles": 20}
    }
    export_dir = _write_export(tmp_path, diagnostics=diagnostics)

    result = run_normalized_availability_audit(export_dir)
    weather = result.report["weather_availability_diagnosis"]

    assert weather["primary_diagnosis"] == (
        "weather_candle_sparsity_supported_by_per_category_diagnostics"
    )
    assert weather["per_category_failure_logs_available"] is True
    assert weather["weather_candle_attempt_count"] == 20
    assert weather["weather_candle_failure_reasons"] == {
        "insufficient_pre_settlement_last_price_candles": 20
    }


def test_fed_macro_absence_uses_retained_unselected_diagnostics(tmp_path: Path):
    export_dir = _write_export(
        tmp_path,
        diagnostics=_diagnostics(
            pre_filter={NORMALIZED_UNKNOWN: 2, NORMALIZED_FED_POLICY_MACRO: 0},
            post_filter={NORMALIZED_UNKNOWN: 2, NORMALIZED_FED_POLICY_MACRO: 0},
            selected={},
            quotas={NORMALIZED_FED_POLICY_MACRO: 1},
            shortfalls={NORMALIZED_FED_POLICY_MACRO: 1},
        ),
        unselected_candidates=[
            {
                "ticker": "KXUNKNOWN-26MAY",
                "title": "Will a local event happen next week?",
                "source_category": "unknown",
                "normalized_category": NORMALIZED_UNKNOWN,
                "semantic_category": NORMALIZED_UNKNOWN,
                "warnings": [],
            }
        ],
    )

    result = run_normalized_availability_audit(export_dir)
    fed = result.report["fed_macro_taxonomy_diagnosis"]

    assert fed["primary_diagnosis"] == (
        "fed_policy_candidates_absent_in_retained_diagnostics"
    )
    assert fed["source_scarcity_proven"] is False
    assert "unselected_candidate_examples_missing_warning" not in fed["warnings"]


def test_probe_mode_does_not_write_historical_dataset_rows(tmp_path: Path):
    export_dir = _write_export(tmp_path, diagnostics=_diagnostics())
    client = FakeProbeClient()

    result = run_normalized_availability_audit(
        export_dir,
        probe_candles=True,
        probe_category=NORMALIZED_WEATHER,
        probe_limit=1,
        probe_client=client,
    )
    artifacts = write_normalized_availability_audit_reports(
        result,
        tmp_path / "reports",
        docs_markdown_path=tmp_path / "docs" / "audit.md",
    )

    assert result.report["probe"]["network_used"] is True
    assert result.report["probe"]["historical_dataset_written"] is False
    assert result.report["probe"]["historical_rows_imported"] is False
    assert result.report["probe"]["successful_markets"] == 1
    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()
    assert not (tmp_path / "historical").exists()


def test_missing_diagnostics_handled_safely(tmp_path: Path):
    export_dir = _write_export(tmp_path, diagnostics=None, write_diagnostics=False)

    result = run_normalized_availability_audit(export_dir)

    assert result.report["source_export"]["collector_diagnostics_status"] == "missing"
    assert result.report["diagnostics_summary"]["warnings"] == [
        "collector_diagnostics_missing_warning"
    ]
    assert result.report["weather_availability_diagnosis"]["primary_diagnosis"] in {
        "no_weather_shortfall_detected",
        "unknown",
    }


def test_old_diagnostics_payload_without_per_category_fields_is_compatible(
    tmp_path: Path,
):
    export_dir = _write_export(tmp_path, diagnostics=_diagnostics())

    result = run_normalized_availability_audit(export_dir)

    assert result.report["diagnostics_summary"]["per_category"] == {}
    assert result.report["category_availability"][NORMALIZED_WEATHER][
        "per_category_diagnostics"
    ] == {}


def test_normalized_availability_audit_cli_writes_json_and_markdown(tmp_path: Path):
    export_dir = _write_export(tmp_path, diagnostics=_diagnostics())

    result = CliRunner().invoke(
        app,
        [
            "normalized-availability-audit",
            "--source-export-dir",
            str(export_dir),
            "--output-dir",
            str(tmp_path / "reports"),
            "--docs-report-path",
            str(tmp_path / "docs" / "availability.md"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["collector_diagnostics_status"] == "loaded_from_export_json"
    assert payload["weather_availability_diagnosis"]["quota_shortfall"] == 10
    assert payload["guardrails"]["historical_dataset_built"] is False
    assert Path(payload["json_path"]).exists()
    assert Path(payload["markdown_path"]).exists()
    assert Path(payload["docs_markdown_path"]).exists()
    markdown = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "Kalshi Normalized Availability Audit" in markdown
    assert "Weather Diagnosis" in markdown


def test_normalized_availability_audit_adds_no_broker_live_or_order_api():
    source = inspect.getsource(audit_module)
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
        "portfolio",
        "fills",
    }
    assert forbidden_symbols.isdisjoint(referenced_symbols)
    assert "local_market_agent.paper" not in source
    assert "local_market_agent.risk" not in source


class FakeProbeClient:
    def __init__(self) -> None:
        self.requested_urls: list[str] = []

    def get_json(self, path: str, params: dict[str, object]) -> dict[str, Any]:
        self.requested_urls.append(f"{path}?{params}")
        if path in {"/markets", "/historical/markets"}:
            return {
                "markets": [
                    {
                        "ticker": "KXNYCRAIN-26MAY",
                        "title": "Will New York City receive rain tomorrow?",
                        "status": "settled",
                        "market_type": "binary",
                        "result": "yes",
                        "open_time": "2026-05-01T00:00:00Z",
                        "settlement_ts": "2026-05-02T00:00:00Z",
                        "close_time": "2026-05-02T00:00:00Z",
                        "volume_fp": "1000",
                        "category": "weather",
                    }
                ],
                "cursor": None,
            }
        if path == "/markets/candlesticks":
            return {
                "markets": [
                    {
                        "market_ticker": "KXNYCRAIN-26MAY",
                        "candlesticks": [
                            {
                                "end_period_ts": f"2026-05-01T0{hour}:00:00Z",
                                "price": {"close_dollars": "0.50"},
                            }
                            for hour in range(4)
                        ],
                    }
                ]
            }
        raise AssertionError(f"unexpected probe path {path}")


def _write_export(
    tmp_path: Path,
    *,
    diagnostics: dict[str, object] | None,
    markets: list[dict[str, object]] | None = None,
    unselected_candidates: list[dict[str, object]] | None = None,
    write_diagnostics: bool = True,
) -> Path:
    export_dir = tmp_path / "source_exports" / "kalshi_normalized_synthetic"
    export_dir.mkdir(parents=True)
    selected_markets = markets or [
        _market(
            "KXWTAMATCH-26MAY",
            NORMALIZED_SPORTS_TENNIS,
            "Will a player win the professional tennis match?",
        ),
        _market(
            "KXFOXMENTION-26MAY-WEATHER",
            NORMALIZED_MENTION_MARKET,
            "What will a senator say during a TV appearance?",
        ),
    ]
    (export_dir / "markets.jsonl").write_text(
        "\n".join(json.dumps(market, sort_keys=True) for market in selected_markets)
        + "\n",
        encoding="utf-8",
    )
    candles = [
        {
            "market_ticker": str(market["ticker"]),
            "end_period_ts": "2026-05-01T00:00:00Z",
            "price": {"close_dollars": "0.50"},
            "metadata": {"normalized_category": _metadata_category(market)},
        }
        for market in selected_markets
    ]
    (export_dir / "candlesticks.jsonl").write_text(
        "\n".join(json.dumps(candle, sort_keys=True) for candle in candles) + "\n",
        encoding="utf-8",
    )
    (export_dir / "evidence.jsonl").write_text("", encoding="utf-8")
    if unselected_candidates is not None:
        (export_dir / "unselected_candidates.jsonl").write_text(
            "\n".join(
                json.dumps(candidate, sort_keys=True)
                for candidate in unselected_candidates
            )
            + "\n",
            encoding="utf-8",
        )
        (export_dir / "unselected_candidates_summary.md").write_text(
            "# synthetic unselected diagnostics\n",
            encoding="utf-8",
        )
    manifest = {
        "export_id": "kalshi_normalized_synthetic",
        "collection_summary": {
            "discovered_count": 10,
            "selected_count": len(selected_markets),
            "candle_count": len(candles),
            "quotas": (diagnostics or {}).get("quota_targets", {}),
            "availability_limitations": [],
            "target_status": "minimum_size_availability_limited",
        },
        "collector_diagnostics": diagnostics or {},
        "safety": {
            "evidence_collected": False,
            "acceptance_claim": False,
        },
    }
    (export_dir / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if write_diagnostics and diagnostics is not None:
        (export_dir / "collector_diagnostics.json").write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return export_dir


def _diagnostics(
    *,
    pre_filter: dict[str, int] | None = None,
    post_filter: dict[str, int] | None = None,
    selected: dict[str, int] | None = None,
    quotas: dict[str, int] | None = None,
    shortfalls: dict[str, int] | None = None,
    candle_attempts: int = 10,
    candle_successes: int = 2,
    candle_failures: int = 8,
) -> dict[str, object]:
    pre = pre_filter or {NORMALIZED_WEATHER: 12, NORMALIZED_SPORTS_TENNIS: 2}
    post = post_filter or {NORMALIZED_WEATHER: 12, NORMALIZED_SPORTS_TENNIS: 2}
    selected_counts = selected or {NORMALIZED_SPORTS_TENNIS: 2}
    quota_targets = quotas or {NORMALIZED_WEATHER: 10, NORMALIZED_SPORTS_TENNIS: 2}
    quota_shortfalls = shortfalls or {NORMALIZED_WEATHER: 10}
    return {
        "discovered_count": 10,
        "pre_filter_category_counts": pre,
        "post_filter_category_counts": post,
        "selected_category_counts": selected_counts,
        "quota_targets": quota_targets,
        "quota_filled": selected_counts,
        "quota_shortfalls": quota_shortfalls,
        "candle_attempt_count": candle_attempts,
        "candle_success_count": candle_successes,
        "candle_failure_count": candle_failures,
        "candle_failure_reasons": {
            "insufficient_pre_settlement_last_price_candles": candle_failures
        },
        "filter_losses": {
            "unresolved_loss": 0,
            "not_finalized_loss": 0,
            "non_binary_loss": 0,
        },
        "availability_limitations": [
            {
                "category": category,
                "quota_target": quota_targets.get(category, 0),
                "quota_filled": selected_counts.get(category, 0),
                "missing_count": missing,
                "classification": "available_source_limitation",
                "reasons": ["selected_count_below_quota", "candle_failures_observed"],
                "not_a_true_category_effect": True,
            }
            for category, missing in quota_shortfalls.items()
        ],
    }


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
            "normalized_category": category,
            "semantic_category": category,
            "market_type": "binary",
            "source_family": "synthetic",
        },
    }


def _metadata_category(market: dict[str, object]) -> str:
    metadata = market.get("metadata")
    if isinstance(metadata, dict):
        return str(metadata.get("normalized_category"))
    return "unknown"
