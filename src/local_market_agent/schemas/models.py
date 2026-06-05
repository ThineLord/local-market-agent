from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class MarketType(StrEnum):
    PREDICTION = "prediction"
    EQUITY = "equity"
    CRYPTO = "crypto"
    EVENT = "event"


class MarketStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    SETTLED = "settled"
    UNKNOWN = "unknown"


class RecommendedAction(StrEnum):
    OBSERVE = "observe"
    PAPER_BUY_YES = "paper_buy_yes"
    PAPER_BUY_NO = "paper_buy_no"
    PAPER_BUY = "paper_buy"
    PAPER_SELL = "paper_sell"
    SKIP = "skip"


class SignalAction(StrEnum):
    OBSERVE = "observe"
    PAPER_BUY_YES = "paper_buy_yes"
    PAPER_BUY_NO = "paper_buy_no"
    PAPER_BUY = "paper_buy"
    PAPER_SELL = "paper_sell"
    SKIP = "skip"


class RiskStatus(StrEnum):
    APPROVED = "approved"
    VETOED = "vetoed"


class RiskGateDecisionStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING_MANUAL_APPROVAL = "pending_manual_approval"
    HALTED = "halted"


class Phase7RunStatus(StrEnum):
    COMPLETED = "completed"
    REJECTED = "rejected"
    PENDING_MANUAL_APPROVAL = "pending_manual_approval"
    HALTED = "halted"
    DRY_RUN = "dry_run"
    FAILED = "failed"


class OrderSide(StrEnum):
    BUY_YES = "BUY_YES"
    BUY_NO = "BUY_NO"
    SELL = "SELL"
    OBSERVE = "OBSERVE"
    BUY = "buy"


class OrderStatus(StrEnum):
    OPEN = "open"
    CANCELLED = "cancelled"
    FILLED = "filled"
    REJECTED = "rejected"
    CLOSED = "closed"


class ExecutionMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class Market(StrictBaseModel):
    market_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    market_type: MarketType
    status: MarketStatus = MarketStatus.UNKNOWN
    close_time: datetime | None = None
    url: str | None = None
    outcomes: list[str] = Field(default_factory=list)


class MarketSnapshot(StrictBaseModel):
    snapshot_id: str = Field(default_factory=lambda: new_id("snapshot"))
    market: Market
    as_of: datetime = Field(default_factory=utc_now)
    best_bid: float | None = Field(default=None, ge=0, le=1)
    best_ask: float | None = Field(default=None, ge=0, le=1)
    last_price: float | None = Field(default=None, ge=0, le=1)
    market_implied_probability: float | None = Field(default=None, ge=0, le=1)
    volume: float | None = Field(default=None, ge=0)
    liquidity: float | None = Field(default=None, ge=0)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_prices(self) -> MarketSnapshot:
        if self.best_bid is not None and self.best_ask is not None and self.best_bid > self.best_ask:
            msg = "best_bid cannot be greater than best_ask"
            raise ValueError(msg)
        return self

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return round(self.best_ask - self.best_bid, 10)


class EvidenceItem(StrictBaseModel):
    evidence_id: str = Field(default_factory=lambda: new_id("evidence"))
    source: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=utc_now)
    summary: str = Field(min_length=1)
    relevance_score: float = Field(ge=0, le=1)
    credibility_score: float = Field(ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchBrief(StrictBaseModel):
    brief_id: str = Field(default_factory=lambda: new_id("brief"))
    market_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    thesis: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    counter_evidence: list[EvidenceItem] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence_quality: float = Field(ge=0, le=1)
    estimated_probability: float | None = Field(default=None, ge=0, le=1)
    market_implied_probability: float | None = Field(default=None, ge=0, le=1)
    recommended_action: RecommendedAction
    must_not_trade_reasons: list[str] = Field(default_factory=list)
    resolution_source: str | None = None
    resolution_ambiguity: bool = False

    @field_validator("uncertainty_notes", "must_not_trade_reasons")
    @classmethod
    def no_blank_items(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            msg = "list entries cannot be blank"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_skip_has_reason(self) -> ResearchBrief:
        if self.recommended_action == RecommendedAction.SKIP and not self.must_not_trade_reasons:
            msg = "skip recommendations require must_not_trade_reasons"
            raise ValueError(msg)
        return self


class Signal(StrictBaseModel):
    signal_id: str = Field(default_factory=lambda: new_id("signal"))
    brief_id: str = Field(min_length=1)
    market_id: str = Field(min_length=1)
    strategy_name: str = "prediction_market_edge"
    created_at: datetime = Field(default_factory=utc_now)
    action: SignalAction
    agent_probability: float | None = Field(default=None, ge=0, le=1)
    market_probability: float | None = Field(default=None, ge=0, le=1)
    spread: float | None = Field(default=None, ge=0, le=1)
    edge: float | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_quality: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1)
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskDecision(StrictBaseModel):
    risk_decision_id: str = Field(default_factory=lambda: new_id("risk"))
    signal_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    status: RiskStatus
    reasons: list[str] = Field(min_length=1)
    max_position_pct: float = Field(default=0.01, ge=0, le=1)
    max_position_usd: float = Field(default=100.0, ge=0)
    requires_human_approval: bool = True
    live_trading_allowed: bool = False
    config_snapshot: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_approved(self) -> bool:
        return self.status == RiskStatus.APPROVED

    @property
    def approved(self) -> bool:
        return self.is_approved

    @property
    def veto_reasons(self) -> list[str]:
        return [] if self.is_approved else self.reasons


class PaperOrder(StrictBaseModel):
    order_id: str = Field(default_factory=lambda: new_id("paper_order"))
    signal_id: str = Field(min_length=1)
    risk_decision_id: str = Field(min_length=1)
    market_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    side: OrderSide
    quantity: float = Field(gt=0)
    limit_price: float = Field(ge=0, le=1)
    fill_price: float = Field(ge=0, le=1)
    fees: float = Field(default=0.0, ge=0)
    status: OrderStatus = OrderStatus.OPEN
    execution_mode: ExecutionMode = ExecutionMode.PAPER

    @model_validator(mode="after")
    def validate_paper_only(self) -> PaperOrder:
        if self.execution_mode != ExecutionMode.PAPER:
            msg = "paper orders cannot use live execution mode"
            raise ValueError(msg)
        return self


class PaperFill(StrictBaseModel):
    fill_id: str = Field(default_factory=lambda: new_id("paper_fill"))
    order_id: str = Field(min_length=1)
    position_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    risk_decision_id: str = Field(min_length=1)
    market_id: str = Field(min_length=1)
    filled_at: datetime = Field(default_factory=utc_now)
    side: OrderSide
    quantity: float = Field(gt=0)
    price: float = Field(ge=0, le=1)
    fees: float = Field(default=0.0, ge=0)
    is_closing: bool = False
    execution_mode: ExecutionMode = ExecutionMode.PAPER

    @model_validator(mode="after")
    def validate_paper_fill(self) -> PaperFill:
        if self.execution_mode != ExecutionMode.PAPER:
            msg = "paper fills cannot use live execution mode"
            raise ValueError(msg)
        if self.is_closing and self.side != OrderSide.SELL:
            msg = "closing paper fills must use SELL side"
            raise ValueError(msg)
        if not self.is_closing and self.side == OrderSide.SELL:
            msg = "SELL fills can only close existing paper positions"
            raise ValueError(msg)
        return self


class PaperOrderIntent(StrictBaseModel):
    intent_id: str = Field(default_factory=lambda: new_id("paper_intent"))
    signal_id: str = Field(min_length=1)
    market_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    side: OrderSide
    quantity: float = Field(gt=0)
    limit_price: float = Field(ge=0, le=1)
    notional: float = Field(gt=0)
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_paper_intent(self) -> PaperOrderIntent:
        if self.execution_mode != ExecutionMode.PAPER:
            msg = "paper order intents cannot use live execution mode"
            raise ValueError(msg)
        if self.side not in {OrderSide.BUY_YES, OrderSide.BUY_NO, OrderSide.BUY}:
            msg = "paper order intents can only open paper buy positions"
            raise ValueError(msg)
        return self


class Position(StrictBaseModel):
    position_id: str = Field(default_factory=lambda: new_id("position"))
    market_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    risk_decision_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    side: OrderSide
    quantity: float = Field(gt=0)
    average_price: float = Field(ge=0, le=1)
    opened_at: datetime = Field(default_factory=utc_now)
    closed_at: datetime | None = None
    close_price: float | None = Field(default=None, ge=0, le=1)
    realized_pnl: float = 0.0
    fees: float = Field(default=0.0, ge=0)

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


class PortfolioSnapshot(StrictBaseModel):
    snapshot_id: str = Field(default_factory=lambda: new_id("portfolio_snapshot"))
    as_of: datetime = Field(default_factory=utc_now)
    starting_cash: float = Field(ge=0)
    cash_balance: float = Field(ge=0)
    portfolio_value: float = Field(ge=0)
    realized_pnl: float
    unrealized_pnl: float
    total_fees: float = Field(ge=0)
    open_positions: int = Field(ge=0)
    closed_positions: int = Field(ge=0)
    total_positions: int = Field(ge=0)
    market_values: dict[str, float] = Field(default_factory=dict)
    execution_mode: ExecutionMode = ExecutionMode.PAPER

    @model_validator(mode="after")
    def validate_paper_only(self) -> PortfolioSnapshot:
        if self.execution_mode != ExecutionMode.PAPER:
            msg = "portfolio snapshots cannot use live execution mode"
            raise ValueError(msg)
        if self.total_positions != self.open_positions + self.closed_positions:
            msg = "total_positions must equal open_positions plus closed_positions"
            raise ValueError(msg)
        return self


class RiskGateCheck(StrictBaseModel):
    gate: str = Field(min_length=1)
    status: RiskGateDecisionStatus
    passed: bool
    reason: str
    observed: float | int | str | bool | None = None
    limit: float | int | str | bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskGateDecision(StrictBaseModel):
    risk_gate_decision_id: str = Field(default_factory=lambda: new_id("risk_gate"))
    intent_id: str = Field(min_length=1)
    signal_id: str = Field(min_length=1)
    market_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    status: RiskGateDecisionStatus
    reasons: list[str] = Field(min_length=1)
    checks: list[RiskGateCheck] = Field(min_length=1)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    execution_mode: ExecutionMode = ExecutionMode.PAPER

    @model_validator(mode="after")
    def validate_paper_only(self) -> RiskGateDecision:
        if self.execution_mode != ExecutionMode.PAPER:
            msg = "risk gate decisions cannot use live execution mode"
            raise ValueError(msg)
        return self

    @property
    def is_approved(self) -> bool:
        return self.status == RiskGateDecisionStatus.APPROVED

    @property
    def requires_manual_approval(self) -> bool:
        return self.status == RiskGateDecisionStatus.PENDING_MANUAL_APPROVAL

    @property
    def is_halted(self) -> bool:
        return self.status == RiskGateDecisionStatus.HALTED


class Phase7RunRecord(StrictBaseModel):
    run_id: str = Field(default_factory=lambda: new_id("phase7_run"))
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    report_date: datetime
    status: Phase7RunStatus
    dry_run: bool = False
    market_id: str | None = None
    snapshot_id: str | None = None
    brief_id: str | None = None
    signal_id: str | None = None
    risk_decision_id: str | None = None
    risk_gate_decision_id: str | None = None
    paper_order_id: str | None = None
    portfolio_snapshot_id: str | None = None
    report_path: str | None = None
    manifest_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    execution_mode: ExecutionMode = ExecutionMode.PAPER

    @model_validator(mode="after")
    def validate_paper_only(self) -> Phase7RunRecord:
        if self.execution_mode != ExecutionMode.PAPER:
            msg = "phase 7 run records cannot use live execution mode"
            raise ValueError(msg)
        return self


class Phase7RunManifest(StrictBaseModel):
    run_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    code_version: str | None = None
    configuration_snapshot: dict[str, Any] = Field(default_factory=dict)
    cli_arguments: dict[str, Any] = Field(default_factory=dict)
    fixture_paths: dict[str, str] = Field(default_factory=dict)
    report_path: str | None = None
    report_checksum: str | None = None
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_paper_only(self) -> Phase7RunManifest:
        if self.execution_mode != ExecutionMode.PAPER:
            msg = "phase 7 run manifests cannot use live execution mode"
            raise ValueError(msg)
        return self


class PerformanceReport(StrictBaseModel):
    report_id: str = Field(default_factory=lambda: new_id("performance"))
    as_of: datetime = Field(default_factory=utc_now)
    starting_cash: float = Field(ge=0)
    ending_cash: float = Field(ge=0)
    realized_pnl: float
    unrealized_pnl: float
    total_fees: float = Field(ge=0)
    open_positions: int = Field(ge=0)
    orders: int = Field(ge=0)
    notes: list[str] = Field(default_factory=list)
