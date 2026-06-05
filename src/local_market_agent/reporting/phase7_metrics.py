from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from local_market_agent.schemas import Phase7RunStatus
from local_market_agent.storage import SQLiteRepository


@dataclass(frozen=True)
class Phase7EquityCurvePoint:
    as_of: datetime
    portfolio_value: float
    realized_pnl: float
    unrealized_pnl: float

    def as_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of.isoformat(),
            "portfolio_value": self.portfolio_value,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
        }


@dataclass(frozen=True)
class Phase7Metrics:
    equity_curve: list[Phase7EquityCurvePoint]
    win_rate: float | None
    profit_factor: float | None
    max_drawdown: float
    run_success_rate: float | None
    total_runs: int
    successful_runs: int
    failed_runs: int
    closed_positions: int
    winning_positions: int
    losing_positions: int

    def as_dict(self) -> dict[str, object]:
        return {
            "equity_curve": [point.as_dict() for point in self.equity_curve],
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "max_drawdown": self.max_drawdown,
            "run_success_rate": self.run_success_rate,
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "closed_positions": self.closed_positions,
            "winning_positions": self.winning_positions,
            "losing_positions": self.losing_positions,
        }


@dataclass
class Phase7MetricsCalculator:
    repository: SQLiteRepository

    def compute(self) -> Phase7Metrics:
        snapshots = sorted(
            self.repository.list_portfolio_snapshots(),
            key=lambda snapshot: snapshot.as_of,
        )
        equity_curve = [
            Phase7EquityCurvePoint(
                as_of=snapshot.as_of,
                portfolio_value=snapshot.portfolio_value,
                realized_pnl=snapshot.realized_pnl,
                unrealized_pnl=snapshot.unrealized_pnl,
            )
            for snapshot in snapshots
        ]

        closed_positions = [
            position for position in self.repository.list_positions() if not position.is_open
        ]
        wins = [position for position in closed_positions if position.realized_pnl > 0]
        losses = [position for position in closed_positions if position.realized_pnl < 0]
        gross_profit = round(sum(position.realized_pnl for position in wins), 4)
        gross_loss = round(abs(sum(position.realized_pnl for position in losses)), 4)
        win_rate = (
            round(len(wins) / len(closed_positions), 8) if closed_positions else None
        )
        profit_factor = round(gross_profit / gross_loss, 8) if gross_loss > 0 else None

        runs = self.repository.list_phase7_run_records()
        failed_runs = len([record for record in runs if record.status == Phase7RunStatus.FAILED])
        successful_runs = len(runs) - failed_runs
        run_success_rate = round(successful_runs / len(runs), 8) if runs else None

        return Phase7Metrics(
            equity_curve=equity_curve,
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown=_max_drawdown(equity_curve),
            run_success_rate=run_success_rate,
            total_runs=len(runs),
            successful_runs=successful_runs,
            failed_runs=failed_runs,
            closed_positions=len(closed_positions),
            winning_positions=len(wins),
            losing_positions=len(losses),
        )


def _max_drawdown(points: list[Phase7EquityCurvePoint]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for point in points:
        if point.portfolio_value > peak:
            peak = point.portfolio_value
        if peak <= 0:
            continue
        drawdown = (peak - point.portfolio_value) / peak
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return round(max_drawdown, 8)
