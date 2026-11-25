from __future__ import annotations

from dataclasses import dataclass

from local_market_agent.config import RiskConfig
from local_market_agent.paper import PaperLedger
from local_market_agent.schemas import PaperFill, PaperOrder, PerformanceReport
from local_market_agent.storage import SQLiteRepository


def _total_fees(orders: list[PaperOrder], fills: list[PaperFill]) -> float:
    """Count each order's opening fee and each recorded closing fill once.

    The opening fee stays on the order. Closing a position records its fee on a
    fill and does not add it to that order, so the report adds the two amounts
    separately. Opening fills are not added again; a complete open-and-close
    pair would otherwise count the opening fee twice. An order with no fills
    keeps its saved opening fee. The total is recalculated from current rows,
    so building another report does not add the previous total again.
    """
    closing_fees: dict[str, float] = {}
    for fill in fills:
        if fill.is_closing:
            closing_fees[fill.order_id] = closing_fees.get(fill.order_id, 0.0) + fill.fees
    total = sum(order.fees + closing_fees.get(order.order_id, 0.0) for order in orders)
    return round(total, 4)


@dataclass
class DailyReportService:
    repository: SQLiteRepository
    config: RiskConfig = RiskConfig()

    def build_report(self, marks: dict[str, float] | None = None) -> PerformanceReport:
        positions = self.repository.list_positions()
        orders = self.repository.list_paper_orders()
        fills = self.repository.list_paper_fills()
        realized = round(sum(position.realized_pnl for position in positions if not position.is_open), 4)
        unrealized = PaperLedger(self.repository, self.config).unrealized_pnl(marks)
        total_fees = _total_fees(orders, fills)
        report = PerformanceReport(
            starting_cash=self.config.paper_starting_cash,
            ending_cash=round(self.config.paper_starting_cash + realized + unrealized, 4),
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            total_fees=total_fees,
            open_positions=len([position for position in positions if position.is_open]),
            orders=len(orders),
            notes=[
                "Paper-only report; no live orders were placed.",
                "`ending_cash` is a mark-to-market paper equity estimate, not cash-accounting or reserved-notional accounting.",
            ],
        )
        self.repository.save_performance_report(report)
        return report
