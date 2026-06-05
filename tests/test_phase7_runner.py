from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from local_market_agent.adapters import FixtureAdapter, PolymarketAdapter
from local_market_agent.config import RiskGateConfig, Settings
from local_market_agent.llm import MockLLMProvider, OpenAICompatibleProvider
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
    assert manifest.configuration_snapshot["llm"]["provider"] == "mock"
    assert manifest.configuration_snapshot["market_data"]["market_source"] == "fixture"
    assert manifest.configuration_snapshot["market_data"]["network_calls_enabled"] is False
    assert record.metadata["llm_provider"]["provider"] == "mock"
    assert record.metadata["llm_provider"]["network_calls_enabled"] is False
    assert record.metadata["market_data"]["market_source"] == "fixture"
    assert record.metadata["market_data"]["data_mode"] == "fixture"
    assert record.metadata["market_data"]["profitability_claims_meaningful"] is False
    assert len(repo.list_paper_orders()) == 1
    assert len(repo.list_paper_fills()) == 1
    assert len(repo.list_positions()) == 1
    assert repo.list_risk_gate_decisions(limit=1)[0].status == RiskGateDecisionStatus.APPROVED


def test_phase7_runner_uses_configured_provider_without_real_network(monkeypatch, tmp_path):
    calls: list[tuple[str, str]] = []

    def fake_complete_json(self: OpenAICompatibleProvider, prompt: str) -> str:
        calls.append((self.base_url, self.model))
        return MockLLMProvider().complete_json(prompt)

    monkeypatch.setattr(OpenAICompatibleProvider, "complete_json", fake_complete_json)
    settings = Settings(
        db_path=tmp_path / "phase7-openai-compatible.sqlite",
        research_brief_dir=tmp_path / "briefs",
        llm_provider="openai-compatible",
        openai_compatible_base_url="http://127.0.0.1:9999/v1",
        openai_compatible_model="phase7-test-model",
        risk_gates=RiskGateConfig(require_manual_approval=False),
    )
    repo = SQLiteRepository(settings.db_path)
    runner = Phase7DailyRunner(
        repository=repo,
        settings=settings,
        report_dir=tmp_path / "reports",
    )

    record = runner.run(now=NOW)

    assert record.status == Phase7RunStatus.COMPLETED
    assert calls == [("http://127.0.0.1:9999/v1", "phase7-test-model")]
    assert record.metadata["llm_provider"] == {
        "api_key_configured": False,
        "base_url": "http://127.0.0.1:9999/v1",
        "can_create_orders": False,
        "is_mock": False,
        "is_real": True,
        "model": "phase7-test-model",
        "network_calls_enabled": True,
        "provider": "openai-compatible",
        "research_only": True,
    }
    manifest = repo.load_phase7_run_manifest(record.run_id)
    assert manifest is not None
    assert manifest.configuration_snapshot["llm"] == record.metadata["llm_provider"]
    assert manifest.execution_mode == ExecutionMode.PAPER
    assert repo.list_paper_orders()[0].execution_mode == ExecutionMode.PAPER
    assert repo.list_risk_gate_decisions()[0].execution_mode == ExecutionMode.PAPER


def test_phase7_runner_selects_non_fixture_market_source_without_network(monkeypatch, tmp_path):
    calls: list[str] = []
    fixture_snapshot = FixtureAdapter().fetch_snapshot()

    def fake_fetch_snapshot(self: PolymarketAdapter, market_id: str):
        calls.append(market_id)
        return fixture_snapshot.model_copy(
            update={
                "market": fixture_snapshot.market.model_copy(
                    update={"market_id": market_id, "platform": "polymarket"}
                )
            }
        )

    monkeypatch.setattr(PolymarketAdapter, "fetch_snapshot", fake_fetch_snapshot)
    settings = _settings(tmp_path)
    repo = SQLiteRepository(settings.db_path)
    runner = Phase7DailyRunner(
        repository=repo,
        settings=settings,
        report_dir=tmp_path / "reports",
        market_source="polymarket",
        market_id="pm-test-market",
    )

    record = runner.run(now=NOW)

    assert calls == ["pm-test-market"]
    assert record.status == Phase7RunStatus.REJECTED
    assert record.paper_order_id is None
    assert len(repo.list_paper_orders()) == 0
    market_data = record.metadata["market_data"]
    assert market_data["market_source"] == "polymarket"
    assert market_data["market_id"] == "pm-test-market"
    assert market_data["data_mode"] == "current_snapshot"
    assert market_data["network_calls_enabled"] is True
    assert market_data["is_historical"] is False
    assert market_data["profitability_claims_meaningful"] is False
    assert market_data["evidence_source"] == "none"
    assert market_data["can_create_orders"] is False
    manifest = repo.load_phase7_run_manifest(record.run_id)
    assert manifest is not None
    assert manifest.configuration_snapshot["market_data"] == market_data
    assert manifest.execution_mode == ExecutionMode.PAPER


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
