from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from local_market_agent.config import Settings
from local_market_agent.llm import llm_provider_audit
from local_market_agent.llm.factory import MOCK_PROVIDER, OPENAI_COMPATIBLE_PROVIDER
from local_market_agent.operations import Phase7DailyRunner, Phase7SandboxRunner
from local_market_agent.operations.phase7_market_data import phase7_market_data_audit
from local_market_agent.schemas import (
    PaperOrder,
    Phase7RunRecord,
    ResearchBrief,
    RiskDecision,
    RiskGateDecision,
    Signal,
)
from local_market_agent.schemas.models import deterministic_model_context
from local_market_agent.storage import SQLiteRepository

DEFAULT_QWEN_MODEL = "qwen3:14b"
DEFAULT_QWEN_BASE_URL = "http://localhost:11434/v1"


@dataclass(frozen=True)
class ResearchQualityProviderSpec:
    label: str
    llm_provider: str
    llm_model: str | None = None
    llm_base_url: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
        }


def qwen_provider_spec(
    *,
    model: str = DEFAULT_QWEN_MODEL,
    base_url: str = DEFAULT_QWEN_BASE_URL,
) -> ResearchQualityProviderSpec:
    return ResearchQualityProviderSpec(
        label="qwen3_14b_ollama",
        llm_provider=OPENAI_COMPATIBLE_PROVIDER,
        llm_model=model,
        llm_base_url=base_url,
    )


def run_daily_provider_comparison(
    settings: Settings,
    *,
    artifact_dir: Path = Path("data/reports/research_quality"),
    comparison_id: str | None = None,
    qwen_model: str = DEFAULT_QWEN_MODEL,
    qwen_base_url: str = DEFAULT_QWEN_BASE_URL,
    market_fixture: Path = Path("data/fixtures/demo_market.json"),
    evidence_fixture: Path = Path("data/fixtures/demo_evidence.json"),
    market_source: str | None = None,
    market_id: str | None = None,
    historical_file: Path | None = None,
    dry_run: bool = False,
    require_manual_approval: bool | None = False,
    refresh_market_timestamp: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    comparison_id = comparison_id or _comparison_id("daily")
    evaluated_at = _as_utc(now or datetime.now(UTC))
    root = artifact_dir / comparison_id
    root.mkdir(parents=True, exist_ok=True)
    providers = [
        ResearchQualityProviderSpec(label="mock", llm_provider=MOCK_PROVIDER),
        qwen_provider_spec(model=qwen_model, base_url=qwen_base_url),
    ]
    runs: list[dict[str, Any]] = []
    for provider in providers:
        provider_settings = _settings_for_provider(
            settings,
            provider=provider,
            db_path=root / f"{provider.label}_daily.sqlite",
            research_brief_dir=root / provider.label / "research_briefs",
        )
        _reset_sqlite(provider_settings.db_path)
        repo = SQLiteRepository(provider_settings.db_path)
        report_dir = root / provider.label / "reports"
        runner = Phase7DailyRunner(
            repository=repo,
            settings=provider_settings,
            market_fixture=market_fixture,
            evidence_fixture=evidence_fixture,
            report_dir=report_dir,
            refresh_market_timestamp=refresh_market_timestamp,
            market_source=market_source or settings.market_source,
            market_id=market_id if market_id is not None else settings.market_id,
            historical_file=historical_file
            if historical_file is not None
            else settings.historical_file,
        )
        with deterministic_model_context(
            seed=f"{comparison_id}:{provider.label}:daily",
            now=evaluated_at,
        ):
            record = runner.run(
                dry_run=dry_run,
                require_manual_approval=require_manual_approval,
                now=evaluated_at,
                cli_arguments={
                    "source": "research_quality_daily_comparison",
                    "comparison_id": comparison_id,
                    "provider_label": provider.label,
                    "fixture": str(market_fixture),
                    "evidence": str(evidence_fixture),
                    "market_source": market_source or settings.market_source,
                    "market_id": market_id if market_id is not None else settings.market_id,
                    "historical_file": str(historical_file)
                    if historical_file is not None
                    else (
                        str(settings.historical_file)
                        if settings.historical_file is not None
                        else None
                    ),
                    "dry_run": dry_run,
                    "require_manual_approval": require_manual_approval,
                    "refresh_market_timestamp": refresh_market_timestamp,
                    "llm_provider": provider.llm_provider,
                    "llm_model": provider.llm_model,
                    "llm_base_url": provider.llm_base_url,
                },
            )
        runs.append(_summarize_run(repo, record, provider))

    payload = _comparison_payload(
        comparison_kind="daily",
        comparison_id=comparison_id,
        evaluated_at=evaluated_at,
        artifact_root=root,
        inputs={
            "market_fixture": str(market_fixture),
            "evidence_fixture": str(evidence_fixture),
            "market_source": market_source or settings.market_source,
            "market_id": market_id if market_id is not None else settings.market_id,
            "historical_file": str(historical_file)
            if historical_file is not None
            else (str(settings.historical_file) if settings.historical_file else None),
            "dry_run": dry_run,
            "require_manual_approval": require_manual_approval,
            "refresh_market_timestamp": refresh_market_timestamp,
        },
        runs=runs,
        sandbox_summaries=None,
    )
    _write_comparison_artifacts(root, payload)
    return payload


def run_sandbox_provider_comparison(
    settings: Settings,
    *,
    artifact_dir: Path = Path("data/reports/research_quality"),
    comparison_id: str | None = None,
    qwen_model: str = DEFAULT_QWEN_MODEL,
    qwen_base_url: str = DEFAULT_QWEN_BASE_URL,
    market_fixture: Path = Path("data/fixtures/demo_market.json"),
    evidence_fixture: Path = Path("data/fixtures/demo_evidence.json"),
    market_source: str | None = None,
    market_id: str | None = None,
    historical_file: Path | None = None,
    days: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    dry_run: bool = False,
    require_manual_approval: bool | None = False,
    refresh_market_timestamp: bool = True,
    replay_sample_size: int = 1,
) -> dict[str, Any]:
    comparison_id = comparison_id or _comparison_id("sandbox")
    evaluated_at = datetime.now(UTC)
    root = artifact_dir / comparison_id
    root.mkdir(parents=True, exist_ok=True)
    providers = [
        ResearchQualityProviderSpec(label="mock", llm_provider=MOCK_PROVIDER),
        qwen_provider_spec(model=qwen_model, base_url=qwen_base_url),
    ]
    runs_by_provider: dict[str, list[dict[str, Any]]] = {}
    sandbox_summaries: dict[str, dict[str, Any]] = {}
    for provider in providers:
        provider_settings = _settings_for_provider(
            settings,
            provider=provider,
            db_path=root / f"{provider.label}_sandbox.sqlite",
            research_brief_dir=root / provider.label / "research_briefs",
        )
        _reset_sqlite(provider_settings.db_path)
        repo = SQLiteRepository(provider_settings.db_path)
        report_dir = root / provider.label / "reports"
        runner = Phase7SandboxRunner(
            repository=repo,
            settings=provider_settings,
            market_fixture=market_fixture,
            evidence_fixture=evidence_fixture,
            report_dir=report_dir,
            summary_dir=root / provider.label,
            refresh_market_timestamp=refresh_market_timestamp,
            market_source=market_source or settings.market_source,
            market_id=market_id if market_id is not None else settings.market_id,
            historical_file=historical_file
            if historical_file is not None
            else settings.historical_file,
        )
        result = runner.run(
            start_date=start_date,
            end_date=end_date,
            days=days,
            dry_run=dry_run,
            require_manual_approval=require_manual_approval,
            replay_sample_size=replay_sample_size,
            sandbox_id=f"{comparison_id}_{provider.label}",
        )
        sandbox_summaries[provider.label] = result.summary
        runs_by_provider[provider.label] = [
            _summarize_run(repo, record, provider) for record in result.records
        ]

    runs = [
        {
            "provider": provider.label,
            "provider_spec": provider.as_dict(),
            "runs": runs_by_provider[provider.label],
            "summary": sandbox_summaries[provider.label],
        }
        for provider in providers
    ]
    payload = _comparison_payload(
        comparison_kind="sandbox",
        comparison_id=comparison_id,
        evaluated_at=evaluated_at,
        artifact_root=root,
        inputs={
            "market_fixture": str(market_fixture),
            "evidence_fixture": str(evidence_fixture),
            "market_source": market_source or settings.market_source,
            "market_id": market_id if market_id is not None else settings.market_id,
            "historical_file": str(historical_file)
            if historical_file is not None
            else (str(settings.historical_file) if settings.historical_file else None),
            "days": days,
            "start_date": start_date.isoformat() if start_date is not None else None,
            "end_date": end_date.isoformat() if end_date is not None else None,
            "dry_run": dry_run,
            "require_manual_approval": require_manual_approval,
            "refresh_market_timestamp": refresh_market_timestamp,
            "replay_sample_size": replay_sample_size,
        },
        runs=runs,
        sandbox_summaries=sandbox_summaries,
    )
    _write_comparison_artifacts(root, payload)
    return payload


def _comparison_payload(
    *,
    comparison_kind: str,
    comparison_id: str,
    evaluated_at: datetime,
    artifact_root: Path,
    inputs: dict[str, Any],
    runs: list[dict[str, Any]],
    sandbox_summaries: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    if comparison_kind == "sandbox":
        comparison = _compare_sandbox_runs(runs)
        provider_specs = {
            item["provider"]: item["provider_spec"]
            for item in runs
            if isinstance(item.get("provider_spec"), dict)
        }
    else:
        comparison = _compare_provider_runs(runs[0], runs[1])
        provider_specs = {
            item["provider"]: item["provider_spec"]
            for item in runs
            if isinstance(item.get("provider_spec"), dict)
        }
    qwen_spec = provider_specs.get("qwen3_14b_ollama", {})
    market_audit = phase7_market_data_audit(
        inputs.get("market_source"),
        market_id=inputs.get("market_id"),
        historical_file=inputs.get("historical_file"),
    ).as_dict()
    payload = {
        "phase": "7D",
        "comparison_kind": comparison_kind,
        "comparison_id": comparison_id,
        "evaluated_at": evaluated_at.isoformat(),
        "artifact_root": str(artifact_root),
        "inputs": inputs,
        "market_data_audit": market_audit,
        "provider_audits": {
            "mock": llm_provider_audit(
                _settings_for_audit(
                    llm_provider=MOCK_PROVIDER,
                    llm_model=None,
                    llm_base_url=None,
                )
            ).as_dict(),
            "qwen3_14b_ollama": llm_provider_audit(
                _settings_for_audit(
                    llm_provider=OPENAI_COMPATIBLE_PROVIDER,
                    llm_model=qwen_spec.get("llm_model") or DEFAULT_QWEN_MODEL,
                    llm_base_url=qwen_spec.get("llm_base_url") or DEFAULT_QWEN_BASE_URL,
                )
            ).as_dict(),
        },
        "runs": runs,
        "comparison": comparison,
        "sandbox_summaries": sandbox_summaries,
        "safety": {
            "paper_only": True,
            "real_money_enabled": False,
            "allow_live_orders": False,
            "live_trading_allowed": False,
            "direct_llm_to_order_path": False,
            "broker_integrations_added": False,
            "scheduler_added": False,
            "phase8_functionality_added": False,
        },
    }
    payload["artifacts"] = {
        "json": str(artifact_root / "research_quality_comparison.json"),
        "markdown": str(artifact_root / "research_quality_comparison.md"),
    }
    return payload


def _settings_for_provider(
    settings: Settings,
    *,
    provider: ResearchQualityProviderSpec,
    db_path: Path,
    research_brief_dir: Path,
) -> Settings:
    return replace(
        settings,
        db_path=db_path,
        research_brief_dir=research_brief_dir,
        llm_provider=provider.llm_provider,
        openai_compatible_model=provider.llm_model or settings.openai_compatible_model,
        openai_compatible_base_url=provider.llm_base_url or settings.openai_compatible_base_url,
    )


def _settings_for_audit(
    *,
    llm_provider: str,
    llm_model: str | None,
    llm_base_url: str | None,
) -> Settings:
    return Settings(
        llm_provider=llm_provider,
        openai_compatible_model=llm_model or DEFAULT_QWEN_MODEL,
        openai_compatible_base_url=llm_base_url or DEFAULT_QWEN_BASE_URL,
    )


def _summarize_run(
    repo: SQLiteRepository,
    record: Phase7RunRecord,
    provider: ResearchQualityProviderSpec,
) -> dict[str, Any]:
    brief = repo.load_brief(record.brief_id) if record.brief_id is not None else None
    signal = repo.load_signal(record.signal_id) if record.signal_id is not None else None
    risk_decision = (
        repo.load_risk_decision(record.risk_decision_id)
        if record.risk_decision_id is not None
        else None
    )
    risk_gate = (
        repo.load_risk_gate_decision(record.risk_gate_decision_id)
        if record.risk_gate_decision_id is not None
        else None
    )
    order = repo.load_paper_order(record.paper_order_id) if record.paper_order_id else None
    return {
        "provider": provider.label,
        "provider_spec": provider.as_dict(),
        "provider_audit": record.metadata.get("llm_provider"),
        "db_path": str(repo.db_path),
        "run": _run_summary(record),
        "research_brief": _brief_summary(brief),
        "signal": _signal_summary(signal),
        "risk_decision": _risk_decision_summary(risk_decision),
        "risk_gate_decision": _risk_gate_summary(risk_gate),
        "paper_order": _paper_order_summary(order),
    }


def _run_summary(record: Phase7RunRecord) -> dict[str, Any]:
    return {
        "run_id": record.run_id,
        "created_at": record.created_at.isoformat(),
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        "report_date": record.report_date.isoformat(),
        "status": record.status.value,
        "dry_run": record.dry_run,
        "market_id": record.market_id,
        "snapshot_id": record.snapshot_id,
        "brief_id": record.brief_id,
        "signal_id": record.signal_id,
        "risk_decision_id": record.risk_decision_id,
        "risk_gate_decision_id": record.risk_gate_decision_id,
        "paper_order_id": record.paper_order_id,
        "portfolio_snapshot_id": record.portfolio_snapshot_id,
        "report_path": record.report_path,
        "manifest_id": record.manifest_id,
        "reasons": record.reasons,
        "error_type": record.metadata.get("error_type"),
        "error_message": record.metadata.get("error_message"),
        "report_checksum": record.metadata.get("report_checksum"),
        "market_data": record.metadata.get("market_data"),
    }


def _brief_summary(brief: ResearchBrief | None) -> dict[str, Any] | None:
    if brief is None:
        return None
    return {
        "brief_id": brief.brief_id,
        "market_id": brief.market_id,
        "snapshot_id": brief.snapshot_id,
        "created_at": brief.created_at.isoformat(),
        "thesis": brief.thesis,
        "rationale": brief.rationale,
        "recommended_action": brief.recommended_action.value,
        "confidence": brief.confidence,
        "evidence_quality": brief.evidence_quality,
        "estimated_probability": brief.estimated_probability,
        "market_implied_probability": brief.market_implied_probability,
        "evidence_titles": [item.title for item in brief.evidence],
        "counter_evidence_titles": [item.title for item in brief.counter_evidence],
        "uncertainty_notes": brief.uncertainty_notes,
        "must_not_trade_reasons": brief.must_not_trade_reasons,
        "resolution_source": brief.resolution_source,
        "resolution_ambiguity": brief.resolution_ambiguity,
    }


def _signal_summary(signal: Signal | None) -> dict[str, Any] | None:
    if signal is None:
        return None
    return {
        "signal_id": signal.signal_id,
        "brief_id": signal.brief_id,
        "market_id": signal.market_id,
        "action": signal.action.value,
        "agent_probability": signal.agent_probability,
        "market_probability": signal.market_probability,
        "spread": signal.spread,
        "edge": signal.edge,
        "confidence": signal.confidence,
        "evidence_quality": signal.evidence_quality,
        "rationale": signal.rationale,
        "execution_mode": signal.execution_mode.value,
    }


def _risk_decision_summary(decision: RiskDecision | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "risk_decision_id": decision.risk_decision_id,
        "signal_id": decision.signal_id,
        "status": decision.status.value,
        "reasons": decision.reasons,
        "max_position_pct": decision.max_position_pct,
        "max_position_usd": decision.max_position_usd,
        "requires_human_approval": decision.requires_human_approval,
        "live_trading_allowed": decision.live_trading_allowed,
    }


def _risk_gate_summary(decision: RiskGateDecision | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "risk_gate_decision_id": decision.risk_gate_decision_id,
        "intent_id": decision.intent_id,
        "signal_id": decision.signal_id,
        "market_id": decision.market_id,
        "status": decision.status.value,
        "reasons": decision.reasons,
        "checks": [
            {
                "gate": check.gate,
                "status": check.status.value,
                "passed": check.passed,
                "reason": check.reason,
                "observed": check.observed,
                "limit": check.limit,
            }
            for check in decision.checks
        ],
        "execution_mode": decision.execution_mode.value,
    }


def _paper_order_summary(order: PaperOrder | None) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "order_id": order.order_id,
        "signal_id": order.signal_id,
        "risk_decision_id": order.risk_decision_id,
        "market_id": order.market_id,
        "side": order.side.value,
        "quantity": order.quantity,
        "limit_price": order.limit_price,
        "fill_price": order.fill_price,
        "fees": order.fees,
        "status": order.status.value,
        "execution_mode": order.execution_mode.value,
    }


def _compare_provider_runs(
    mock: dict[str, Any],
    qwen: dict[str, Any],
) -> dict[str, Any]:
    brief = _compare_briefs(mock.get("research_brief"), qwen.get("research_brief"))
    signal = _compare_section(
        mock.get("signal"),
        qwen.get("signal"),
        keys=["action", "agent_probability", "edge", "confidence", "evidence_quality"],
    )
    risk = _compare_section(
        mock.get("risk_decision"),
        qwen.get("risk_decision"),
        keys=["status", "reasons"],
    )
    gate = _compare_section(
        mock.get("risk_gate_decision"),
        qwen.get("risk_gate_decision"),
        keys=["status", "reasons"],
    )
    order = _compare_section(
        mock.get("paper_order"),
        qwen.get("paper_order"),
        keys=["side", "quantity", "limit_price", "fill_price", "status"],
    )
    run_status_changed = _value(mock, "run", "status") != _value(qwen, "run", "status")
    order_created_changed = (mock.get("paper_order") is not None) != (
        qwen.get("paper_order") is not None
    )
    signal_action_changed = _section_field_changed(signal, "action")
    risk_status_changed = _section_field_changed(risk, "status")
    gate_status_changed = _section_field_changed(gate, "status")
    materially_changed = any(
        [
            run_status_changed,
            brief["recommendation_changed"],
            signal_action_changed,
            risk_status_changed,
            gate_status_changed,
            order["changed"],
            order_created_changed,
        ]
    )
    return {
        "research_brief": brief,
        "signal": signal,
        "risk_decision": risk,
        "risk_gate_decision": gate,
        "paper_order": order,
        "run_status_changed": run_status_changed,
        "paper_order_created_changed": order_created_changed,
        "materially_changed_outcomes": materially_changed,
        "materiality_basis": _materiality_basis(
            brief=brief,
            signal=signal,
            risk=risk,
            gate=gate,
            order=order,
            run_status_changed=run_status_changed,
            order_created_changed=order_created_changed,
            signal_action_changed=signal_action_changed,
            risk_status_changed=risk_status_changed,
            gate_status_changed=gate_status_changed,
        ),
    }


def _compare_sandbox_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    mock = next(item for item in runs if item["provider"] == "mock")
    qwen = next(item for item in runs if item["provider"] == "qwen3_14b_ollama")
    mock_by_date = {_simulated_date(item): item for item in mock["runs"]}
    qwen_by_date = {_simulated_date(item): item for item in qwen["runs"]}
    dates = sorted(set(mock_by_date) | set(qwen_by_date))
    daily_comparisons = []
    for simulated_date in dates:
        mock_run = mock_by_date.get(simulated_date)
        qwen_run = qwen_by_date.get(simulated_date)
        if mock_run is None or qwen_run is None:
            daily_comparisons.append(
                {
                    "simulated_date": simulated_date,
                    "missing_provider_run": "mock" if mock_run is None else "qwen3_14b_ollama",
                    "materially_changed_outcomes": True,
                }
            )
            continue
        daily = _compare_provider_runs(mock_run, qwen_run)
        daily["simulated_date"] = simulated_date
        daily_comparisons.append(daily)

    mock_summary = mock["summary"]
    qwen_summary = qwen["summary"]
    status_counts_changed = mock_summary.get("status_counts") != qwen_summary.get(
        "status_counts"
    )
    material_days = [
        item["simulated_date"]
        for item in daily_comparisons
        if item.get("materially_changed_outcomes")
    ]
    return {
        "status_counts_changed": status_counts_changed,
        "mock_status_counts": mock_summary.get("status_counts"),
        "qwen_status_counts": qwen_summary.get("status_counts"),
        "mock_run_success_rate": mock_summary.get("run_success_rate"),
        "qwen_run_success_rate": qwen_summary.get("run_success_rate"),
        "mock_total_return": mock_summary.get("total_return"),
        "qwen_total_return": qwen_summary.get("total_return"),
        "mock_win_rate": mock_summary.get("win_rate"),
        "qwen_win_rate": qwen_summary.get("win_rate"),
        "daily_comparisons": daily_comparisons,
        "materially_changed_days": material_days,
        "materially_changed_outcomes": bool(material_days or status_counts_changed),
        "materiality_basis": (
            ["At least one simulated day changed downstream outcomes."]
            if material_days
            else []
        )
        + (
            ["Aggregate sandbox status counts changed."]
            if status_counts_changed
            else []
        ),
    }


def _compare_briefs(
    mock: dict[str, Any] | None,
    qwen: dict[str, Any] | None,
) -> dict[str, Any]:
    changed = _normalized_brief(mock) != _normalized_brief(qwen)
    confidence_delta = _numeric_delta(_field(mock, "confidence"), _field(qwen, "confidence"))
    probability_delta = _numeric_delta(
        _field(mock, "estimated_probability"),
        _field(qwen, "estimated_probability"),
    )
    evidence_quality_delta = _numeric_delta(
        _field(mock, "evidence_quality"),
        _field(qwen, "evidence_quality"),
    )
    return {
        "changed": changed,
        "recommendation_changed": _field(mock, "recommended_action")
        != _field(qwen, "recommended_action"),
        "mock_recommendation": _field(mock, "recommended_action"),
        "qwen_recommendation": _field(qwen, "recommended_action"),
        "mock_confidence": _field(mock, "confidence"),
        "qwen_confidence": _field(qwen, "confidence"),
        "confidence_delta": confidence_delta,
        "mock_estimated_probability": _field(mock, "estimated_probability"),
        "qwen_estimated_probability": _field(qwen, "estimated_probability"),
        "estimated_probability_delta": probability_delta,
        "mock_evidence_quality": _field(mock, "evidence_quality"),
        "qwen_evidence_quality": _field(qwen, "evidence_quality"),
        "evidence_quality_delta": evidence_quality_delta,
    }


def _compare_section(
    mock: dict[str, Any] | None,
    qwen: dict[str, Any] | None,
    *,
    keys: list[str],
) -> dict[str, Any]:
    fields = {
        key: {
            "mock": _field(mock, key),
            "qwen": _field(qwen, key),
            "changed": _field(mock, key) != _field(qwen, key),
        }
        for key in keys
    }
    return {
        "changed": any(item["changed"] for item in fields.values()),
        "fields": fields,
    }


def _normalized_brief(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    ignored = {"brief_id", "snapshot_id", "created_at"}
    return {key: item for key, item in value.items() if key not in ignored}


def _materiality_basis(
    *,
    brief: dict[str, Any],
    signal: dict[str, Any],
    risk: dict[str, Any],
    gate: dict[str, Any],
    order: dict[str, Any],
    run_status_changed: bool,
    order_created_changed: bool,
    signal_action_changed: bool,
    risk_status_changed: bool,
    gate_status_changed: bool,
) -> list[str]:
    basis: list[str] = []
    if brief["recommendation_changed"]:
        basis.append("Research recommendation changed.")
    if signal_action_changed:
        basis.append("Strategy signal action changed.")
    if risk_status_changed:
        basis.append("Risk decision status changed.")
    if gate_status_changed:
        basis.append("Risk gate status changed.")
    if order["changed"] or order_created_changed:
        basis.append("Paper-order outcome changed.")
    if run_status_changed:
        basis.append("Run status changed.")
    return basis


def _section_field_changed(section: dict[str, Any], field: str) -> bool:
    fields = section.get("fields")
    if not isinstance(fields, dict):
        return False
    field_payload = fields.get(field)
    if not isinstance(field_payload, dict):
        return False
    return bool(field_payload.get("changed"))


def _write_comparison_artifacts(root: Path, payload: dict[str, Any]) -> None:
    json_path = root / "research_quality_comparison.json"
    markdown_path = root / "research_quality_comparison.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_comparison_markdown(payload), encoding="utf-8")


def _comparison_markdown(payload: dict[str, Any]) -> str:
    comparison = payload["comparison"]
    lines = [
        f"# Phase 7D Research Quality {payload['comparison_kind'].title()} Comparison",
        "",
        "## Methodology",
        "",
        "- Compared the deterministic mock provider against qwen3:14b through the "
        "OpenAI-compatible Ollama endpoint.",
        "- Used isolated SQLite databases and identical market/evidence inputs per provider.",
        "- Measured research brief fields, strategy signal, risk decision, risk gate outcome, "
        "and paper-order outcome.",
        "- This evaluates research and decision quality effects, not profitability.",
        "",
        "## Inputs",
        "",
        _table(
            ["Field", "Value"],
            [[key, str(value)] for key, value in sorted(payload["inputs"].items())],
        ),
        "",
        "## Outcome Summary",
        "",
        _table(
            ["Metric", "Value"],
            [
                ["Materially changed outcomes", str(comparison["materially_changed_outcomes"])],
                [
                    "Materiality basis",
                    "; ".join(comparison.get("materiality_basis", [])) or "None",
                ],
            ],
        ),
        "",
    ]
    if payload["comparison_kind"] == "sandbox":
        lines += _sandbox_markdown_sections(payload)
    else:
        lines += _daily_markdown_sections(payload)
    lines += [
        "",
        "## Safety",
        "",
        "- Paper-only comparison; no broker integration, live order, scheduler, or Phase 8 path.",
        "- LLM output remained research-only; downstream signal, risk, gate, and paper-order "
        "logic stayed deterministic.",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _daily_markdown_sections(payload: dict[str, Any]) -> list[str]:
    rows = []
    for run in payload["runs"]:
        rows.append(
            [
                run["provider"],
                _value(run, "run", "status"),
                _value(run, "research_brief", "recommended_action"),
                _value(run, "research_brief", "confidence"),
                _value(run, "signal", "action"),
                _value(run, "risk_decision", "status"),
                _value(run, "risk_gate_decision", "status"),
                "yes" if run.get("paper_order") is not None else "no",
            ]
        )
    return [
        "## Provider Runs",
        "",
        _table(
            [
                "Provider",
                "Run Status",
                "Recommendation",
                "Confidence",
                "Signal",
                "Risk",
                "Gate",
                "Paper Order",
            ],
            rows,
        ),
    ]


def _sandbox_markdown_sections(payload: dict[str, Any]) -> list[str]:
    comparison = payload["comparison"]
    return [
        "## Sandbox Aggregate",
        "",
        _table(
            ["Metric", "Mock", "Qwen"],
            [
                [
                    "Status counts",
                    str(comparison.get("mock_status_counts")),
                    str(comparison.get("qwen_status_counts")),
                ],
                [
                    "Run success rate",
                    str(comparison.get("mock_run_success_rate")),
                    str(comparison.get("qwen_run_success_rate")),
                ],
                [
                    "Total return",
                    str(comparison.get("mock_total_return")),
                    str(comparison.get("qwen_total_return")),
                ],
                [
                    "Win rate",
                    str(comparison.get("mock_win_rate")),
                    str(comparison.get("qwen_win_rate")),
                ],
            ],
        ),
        "",
        "## Materially Changed Days",
        "",
        "\n".join(f"- {day}" for day in comparison["materially_changed_days"])
        or "- None",
    ]


def _table(headers: list[str], rows: list[list[object]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _header in headers) + " |"
    body = ["| " + " | ".join(_markdown_cell(item) for item in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _markdown_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("\n", " ").replace("|", "\\|")


def _reset_sqlite(path: Path) -> None:
    for candidate in [path, path.with_name(f"{path.name}-wal"), path.with_name(f"{path.name}-shm")]:
        if candidate.exists():
            candidate.unlink()


def _comparison_id(kind: str) -> str:
    now = datetime.now(UTC)
    digest = sha256(f"{kind}:{now.isoformat()}".encode()).hexdigest()[:10]
    return f"phase7d_{kind}_{now.strftime('%Y%m%dT%H%M%SZ')}_{digest}"


def _simulated_date(run: dict[str, Any]) -> str:
    report_date = str(_value(run, "run", "report_date"))
    return report_date[:10]


def _numeric_delta(mock: object, qwen: object) -> float | None:
    if mock is None or qwen is None:
        return None
    return round(float(qwen) - float(mock), 8)


def _field(value: dict[str, Any] | None, key: str) -> Any:
    if value is None:
        return None
    return value.get(key)


def _value(value: dict[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
