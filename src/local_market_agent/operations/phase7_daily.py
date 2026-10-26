from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from local_market_agent.agents import ResearchBriefGenerator
from local_market_agent.config import RiskGateConfig, Settings
from local_market_agent.llm import build_llm_provider, llm_provider_audit
from local_market_agent.operations.phase7_manifest import build_phase7_run_manifest
from local_market_agent.operations.phase7_market_data import (
    load_phase7_market_inputs,
    phase7_market_data_audit,
)
from local_market_agent.paper import PaperLedger
from local_market_agent.reporting import Phase7DailyReportGenerator
from local_market_agent.risk import RiskEngine, RiskGateEvaluator
from local_market_agent.schemas import (
    MarketSnapshot,
    PaperOrder,
    PaperOrderIntent,
    Phase7RunRecord,
    Phase7RunStatus,
    PortfolioSnapshot,
    RiskDecision,
    RiskGateDecision,
    RiskGateDecisionStatus,
    Signal,
)
from local_market_agent.schemas.models import OrderSide, SignalAction, new_id
from local_market_agent.storage import SQLiteRepository
from local_market_agent.strategy import PredictionMarketEdgeStrategy

ACTIONABLE_PAPER_BUYS = {
    SignalAction.PAPER_BUY_YES,
    SignalAction.PAPER_BUY_NO,
}


@dataclass
class Phase7DailyRunner:
    repository: SQLiteRepository
    settings: Settings
    market_fixture: Path = Path("data/fixtures/demo_market.json")
    evidence_fixture: Path = Path("data/fixtures/demo_evidence.json")
    report_dir: Path = Path("data/reports")
    refresh_market_timestamp: bool = True
    market_source: str | None = None
    market_id: str | None = None
    historical_file: Path | None = None

    def run(
        self,
        *,
        dry_run: bool = False,
        require_manual_approval: bool | None = None,
        now: datetime | None = None,
        cli_arguments: dict[str, Any] | None = None,
    ) -> Phase7RunRecord:
        if dry_run:
            with self.repository.preview_copy() as repository:
                preview = replace(
                    self, repository=repository, report_dir=self.report_dir / "dry_run"
                )
                record = preview._run(
                    dry_run=True, require_manual_approval=require_manual_approval,
                    now=now, cli_arguments=cli_arguments,
                )
                # Persist the preview lineage beside its report, never in the ledger.
                preview.report_dir.mkdir(parents=True, exist_ok=True)
                (preview.report_dir / f"{record.run_id}.json").write_text(
                    record.model_dump_json(indent=2) + "\n", encoding="utf-8"
                )
                manifest = repository.load_phase7_run_manifest(record.run_id)
                if manifest is not None:
                    (preview.report_dir / f"{record.run_id}_manifest.json").write_text(
                        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
                    )
                return record
        return self._run(
            dry_run=False, require_manual_approval=require_manual_approval,
            now=now, cli_arguments=cli_arguments,
        )

    def _run(
        self,
        *,
        dry_run: bool,
        require_manual_approval: bool | None,
        now: datetime | None,
        cli_arguments: dict[str, Any] | None,
    ) -> Phase7RunRecord:
        started_at = _as_utc(now or datetime.now(UTC))
        run_id = new_id("phase7_run")
        gate_config = _gate_config(
            self.settings.risk_gates,
            require_manual_approval=require_manual_approval,
        )
        market_source = self.market_source or self.settings.market_source
        market_id = self.market_id if self.market_id is not None else self.settings.market_id
        historical_file = (
            self.historical_file
            if self.historical_file is not None
            else self.settings.historical_file
        )
        cli_arguments = cli_arguments or _runner_cli_arguments(
            dry_run=dry_run,
            require_manual_approval=require_manual_approval,
            refresh_market_timestamp=self.refresh_market_timestamp,
            market_fixture=self.market_fixture,
            evidence_fixture=self.evidence_fixture,
            report_dir=self.report_dir,
            market_source=market_source,
            market_id=market_id,
            historical_file=historical_file,
        )
        provider_audit = llm_provider_audit(self.settings).as_dict()
        try:
            market_data_audit = phase7_market_data_audit(
                market_source,
                market_id=market_id,
                historical_file=historical_file,
            ).as_dict()
        except ValueError as exc:
            market_data_audit = {
                "market_source": market_source,
                "market_id": market_id,
                "configuration_error": str(exc),
            }
        context: dict[str, Any] = {
            "run_id": run_id,
            "dry_run": dry_run,
            "fixture_mode": market_data_audit.get("is_fixture") is True,
            "refresh_market_timestamp": self.refresh_market_timestamp,
            "live_trading_allowed": False,
            "llm_provider": provider_audit,
            "market_data": market_data_audit,
        }
        report_path: Path | None = None
        try:
            ledger = PaperLedger(self.repository, self.settings.risk)

            market_inputs = load_phase7_market_inputs(
                market_source=market_source,
                market_id=market_id,
                market_fixture=self.market_fixture,
                evidence_fixture=self.evidence_fixture,
                raw_cache_dir=self.settings.raw_cache_dir,
                now=started_at,
                refresh_market_timestamp=self.refresh_market_timestamp,
                historical_file=historical_file,
            )
            market_data_audit = market_inputs.audit.as_dict()
            context["fixture_mode"] = market_inputs.audit.is_fixture
            context["market_data"] = market_data_audit
            snapshot = market_inputs.snapshot
            context["market_id"] = snapshot.market.market_id
            context["snapshot_id"] = snapshot.snapshot_id
            self.repository.save_market_snapshot(snapshot)
            brief = ResearchBriefGenerator(
                repository=self.repository,
                provider=build_llm_provider(self.settings),
            ).generate(snapshot, market_inputs.evidence)
            context["brief_id"] = brief.brief_id
            signal = PredictionMarketEdgeStrategy(self.settings.risk).generate_signal(
                brief, snapshot
            )
            context["signal_id"] = signal.signal_id
            self.repository.save_signal(signal)
            risk_decision = RiskEngine(self.settings.risk).evaluate_signal(
                signal,
                open_positions=len(
                    [position for position in self.repository.list_positions() if position.is_open]
                ),
            )
            context["risk_decision_id"] = risk_decision.risk_decision_id
            self.repository.save_risk_decision(risk_decision)

            marks = _marks_from_snapshot(snapshot)
            portfolio_before = ledger.snapshot_portfolio(marks)
            context["portfolio_snapshot_id"] = portfolio_before.snapshot_id
            intent = _intent_from_signal(signal, snapshot, risk_decision, self.settings)
            risk_gate_decision = self._evaluate_risk_gates(
                intent=intent,
                signal=signal,
                portfolio_snapshot=portfolio_before,
                snapshot=snapshot,
                gate_config=gate_config,
                now=started_at,
            )
            context["risk_gate_decision_id"] = risk_gate_decision.risk_gate_decision_id
            order: PaperOrder | None = None
            portfolio_after = portfolio_before
            status = _status_from_gate(risk_gate_decision)
            reasons = list(risk_gate_decision.reasons)

            if intent is None or not risk_decision.is_approved:
                status = Phase7RunStatus.REJECTED
                reasons = list(risk_decision.reasons)
            elif risk_gate_decision.status == RiskGateDecisionStatus.APPROVED:
                if dry_run:
                    status = Phase7RunStatus.DRY_RUN
                    reasons = ["Dry run completed; no paper position mutation was performed."]
                else:
                    order = ledger.create_order(
                        signal=signal,
                        risk_decision=risk_decision,
                        snapshot=snapshot,
                    )
                    context["paper_order_id"] = order.order_id
                    portfolio_after = ledger.snapshot_portfolio(marks)
                    context["portfolio_snapshot_id"] = portfolio_after.snapshot_id
                    status = Phase7RunStatus.COMPLETED
                    reasons = ["Paper run completed with simulated paper order."]

            settled_position_ids = []
            if not dry_run:
                settled_position_ids = _close_historical_settlement_positions(
                    ledger=ledger,
                    market_id=snapshot.market.market_id,
                    settlement_outcome=market_data_audit.get("settlement_outcome"),
                )
            if settled_position_ids:
                context["settled_position_ids"] = settled_position_ids
                portfolio_after = ledger.snapshot_portfolio(marks)
                context["portfolio_snapshot_id"] = portfolio_after.snapshot_id
                reasons = list(reasons) + [
                    "Historical local settlement closed open paper positions."
                ]

            report_path = self.report_dir / f"phase7_daily_report_{run_id}.md"
            report_artifact = Phase7DailyReportGenerator(
                self.repository,
                output_dir=self.report_dir,
            ).generate(
                report_date=started_at.date(),
                generated_at=started_at,
                output_path=report_path,
                run_metadata={
                    "dry_run": dry_run,
                    "state_scope": "temporary preview" if dry_run else "paper ledger",
                    "market_source": market_data_audit.get("market_source"),
                    "data_mode": market_data_audit.get("data_mode"),
                    "profitability_claims_meaningful": market_data_audit.get(
                        "profitability_claims_meaningful"
                    ),
                },
            )
            manifest = build_phase7_run_manifest(
                run_id=run_id,
                settings=self.settings,
                created_at=started_at,
                market_fixture=self.market_fixture,
                evidence_fixture=self.evidence_fixture,
                report_path=report_artifact.path,
                cli_arguments=cli_arguments,
                market_data=market_data_audit,
                metadata={
                    "status": status.value,
                    "report_warnings": report_artifact.warnings,
                    "llm_provider": provider_audit,
                    "market_data": market_data_audit,
                    "settled_position_ids": context.get("settled_position_ids", []),
                },
            )
            record = Phase7RunRecord(
                run_id=run_id,
                created_at=started_at,
                completed_at=started_at,
                report_date=started_at,
                status=status,
                dry_run=dry_run,
                market_id=context.get("market_id"),
                snapshot_id=context.get("snapshot_id"),
                brief_id=context.get("brief_id"),
                signal_id=context.get("signal_id"),
                risk_decision_id=context.get("risk_decision_id"),
                risk_gate_decision_id=context.get("risk_gate_decision_id"),
                paper_order_id=order.order_id if order is not None else None,
                portfolio_snapshot_id=portfolio_after.snapshot_id,
                report_path=str(report_artifact.path),
                manifest_id=manifest.run_id,
                reasons=reasons,
                metadata={
                    "report_warnings": report_artifact.warnings,
                    "risk_gate_status": risk_gate_decision.status.value,
                    "dry_run": dry_run,
                    "fixture_mode": market_data_audit.get("is_fixture") is True,
                    "refresh_market_timestamp": self.refresh_market_timestamp,
                    "live_trading_allowed": False,
                    "manifest_id": manifest.run_id,
                    "report_checksum": manifest.report_checksum,
                    "llm_provider": provider_audit,
                    "market_data": market_data_audit,
                    "settled_position_ids": context.get("settled_position_ids", []),
                },
            )
            self.repository.save_phase7_run_manifest(manifest)
            self.repository.save_phase7_run_record(record)
            return record
        except Exception as exc:
            failed_at = _as_utc(datetime.now(UTC))
            manifest = build_phase7_run_manifest(
                run_id=run_id,
                settings=self.settings,
                created_at=started_at,
                market_fixture=self.market_fixture,
                evidence_fixture=self.evidence_fixture,
                report_path=report_path if report_path is not None and report_path.exists() else None,
                cli_arguments=cli_arguments,
                market_data=market_data_audit,
                metadata={
                    "status": Phase7RunStatus.FAILED.value,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "partial_context": context,
                    "llm_provider": provider_audit,
                    "market_data": market_data_audit,
                },
            )
            record = Phase7RunRecord(
                run_id=run_id,
                created_at=started_at,
                completed_at=failed_at,
                report_date=started_at,
                status=Phase7RunStatus.FAILED,
                dry_run=dry_run,
                market_id=context.get("market_id"),
                snapshot_id=context.get("snapshot_id"),
                brief_id=context.get("brief_id"),
                signal_id=context.get("signal_id"),
                risk_decision_id=context.get("risk_decision_id"),
                risk_gate_decision_id=context.get("risk_gate_decision_id"),
                paper_order_id=context.get("paper_order_id"),
                portfolio_snapshot_id=context.get("portfolio_snapshot_id"),
                report_path=manifest.report_path,
                manifest_id=manifest.run_id,
                reasons=[f"Phase 7 paper run failed: {exc}"],
                metadata={
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "failed_at": failed_at.isoformat(),
                    "partial_context": context,
                    "manifest_id": manifest.run_id,
                    "report_checksum": manifest.report_checksum,
                    "dry_run": dry_run,
                    "fixture_mode": market_data_audit.get("is_fixture") is True,
                    "refresh_market_timestamp": self.refresh_market_timestamp,
                    "live_trading_allowed": False,
                    "llm_provider": provider_audit,
                    "market_data": market_data_audit,
                },
            )
            self.repository.save_phase7_run_manifest(manifest)
            self.repository.save_phase7_run_record(record)
            return record

    def _evaluate_risk_gates(
        self,
        *,
        intent: PaperOrderIntent | None,
        signal: Signal,
        portfolio_snapshot: PortfolioSnapshot,
        snapshot: MarketSnapshot,
        gate_config: RiskGateConfig,
        now: datetime,
    ) -> RiskGateDecision:
        if intent is None:
            intent = PaperOrderIntent(
                signal_id=signal.signal_id,
                market_id=signal.market_id,
                side=OrderSide.BUY,
                quantity=1,
                limit_price=snapshot.last_price or snapshot.market_implied_probability or 0.5,
                notional=1,
                metadata={"placeholder": "non-actionable signal had no paper order intent"},
            )
        return RiskGateEvaluator(
            config=gate_config,
            repository=self.repository,
        ).evaluate(
            signal=signal,
            intent=intent,
            portfolio_snapshot=portfolio_snapshot,
            positions=self.repository.list_positions(),
            recent_fills=self.repository.list_paper_fills(),
            market_data_as_of=snapshot.as_of,
            now=now,
        )


def _intent_from_signal(
    signal: Signal,
    snapshot: MarketSnapshot,
    risk_decision: RiskDecision,
    settings: Settings,
) -> PaperOrderIntent | None:
    if signal.action not in ACTIONABLE_PAPER_BUYS or not risk_decision.is_approved:
        return None

    side, limit_price = _paper_side_and_limit(signal, snapshot)
    if limit_price is None:
        return None
    notional = min(
        settings.risk.paper_starting_cash * risk_decision.max_position_pct,
        risk_decision.max_position_usd,
    )
    return PaperOrderIntent(
        signal_id=signal.signal_id,
        market_id=signal.market_id,
        side=side,
        quantity=round(notional / limit_price, 8),
        limit_price=limit_price,
        notional=round(notional, 4),
        metadata={"source": "phase7_daily_runner"},
    )


def _paper_side_and_limit(
    signal: Signal,
    snapshot: MarketSnapshot,
) -> tuple[OrderSide, float | None]:
    if signal.action == SignalAction.PAPER_BUY_YES:
        return (
            OrderSide.BUY_YES,
            snapshot.best_ask or snapshot.last_price or snapshot.market_implied_probability,
        )
    no_price = None
    if snapshot.best_bid is not None:
        no_price = 1 - snapshot.best_bid
    elif snapshot.market_implied_probability is not None:
        no_price = 1 - snapshot.market_implied_probability
    return (OrderSide.BUY_NO, no_price)


def _marks_from_snapshot(snapshot: MarketSnapshot) -> dict[str, float]:
    mark = snapshot.last_price or snapshot.market_implied_probability
    if mark is None:
        return {}
    return {snapshot.market.market_id: mark}


def _close_historical_settlement_positions(
    *,
    ledger: PaperLedger,
    market_id: str,
    settlement_outcome: object,
) -> list[str]:
    if settlement_outcome not in {"yes", "no"}:
        return []
    yes_wins = settlement_outcome == "yes"
    closed_position_ids: list[str] = []
    for position in ledger.open_positions():
        if position.market_id != market_id:
            continue
        if position.side == OrderSide.BUY_YES:
            close_price = 1.0 if yes_wins else 0.0
        elif position.side == OrderSide.BUY_NO:
            close_price = 0.0 if yes_wins else 1.0
        else:
            continue
        closed = ledger.close_position(position.position_id, close_price=close_price)
        closed_position_ids.append(closed.position_id)
    return closed_position_ids


def _status_from_gate(decision: RiskGateDecision) -> Phase7RunStatus:
    if decision.status == RiskGateDecisionStatus.HALTED:
        return Phase7RunStatus.HALTED
    if decision.status == RiskGateDecisionStatus.PENDING_MANUAL_APPROVAL:
        return Phase7RunStatus.PENDING_MANUAL_APPROVAL
    if decision.status == RiskGateDecisionStatus.REJECTED:
        return Phase7RunStatus.REJECTED
    return Phase7RunStatus.COMPLETED


def _gate_config(
    config: RiskGateConfig,
    *,
    require_manual_approval: bool | None,
) -> RiskGateConfig:
    if require_manual_approval is None:
        return config
    return replace(config, require_manual_approval=require_manual_approval)


def _runner_cli_arguments(
    *,
    dry_run: bool,
    require_manual_approval: bool | None,
    refresh_market_timestamp: bool,
    market_fixture: Path,
    evidence_fixture: Path,
    report_dir: Path,
    market_source: str,
    market_id: str | None,
    historical_file: Path | None,
) -> dict[str, Any]:
    return {
        "source": "runner",
        "dry_run": dry_run,
        "require_manual_approval": require_manual_approval,
        "refresh_market_timestamp": refresh_market_timestamp,
        "market_source": market_source,
        "market_id": market_id,
        "historical_file": str(historical_file) if historical_file is not None else None,
        "fixture": str(market_fixture),
        "evidence": str(evidence_fixture),
        "report_dir": str(report_dir),
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
