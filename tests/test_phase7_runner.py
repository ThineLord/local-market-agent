from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from local_market_agent.config import RiskGateConfig, Settings
from local_market_agent.operations import Phase7DailyRunner
from local_market_agent.schemas.models import ExecutionMode, Phase7RunStatus, RiskGateDecisionStatus
from local_market_agent.storage import SQLiteRepository

NOW = datetime(2026, 6, 5, 0, 1, tzinfo=UTC)


def _settings(tmp_path: Path, risk_gates: RiskGateConfig | None = None) -> Settings:
    return Settings(
        db_path=tmp_path / "phase7.sqlite",
        research_brief_dir=tmp_path / "briefs",
        risk_gates=risk_gates or RiskGateConfig(require_manual_approval=False),
    )


def _runner(
    tmp_path: Path,
    *,
    risk_gates: RiskGateConfig | None = None,
    refresh_market_timestamp: bool = True,
) -> tuple[SQLiteRepository, Phase7DailyRunner]:
    settings = _settings(tmp_path, risk_gates)
    repo = SQLiteRepository(settings.db_path)
    return repo, Phase7DailyRunner(
        repository=repo,
        settings=settings,
        report_dir=tmp_path / "reports",
        refresh_market_timestamp=refresh_market_timestamp,
    )


def test_phase7_runner_successful_approved_paper_run(tmp_path):
    repo, runner = _runner(tmp_path)

    record = runner.run(now=NOW)

    assert record.status == Phase7RunStatus.COMPLETED
    assert record.paper_order_id is not None
    assert record.report_path is not None
    assert record.manifest_id == record.run_id
    assert Path(record.report_path).exists()
    assert Path(record.report_path).name == f"phase7_daily_report_{record.run_id}.md"
    assert repo.load_phase7_run_record(record.run_id) == record
    manifest = repo.load_phase7_run_manifest(record.run_id)
    assert manifest is not None
    assert manifest.run_id == record.run_id
    assert manifest.report_path == record.report_path
    assert manifest.report_checksum == record.metadata["report_checksum"]
    assert manifest.cli_arguments["source"] == "runner"
    assert manifest.fixture_paths["market_fixture"] == "data/fixtures/demo_market.json"
    assert manifest.configuration_snapshot["allow_live_orders"] is False
    assert len(repo.list_paper_orders()) == 1
    assert len(repo.list_paper_fills()) == 1
    assert len(repo.list_positions()) == 1
    assert repo.list_risk_gate_decisions(limit=1)[0].status == RiskGateDecisionStatus.APPROVED


def test_phase7_runner_rejected_risk_gate_does_not_create_order(tmp_path):
    stale_config = RiskGateConfig(
        require_manual_approval=False,
        max_market_data_age_seconds=60,
    )
    repo, runner = _runner(
        tmp_path,
        risk_gates=stale_config,
        refresh_market_timestamp=False,
    )

    record = runner.run(now=datetime(2026, 6, 5, 0, 10, tzinfo=UTC))

    assert record.status == Phase7RunStatus.REJECTED
    assert record.paper_order_id is None
    assert len(repo.list_paper_orders()) == 0
    assert len(repo.list_positions()) == 0
    assert any("stale" in reason.lower() for reason in record.reasons)
    assert Path(record.report_path or "").exists()


def test_phase7_runner_dry_run_does_not_mutate_paper_positions(tmp_path):
    repo, runner = _runner(tmp_path)

    record = runner.run(dry_run=True, now=NOW)

    assert record.status == Phase7RunStatus.DRY_RUN
    assert record.dry_run is True
    assert record.paper_order_id is None
    assert len(repo.list_paper_orders()) == 0
    assert len(repo.list_paper_fills()) == 0
    assert len(repo.list_positions()) == 0
    assert Path(record.report_path or "").exists()


def test_phase7_runner_manual_approval_records_pending_status(tmp_path):
    repo, runner = _runner(tmp_path, risk_gates=RiskGateConfig(require_manual_approval=True))

    record = runner.run(now=NOW)

    assert record.status == Phase7RunStatus.PENDING_MANUAL_APPROVAL
    assert record.paper_order_id is None
    assert len(repo.list_paper_orders()) == 0
    assert repo.list_risk_gate_decisions(limit=1)[0].status == (
        RiskGateDecisionStatus.PENDING_MANUAL_APPROVAL
    )


def test_phase7_runner_records_are_paper_only(tmp_path):
    repo, runner = _runner(tmp_path)

    record = runner.run(now=NOW)

    assert record.execution_mode == ExecutionMode.PAPER
    assert record.metadata["live_trading_allowed"] is False
    assert repo.load_phase7_run_manifest(record.run_id).execution_mode == ExecutionMode.PAPER
    assert repo.list_paper_orders()[0].execution_mode == ExecutionMode.PAPER
    assert repo.list_risk_gate_decisions()[0].execution_mode == ExecutionMode.PAPER


def test_phase7_runner_persists_failed_run_record(tmp_path):
    settings = _settings(tmp_path)
    repo = SQLiteRepository(settings.db_path)
    runner = Phase7DailyRunner(
        repository=repo,
        settings=settings,
        market_fixture=tmp_path / "missing_market.json",
        report_dir=tmp_path / "reports",
    )

    record = runner.run(now=NOW)

    assert record.status == Phase7RunStatus.FAILED
    assert record.manifest_id == record.run_id
    assert record.report_path is None
    assert "No such file" in record.metadata["error_message"]
    assert repo.load_phase7_run_record(record.run_id) == record
    manifest = repo.load_phase7_run_manifest(record.run_id)
    assert manifest is not None
    assert manifest.report_path is None
    assert manifest.report_checksum is None
    assert manifest.metadata["status"] == "failed"
    assert manifest.metadata["error_type"] == "FileNotFoundError"
    assert len(repo.list_paper_orders()) == 0
    assert len(repo.list_positions()) == 0
