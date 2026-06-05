from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_str_or_none(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@dataclass(frozen=True)
class RiskGateConfig:
    max_market_data_age_seconds: int = 300
    max_daily_new_positions: int = 3
    max_position_size_pct: float = 0.10
    max_total_portfolio_exposure_pct: float = 0.50
    daily_drawdown_limit_pct: float = 0.03
    max_consecutive_losses: int = 5
    consecutive_loss_cooldown_hours: int = 48
    require_manual_approval: bool = True

    def as_dict(self) -> dict[str, float | int | bool]:
        return {
            "max_market_data_age_seconds": self.max_market_data_age_seconds,
            "max_daily_new_positions": self.max_daily_new_positions,
            "max_position_size_pct": self.max_position_size_pct,
            "max_total_portfolio_exposure_pct": self.max_total_portfolio_exposure_pct,
            "daily_drawdown_limit_pct": self.daily_drawdown_limit_pct,
            "max_consecutive_losses": self.max_consecutive_losses,
            "consecutive_loss_cooldown_hours": self.consecutive_loss_cooldown_hours,
            "require_manual_approval": self.require_manual_approval,
        }


@dataclass(frozen=True)
class RiskConfig:
    max_position_pct: float = 0.01
    max_daily_loss_pct: float = 0.02
    max_total_drawdown_pct: float = 0.05
    max_open_positions: int = 5
    min_confidence: float = 0.60
    min_edge: float = 0.08
    max_spread: float = 0.08
    min_liquidity_depth: float = 100.0
    no_leverage: bool = True
    no_derivatives: bool = True
    no_live_trading: bool = True
    compliance_requires_manual_approval: bool = True
    live_trading_allowed: bool = False
    paper_starting_cash: float = 10_000.0
    paper_fee_rate: float = 0.001
    paper_slippage_bps: float = 10.0

    def as_dict(self) -> dict[str, float | int | bool]:
        return {
            "max_position_pct": self.max_position_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_total_drawdown_pct": self.max_total_drawdown_pct,
            "max_open_positions": self.max_open_positions,
            "min_confidence": self.min_confidence,
            "min_edge": self.min_edge,
            "max_spread": self.max_spread,
            "min_liquidity_depth": self.min_liquidity_depth,
            "no_leverage": self.no_leverage,
            "no_derivatives": self.no_derivatives,
            "no_live_trading": self.no_live_trading,
            "compliance_requires_manual_approval": self.compliance_requires_manual_approval,
            "live_trading_allowed": self.live_trading_allowed,
            "paper_starting_cash": self.paper_starting_cash,
            "paper_fee_rate": self.paper_fee_rate,
            "paper_slippage_bps": self.paper_slippage_bps,
        }


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path("data/local_market_agent.sqlite")
    raw_cache_dir: Path = Path("data/raw_cache")
    research_brief_dir: Path = Path("data/research_briefs")
    real_money_enabled: bool = False
    allow_live_orders: bool = False
    human_approval_required: bool = True
    market_source: str = "fixture"
    market_id: str | None = None
    llm_provider: str = "mock"
    openai_compatible_base_url: str = "http://localhost:1234/v1"
    openai_compatible_model: str = "local-model"
    openai_compatible_api_key: str | None = None
    sec_user_agent: str = "local-market-agent@example.com"
    run_network_tests: bool = False
    risk: RiskConfig = field(default_factory=RiskConfig)
    risk_gates: RiskGateConfig = field(default_factory=RiskGateConfig)


def load_settings() -> Settings:
    risk = RiskConfig(
        live_trading_allowed=_env_bool("ALLOW_LIVE_ORDERS", False),
        compliance_requires_manual_approval=_env_bool("HUMAN_APPROVAL_REQUIRED", True),
    )
    risk_gates = RiskGateConfig(
        require_manual_approval=_env_bool("HUMAN_APPROVAL_REQUIRED", True),
    )
    return Settings(
        db_path=Path(os.getenv("LMA_DB_PATH", "data/local_market_agent.sqlite")),
        raw_cache_dir=Path(os.getenv("LMA_RAW_CACHE_DIR", "data/raw_cache")),
        research_brief_dir=Path(
            os.getenv("LMA_RESEARCH_BRIEF_DIR", "data/research_briefs")
        ),
        real_money_enabled=_env_bool("REAL_MONEY_ENABLED", False),
        allow_live_orders=_env_bool("ALLOW_LIVE_ORDERS", False),
        human_approval_required=_env_bool("HUMAN_APPROVAL_REQUIRED", True),
        market_source=os.getenv("LMA_MARKET_SOURCE", "fixture"),
        market_id=_env_str_or_none("LMA_MARKET_ID"),
        llm_provider=os.getenv("LMA_LLM_PROVIDER", "mock"),
        openai_compatible_base_url=os.getenv(
            "LMA_OPENAI_COMPATIBLE_BASE_URL", "http://localhost:1234/v1"
        ),
        openai_compatible_model=os.getenv("LMA_OPENAI_COMPATIBLE_MODEL", "local-model"),
        openai_compatible_api_key=os.getenv("LMA_OPENAI_COMPATIBLE_API_KEY"),
        sec_user_agent=os.getenv("LMA_SEC_USER_AGENT", "local-market-agent@example.com"),
        run_network_tests=_env_bool("LMA_RUN_NETWORK_TESTS", False),
        risk=risk,
        risk_gates=risk_gates,
    )
