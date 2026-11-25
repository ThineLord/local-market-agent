from __future__ import annotations

from dataclasses import dataclass

from local_market_agent.config import RiskConfig
from local_market_agent.paper import PaperLedger
from local_market_agent.schemas import PaperFill, PaperOrder, PerformanceReport
from local_market_agent.storage import SQLiteRepository


def _total_fees(orders: list[PaperOrder], fills: list[PaperFill]) -> float:
    """Count opening and closing fill fees once when those fills are complete.

    A fill set is complete for an order when its non-closing fees equal the fee
    stored on that order. Closing fills are then included once. Historical
    orders that have no fill rows, or whose fill fees do not match, keep the
    order fee. That avoids reporting zero when older databases never stored a
    complete fill. The total is recalculated from current rows, so building
    another report does not add the previous total again.
    """
    fills_by_order: dict[str, list[PaperFill]] = {}
    for fill in fills:
        fills_by_order.setdefault(fill.order_id, []).append(fill)
    total = 0.0
    for order in orders:
        order_fills = fills_by_order.get(order.order_id, [])
        opening_fees = round(sum(fill.fees for fill in order_fills if not fill.is_closing), 4)
        if order_fills and opening_fees == round(order.fees, 4):
            total += sum(fill.fees for fill in order_fills)
        else:
            total += order.fees
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
