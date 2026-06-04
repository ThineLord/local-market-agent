from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from local_market_agent.adapters import FixtureAdapter
from local_market_agent.agents import ResearchBriefGenerator
from local_market_agent.config import RiskGateConfig, Settings
from local_market_agent.llm import MockLLMProvider
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
from local_market_agent.schemas.models import OrderSide, SignalAction
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

    def run(
        self,
        *,
        dry_run: bool = False,
        require_manual_approval: bool | None = None,
        now: datetime | None = None,
    ) -> Phase7RunRecord:
        started_at = _as_utc(now or datetime.now(UTC))
        gate_config = _gate_config(
            self.settings.risk_gates,
            require_manual_approval=require_manual_approval,
        )
        ledger = PaperLedger(self.repository, self.settings.risk)

        snapshot = self._load_snapshot(started_at)
        self.repository.save_market_snapshot(snapshot)
        evidence = FixtureAdapter(self.market_fixture, self.evidence_fixture).fetch_evidence(
            snapshot.market.market_id
        )
        brief = ResearchBriefGenerator(
            repository=self.repository,
            provider=MockLLMProvider(),
        ).generate(snapshot, evidence)
        signal = PredictionMarketEdgeStrategy(self.settings.risk).generate_signal(brief, snapshot)
        self.repository.save_signal(signal)
        risk_decision = RiskEngine(self.settings.risk).evaluate_signal(
            signal,
            open_positions=len([position for position in self.repository.list_positions() if position.is_open]),
        )
        self.repository.save_risk_decision(risk_decision)

        marks = _marks_from_snapshot(snapshot)
        portfolio_before = ledger.snapshot_portfolio(marks)
        intent = _intent_from_signal(signal, snapshot, risk_decision, self.settings)
        risk_gate_decision = self._evaluate_risk_gates(
            intent=intent,
            signal=signal,
            portfolio_snapshot=portfolio_before,
            snapshot=snapshot,
            gate_config=gate_config,
            now=started_at,
        )
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
                portfolio_after = ledger.snapshot_portfolio(marks)
                status = Phase7RunStatus.COMPLETED
                reasons = ["Paper run completed with simulated paper order."]

        report_artifact = Phase7DailyReportGenerator(
            self.repository,
            output_dir=self.report_dir,
        ).generate(
            report_date=started_at.date(),
            generated_at=started_at,
            output_path=self.report_dir / f"phase7_daily_report_{started_at.date().isoformat()}.md",
        )
        record = Phase7RunRecord(
            created_at=started_at,
            completed_at=started_at,
            report_date=started_at,
            status=status,
            dry_run=dry_run,
            market_id=snapshot.market.market_id,
            snapshot_id=snapshot.snapshot_id,
            brief_id=brief.brief_id,
            signal_id=signal.signal_id,
            risk_decision_id=risk_decision.risk_decision_id,
            risk_gate_decision_id=(
                risk_gate_decision.risk_gate_decision_id if risk_gate_decision is not None else None
            ),
            paper_order_id=order.order_id if order is not None else None,
            portfolio_snapshot_id=portfolio_after.snapshot_id,
            report_path=str(report_artifact.path),
            reasons=reasons,
            metadata={
                "report_warnings": report_artifact.warnings,
                "risk_gate_status": (
                    risk_gate_decision.status.value if risk_gate_decision is not None else None
                ),
                "dry_run": dry_run,
                "fixture_mode": True,
                "refresh_market_timestamp": self.refresh_market_timestamp,
                "live_trading_allowed": False,
            },
        )
        self.repository.save_phase7_run_record(record)
        return record

    def _load_snapshot(self, now: datetime) -> MarketSnapshot:
        snapshot = FixtureAdapter(self.market_fixture, self.evidence_fixture).fetch_snapshot()
        if not self.refresh_market_timestamp:
            return snapshot
        return snapshot.model_copy(update={"as_of": now})

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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
