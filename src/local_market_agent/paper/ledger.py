from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from local_market_agent.config import RiskConfig
from local_market_agent.schemas.models import (
    MarketSnapshot,
    OrderSide,
    PaperOrder,
    Position,
    RiskDecision,
    Signal,
    SignalAction,
)
from local_market_agent.storage import SQLiteRepository


@dataclass
class PaperLedger:
    repository: SQLiteRepository
    config: RiskConfig = RiskConfig()

    def create_order(
        self,
        *,
        signal: Signal,
        risk_decision: RiskDecision | None,
        snapshot: MarketSnapshot,
    ) -> PaperOrder:
        if risk_decision is None:
            msg = "paper order requires an approved risk decision"
            raise ValueError(msg)
        if not risk_decision.is_approved:
            msg = "paper order requires an approved risk decision"
            raise ValueError(msg)
        if risk_decision.signal_id != signal.signal_id:
            msg = "risk decision does not belong to signal"
            raise ValueError(msg)
        if signal.action != SignalAction.PAPER_BUY:
            msg = "paper ledger can only create paper_buy orders"
            raise ValueError(msg)

        limit_price = snapshot.best_ask or snapshot.last_price or snapshot.market_implied_probability
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
            side=OrderSide.BUY,
            quantity=quantity,
            limit_price=limit_price,
            fill_price=fill_price,
            fees=fees,
        )
        position = Position(
            market_id=signal.market_id,
            signal_id=signal.signal_id,
            risk_decision_id=risk_decision.risk_decision_id,
            order_id=order.order_id,
            side=OrderSide.BUY,
            quantity=quantity,
            average_price=fill_price,
            fees=fees,
        )
        self.repository.append_paper_order(order)
        self.repository.save_position(position)
        return order

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
        realized = round((close_price - position.average_price) * position.quantity - position.fees, 4)
        closed = position.model_copy(
            update={
                "closed_at": datetime.now(UTC),
                "close_price": close_price,
                "realized_pnl": realized,
            }
        )
        self.repository.save_position(closed)
        return closed

    def open_positions(self) -> list[Position]:
        return [position for position in self.repository.list_positions() if position.is_open]

    def unrealized_pnl(self, marks: dict[str, float] | None = None) -> float:
        marks = marks or {}
        total = 0.0
        for position in self.open_positions():
            mark = marks.get(position.market_id, position.average_price)
            total += (mark - position.average_price) * position.quantity - position.fees
        return round(total, 4)

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
