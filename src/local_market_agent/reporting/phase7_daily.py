from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from local_market_agent.reporting.phase7_metrics import Phase7Metrics, Phase7MetricsCalculator
from local_market_agent.schemas import (
    PaperFill,
    PaperOrder,
    PortfolioSnapshot,
    Position,
    RiskGateDecision,
    RiskGateDecisionStatus,
)
from local_market_agent.storage import SQLiteRepository


@dataclass(frozen=True)
class Phase7DailyReportArtifact:
    path: Path
    report_date: date
    generated_at: datetime
    markdown: str
    warnings: list[str]


@dataclass
class Phase7DailyReportGenerator:
    repository: SQLiteRepository
    output_dir: Path = Path("data/reports")

    def generate(
        self,
        *,
        report_date: date | None = None,
        generated_at: datetime | None = None,
        output_path: str | Path | None = None,
    ) -> Phase7DailyReportArtifact:
        generated_at = _as_utc(generated_at or datetime.now(UTC))
        report_date = report_date or generated_at.date()
        output = Path(output_path) if output_path is not None else self._default_path(report_date)
        output.parent.mkdir(parents=True, exist_ok=True)

        latest_snapshot = _first_or_none(self.repository.list_portfolio_snapshots(limit=1))
        positions = self.repository.list_positions()
        orders = self.repository.list_paper_orders()
        fills = self.repository.list_paper_fills()
        risk_gate_decisions = self.repository.list_risk_gate_decisions()
        metrics = Phase7MetricsCalculator(self.repository).compute()
        warnings = _operational_warnings(latest_snapshot, orders, fills, risk_gate_decisions)
        markdown = self.build_markdown(
            report_date=report_date,
            generated_at=generated_at,
            latest_snapshot=latest_snapshot,
            positions=positions,
            orders=orders,
            fills=fills,
            risk_gate_decisions=risk_gate_decisions,
            metrics=metrics,
            warnings=warnings,
        )
        output.write_text(markdown, encoding="utf-8")
        return Phase7DailyReportArtifact(
            path=output,
            report_date=report_date,
            generated_at=generated_at,
            markdown=markdown,
            warnings=warnings,
        )

    def build_markdown(
        self,
        *,
        report_date: date,
        generated_at: datetime,
        latest_snapshot: PortfolioSnapshot | None,
        positions: list[Position],
        orders: list[PaperOrder],
        fills: list[PaperFill],
        risk_gate_decisions: list[RiskGateDecision],
        metrics: Phase7Metrics,
        warnings: list[str],
    ) -> str:
        open_positions = [position for position in positions if position.is_open]
        realized_pnl = _realized_pnl(positions)
        unrealized_pnl = latest_snapshot.unrealized_pnl if latest_snapshot is not None else 0.0
        exposure = _total_exposure(latest_snapshot)
        exposure_pct = _exposure_pct(latest_snapshot)

        sections = [
            "# Phase 7 Paper Operations Daily Report",
            "",
            "## Run Metadata",
            "",
            _table(
                ["Field", "Value"],
                [
                    ["Report date", report_date.isoformat()],
                    ["Generated at", _iso(generated_at)],
                    ["Execution mode", "paper-only"],
                    ["Repository", str(self.repository.db_path)],
                ],
            ),
            "",
            "## Portfolio Snapshot Summary",
            "",
            _portfolio_snapshot_section(latest_snapshot),
            "",
            "## Open Positions",
            "",
            _open_positions_section(open_positions, latest_snapshot),
            "",
            "## Paper Orders",
            "",
            _orders_section(orders),
            "",
            "## Paper Fills",
            "",
            _fills_section(fills),
            "",
            "## PnL",
            "",
            _table(
                ["Metric", "Value"],
                [
                    ["Realized PnL", _money(realized_pnl)],
                    ["Unrealized PnL", _money(unrealized_pnl)],
                ],
            ),
            "",
            "## Exposure",
            "",
            _table(
                ["Metric", "Value"],
                [
                    ["Open position market value", _money(exposure)],
                    ["Portfolio exposure", _pct(exposure_pct)],
                ],
            ),
            "",
            "## Risk Gate Decisions",
            "",
            _risk_gate_decisions_section(risk_gate_decisions),
            "",
            "## Risk Gate Rejection And Halt Reasons",
            "",
            _risk_gate_reasons_section(risk_gate_decisions),
            "",
            "## Phase 7 Metrics",
            "",
            _metrics_section(metrics),
            "",
            "## Operational Warnings",
            "",
            _warnings_section(warnings),
            "",
            "## Safety Notes",
            "",
            "- Paper-only artifact generated from local SQLite data.",
            "- No broker API, live order, scheduler, dashboard, or continuous runner was invoked.",
        ]
        return "\n".join(sections).rstrip() + "\n"

    def _default_path(self, report_date: date) -> Path:
        return self.output_dir / f"phase7_daily_report_{report_date.isoformat()}.md"


def _portfolio_snapshot_section(snapshot: PortfolioSnapshot | None) -> str:
    if snapshot is None:
        return "_No portfolio snapshot found._"
    return _table(
        ["Metric", "Value"],
        [
            ["Snapshot as of", _iso(snapshot.as_of)],
            ["Starting cash", _money(snapshot.starting_cash)],
            ["Cash balance", _money(snapshot.cash_balance)],
            ["Portfolio value", _money(snapshot.portfolio_value)],
            ["Realized PnL", _money(snapshot.realized_pnl)],
            ["Unrealized PnL", _money(snapshot.unrealized_pnl)],
            ["Total fees", _money(snapshot.total_fees)],
            ["Open positions", str(snapshot.open_positions)],
            ["Closed positions", str(snapshot.closed_positions)],
            ["Total positions", str(snapshot.total_positions)],
        ],
    )


def _open_positions_section(
    open_positions: list[Position],
    snapshot: PortfolioSnapshot | None,
) -> str:
    if not open_positions:
        return "_No open paper positions._"
    market_values = snapshot.market_values if snapshot is not None else {}
    rows = []
    for position in open_positions:
        market_value = market_values.get(position.position_id)
        rows.append(
            [
                position.position_id,
                position.market_id,
                position.side.value,
                _number(position.quantity),
                _number(position.average_price),
                _money(position.fees),
                _money(market_value) if market_value is not None else "n/a",
                _iso(position.opened_at),
            ]
        )
    return _table(
        [
            "Position ID",
            "Market",
            "Side",
            "Qty",
            "Avg Price",
            "Fees",
            "Market Value",
            "Opened At",
        ],
        rows,
    )


def _orders_section(orders: list[PaperOrder]) -> str:
    if not orders:
        return "_No paper orders._"
    return _table(
        ["Order ID", "Market", "Side", "Qty", "Limit", "Fill", "Fees", "Status"],
        [
            [
                order.order_id,
                order.market_id,
                order.side.value,
                _number(order.quantity),
                _number(order.limit_price),
                _number(order.fill_price),
                _money(order.fees),
                order.status.value,
            ]
            for order in orders
        ],
    )


def _fills_section(fills: list[PaperFill]) -> str:
    if not fills:
        return "_No paper fills._"
    return _table(
        ["Fill ID", "Order ID", "Position ID", "Market", "Side", "Qty", "Price", "Fees", "Closing"],
        [
            [
                fill.fill_id,
                fill.order_id,
                fill.position_id,
                fill.market_id,
                fill.side.value,
                _number(fill.quantity),
                _number(fill.price),
                _money(fill.fees),
                "yes" if fill.is_closing else "no",
            ]
            for fill in fills
        ],
    )


def _risk_gate_decisions_section(decisions: list[RiskGateDecision]) -> str:
    if not decisions:
        return "_No risk gate decisions._"
    return _table(
        ["Decision ID", "Market", "Status", "Intent", "Reasons"],
        [
            [
                decision.risk_gate_decision_id,
                decision.market_id,
                decision.status.value,
                decision.intent_id,
                "; ".join(decision.reasons),
            ]
            for decision in decisions
        ],
    )


def _risk_gate_reasons_section(decisions: list[RiskGateDecision]) -> str:
    reasons: list[str] = []
    for decision in decisions:
        if decision.status not in {
            RiskGateDecisionStatus.REJECTED,
            RiskGateDecisionStatus.HALTED,
        }:
            continue
        for reason in decision.reasons:
            reasons.append(f"- `{decision.status.value}` {decision.market_id}: {reason}")
    if not reasons:
        return "_No risk gate rejections or halts._"
    return "\n".join(reasons)


def _metrics_section(metrics: Phase7Metrics) -> str:
    latest_equity = metrics.equity_curve[-1] if metrics.equity_curve else None
    return _table(
        ["Metric", "Value"],
        [
            ["Equity curve points", str(len(metrics.equity_curve))],
            [
                "Latest equity value",
                _money(latest_equity.portfolio_value) if latest_equity is not None else "n/a",
            ],
            ["Win rate", _optional_pct(metrics.win_rate)],
            ["Profit factor", _optional_number(metrics.profit_factor)],
            ["Max drawdown", _pct(metrics.max_drawdown)],
            ["Run success rate", _optional_pct(metrics.run_success_rate)],
            ["Total Phase 7 runs", str(metrics.total_runs)],
            ["Failed Phase 7 runs", str(metrics.failed_runs)],
        ],
    )


def _warnings_section(warnings: list[str]) -> str:
    if not warnings:
        return "_No operational warnings._"
    return "\n".join(f"- {warning}" for warning in warnings)


def _operational_warnings(
    snapshot: PortfolioSnapshot | None,
    orders: list[PaperOrder],
    fills: list[PaperFill],
    risk_gate_decisions: list[RiskGateDecision],
) -> list[str]:
    warnings: list[str] = []
    if snapshot is None:
        warnings.append("No portfolio snapshot is available for this report.")
    if orders and not fills:
        warnings.append("Paper orders exist without recorded paper fills.")
    if not risk_gate_decisions:
        warnings.append("No risk gate decisions are available for audit review.")
    if any(decision.status == RiskGateDecisionStatus.HALTED for decision in risk_gate_decisions):
        warnings.append("At least one risk gate decision halted new paper positions.")
    if any(decision.status == RiskGateDecisionStatus.REJECTED for decision in risk_gate_decisions):
        warnings.append("At least one risk gate decision rejected a paper order intent.")
    if any(
        decision.status == RiskGateDecisionStatus.PENDING_MANUAL_APPROVAL
        for decision in risk_gate_decisions
    ):
        warnings.append("At least one paper order intent is pending manual approval.")
    return warnings


def _table(headers: list[str], rows: list[list[str]]) -> str:
    escaped_headers = [_escape_cell(header) for header in headers]
    lines = [
        "| " + " | ".join(escaped_headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_escape_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def _escape_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _first_or_none(items: list[PortfolioSnapshot]) -> PortfolioSnapshot | None:
    return items[0] if items else None


def _realized_pnl(positions: list[Position]) -> float:
    return round(sum(position.realized_pnl for position in positions if not position.is_open), 4)


def _total_exposure(snapshot: PortfolioSnapshot | None) -> float:
    if snapshot is None:
        return 0.0
    return round(sum(max(0.0, value) for value in snapshot.market_values.values()), 4)


def _exposure_pct(snapshot: PortfolioSnapshot | None) -> float:
    if snapshot is None or snapshot.portfolio_value <= 0:
        return 0.0
    return round(_total_exposure(snapshot) / snapshot.portfolio_value, 8)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat()


def _money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _number(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _optional_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return _pct(value)


def _optional_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return _number(value)
