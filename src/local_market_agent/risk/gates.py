from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from local_market_agent.config import RiskGateConfig
from local_market_agent.schemas import (
    PaperFill,
    PaperOrderIntent,
    PortfolioSnapshot,
    Position,
    RiskGateCheck,
    RiskGateDecision,
    RiskGateDecisionStatus,
    Signal,
)
from local_market_agent.schemas.models import ExecutionMode, SignalAction
from local_market_agent.storage import SQLiteRepository

ACTIONABLE_PAPER_BUYS = {
    SignalAction.PAPER_BUY_YES,
    SignalAction.PAPER_BUY_NO,
}


@dataclass
class RiskGateEvaluator:
    config: RiskGateConfig = RiskGateConfig()
    repository: SQLiteRepository | None = None

    def evaluate(
        self,
        *,
        intent: PaperOrderIntent,
        portfolio_snapshot: PortfolioSnapshot,
        positions: Sequence[Position],
        recent_fills: Sequence[PaperFill],
        market_data_as_of: datetime,
        signal: Signal | None = None,
        now: datetime | None = None,
        persist: bool = True,
    ) -> RiskGateDecision:
        evaluated_at = _as_utc(now or datetime.now(UTC))
        market_data_as_of = _as_utc(market_data_as_of)
        checks: list[RiskGateCheck] = []
        rejected_reasons: list[str] = []
        halted_reasons: list[str] = []

        self._evaluate_signal_match(signal, intent, checks, rejected_reasons)
        self._evaluate_market_data_freshness(
            market_data_as_of,
            evaluated_at,
            checks,
            rejected_reasons,
        )
        self._evaluate_daily_new_positions(
            recent_fills,
            evaluated_at,
            checks,
            rejected_reasons,
        )
        position_size_pct = self._evaluate_position_size(
            intent,
            portfolio_snapshot,
            checks,
            rejected_reasons,
        )
        projected_exposure_pct = self._evaluate_portfolio_exposure(
            intent,
            portfolio_snapshot,
            checks,
            rejected_reasons,
        )
        daily_drawdown_pct = self._evaluate_daily_drawdown(
            portfolio_snapshot,
            checks,
            halted_reasons,
        )
        consecutive_losses, cooldown_until = self._evaluate_consecutive_losses(
            positions,
            evaluated_at,
            checks,
            halted_reasons,
        )

        manual_reason = "Manual approval is required before accepting paper orders."
        if halted_reasons:
            status = RiskGateDecisionStatus.HALTED
            reasons = halted_reasons + rejected_reasons
        elif rejected_reasons:
            status = RiskGateDecisionStatus.REJECTED
            reasons = rejected_reasons
        elif self.config.require_manual_approval:
            status = RiskGateDecisionStatus.PENDING_MANUAL_APPROVAL
            reasons = [manual_reason]
            checks.append(
                RiskGateCheck(
                    gate="manual_approval",
                    status=RiskGateDecisionStatus.PENDING_MANUAL_APPROVAL,
                    passed=False,
                    reason=manual_reason,
                    observed=True,
                    limit=True,
                )
            )
        else:
            status = RiskGateDecisionStatus.APPROVED
            reasons = ["Approved by paper risk gates; live orders remain disabled."]
            checks.append(
                RiskGateCheck(
                    gate="manual_approval",
                    status=RiskGateDecisionStatus.APPROVED,
                    passed=True,
                    reason="Manual approval is not required by risk gate configuration.",
                    observed=False,
                    limit=False,
                )
            )

        decision = RiskGateDecision(
            intent_id=intent.intent_id,
            signal_id=intent.signal_id,
            market_id=intent.market_id,
            status=status,
            reasons=reasons,
            checks=checks,
            config_snapshot=self.config.as_dict(),
            metadata={
                "evaluated_at": evaluated_at.isoformat(),
                "market_data_as_of": market_data_as_of.isoformat(),
                "market_data_age_seconds": round(
                    max(0.0, (evaluated_at - market_data_as_of).total_seconds()),
                    4,
                ),
                "position_size_pct": position_size_pct,
                "projected_exposure_pct": projected_exposure_pct,
                "daily_drawdown_pct": daily_drawdown_pct,
                "consecutive_losses": consecutive_losses,
                "consecutive_loss_cooldown_until": (
                    cooldown_until.isoformat() if cooldown_until is not None else None
                ),
            },
        )
        if persist and self.repository is not None:
            self.repository.save_risk_gate_decision(decision)
        return decision

    def export_jsonl(self, path: str | Path) -> Path:
        if self.repository is None:
            msg = "risk gate decision export requires a repository"
            raise ValueError(msg)
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for payload in self.repository.export_payloads("risk_gate_decisions"):
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return output

    def _evaluate_signal_match(
        self,
        signal: Signal | None,
        intent: PaperOrderIntent,
        checks: list[RiskGateCheck],
        rejected_reasons: list[str],
    ) -> None:
        if signal is None:
            checks.append(
                RiskGateCheck(
                    gate="paper_signal",
                    status=RiskGateDecisionStatus.APPROVED,
                    passed=True,
                    reason="No signal object supplied; intent signal_id is preserved for audit.",
                    observed=intent.signal_id,
                    limit="paper signal audit reference",
                )
            )
            return

        reasons: list[str] = []
        if signal.signal_id != intent.signal_id:
            reasons.append("Signal ID does not match paper order intent.")
        if signal.market_id != intent.market_id:
            reasons.append("Signal market does not match paper order intent.")
        if signal.execution_mode != ExecutionMode.PAPER:
            reasons.append("Risk gates only accept paper-mode signals.")
        if signal.action not in ACTIONABLE_PAPER_BUYS:
            reasons.append("Risk gates only accept paper_buy_yes/no signals.")

        if reasons:
            reason = " ".join(reasons)
            rejected_reasons.append(reason)
            checks.append(
                RiskGateCheck(
                    gate="paper_signal",
                    status=RiskGateDecisionStatus.REJECTED,
                    passed=False,
                    reason=reason,
                    observed=signal.signal_id,
                    limit=intent.signal_id,
                )
            )
            return

        checks.append(
            RiskGateCheck(
                gate="paper_signal",
                status=RiskGateDecisionStatus.APPROVED,
                passed=True,
                reason="Paper signal matches paper order intent.",
                observed=signal.signal_id,
                limit=intent.signal_id,
            )
        )

    def _evaluate_market_data_freshness(
        self,
        market_data_as_of: datetime,
        evaluated_at: datetime,
        checks: list[RiskGateCheck],
        rejected_reasons: list[str],
    ) -> None:
        age_seconds = max(0.0, (evaluated_at - market_data_as_of).total_seconds())
        if age_seconds > self.config.max_market_data_age_seconds:
            reason = "Market data is stale for paper risk gate evaluation."
            rejected_reasons.append(reason)
            checks.append(
                RiskGateCheck(
                    gate="market_data_freshness",
                    status=RiskGateDecisionStatus.REJECTED,
                    passed=False,
                    reason=reason,
                    observed=round(age_seconds, 4),
                    limit=self.config.max_market_data_age_seconds,
                )
            )
            return
        checks.append(
            RiskGateCheck(
                gate="market_data_freshness",
                status=RiskGateDecisionStatus.APPROVED,
                passed=True,
                reason="Market data is fresh enough for paper evaluation.",
                observed=round(age_seconds, 4),
                limit=self.config.max_market_data_age_seconds,
            )
        )

    def _evaluate_daily_new_positions(
        self,
        recent_fills: Sequence[PaperFill],
        evaluated_at: datetime,
        checks: list[RiskGateCheck],
        rejected_reasons: list[str],
    ) -> None:
        new_positions_today = sum(
            1
            for fill in recent_fills
            if not fill.is_closing and _as_utc(fill.filled_at).date() == evaluated_at.date()
        )
        if new_positions_today >= self.config.max_daily_new_positions:
            reason = "Daily new paper position limit reached."
            rejected_reasons.append(reason)
            checks.append(
                RiskGateCheck(
                    gate="daily_new_positions",
                    status=RiskGateDecisionStatus.REJECTED,
                    passed=False,
                    reason=reason,
                    observed=new_positions_today,
                    limit=self.config.max_daily_new_positions,
                )
            )
            return
        checks.append(
            RiskGateCheck(
                gate="daily_new_positions",
                status=RiskGateDecisionStatus.APPROVED,
                passed=True,
                reason="Daily new paper position count is within limit.",
                observed=new_positions_today,
                limit=self.config.max_daily_new_positions,
            )
        )

    def _evaluate_position_size(
        self,
        intent: PaperOrderIntent,
        portfolio_snapshot: PortfolioSnapshot,
        checks: list[RiskGateCheck],
        rejected_reasons: list[str],
    ) -> float:
        position_size_pct = _safe_pct(intent.notional, portfolio_snapshot.portfolio_value)
        if position_size_pct > self.config.max_position_size_pct:
            reason = "Paper order intent exceeds max position size percentage."
            rejected_reasons.append(reason)
            checks.append(
                RiskGateCheck(
                    gate="position_size",
                    status=RiskGateDecisionStatus.REJECTED,
                    passed=False,
                    reason=reason,
                    observed=position_size_pct,
                    limit=self.config.max_position_size_pct,
                )
            )
            return position_size_pct
        checks.append(
            RiskGateCheck(
                gate="position_size",
                status=RiskGateDecisionStatus.APPROVED,
                passed=True,
                reason="Paper order intent size is within limit.",
                observed=position_size_pct,
                limit=self.config.max_position_size_pct,
            )
        )
        return position_size_pct

    def _evaluate_portfolio_exposure(
        self,
        intent: PaperOrderIntent,
        portfolio_snapshot: PortfolioSnapshot,
        checks: list[RiskGateCheck],
        rejected_reasons: list[str],
    ) -> float:
        current_exposure = sum(max(0.0, value) for value in portfolio_snapshot.market_values.values())
        projected_exposure_pct = _safe_pct(
            current_exposure + intent.notional,
            portfolio_snapshot.portfolio_value,
        )
        if projected_exposure_pct > self.config.max_total_portfolio_exposure_pct:
            reason = "Projected paper portfolio exposure exceeds configured limit."
            rejected_reasons.append(reason)
            checks.append(
                RiskGateCheck(
                    gate="portfolio_exposure",
                    status=RiskGateDecisionStatus.REJECTED,
                    passed=False,
                    reason=reason,
                    observed=projected_exposure_pct,
                    limit=self.config.max_total_portfolio_exposure_pct,
                    metadata={"current_exposure": round(current_exposure, 4)},
                )
            )
            return projected_exposure_pct
        checks.append(
            RiskGateCheck(
                gate="portfolio_exposure",
                status=RiskGateDecisionStatus.APPROVED,
                passed=True,
                reason="Projected paper portfolio exposure is within limit.",
                observed=projected_exposure_pct,
                limit=self.config.max_total_portfolio_exposure_pct,
                metadata={"current_exposure": round(current_exposure, 4)},
            )
        )
        return projected_exposure_pct

    def _evaluate_daily_drawdown(
        self,
        portfolio_snapshot: PortfolioSnapshot,
        checks: list[RiskGateCheck],
        halted_reasons: list[str],
    ) -> float:
        if portfolio_snapshot.starting_cash <= 0:
            reason = "Cannot evaluate drawdown with zero starting cash."
            halted_reasons.append(reason)
            checks.append(
                RiskGateCheck(
                    gate="daily_drawdown",
                    status=RiskGateDecisionStatus.HALTED,
                    passed=False,
                    reason=reason,
                    observed=portfolio_snapshot.starting_cash,
                    limit="starting_cash > 0",
                )
            )
            return 1.0

        drawdown_pct = max(
            0.0,
            round(
                (portfolio_snapshot.starting_cash - portfolio_snapshot.portfolio_value)
                / portfolio_snapshot.starting_cash,
                8,
            ),
        )
        if drawdown_pct >= self.config.daily_drawdown_limit_pct:
            reason = "Daily drawdown circuit breaker is active."
            halted_reasons.append(reason)
            checks.append(
                RiskGateCheck(
                    gate="daily_drawdown",
                    status=RiskGateDecisionStatus.HALTED,
                    passed=False,
                    reason=reason,
                    observed=drawdown_pct,
                    limit=self.config.daily_drawdown_limit_pct,
                )
            )
            return drawdown_pct
        checks.append(
            RiskGateCheck(
                gate="daily_drawdown",
                status=RiskGateDecisionStatus.APPROVED,
                passed=True,
                reason="Daily drawdown is within circuit breaker limit.",
                observed=drawdown_pct,
                limit=self.config.daily_drawdown_limit_pct,
            )
        )
        return drawdown_pct

    def _evaluate_consecutive_losses(
        self,
        positions: Sequence[Position],
        evaluated_at: datetime,
        checks: list[RiskGateCheck],
        halted_reasons: list[str],
    ) -> tuple[int, datetime | None]:
        closed_positions = sorted(
            (
                position
                for position in positions
                if not position.is_open and position.closed_at is not None
            ),
            key=lambda position: _as_utc(position.closed_at or evaluated_at),
            reverse=True,
        )
        consecutive_losses = 0
        latest_loss_closed_at: datetime | None = None
        for position in closed_positions:
            if position.realized_pnl >= 0:
                break
            consecutive_losses += 1
            if latest_loss_closed_at is None:
                latest_loss_closed_at = _as_utc(position.closed_at or evaluated_at)

        cooldown_until = None
        if (
            consecutive_losses >= self.config.max_consecutive_losses
            and latest_loss_closed_at is not None
        ):
            cooldown_until = latest_loss_closed_at + timedelta(
                hours=self.config.consecutive_loss_cooldown_hours
            )
            if evaluated_at < cooldown_until:
                reason = "Consecutive loss circuit breaker cooldown is active."
                halted_reasons.append(reason)
                checks.append(
                    RiskGateCheck(
                        gate="consecutive_losses",
                        status=RiskGateDecisionStatus.HALTED,
                        passed=False,
                        reason=reason,
                        observed=consecutive_losses,
                        limit=self.config.max_consecutive_losses,
                        metadata={"cooldown_until": cooldown_until.isoformat()},
                    )
                )
                return consecutive_losses, cooldown_until

        checks.append(
            RiskGateCheck(
                gate="consecutive_losses",
                status=RiskGateDecisionStatus.APPROVED,
                passed=True,
                reason="Consecutive loss count is within cooldown limits.",
                observed=consecutive_losses,
                limit=self.config.max_consecutive_losses,
                metadata={
                    "cooldown_until": cooldown_until.isoformat()
                    if cooldown_until is not None
                    else None
                },
            )
        )
        return consecutive_losses, cooldown_until


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _safe_pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 1.0
    return round(numerator / denominator, 8)
