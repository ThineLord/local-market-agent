from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from local_market_agent.adapters import FixtureAdapter, PolymarketAdapter
from local_market_agent.cli import app
from local_market_agent.config import RiskGateConfig, Settings
from local_market_agent.llm import MockLLMProvider, OpenAICompatibleProvider
from local_market_agent.operations import Phase7ReplayService, Phase7SandboxRunner
from local_market_agent.storage import SQLiteRepository


def _settings(tmp_path: Path, *, allow_live_orders: bool = False) -> Settings:
    return Settings(
        db_path=tmp_path / "phase7-sandbox.sqlite",
        research_brief_dir=tmp_path / "briefs",
        allow_live_orders=allow_live_orders,
        risk_gates=RiskGateConfig(require_manual_approval=False),
    )


def _sandbox_runner(tmp_path: Path, *, allow_live_orders: bool = False):
    settings = _settings(tmp_path, allow_live_orders=allow_live_orders)
    repo = SQLiteRepository(settings.db_path)
    runner = Phase7SandboxRunner(
        repository=repo,
        settings=settings,
        report_dir=tmp_path / "reports",
    )
    return repo, runner


def test_phase7_sandbox_cli_runs_seven_days(tmp_path):
    cli = CliRunner()
    db = tmp_path / "sandbox-cli.sqlite"
    report_dir = tmp_path / "reports"

    result = cli.invoke(
        app,
        [
            "phase7-sandbox-run",
            "--days",
            "7",
            "--db",
            str(db),
            "--report-dir",
            str(report_dir),
            "--no-require-manual-approval",
            "--replay-sample-size",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["simulated_days"] == 7
    assert payload["market_source"] == "fixture"
    assert payload["data_mode"] == "fixture"
    assert payload["market_data"]["network_calls_enabled"] is False
    assert payload["market_data"]["profitability_claims_meaningful"] is False
    assert payload["sandbox_data_semantics"]["label"] == "fixture replay sandbox"
    assert payload["status_counts"]["completed"] > 0
    assert sum(payload["status_counts"].values()) == 7
    assert len(payload["equity_curve"]) == 7
    assert payload["total_return"] is not None
    assert payload["max_drawdown"] >= 0
    assert payload["run_success_rate"] == 1.0
    assert len(payload["report_paths"]) == 7
    assert Path(payload["summary_path"]).exists()
    assert len(payload["replay_validation_sample_results"]) == 2
    assert all(sample["ok"] for sample in payload["replay_validation_sample_results"])


def test_phase7_sandbox_preserves_immutable_report_paths_per_run(tmp_path):
    repo, runner = _sandbox_runner(tmp_path)

    result = runner.run(days=7, require_manual_approval=False)

    report_paths = result.summary["report_paths"]
    assert len(report_paths) == 7
    assert len(set(report_paths)) == 7
    for record in result.records:
        assert record.report_path is not None
        assert Path(record.report_path).exists()
        assert Path(record.report_path).name == f"phase7_daily_report_{record.run_id}.md"
        manifest = repo.load_phase7_run_manifest(record.run_id)
        assert manifest is not None
        assert manifest.run_id == record.run_id
        assert manifest.report_path == record.report_path
        assert manifest.report_checksum == record.metadata["report_checksum"]


def test_phase7_sandbox_replay_does_not_mutate_records(tmp_path):
    repo, runner = _sandbox_runner(tmp_path)
    result = runner.run(days=7, require_manual_approval=False, replay_sample_size=1)
    sample = result.summary["replay_validation_sample_results"][0]

    assert sample["mutation_detected"] is False
    assert sample["counts_before"] == sample["counts_after"]

    counts_before = _counts(repo)
    replay = Phase7ReplayService(repo).replay(result.records[-1].run_id)
    counts_after = _counts(repo)

    assert replay.ok is True
    assert counts_before == counts_after


def test_phase7_sandbox_repeated_run_is_deterministic_on_same_input(tmp_path):
    first = _run_repeatable_sandbox(tmp_path)
    shutil.rmtree(tmp_path / "reports")
    (tmp_path / "phase7-sandbox.sqlite").unlink()

    second = _run_repeatable_sandbox(tmp_path)

    assert second == first


def test_phase7_sandbox_inherits_configured_provider_without_real_network(monkeypatch, tmp_path):
    calls: list[tuple[str, str]] = []

    def fake_complete_json(self: OpenAICompatibleProvider, prompt: str) -> str:
        calls.append((self.base_url, self.model))
        return MockLLMProvider().complete_json(prompt)

    monkeypatch.setattr(OpenAICompatibleProvider, "complete_json", fake_complete_json)
    settings = Settings(
        db_path=tmp_path / "phase7-sandbox-openai-compatible.sqlite",
        research_brief_dir=tmp_path / "briefs",
        llm_provider="openai-compatible",
        openai_compatible_base_url="http://127.0.0.1:9999/v1",
        openai_compatible_model="sandbox-test-model",
        risk_gates=RiskGateConfig(require_manual_approval=False),
    )
    repo = SQLiteRepository(settings.db_path)
    runner = Phase7SandboxRunner(
        repository=repo,
        settings=settings,
        report_dir=tmp_path / "reports",
    )

    result = runner.run(days=2, require_manual_approval=False, replay_sample_size=0)

    assert calls == [
        ("http://127.0.0.1:9999/v1", "sandbox-test-model"),
        ("http://127.0.0.1:9999/v1", "sandbox-test-model"),
    ]
    assert result.summary["llm_provider"]["provider"] == "openai-compatible"
    assert result.summary["llm_provider"]["network_calls_enabled"] is True
    assert result.summary["safety"]["direct_llm_to_order_path"] is False
    assert result.summary["safety"]["allow_live_orders"] is False
    assert all(
        record.metadata["llm_provider"]["model"] == "sandbox-test-model"
        for record in result.records
    )


def test_phase7_sandbox_inherits_non_fixture_market_source_without_network(
    monkeypatch,
    tmp_path,
):
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
    runner = Phase7SandboxRunner(
        repository=repo,
        settings=settings,
        report_dir=tmp_path / "reports",
        market_source="polymarket",
        market_id="pm-sandbox-market",
    )

    result = runner.run(days=2, require_manual_approval=False, replay_sample_size=0)

    assert calls == ["pm-sandbox-market", "pm-sandbox-market"]
    assert result.summary["market_source"] == "polymarket"
    assert result.summary["data_mode"] == "current_snapshot"
    assert result.summary["local_only"] is False
    assert result.summary["deterministic"] is False
    assert result.summary["profitability_claims_meaningful"] is False
    assert result.summary["sandbox_data_semantics"]["label"] == "snapshot repeated sandbox"
    assert result.summary["sandbox_data_semantics"]["historical_market_data"] is False
    assert result.summary["sandbox_data_semantics"]["snapshot_only"] is True
    assert result.summary["market_data"]["network_calls_enabled"] is True
    assert all(record.status.value == "rejected" for record in result.records)
    assert all(
        record.metadata["market_data"]["market_source"] == "polymarket"
        for record in result.records
    )
    assert len(repo.list_paper_orders()) == 0


def test_phase7_sandbox_rejects_live_execution_flags(tmp_path):
    _, runner = _sandbox_runner(tmp_path, allow_live_orders=True)

    with pytest.raises(ValueError, match="ALLOW_LIVE_ORDERS"):
        runner.run(days=7, require_manual_approval=False)


def _run_repeatable_sandbox(tmp_path: Path) -> dict[str, object]:
    _, runner = _sandbox_runner(tmp_path)
    result = runner.run(days=7, require_manual_approval=False, replay_sample_size=2)
    return result.summary


def _counts(repo: SQLiteRepository) -> dict[str, int]:
    return {table: repo.count(table) for table in sorted(SQLiteRepository.TABLES)}
