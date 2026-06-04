from __future__ import annotations

from dataclasses import dataclass

from local_market_agent.config import RiskConfig
from local_market_agent.schemas.models import (
    ExecutionMode,
    RiskDecision,
    RiskStatus,
    Signal,
    SignalAction,
)

ACTIONABLE_PAPER_BUYS = {
    SignalAction.PAPER_BUY_YES,
    SignalAction.PAPER_BUY_NO,
}


@dataclass
class RiskEngine:
    config: RiskConfig = RiskConfig()

    def evaluate_signal(
        self,
        signal: Signal,
        *,
        open_positions: int = 0,
        daily_loss_pct: float = 0.0,
        total_drawdown_pct: float = 0.0,
        live_order_requested: bool = False,
        leverage_requested: bool = False,
        derivative_requested: bool = False,
    ) -> RiskDecision:
        reasons: list[str] = []

        if (
            self.config.no_live_trading or not self.config.live_trading_allowed
        ) and (signal.execution_mode == ExecutionMode.LIVE or live_order_requested):
            reasons.append("Live trading is disabled and vetoed.")
        if leverage_requested and self.config.no_leverage:
            reasons.append("Leverage is disabled.")
        if derivative_requested and self.config.no_derivatives:
            reasons.append("Derivatives are disabled.")
        if signal.action == SignalAction.PAPER_SELL:
            reasons.append("Shorting is disabled; standalone paper_sell is vetoed.")
        if signal.action not in ACTIONABLE_PAPER_BUYS:
            reasons.append("Only paper_buy_yes/no signals can be approved for paper orders.")
        if signal.confidence < self.config.min_confidence:
            reasons.append("Signal confidence is below the risk threshold.")
        if signal.evidence_quality < 0.65:
            reasons.append("Signal evidence quality is below the risk threshold.")
        if signal.edge is None or signal.edge < self.config.min_edge:
            reasons.append("Signal edge is missing or below the risk threshold.")
        if signal.spread is None or signal.spread > self.config.max_spread:
            reasons.append("Signal spread is missing or too wide.")
        if open_positions >= self.config.max_open_positions:
            reasons.append("Maximum open positions limit reached.")
        if daily_loss_pct >= self.config.max_daily_loss_pct:
            reasons.append("Daily loss limit reached.")
        if total_drawdown_pct >= self.config.max_total_drawdown_pct:
            reasons.append("Total drawdown limit reached.")

        status = RiskStatus.VETOED if reasons else RiskStatus.APPROVED
        if status == RiskStatus.APPROVED:
            reasons = ["Approved for paper trading only; live orders remain disabled."]

        return RiskDecision(
            signal_id=signal.signal_id,
            status=status,
            reasons=reasons,
            max_position_pct=self.config.max_position_pct,
            max_position_usd=self.config.paper_starting_cash * self.config.max_position_pct,
            requires_human_approval=self.config.compliance_requires_manual_approval,
            live_trading_allowed=self.config.live_trading_allowed,
            config_snapshot=self.config.as_dict(),
        )
