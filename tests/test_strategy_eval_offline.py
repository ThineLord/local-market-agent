from __future__ import annotations

import ast
import copy
import inspect
import json
from pathlib import Path

from typer.testing import CliRunner

import local_market_agent.eval.offline_strategy as offline_strategy_module
import local_market_agent.operations.phase7_daily as phase7_daily_module
from local_market_agent.cli import app
from local_market_agent.eval.offline_strategy import (
    REQUIRED_BASELINES,
    evaluate_strategy_acceptance_gate,
    run_strategy_offline_evaluation,
)

HISTORICAL_FIXTURE = Path("data/fixtures/phase7_historical_5d.jsonl")


def test_strategy_eval_offline_evaluates_5_day_historical_fixture(tmp_path):
    result = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path,
    )

    assert result.json_path.exists()
    assert result.markdown_path.exists()
    assert result.report["dataset"]["evaluated_rows"] == 5
    assert result.report["dataset"]["markets_evaluated"] == 1
    assert result.report["dataset"]["classification"] == "fixture_smoke"
    assert set(result.report["baselines"]) == set(REQUIRED_BASELINES)

    payload = json.loads(result.json_path.read_text())
    assert payload["report_id"] == result.report["report_id"]
    assert "Strategy Offline Evaluation Report" in result.markdown_path.read_text()


def test_strategy_eval_offline_produces_required_baseline_metric_sections(tmp_path):
    result = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path,
    )

    for baseline_name in REQUIRED_BASELINES:
        baseline = result.report["baselines"][baseline_name]
        assert len(baseline["rows"]) == 5
        assert set(baseline["metrics"]) == {
            "activity",
            "forecast",
            "paper_outcome",
            "risk_reliability",
        }
        assert baseline["metrics"]["activity"]["evaluated_rows"] == 5


def test_strategy_eval_offline_computes_brier_score_and_calibration_buckets(tmp_path):
    result = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path,
    )
    strategy_metrics = result.report["baselines"]["strategy_v1"]["metrics"]
    market_metrics = result.report["baselines"]["market_implied_probability_only"][
        "metrics"
    ]

    assert strategy_metrics["forecast"]["brier_score"] == 0.07827957
    assert market_metrics["forecast"]["brier_score"] == 0.18344
    assert strategy_metrics["forecast"]["structured_probability_completeness_rate"] == 1.0

    buckets = strategy_metrics["forecast"]["calibration_by_bucket"]
    assert buckets["0.60-0.70"]["row_count"] == 3
    assert buckets["0.70-0.80"]["row_count"] == 1
    assert buckets["0.80-0.90"]["row_count"] == 1


def test_strategy_eval_offline_computes_abstention_rate_and_below_target_label(
    tmp_path,
):
    result = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path,
    )
    report = result.report

    assert report["baselines"]["always_observe"]["metrics"]["activity"][
        "abstention_rate"
    ] == 1.0
    assert report["baselines"]["strategy_v1"]["metrics"]["activity"][
        "abstention_rate"
    ] == 0.2
    assert "below sample-size target" in report["dataset"]["classification_detail"]
    assert report["dataset"]["sample_size_gates"]["evaluation_rows"]["passed"] is False
    assert report["dataset"]["sample_size_gates"]["resolved_binary_markets"][
        "passed"
    ] is False
    assert report["dataset"]["superiority_claim_allowed"] is False


def test_strategy_eval_fixture_gate_blocks_superiority_claim(tmp_path):
    result = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path,
    )
    gate = result.report["acceptance_gate"]

    assert gate["gate_status"] == "not_applicable"
    assert gate["superiority_claim_allowed"] is False
    assert gate["dataset_label"] == "fixture_smoke"
    assert "dataset.evaluation_rows" in gate["failed_gates"]
    assert "dataset.resolved_binary_markets" in gate["failed_gates"]


def test_strategy_eval_missing_settlement_blocks_acceptance(tmp_path):
    dataset_path = _dataset_without_settlement(tmp_path)

    result = run_strategy_offline_evaluation(
        historical_file=dataset_path,
        output_dir=tmp_path / "reports",
    )
    gate = result.report["acceptance_gate"]

    assert result.report["dataset"]["classification"] == (
        "historical_local_dataset_without_settlement"
    )
    assert gate["gate_status"] == "not_applicable"
    assert gate["superiority_claim_allowed"] is False
    assert "dataset.settlement_coverage_pct" in gate["failed_gates"]


def test_strategy_eval_insufficient_sample_size_blocks_acceptance(tmp_path):
    result = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path,
    )
    gate = result.report["acceptance_gate"]

    assert gate["gate_status"] == "not_applicable"
    assert gate["superiority_claim_allowed"] is False
    assert any(name.startswith("dataset.") for name in gate["failed_gates"])


def test_strategy_eval_strategy_v2_not_better_than_v1_fails_gate(tmp_path):
    result = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path,
    )
    dataset_summary = _eligible_dataset_summary(result.report)
    baselines = copy.deepcopy(result.report["baselines"])
    baselines["strategy_v2_candidate"]["metrics"]["forecast"]["brier_score"] = (
        baselines["strategy_v1"]["metrics"]["forecast"]["brier_score"] + 0.05
    )

    gate = evaluate_strategy_acceptance_gate(
        dataset_summary=dataset_summary,
        baselines=baselines,
        safety=result.report["safety"],
    )

    assert gate["gate_status"] == "fail"
    assert gate["superiority_claim_allowed"] is False
    assert "forecast.brier_score_not_better_than_strategy_v1" in gate["failed_gates"]


def test_strategy_eval_safety_placeholder_failure_blocks_gate(tmp_path):
    result = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path,
    )
    safety = copy.deepcopy(result.report["safety"])
    safety["can_create_orders"] = True

    gate = evaluate_strategy_acceptance_gate(
        dataset_summary=_eligible_dataset_summary(result.report),
        baselines=result.report["baselines"],
        safety=safety,
    )

    assert gate["gate_status"] == "fail"
    assert gate["superiority_claim_allowed"] is False
    assert "safety.can_create_orders" in gate["failed_gates"]


def test_strategy_eval_markdown_report_includes_gate_verdict(tmp_path):
    result = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path,
    )
    markdown = result.markdown_path.read_text()

    assert "## Strategy v2 Acceptance Gate" in markdown
    assert "Gate status: `not_applicable`" in markdown
    assert "Superiority claims allowed: False" in markdown


def test_strategy_eval_json_report_includes_gate_fields(tmp_path):
    result = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path,
    )
    payload = json.loads(result.json_path.read_text())
    gate = payload["acceptance_gate"]

    assert gate["gate_status"] == "not_applicable"
    assert gate["superiority_claim_allowed"] is False
    assert gate["dataset_label"] == "fixture_smoke"
    assert "failed_gates" in gate
    assert "warning_gates" in gate
    assert "metric_deltas" in gate
    assert "strategy_v1_summary" in gate
    assert "strategy_v2_summary" in gate
    assert "baseline_summaries" in gate
    assert "recommendation" in gate


def test_strategy_eval_offline_random_baseline_is_fixed_seed_deterministic(tmp_path):
    first = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path / "first",
        random_seed=12345,
    )
    second = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path / "second",
        random_seed=12345,
    )

    first_rows = first.report["baselines"]["random_naive_policy"]["rows"]
    second_rows = second.report["baselines"]["random_naive_policy"]["rows"]
    assert [row["action"] for row in first_rows] == [
        row["action"] for row in second_rows
    ]
    assert [row["forecast_probability"] for row in first_rows] == [
        row["forecast_probability"] for row in second_rows
    ]


def test_strategy_eval_offline_cli_writes_json_and_markdown_reports(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "strategy-eval-offline",
            "--historical-file",
            str(HISTORICAL_FIXTURE),
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dataset_classification"] == "fixture_smoke"
    assert payload["gate_status"] == "not_applicable"
    assert payload["superiority_claim_allowed"] is False
    assert "dataset.evaluation_rows" in payload["failed_gates"]
    assert set(payload["baselines"]) == set(REQUIRED_BASELINES)
    assert Path(payload["json_path"]).exists()
    assert Path(payload["markdown_path"]).exists()


def test_strategy_eval_calibration_only_last_price_blocks_acceptance_and_pnl(tmp_path):
    dataset_path = _calibration_only_last_price_dataset(tmp_path)

    result = run_strategy_offline_evaluation(
        historical_file=dataset_path,
        output_dir=tmp_path / "reports",
    )

    assert result.json_path.exists()
    assert result.markdown_path.exists()

    dataset = result.report["dataset"]
    gate = result.report["acceptance_gate"]
    assert dataset["classification"] == "calibration_only_last_price_dataset"
    assert dataset["evaluated_rows"] == 4
    assert dataset["markets_evaluated"] == 2
    assert dataset["bid_ask_coverage_pct"] == 0.0
    assert dataset["last_price_coverage_pct"] == 1.0
    assert dataset["paper_pnl_allowed_row_count"] == 0
    assert dataset["acceptance_candidate_row_count"] == 0
    assert dataset["paper_pnl_interpretation"] == "blocked"
    assert dataset["acceptance_evaluation_eligible"] is False
    assert dataset["acceptance_gate_pass"] is False

    assert gate["gate_status"] == "not_applicable"
    assert gate["superiority_claim_allowed"] is False
    assert gate["dataset_label"] == "calibration_only_last_price_dataset"
    assert "dataset.closed_paper_trades" in gate["failed_gates"]
    assert "dataset.evidence_timestamp_coverage_pct" in gate["failed_gates"]

    assert result.report["paper_fill_assumptions"]["paper_pnl_interpretation"] == "blocked"
    assert result.report["paper_fill_assumptions"]["paper_pnl_claim_allowed"] is False
    assert result.report["paper_fill_assumptions"][
        "calibration_only_last_price_mode"
    ] is True

    for baseline in result.report["baselines"].values():
        paper = baseline["metrics"]["paper_outcome"]
        assert paper["paper_pnl_interpretation"] == "blocked"
        assert paper["paper_pnl_claim_allowed"] is False
        assert paper["realized_paper_pnl"] == 0


def test_strategy_v2_appears_in_offline_evaluation_report(tmp_path):
    result = run_strategy_offline_evaluation(
        historical_file=HISTORICAL_FIXTURE,
        output_dir=tmp_path,
    )
    report = result.report

    assert "strategy_v2_candidate" in report["baselines"]
    assert report["baselines"]["strategy_v2_candidate"]["metrics"]["activity"][
        "evaluated_rows"
    ] == 5
    assert report["safety"]["strategy_v2_candidate_policy_included"] is True
    assert report["safety"]["strategy_v2_production_enabled"] is False


def test_strategy_v2_is_not_used_by_phase7_daily_runner():
    source = inspect.getsource(phase7_daily_module)

    assert "PredictionMarketV2CandidateStrategy" not in source
    assert "prediction_market_v2" not in source
    assert "strategy_v2_candidate" not in source


def test_strategy_eval_offline_adds_no_broker_live_or_order_apis():
    source = inspect.getsource(offline_strategy_module)
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
    assert "broker" not in source.lower()


def _dataset_without_settlement(tmp_path: Path) -> Path:
    rows = []
    for line in HISTORICAL_FIXTURE.read_text().splitlines()[:2]:
        payload = json.loads(line)
        payload.pop("settlement_outcome", None)
        rows.append(json.dumps(payload, sort_keys=True))
    path = tmp_path / "historical_without_settlement.jsonl"
    path.write_text("\n".join(rows) + "\n")
    return path


def _calibration_only_last_price_dataset(tmp_path: Path) -> Path:
    rows = []
    for market_index in range(2):
        for row_index in range(2):
            price = round(0.35 + (0.1 * market_index) + (0.05 * row_index), 4)
            rows.append(
                json.dumps(
                    {
                        "timestamp": (
                            f"2026-05-0{market_index + 1}T1{row_index}:00:00Z"
                        ),
                        "market_id": f"calibration-market-{market_index}",
                        "profile": "calibration_only_last_price",
                        "bid": None,
                        "ask": None,
                        "last_price": price,
                        "implied_probability": price,
                        "paper_pnl_allowed": False,
                        "acceptance_candidate": False,
                        "settlement_outcome": "yes"
                        if market_index == 0
                        else "no",
                        "evidence": [],
                    },
                    sort_keys=True,
                )
            )
    path = tmp_path / "calibration_only_last_price.jsonl"
    path.write_text("\n".join(rows) + "\n")
    return path


def _eligible_dataset_summary(report: dict[str, object]) -> dict[str, object]:
    dataset = copy.deepcopy(report["dataset"])
    dataset["classification"] = (
        "historical_local_dataset_eligible_for_acceptance_evaluation"
    )
    dataset["classification_detail"] = (
        "historical local dataset eligible for acceptance evaluation"
    )
    dataset["acceptance_evaluation_eligible"] = True
    dataset["has_settlement"] = True
    dataset["settlement_coverage"] = "full"
    dataset["market_settlement_coverage"] = "full"
    for gate in dataset["sample_size_gates"].values():
        gate["observed"] = gate["required"]
        gate["passed"] = True
    return dataset
