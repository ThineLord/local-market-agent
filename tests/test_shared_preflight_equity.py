from datetime import UTC, datetime, timedelta

import pytest

from local_market_agent.config import RiskGateConfig, Settings
from local_market_agent.operations import Phase7DailyRunner
from local_market_agent.risk.equity import loss_metrics, observe_equity
from local_market_agent.risk.preflight import preflight
from local_market_agent.schemas import PortfolioSnapshot
from local_market_agent.schemas.models import MarketStatus

NOW = datetime(2026, 6, 5, 0, 2, tzinfo=UTC)


def portfolio(value):
    return PortfolioSnapshot(
        starting_cash=10000,
        cash_balance=value,
        portfolio_value=value,
        realized_pnl=value - 10000,
        unrealized_pnl=0,
        total_fees=0,
        open_positions=0,
        closed_positions=0,
        total_positions=0,
    )


def test_equity_gain_then_loss_uses_day_start_and_high_water(repo):
    observe_equity(repo, portfolio(12000), NOW)
    next_day = NOW + timedelta(days=1)
    current = observe_equity(repo, portfolio(11000), next_day)
    assert current.day_start_equity == 12000
    assert loss_metrics(current) == {"daily_loss_pct": 1 / 12, "total_drawdown_pct": 1 / 12}
    recovered = observe_equity(repo, portfolio(11500), next_day + timedelta(minutes=1))
    assert recovered.day_start_equity == 12000
    assert recovered.peak_equity == 12000
    assert len(repo.list_equity_baselines()) == 2
    with pytest.raises(ValueError, match="backdate"):
        observe_equity(repo, portfolio(10000), NOW)


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("closed", "market_open"),
        ("veto", "brief_veto"),
        ("identity", "brief_identity"),
        ("future", "evidence_time"),
        ("liquidity", "liquidity"),
        ("infinite", "finite_values"),
    ],
)
def test_shared_preflight_blocks_unsafe_inputs(snapshot, brief, mutation, code):
    brief = brief.model_copy(update={"created_at": NOW})
    if mutation == "closed":
        snapshot = snapshot.model_copy(
            update={"market": snapshot.market.model_copy(update={"status": MarketStatus.CLOSED})}
        )
    elif mutation == "veto":
        brief = brief.model_copy(
            update={"must_not_trade_reasons": ["Unresolved source contradiction"]}
        )
    elif mutation == "identity":
        brief = brief.model_copy(update={"snapshot_id": "different"})
    elif mutation == "future":
        brief = brief.model_copy(
            update={
                "evidence": [
                    e.model_copy(update={"published_at": NOW + timedelta(days=1)})
                    for e in brief.evidence
                ]
            }
        )
    elif mutation == "liquidity":
        snapshot = snapshot.model_copy(update={"liquidity": None})
    else:
        snapshot = snapshot.model_copy(update={"liquidity": float("inf")})
    assert code in {c.code for c in preflight(snapshot, brief, Settings(), NOW) if not c.passed}


def test_daily_runner_receives_actual_loss_metrics(repo, tmp_path, monkeypatch):
    from local_market_agent.risk import RiskEngine

    observe_equity(repo, portfolio(12000), NOW - timedelta(days=1))
    calls = []
    original = RiskEngine.evaluate_signal

    def spy(self, signal, **kwargs):
        calls.append(kwargs)
        return original(self, signal, **kwargs)

    monkeypatch.setattr(RiskEngine, "evaluate_signal", spy)
    settings = Settings(
        db_path=repo.db_path, risk_gates=RiskGateConfig(require_manual_approval=False)
    )
    record = Phase7DailyRunner(repo, settings, report_dir=tmp_path / "reports").run(now=NOW)
    assert calls[0]["daily_loss_pct"] == pytest.approx(1 / 6)
    assert calls[0]["total_drawdown_pct"] == pytest.approx(1 / 6)
    assert record.paper_order_id is None
