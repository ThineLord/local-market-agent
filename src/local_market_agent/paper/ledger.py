from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from local_market_agent.config import RiskConfig
from local_market_agent.schemas.models import (
    MarketSnapshot,
    OrderSide,
    OrderStatus,
    PaperFill,
    PaperOrder,
    PortfolioSnapshot,
    Position,
    RiskDecision,
    Signal,
    SignalAction,
    utc_now,
)
from local_market_agent.storage import SQLiteRepository

ACTIONABLE_PAPER_BUYS = {
    SignalAction.PAPER_BUY_YES,
    SignalAction.PAPER_BUY_NO,
}


@dataclass
class PaperLedger:
    repository: SQLiteRepository
    config: RiskConfig = RiskConfig()

    def open_position(
        self,
        *,
        signal: Signal,
        risk_decision: RiskDecision | None,
        snapshot: MarketSnapshot,
    ) -> Position:
        _, _, position = self._open_paper_position(
            signal=signal,
            risk_decision=risk_decision,
            snapshot=snapshot,
        )
        return position

    def create_order(
        self,
        *,
        signal: Signal,
        risk_decision: RiskDecision | None,
        snapshot: MarketSnapshot,
    ) -> PaperOrder:
        order, _, _ = self._open_paper_position(
            signal=signal,
            risk_decision=risk_decision,
            snapshot=snapshot,
        )
        return order

    def _open_paper_position(
        self,
        *,
        signal: Signal,
        risk_decision: RiskDecision | None,
        snapshot: MarketSnapshot,
    ) -> tuple[PaperOrder, PaperFill, Position]:
        if risk_decision is None:
            msg = "paper order requires an approved risk decision"
            raise ValueError(msg)
        if not risk_decision.is_approved:
            msg = "paper order requires an approved risk decision"
            raise ValueError(msg)
        if risk_decision.signal_id != signal.signal_id:
            msg = "risk decision does not belong to signal"
            raise ValueError(msg)
        if signal.action not in ACTIONABLE_PAPER_BUYS:
            msg = "paper ledger can only create paper_buy_yes/no orders"
            raise ValueError(msg)

        side, limit_price = _paper_side_and_limit(signal, snapshot)
        if limit_price is None:
            msg = "cannot simulate fill without a market price"
            raise ValueError(msg)
        fill_price = min(1.0, round(limit_price + self.config.paper_slippage_bps / 10_000, 4))
        notional = min(
            self.config.paper_starting_cash * risk_decision.max_position_pct,
            risk_decision.max_position_usd,
        )
        quantity = round(notional / fill_price, 8)
        fees = round(notional * self.config.paper_fee_rate, 4)
        order = PaperOrder(
            signal_id=signal.signal_id,
            risk_decision_id=risk_decision.risk_decision_id,
            market_id=signal.market_id,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            fill_price=fill_price,
            fees=fees,
            status=OrderStatus.FILLED,
        )
        position = Position(
            market_id=signal.market_id,
            signal_id=signal.signal_id,
            risk_decision_id=risk_decision.risk_decision_id,
            order_id=order.order_id,
            side=side,
            quantity=quantity,
            average_price=fill_price,
            fees=fees,
        )
        fill = PaperFill(
            order_id=order.order_id,
            position_id=position.position_id,
            signal_id=signal.signal_id,
            risk_decision_id=risk_decision.risk_decision_id,
            market_id=signal.market_id,
            side=side,
            quantity=quantity,
            price=fill_price,
            fees=fees,
        )
        self.repository.append_paper_order(order)
        self.repository.save_position(position)
        self.repository.append_paper_fill(fill)
        return order, fill, position

    def close_position(self, position_id: str, close_price: float) -> Position:
        if not 0 <= close_price <= 1:
            msg = "close_price must be between 0 and 1"
            raise ValueError(msg)
        position = self.repository.load_position(position_id)
        if position is None:
            msg = f"unknown position: {position_id}"
            raise ValueError(msg)
        if not position.is_open:
            return position
        close_fees = round(close_price * position.quantity * self.config.paper_fee_rate, 4)
        total_fees = round(position.fees + close_fees, 4)
        realized = round((close_price - position.average_price) * position.quantity - total_fees, 4)
        fill = PaperFill(
            order_id=position.order_id,
            position_id=position.position_id,
            signal_id=position.signal_id,
            risk_decision_id=position.risk_decision_id,
            market_id=position.market_id,
            side=OrderSide.SELL,
            quantity=position.quantity,
            price=close_price,
            fees=close_fees,
            is_closing=True,
        )
        closed = position.model_copy(
            update={
                "closed_at": utc_now(),
                "close_price": close_price,
                "realized_pnl": realized,
                "fees": total_fees,
            }
        )
        self.repository.append_paper_fill(fill)
        self.repository.save_position(closed)
        return closed

    def open_positions(self) -> list[Position]:
        return [position for position in self.repository.list_positions() if position.is_open]

    def realized_pnl(self) -> float:
        total = sum(
            position.realized_pnl
            for position in self.repository.list_positions()
            if not position.is_open
        )
        return round(total, 4)

    def unrealized_pnl(self, marks: dict[str, float] | None = None) -> float:
        marks = marks or {}
        total = 0.0
        for position in self.open_positions():
            mark = _mark_for_position(position, marks)
            total += (mark - position.average_price) * position.quantity - position.fees
        return round(total, 4)

    def snapshot_portfolio(
        self,
        marks: dict[str, float] | None = None,
        *,
        persist: bool = True,
    ) -> PortfolioSnapshot:
        marks = marks or {}
        positions = self.repository.list_positions()
        fills = self.repository.list_paper_fills()
        market_values: dict[str, float] = {}
        for position in positions:
            if not position.is_open:
                continue
            mark = _mark_for_position(position, marks)
            market_values[position.position_id] = round(mark * position.quantity, 4)

        cash_balance = _cash_balance(self.config.paper_starting_cash, fills)
        snapshot = PortfolioSnapshot(
            starting_cash=self.config.paper_starting_cash,
            cash_balance=cash_balance,
            portfolio_value=round(cash_balance + sum(market_values.values()), 4),
            realized_pnl=self.realized_pnl(),
            unrealized_pnl=self.unrealized_pnl(marks),
            total_fees=round(sum(fill.fees for fill in fills), 4),
            open_positions=len([position for position in positions if position.is_open]),
            closed_positions=len([position for position in positions if not position.is_open]),
            total_positions=len(positions),
            market_values=market_values,
        )
        if persist:
            self.repository.save_portfolio_snapshot(snapshot)
        return snapshot

    def export_jsonl(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for payload in self.repository.export_payloads("paper_orders"):
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return output

    def export_csv(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        orders = self.repository.list_paper_orders()
        fieldnames = [
            "order_id",
            "signal_id",
            "risk_decision_id",
            "market_id",
            "side",
            "quantity",
            "limit_price",
            "fill_price",
            "fees",
            "status",
        ]
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for order in orders:
                row = order.model_dump(mode="json")
                writer.writerow({key: row[key] for key in fieldnames})
        return output

    def export_fills_jsonl(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for payload in self.repository.export_payloads("paper_fills"):
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return output

    def export_fills_csv(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        fills = self.repository.list_paper_fills()
        fieldnames = [
            "fill_id",
            "order_id",
            "position_id",
            "signal_id",
            "risk_decision_id",
            "market_id",
            "side",
            "quantity",
            "price",
            "fees",
            "is_closing",
        ]
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for fill in fills:
                row = fill.model_dump(mode="json")
                writer.writerow({key: row[key] for key in fieldnames})
        return output


def _paper_side_and_limit(
    signal: Signal, snapshot: MarketSnapshot
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


def _mark_for_position(position: Position, marks: dict[str, float]) -> float:
    mark = marks.get(position.market_id, position.average_price)
    if not 0 <= mark <= 1:
        msg = "mark prices must be between 0 and 1"
        raise ValueError(msg)
    return mark


def _cash_balance(starting_cash: float, fills: list[PaperFill]) -> float:
    cash = starting_cash
    for fill in fills:
        notional = fill.quantity * fill.price
        if fill.is_closing:
            cash += notional - fill.fees
        else:
            cash -= notional + fill.fees
    return round(cash, 4)
