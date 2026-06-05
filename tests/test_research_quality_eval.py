from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from local_market_agent.cli import app
from local_market_agent.config import RiskGateConfig, Settings
from local_market_agent.eval import (
    run_daily_provider_comparison,
    run_sandbox_provider_comparison,
)
from local_market_agent.llm import MockLLMProvider, OpenAICompatibleProvider

NOW = datetime(2026, 6, 5, 16, tzinfo=UTC)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "unused.sqlite",
        research_brief_dir=tmp_path / "unused-briefs",
        risk_gates=RiskGateConfig(require_manual_approval=False),
    )


def _observe_research_json(prompt: str) -> str:
    payload = json.loads(prompt)
    snapshot = payload["input"]["snapshot"]
    evidence = payload["input"]["evidence"]
    return json.dumps(
        {
            "market_id": snapshot["market"]["market_id"],
            "snapshot_id": snapshot["snapshot_id"],
            "thesis": "Qwen-style cautious research recommends observing.",
            "rationale": "The estimated edge is not strong enough for a paper recommendation.",
            "evidence": evidence,
            "counter_evidence": [],
            "uncertainty_notes": ["Cautious fake-provider evaluation for regression tests."],
            "confidence": 0.58,
            "evidence_quality": 0.75,
            "estimated_probability": snapshot["market_implied_probability"],
            "market_implied_probability": snapshot["market_implied_probability"],
            "recommended_action": "observe",
            "must_not_trade_reasons": ["No paper order without a clear research edge."],
        },
        sort_keys=True,
    )


def _same_decision_higher_confidence_json(prompt: str) -> str:
    payload = json.loads(prompt)
    snapshot = payload["input"]["snapshot"]
    evidence = payload["input"]["evidence"]
    counter_evidence = [
        item for item in evidence if item.get("metadata", {}).get("counter") is True
    ]
    positive_evidence = [
        item for item in evidence if item.get("metadata", {}).get("counter") is not True
    ]
    return json.dumps(
        {
            "market_id": snapshot["market"]["market_id"],
            "snapshot_id": snapshot["snapshot_id"],
            "thesis": "Qwen-style research supports the same paper YES action.",
            "rationale": "The same probability estimate clears the paper-only edge threshold.",
            "evidence": positive_evidence,
            "counter_evidence": counter_evidence,
            "uncertainty_notes": ["Confidence differs, but downstream action should not."],
            "confidence": 0.82,
            "evidence_quality": 0.81,
            "estimated_probability": 0.6083,
            "market_implied_probability": snapshot["market_implied_probability"],
            "recommended_action": "paper_buy_yes",
            "must_not_trade_reasons": ["Paper-only validation path."],
        },
        sort_keys=True,
    )


def test_daily_research_quality_comparison_detects_material_downstream_change(
    monkeypatch,
    tmp_path,
):
    calls: list[tuple[str, str]] = []

    def fake_complete_json(self: OpenAICompatibleProvider, prompt: str) -> str:
        calls.append((self.base_url, self.model))
        return _observe_research_json(prompt)

    monkeypatch.setattr(OpenAICompatibleProvider, "complete_json", fake_complete_json)

    payload = run_daily_provider_comparison(
        _settings(tmp_path),
        artifact_dir=tmp_path / "artifacts",
        comparison_id="daily-material-change",
        now=NOW,
    )

    assert calls == [("http://localhost:11434/v1", "qwen3:14b")]
    assert payload["comparison"]["materially_changed_outcomes"] is True
    assert payload["comparison"]["research_brief"]["recommendation_changed"] is True
    assert payload["runs"][0]["run"]["status"] == "completed"
    assert payload["runs"][1]["run"]["status"] == "rejected"
    assert payload["runs"][0]["paper_order"] is not None
    assert payload["runs"][1]["paper_order"] is None
    assert Path(payload["artifacts"]["json"]).exists()
    assert Path(payload["artifacts"]["markdown"]).exists()


def test_daily_research_quality_comparison_does_not_overstate_matching_outputs(
    monkeypatch,
    tmp_path,
):
    def fake_complete_json(self: OpenAICompatibleProvider, prompt: str) -> str:
        return MockLLMProvider().complete_json(prompt)

    monkeypatch.setattr(OpenAICompatibleProvider, "complete_json", fake_complete_json)

    payload = run_daily_provider_comparison(
        _settings(tmp_path),
        artifact_dir=tmp_path / "artifacts",
        comparison_id="daily-no-material-change",
        now=NOW,
    )

    assert payload["comparison"]["materially_changed_outcomes"] is False
    assert payload["comparison"]["research_brief"]["recommendation_changed"] is False
    assert payload["runs"][0]["run"]["status"] == payload["runs"][1]["run"]["status"]
    assert payload["runs"][0]["paper_order"] is not None
    assert payload["runs"][1]["paper_order"] is not None


def test_daily_comparison_confidence_only_signal_changes_are_not_material(
    monkeypatch,
    tmp_path,
):
    def fake_complete_json(self: OpenAICompatibleProvider, prompt: str) -> str:
        return _same_decision_higher_confidence_json(prompt)

    monkeypatch.setattr(OpenAICompatibleProvider, "complete_json", fake_complete_json)

    payload = run_daily_provider_comparison(
        _settings(tmp_path),
        artifact_dir=tmp_path / "artifacts",
        comparison_id="daily-confidence-only-change",
        now=NOW,
    )

    assert payload["comparison"]["research_brief"]["changed"] is True
    assert payload["comparison"]["signal"]["changed"] is True
    assert payload["comparison"]["materially_changed_outcomes"] is False
    assert payload["comparison"]["materiality_basis"] == []
    assert payload["runs"][0]["paper_order"] is not None
    assert payload["runs"][1]["paper_order"] is not None


def test_sandbox_research_quality_comparison_aggregates_changed_days(
    monkeypatch,
    tmp_path,
):
    def fake_complete_json(self: OpenAICompatibleProvider, prompt: str) -> str:
        return _observe_research_json(prompt)

    monkeypatch.setattr(OpenAICompatibleProvider, "complete_json", fake_complete_json)

    payload = run_sandbox_provider_comparison(
        _settings(tmp_path),
        artifact_dir=tmp_path / "artifacts",
        comparison_id="sandbox-material-change",
        days=2,
        replay_sample_size=0,
    )

    assert payload["comparison"]["materially_changed_outcomes"] is True
    assert payload["comparison"]["status_counts_changed"] is True
    assert payload["comparison"]["mock_status_counts"]["completed"] == 2
    assert payload["comparison"]["qwen_status_counts"]["rejected"] == 2
    assert payload["comparison"]["materially_changed_days"] == ["2026-06-04", "2026-06-05"]
    assert Path(payload["artifacts"]["json"]).exists()
    assert Path(payload["artifacts"]["markdown"]).exists()


def test_research_quality_daily_compare_cli(monkeypatch, tmp_path):
    def fake_complete_json(self: OpenAICompatibleProvider, prompt: str) -> str:
        return _observe_research_json(prompt)

    monkeypatch.setattr(OpenAICompatibleProvider, "complete_json", fake_complete_json)
    result = CliRunner().invoke(
        app,
        [
            "phase7-research-quality-daily-compare",
            "--artifact-dir",
            str(tmp_path / "artifacts"),
            "--comparison-id",
            "cli-daily-material-change",
            "--evaluation-date",
            "2026-06-05",
            "--no-require-manual-approval",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["comparison_id"] == "cli-daily-material-change"
    assert payload["comparison_kind"] == "daily"
    assert payload["materially_changed_outcomes"] is True
    assert payload["provider_statuses"] == {
        "mock": "completed",
        "qwen3_14b_ollama": "rejected",
    }
    assert Path(payload["json_path"]).exists()
    assert Path(payload["markdown_path"]).exists()
