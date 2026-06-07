from __future__ import annotations

import ast
import inspect
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

import local_market_agent.eval.calibration_audit as calibration_audit_module
from local_market_agent.cli import app
from local_market_agent.eval.calibration_audit import (
    CLASSIFICATION_ACCEPTANCE_POSSIBLE,
    CLASSIFICATION_MINIMUM,
    CLASSIFICATION_PREFERRED,
    CLASSIFICATION_STRETCH,
    CLASSIFICATION_UNUSABLE,
    audit_calibration_dataset,
    write_calibration_audit_reports,
)


def test_tiny_fixture_classified_calibration_unusable(tmp_path):
    path = _write_dataset(tmp_path, market_count=1, rows_per_market=5)

    result = audit_calibration_dataset(path)

    assert result.classification == CLASSIFICATION_UNUSABLE
    assert "market_count_below_acceptance_minimum" in result.acceptance_blockers
    assert result.claim_guardrails["forecast_calibration_diagnostics"] is False


def test_minimum_fixture_classified_calibration_minimum(tmp_path):
    path = _write_dataset(tmp_path, market_count=25, rows_per_market=10)

    result = audit_calibration_dataset(path)

    assert result.classification == CLASSIFICATION_MINIMUM
    assert result.market_count == 25
    assert result.row_count == 250
    assert result.resolved_market_count == 25
    assert result.scored_row_count == 250
    assert result.settlement_coverage_pct == 1.0
    assert result.last_price_coverage_pct == 1.0


def test_preferred_fixture_classified_calibration_preferred(tmp_path):
    path = _write_dataset(tmp_path, market_count=60, rows_per_market=12)

    result = audit_calibration_dataset(path)

    assert result.classification == CLASSIFICATION_PREFERRED
    assert result.market_count == 60
    assert result.row_count == 720


def test_stretch_fixture_classified_calibration_stretch(tmp_path):
    path = _write_dataset(tmp_path, market_count=150, rows_per_market=14)

    result = audit_calibration_dataset(path)

    assert result.classification == CLASSIFICATION_STRETCH
    assert result.market_count == 150
    assert result.row_count == 2100


def test_missing_settlement_blocks_calibration(tmp_path):
    path = _write_dataset(
        tmp_path,
        market_count=25,
        rows_per_market=10,
        mutate_row=lambda row, index: row.pop("settlement") if index == 1 else None,
    )

    result = audit_calibration_dataset(path)

    assert result.classification == CLASSIFICATION_UNUSABLE
    assert result.missing_outcome_count == 1
    assert "settlement_coverage_below_100_pct" in result.acceptance_blockers


def test_missing_evidence_blocks_acceptance_but_not_calibration(tmp_path):
    path = _write_dataset(tmp_path, market_count=25, rows_per_market=10, evidence=False)

    result = audit_calibration_dataset(path)

    assert result.classification == CLASSIFICATION_MINIMUM
    assert result.evidence_timestamp_coverage_pct == 0.0
    assert "evidence_timestamp_coverage_below_95_pct" in result.acceptance_blockers
    assert (
        "timestamp_safe_evidence_incomplete_acceptance_blocker_only"
        in result.calibration_warnings
    )


def test_calibration_only_dataset_blocks_superiority_and_profitability_claims(tmp_path):
    path = _write_dataset(tmp_path, market_count=25, rows_per_market=10)

    result = audit_calibration_dataset(path)
    guardrails = result.claim_guardrails

    assert guardrails["forecast_calibration_diagnostics"] is True
    assert guardrails["strategy_comparison_diagnostics"] is True
    assert guardrails["acceptance_gate_pass"] is False
    assert guardrails["strategy_v2_superiority"] is False
    assert guardrails["profitability_claim"] is False


def test_acceptance_shaped_fixture_classified_acceptance_candidate_possible(tmp_path):
    path = _write_dataset(
        tmp_path,
        market_count=25,
        rows_per_market=10,
        profile="acceptance_candidate",
        evidence=True,
        bid_ask=True,
    )

    result = audit_calibration_dataset(path)

    assert result.classification == CLASSIFICATION_ACCEPTANCE_POSSIBLE
    assert result.acceptance_blockers == ()
    assert result.bid_ask_coverage_pct == 1.0
    assert result.evidence_timestamp_coverage_pct == 1.0
    assert result.claim_guardrails["acceptance_gate_evaluation_possible"] is True
    assert result.claim_guardrails["acceptance_gate_pass"] is False
    assert result.claim_guardrails["strategy_v2_superiority"] is False


def test_cli_writes_json_and_markdown_reports(tmp_path):
    dataset_path = _write_dataset(tmp_path, market_count=25, rows_per_market=10)
    report_dir = tmp_path / "reports"

    cli_result = CliRunner().invoke(
        app,
        [
            "audit-calibration-dataset",
            "--historical-file",
            str(dataset_path),
            "--output-dir",
            str(report_dir),
        ],
    )

    assert cli_result.exit_code == 0, cli_result.output
    payload = json.loads(cli_result.output)
    assert payload["classification"] == CLASSIFICATION_MINIMUM
    assert payload["claim_guardrails"]["acceptance_gate_pass"] is False
    assert Path(payload["json_path"]).exists()
    assert Path(payload["markdown_path"]).exists()

    report = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    assert report["classification"] == CLASSIFICATION_MINIMUM
    markdown = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "Calibration Dataset Audit" in markdown
    assert "Strategy v2 superiority | False" in markdown


def test_report_writer_outputs_json_and_markdown(tmp_path):
    path = _write_dataset(tmp_path, market_count=25, rows_per_market=10)
    result = audit_calibration_dataset(path)

    artifacts = write_calibration_audit_reports(result, tmp_path / "reports")

    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()


def test_calibration_audit_adds_no_broker_live_or_order_api():
    source = inspect.getsource(calibration_audit_module)
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


def _write_dataset(
    tmp_path: Path,
    *,
    market_count: int,
    rows_per_market: int,
    profile: str = "calibration_only_last_price",
    evidence: bool = False,
    bid_ask: bool = False,
    mutate_row=None,
) -> Path:
    rows = []
    for market_index in range(1, market_count + 1):
        for row_index in range(1, rows_per_market + 1):
            absolute_index = (market_index - 1) * rows_per_market + row_index
            row = _historical_row(
                market_index=market_index,
                row_index=row_index,
                absolute_index=absolute_index,
                profile=profile,
                evidence=evidence,
                bid_ask=bid_ask,
            )
            if mutate_row is not None:
                mutate_row(row, absolute_index)
            rows.append(row)

    path = tmp_path / f"{profile}_{market_count}m_{rows_per_market}r.jsonl"
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
        + "\n",
        encoding="utf-8",
    )
    return path


def _historical_row(
    *,
    market_index: int,
    row_index: int,
    absolute_index: int,
    profile: str,
    evidence: bool,
    bid_ask: bool,
) -> dict[str, object]:
    timestamp = datetime(2026, 1, 1, 12, tzinfo=UTC) + timedelta(days=row_index)
    label_available_at = datetime(2026, 6, 1, 12, tzinfo=UTC)
    market_id = f"KXCAL-{market_index:04d}"
    probability = round(0.2 + ((absolute_index % 60) / 100), 4)
    source_provenance = {
        "source_name": "deterministic local calibration fixture",
        "source_type": "manual_jsonl",
        "source_url": "https://example.test/calibration",
        "source_record_id": f"{market_id}:{row_index}",
        "retrieved_at": "2026-06-07T00:00:00Z",
        "exported_at": "2026-06-07T00:05:00Z",
        "raw_sha256": None,
        "transform_version": "test_calibration_audit_v1",
        "terms_review": "reviewed_public_research_local_only",
        "network_used_by_builder": False,
        "private_or_authenticated_source": False,
    }
    is_acceptance = profile == "acceptance_candidate"
    row = {
        "schema_version": "phase7g.historical_dataset.v1",
        "row_id": f"row_{absolute_index:06d}",
        "dataset_id": f"test_{profile}",
        "dataset_label": "test_calibration_audit",
        "profile": profile,
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "date": timestamp.date().isoformat(),
        "market_id": market_id,
        "platform": "kalshi",
        "title": f"Calibration audit test market {market_index}",
        "category": f"category_{market_index % 5}",
        "market_type": "binary_prediction",
        "outcome_side": "yes",
        "bid": round(max(probability - 0.01, 0.0), 4) if bid_ask else None,
        "ask": round(min(probability + 0.01, 1.0), 4) if bid_ask else None,
        "last_price": probability,
        "implied_probability": probability,
        "liquidity": 1000.0,
        "volume": 5000.0,
        "market_status_at_timestamp": "open",
        "paper_pnl_allowed": is_acceptance,
        "acceptance_candidate": is_acceptance,
        "calibration_only_reason": None if is_acceptance else "calibration_audit_test",
        "evidence": _evidence(timestamp, absolute_index) if evidence else [],
        "settlement": {
            "outcome": "yes" if market_index % 2 else "no",
            "status": "settled",
            "resolved_at": "2026-06-01T12:00:00Z",
            "label_available_at": label_available_at.isoformat().replace("+00:00", "Z"),
            "source": "deterministic_test_resolution",
            "source_url": "https://example.test/calibration/resolution",
            "resolution_rule": "Deterministic generated fixture settlement.",
            "verified_at": "2026-06-07T00:10:00Z",
            "ambiguous": False,
        },
        "source_provenance": source_provenance,
    }
    if is_acceptance:
        row.pop("calibration_only_reason")
    return row


def _evidence(timestamp: datetime, absolute_index: int) -> list[dict[str, object]]:
    published_at = timestamp - timedelta(hours=2)
    return [
        {
            "evidence_id": f"ev_{absolute_index:06d}",
            "source": "official_test_source",
            "title": "Deterministic test evidence",
            "url": "https://example.test/calibration/evidence",
            "published_at": published_at.isoformat().replace("+00:00", "Z"),
            "retrieved_at": "2026-06-07T00:00:00Z",
            "summary": "Evidence was available before the forecast timestamp.",
            "relevance_score": 0.8,
            "credibility_score": 0.9,
        }
    ]
