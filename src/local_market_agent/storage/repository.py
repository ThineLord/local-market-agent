from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from local_market_agent.schemas import (
    MarketSnapshot,
    PaperOrder,
    PerformanceReport,
    Position,
    ResearchBrief,
    RiskDecision,
    Signal,
)

T = TypeVar("T", bound=BaseModel)


class SQLiteRepository:
    """Small JSON-object repository backed by SQLite."""

    TABLES = {
        "market_snapshots": "snapshot_id",
        "research_briefs": "brief_id",
        "signals": "signal_id",
        "risk_decisions": "risk_decision_id",
        "paper_orders": "order_id",
        "positions": "position_id",
        "performance_reports": "report_id",
    }

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            for table, key in self.TABLES.items():
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        {key} TEXT PRIMARY KEY,
                        market_id TEXT,
                        created_at TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_market ON market_snapshots(market_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_briefs_market ON research_briefs(market_id)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_market ON signals(market_id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_orders_market ON paper_orders(market_id)"
            )

    @staticmethod
    def _payload(model: BaseModel) -> str:
        return json.dumps(model.model_dump(mode="json"), sort_keys=True)

    @staticmethod
    def _created_at(model: BaseModel) -> str:
        value = getattr(model, "created_at", None) or getattr(model, "as_of", None)
        if value is None:
            return ""
        return value.isoformat()

    @staticmethod
    def _market_id(model: BaseModel) -> str | None:
        if hasattr(model, "market_id"):
            return model.market_id
        market = getattr(model, "market", None)
        if market is not None:
            return getattr(market, "market_id", None)
        return None

    def _save(self, table: str, key_name: str, model: BaseModel) -> None:
        key = getattr(model, key_name)
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {table} ({key_name}, market_id, created_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT({key_name}) DO UPDATE SET
                    market_id = excluded.market_id,
                    created_at = excluded.created_at,
                    payload = excluded.payload
                """,
                (key, self._market_id(model), self._created_at(model), self._payload(model)),
            )

    def _load(self, table: str, key_name: str, key: str, model_cls: type[T]) -> T | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT payload FROM {table} WHERE {key_name} = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return model_cls.model_validate_json(row["payload"])

    def _list(
        self,
        table: str,
        model_cls: type[T],
        market_id: str | None = None,
        limit: int | None = None,
    ) -> list[T]:
        params: list[str | int] = []
        where = ""
        if market_id is not None:
            where = "WHERE market_id = ?"
            params.append(market_id)
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ?"
            params.append(limit)
        query = f"SELECT payload FROM {table} {where} ORDER BY created_at DESC {limit_clause}"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [model_cls.model_validate_json(row["payload"]) for row in rows]

    def save_market_snapshot(self, snapshot: MarketSnapshot) -> None:
        self._save("market_snapshots", "snapshot_id", snapshot)

    def load_market_snapshot(self, snapshot_id: str) -> MarketSnapshot | None:
        return self._load("market_snapshots", "snapshot_id", snapshot_id, MarketSnapshot)

    def list_market_snapshots(
        self, market_id: str | None = None, limit: int | None = None
    ) -> list[MarketSnapshot]:
        return self._list("market_snapshots", MarketSnapshot, market_id, limit)

    def save_brief(self, brief: ResearchBrief) -> None:
        self._save("research_briefs", "brief_id", brief)

    def load_brief(self, brief_id: str) -> ResearchBrief | None:
        return self._load("research_briefs", "brief_id", brief_id, ResearchBrief)

    def list_briefs(
        self, market_id: str | None = None, limit: int | None = None
    ) -> list[ResearchBrief]:
        return self._list("research_briefs", ResearchBrief, market_id, limit)

    def save_signal(self, signal: Signal) -> None:
        self._save("signals", "signal_id", signal)

    def load_signal(self, signal_id: str) -> Signal | None:
        return self._load("signals", "signal_id", signal_id, Signal)

    def list_signals(self, market_id: str | None = None, limit: int | None = None) -> list[Signal]:
        return self._list("signals", Signal, market_id, limit)

    def save_risk_decision(self, decision: RiskDecision) -> None:
        self._save("risk_decisions", "risk_decision_id", decision)

    def load_risk_decision(self, risk_decision_id: str) -> RiskDecision | None:
        return self._load("risk_decisions", "risk_decision_id", risk_decision_id, RiskDecision)

    def list_risk_decisions(
        self, market_id: str | None = None, limit: int | None = None
    ) -> list[RiskDecision]:
        return self._list("risk_decisions", RiskDecision, market_id, limit)

    def append_paper_order(self, order: PaperOrder) -> None:
        self._save("paper_orders", "order_id", order)

    def load_paper_order(self, order_id: str) -> PaperOrder | None:
        return self._load("paper_orders", "order_id", order_id, PaperOrder)

    def list_paper_orders(
        self, market_id: str | None = None, limit: int | None = None
    ) -> list[PaperOrder]:
        return self._list("paper_orders", PaperOrder, market_id, limit)

    def save_position(self, position: Position) -> None:
        self._save("positions", "position_id", position)

    def load_position(self, position_id: str) -> Position | None:
        return self._load("positions", "position_id", position_id, Position)

    def list_positions(
        self, market_id: str | None = None, limit: int | None = None
    ) -> list[Position]:
        return self._list("positions", Position, market_id, limit)

    def save_performance_report(self, report: PerformanceReport) -> None:
        self._save("performance_reports", "report_id", report)

    def load_performance_report(self, report_id: str) -> PerformanceReport | None:
        return self._load(
            "performance_reports", "report_id", report_id, PerformanceReport
        )

    def list_performance_reports(self, limit: int | None = None) -> list[PerformanceReport]:
        return self._list("performance_reports", PerformanceReport, None, limit)

    def count(self, table: str) -> int:
        if table not in self.TABLES:
            msg = f"unknown table: {table}"
            raise ValueError(msg)
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])

    def export_payloads(self, table: str) -> Iterable[dict[str, object]]:
        if table not in self.TABLES:
            msg = f"unknown table: {table}"
            raise ValueError(msg)
        with self._connect() as conn:
            rows = conn.execute(f"SELECT payload FROM {table} ORDER BY created_at").fetchall()
        for row in rows:
            yield json.loads(row["payload"])
