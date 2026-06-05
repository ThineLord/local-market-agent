from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from local_market_agent.config import RiskGateConfig, Settings
from local_market_agent.operations import Phase7DailyRunner, Phase7ReplayService
from local_market_agent.storage import SQLiteRepository

NOW = datetime(2026, 6, 5, 0, 1, tzinfo=UTC)


def test_phase7_replay_reconstructs_and_validates_stored_artifacts(tmp_path):
    repo, record = _run_phase7(tmp_path)

    result = Phase7ReplayService(repo).replay(record.run_id)

    assert result.ok is True
    assert result.errors == []
    assert result.manifest is not None
    assert result.manifest.run_id == record.run_id
    assert result.report_path == record.report_path
    assert result.report_checksum == result.manifest.report_checksum
    assert result.artifacts["run_record"]["present"] is True
    assert result.artifacts["run_manifest"]["present"] is True
    assert result.artifacts["market_snapshot"]["present"] is True
    assert result.artifacts["research_brief"]["present"] is True
    assert result.artifacts["signal"]["present"] is True
    assert result.artifacts["risk_decision"]["present"] is True
    assert result.artifacts["risk_gate_decision"]["present"] is True
    assert result.artifacts["paper_order"]["present"] is True
    assert result.artifacts["portfolio_snapshot"]["present"] is True
    assert result.artifacts["report"]["present"] is True


def test_phase7_replay_detects_missing_report_without_mutation(tmp_path):
    repo, record = _run_phase7(tmp_path)
    counts_before = _counts(repo)
    Path(record.report_path or "").unlink()

    result = Phase7ReplayService(repo).replay(record.run_id)

    assert result.ok is False
    assert any("Report artifact not found" in error for error in result.errors)
    assert _counts(repo) == counts_before


def _run_phase7(tmp_path):
    settings = Settings(
        db_path=tmp_path / "phase7-replay.sqlite",
        research_brief_dir=tmp_path / "briefs",
        risk_gates=RiskGateConfig(require_manual_approval=False),
    )
    repo = SQLiteRepository(settings.db_path)
    record = Phase7DailyRunner(
        repository=repo,
        settings=settings,
        report_dir=tmp_path / "reports",
    ).run(now=NOW)
    return repo, record


def _counts(repo: SQLiteRepository) -> dict[str, int]:
    return {
        table: repo.count(table)
        for table in [
            "phase7_run_records",
            "phase7_run_manifests",
            "paper_orders",
            "paper_fills",
            "positions",
        ]
    }
