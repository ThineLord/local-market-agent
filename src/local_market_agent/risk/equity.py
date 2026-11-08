"""Persist UTC session equity and high-water marks for risk checks."""

from datetime import UTC, datetime

from local_market_agent.schemas import PortfolioSnapshot
from local_market_agent.schemas.models import EquityBaseline
from local_market_agent.storage import SQLiteRepository


def observe_equity(
    repository: SQLiteRepository, portfolio: PortfolioSnapshot, now: datetime
) -> PortfolioSnapshot:
    if now.tzinfo is None:
        raise ValueError("Equity observation requires timezone")
    now = now.astimezone(UTC)
    with repository.transaction() as repo:
        return observe_equity_in_transaction(repo, portfolio, now)


def observe_equity_in_transaction(repo, portfolio, now):
    history = sorted(repo.list_equity_baselines(), key=lambda b: b.observed_at)
    if history and now < history[-1].observed_at:
        raise ValueError("Cannot backdate equity history; use a separate replay database")
    previous = history[-1] if history else None
    day = now.date().isoformat()
    if previous and previous.baseline_id == day:
        start = previous.day_start_equity
        basis = previous.basis
    else:
        start = previous.last_equity if previous else portfolio.starting_cash
        basis = (
            "previous UTC session last observed equity" if previous else "initial capital bootstrap"
        )
    if start <= 0:
        raise ValueError("Cannot open a risk session with zero equity")
    peak = max(
        previous.peak_equity if previous else portfolio.starting_cash, portfolio.portfolio_value
    )
    repo.save_equity_baseline(
        EquityBaseline(
            baseline_id=day,
            observed_at=now,
            day_start_equity=start,
            peak_equity=peak,
            last_equity=portfolio.portfolio_value,
            basis=basis,
        )
    )
    return portfolio.model_copy(
        update={"as_of": now, "day_start_equity": start, "peak_equity": peak}
    )


def loss_metrics(portfolio: PortfolioSnapshot) -> dict[str, float]:
    day = portfolio.day_start_equity or portfolio.starting_cash
    peak = portfolio.peak_equity or portfolio.starting_cash
    return {
        "daily_loss_pct": max(0.0, (day - portfolio.portfolio_value) / day) if day else 1.0,
        "total_drawdown_pct": max(0.0, (peak - portfolio.portfolio_value) / peak) if peak else 1.0,
    }
