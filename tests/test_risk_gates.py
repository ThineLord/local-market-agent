from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from local_market_agent.config import RiskGateConfig
from local_market_agent.risk import RiskGateEvaluator
from local_market_agent.schemas.models import (
    OrderSide,
    PaperFill,
    PaperOrderIntent,
    PortfolioSnapshot,
    Position,
    RiskGateDecisionStatus,
    Signal,
    SignalAction,
)

NOW = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)


def _signal(brief) -> Signal:
    return Signal(
        brief_id=brief.brief_id,
        market_id=brief.market_id,
        action=SignalAction.PAPER_BUY_YES,
        agent_probability=0.65,
        market_probability=0.50,
        spread=0.03,
        edge=0.15,
        confidence=0.8,
        evidence_quality=0.8,
        rationale="test paper gate signal",
    )


def _intent(signal: Signal, *, notional: float = 100.0) -> PaperOrderIntent:
    return PaperOrderIntent(
        signal_id=signal.signal_id,
        market_id=signal.market_id,
        side=OrderSide.BUY_YES,
        quantity=100,
        limit_price=0.50,
        notional=notional,
    )


def _portfolio(
    *,
    starting_cash: float = 10_000.0,
    portfolio_value: float = 10_000.0,
    market_values: dict[str, float] | None = None,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        starting_cash=starting_cash,
        cash_balance=portfolio_value,
        portfolio_value=portfolio_value,
        realized_pnl=0,
        unrealized_pnl=portfolio_value - starting_cash,
        total_fees=0,
        open_positions=len(market_values or {}),
        closed_positions=0,
        total_positions=len(market_values or {}),
        market_values=market_values or {},
    )


def _opening_fill(signal: Signal, index: int, *, filled_at: datetime = NOW) -> PaperFill:
    return PaperFill(
        fill_id=f"paper_fill_{index}",
        order_id=f"paper_order_{index}",
        position_id=f"position_{index}",
        signal_id=signal.signal_id,
        risk_decision_id=f"risk_{index}",
        market_id=signal.market_id,
        filled_at=filled_at,
        side=OrderSide.BUY_YES,
        quantity=1,
        price=0.5,
    )


def _closed_position(signal: Signal, index: int, *, pnl: float, closed_at: datetime) -> Position:
    return Position(
        position_id=f"position_{index}",
        market_id=signal.market_id,
        signal_id=signal.signal_id,
        risk_decision_id=f"risk_{index}",
        order_id=f"paper_order_{index}",
        side=OrderSide.BUY_YES,
        quantity=1,
        average_price=0.5,
        opened_at=closed_at - timedelta(hours=1),
        closed_at=closed_at,
        close_price=0.4 if pnl < 0 else 0.6,
        realized_pnl=pnl,
    )


def _evaluate(
    *,
    signal: Signal,
    config: RiskGateConfig | None = None,
    intent: PaperOrderIntent | None = None,
    portfolio_snapshot: PortfolioSnapshot | None = None,
    positions: list[Position] | None = None,
    recent_fills: list[PaperFill] | None = None,
    market_data_as_of: datetime | None = None,
    repo=None,
):
    return RiskGateEvaluator(
        config=config or RiskGateConfig(require_manual_approval=False),
        repository=repo,
    ).evaluate(
        signal=signal,
        intent=intent or _intent(signal),
        portfolio_snapshot=portfolio_snapshot or _portfolio(),
        positions=positions or [],
        recent_fills=recent_fills or [],
        market_data_as_of=market_data_as_of or NOW,
        now=NOW,
    )


def test_approved_risk_gate_decision_persists_and_exports(repo, brief, tmp_path: Path):
    signal = _signal(brief)
    decision = _evaluate(signal=signal, repo=repo)

    assert decision.status == RiskGateDecisionStatus.APPROVED
    assert decision.is_approved
    assert repo.load_risk_gate_decision(decision.risk_gate_decision_id) == decision

    output = RiskGateEvaluator(repository=repo).export_jsonl(tmp_path / "risk_gates.jsonl")
    payload = output.read_text(encoding="utf-8")
    assert decision.risk_gate_decision_id in payload
    assert "market_data_freshness" in payload


def test_stale_market_data_rejects(brief):
    signal = _signal(brief)
    decision = _evaluate(
        signal=signal,
        market_data_as_of=NOW - timedelta(minutes=6),
    )

    assert decision.status == RiskGateDecisionStatus.REJECTED
    assert any(check.gate == "market_data_freshness" for check in decision.checks)
    assert any("stale" in reason.lower() for reason in decision.reasons)


def test_too_many_daily_new_positions_rejects(brief):
    signal = _signal(brief)
    fills = [_opening_fill(signal, index) for index in range(3)]
    decision = _evaluate(signal=signal, recent_fills=fills)

    assert decision.status == RiskGateDecisionStatus.REJECTED
    assert any(check.gate == "daily_new_positions" for check in decision.checks)
    assert any("daily new paper position limit" in reason.lower() for reason in decision.reasons)


def test_oversized_position_rejects(brief):
    signal = _signal(brief)
    decision = _evaluate(signal=signal, intent=_intent(signal, notional=1_100.0))

    assert decision.status == RiskGateDecisionStatus.REJECTED
    assert any(check.gate == "position_size" for check in decision.checks)
    assert any("max position size" in reason.lower() for reason in decision.reasons)


def test_over_exposure_rejects(brief):
    signal = _signal(brief)
    decision = _evaluate(
        signal=signal,
        portfolio_snapshot=_portfolio(market_values={"existing_position": 5_000.0}),
    )

    assert decision.status == RiskGateDecisionStatus.REJECTED
    assert any(check.gate == "portfolio_exposure" for check in decision.checks)
    assert any("exposure" in reason.lower() for reason in decision.reasons)


def test_drawdown_breach_halts_new_positions(brief):
    signal = _signal(brief)
    decision = _evaluate(
        signal=signal,
        portfolio_snapshot=_portfolio(portfolio_value=9_600.0),
    )

    assert decision.status == RiskGateDecisionStatus.HALTED
    assert decision.is_halted
    assert any(check.gate == "daily_drawdown" for check in decision.checks)
    assert any("drawdown" in reason.lower() for reason in decision.reasons)


def test_consecutive_losses_trigger_cooldown_halt(brief):
    signal = _signal(brief)
    positions = [
        _closed_position(
            signal,
            index,
            pnl=-10.0,
            closed_at=NOW - timedelta(minutes=index + 1),
        )
        for index in range(5)
    ]
    decision = _evaluate(signal=signal, positions=positions)

    assert decision.status == RiskGateDecisionStatus.HALTED
    assert decision.metadata["consecutive_losses"] == 5
    assert any(check.gate == "consecutive_losses" for check in decision.checks)
    assert any("consecutive loss" in reason.lower() for reason in decision.reasons)


def test_manual_approval_returns_pending_instead_of_approved(brief):
    signal = _signal(brief)
    decision = _evaluate(signal=signal, config=RiskGateConfig(require_manual_approval=True))

    assert decision.status == RiskGateDecisionStatus.PENDING_MANUAL_APPROVAL
    assert decision.requires_manual_approval
    assert not decision.is_approved
    assert any(check.gate == "manual_approval" for check in decision.checks)
