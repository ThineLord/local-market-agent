from __future__ import annotations

from dataclasses import dataclass

from local_market_agent.config import RiskConfig
from local_market_agent.paper import PaperLedger
from local_market_agent.schemas import PerformanceReport
from local_market_agent.storage import SQLiteRepository


@dataclass
class DailyReportService:
    repository: SQLiteRepository
    config: RiskConfig = RiskConfig()

    def build_report(self, marks: dict[str, float] | None = None) -> PerformanceReport:
        positions = self.repository.list_positions()
        orders = self.repository.list_paper_orders()
        realized = round(sum(position.realized_pnl for position in positions if not position.is_open), 4)
        unrealized = PaperLedger(self.repository, self.config).unrealized_pnl(marks)
        total_fees = round(sum(order.fees for order in orders), 4)
        report = PerformanceReport(
            starting_cash=self.config.paper_starting_cash,
            ending_cash=round(self.config.paper_starting_cash + realized + unrealized, 4),
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            total_fees=total_fees,
            open_positions=len([position for position in positions if position.is_open]),
            orders=len(orders),
            notes=["Paper trading report only; no live orders were placed."],
        )
        self.repository.save_performance_report(report)
        return report
