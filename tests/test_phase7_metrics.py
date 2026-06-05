from __future__ import annotations

from datetime import UTC, datetime, timedelta

from local_market_agent.reporting import Phase7MetricsCalculator
from local_market_agent.schemas.models import (
    OrderSide,
    Phase7RunRecord,
    Phase7RunStatus,
    PortfolioSnapshot,
    Position,
)

NOW = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)


def test_phase7_metrics_calculator_rolls_up_local_records(repo):
    for index, value in enumerate([10_000.0, 11_000.0, 9_900.0]):
        repo.save_portfolio_snapshot(
            PortfolioSnapshot(
                as_of=NOW + timedelta(days=index),
                starting_cash=10_000.0,
                cash_balance=value,
                portfolio_value=value,
                realized_pnl=value - 10_000.0,
                unrealized_pnl=0.0,
                total_fees=0.0,
                open_positions=0,
                closed_positions=0,
                total_positions=0,
            )
        )

    repo.save_position(_closed_position("position_win", realized_pnl=40.0))
    repo.save_position(_closed_position("position_loss", realized_pnl=-20.0))

    for status in [
        Phase7RunStatus.COMPLETED,
        Phase7RunStatus.REJECTED,
        Phase7RunStatus.FAILED,
    ]:
        repo.save_phase7_run_record(
            Phase7RunRecord(
                report_date=NOW,
                status=status,
                reasons=[f"{status.value} test run"],
            )
        )

    metrics = Phase7MetricsCalculator(repo).compute()

    assert [point.portfolio_value for point in metrics.equity_curve] == [
        10_000.0,
        11_000.0,
        9_900.0,
    ]
    assert metrics.max_drawdown == 0.1
    assert metrics.win_rate == 0.5
    assert metrics.profit_factor == 2.0
    assert metrics.run_success_rate == round(2 / 3, 8)
    assert metrics.failed_runs == 1
    assert metrics.closed_positions == 2
    assert metrics.as_dict()["equity_curve"][0]["portfolio_value"] == 10_000.0


def _closed_position(position_id: str, *, realized_pnl: float) -> Position:
    return Position(
        position_id=position_id,
        market_id="demo-election-turnout-2026",
        signal_id="signal_test",
        risk_decision_id="risk_test",
        order_id=f"order_{position_id}",
        side=OrderSide.BUY_YES,
        quantity=1,
        average_price=0.5,
        opened_at=NOW - timedelta(days=1),
        closed_at=NOW,
        close_price=0.6 if realized_pnl > 0 else 0.4,
        realized_pnl=realized_pnl,
    )
