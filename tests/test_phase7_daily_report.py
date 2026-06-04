from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from local_market_agent.config import RiskGateConfig
from local_market_agent.paper import PaperLedger
from local_market_agent.reporting import Phase7DailyReportGenerator
from local_market_agent.risk import RiskEngine, RiskGateEvaluator
from local_market_agent.schemas.models import OrderSide, PaperOrderIntent
from local_market_agent.strategy import PredictionMarketEdgeStrategy

NOW = datetime(2026, 6, 5, 16, 0, tzinfo=UTC)


def _approved_signal_and_decision(repo, brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.is_approved
    repo.save_signal(signal)
    repo.save_risk_decision(decision)
    return signal, decision


def _intent(signal, *, notional: float = 100.0) -> PaperOrderIntent:
    return PaperOrderIntent(
        signal_id=signal.signal_id,
        market_id=signal.market_id,
        side=OrderSide.BUY_YES,
        quantity=100,
        limit_price=0.50,
        notional=notional,
    )


def test_phase7_daily_report_writes_markdown_artifact(repo, brief, snapshot, tmp_path):
    signal, decision = _approved_signal_and_decision(repo, brief, snapshot)
    ledger = PaperLedger(repo)

    ledger.create_order(signal=signal, risk_decision=decision, snapshot=snapshot)
    first_position = repo.list_positions()[0]
    closed = ledger.close_position(first_position.position_id, close_price=0.60)
    order = ledger.create_order(signal=signal, risk_decision=decision, snapshot=snapshot)
    portfolio_snapshot = ledger.snapshot_portfolio({snapshot.market.market_id: 0.72})

    evaluator = RiskGateEvaluator(
        config=RiskGateConfig(require_manual_approval=False),
        repository=repo,
    )
    evaluator.evaluate(
        signal=signal,
        intent=_intent(signal),
        portfolio_snapshot=portfolio_snapshot,
        positions=repo.list_positions(),
        recent_fills=repo.list_paper_fills(),
        market_data_as_of=NOW - timedelta(minutes=6),
        now=NOW,
    )
    evaluator.evaluate(
        signal=signal,
        intent=_intent(signal),
        portfolio_snapshot=portfolio_snapshot.model_copy(
            update={"portfolio_value": 9_600.0, "cash_balance": 9_600.0}
        ),
        positions=repo.list_positions(),
        recent_fills=repo.list_paper_fills(),
        market_data_as_of=NOW,
        now=NOW,
    )

    artifact = Phase7DailyReportGenerator(repo).generate(
        report_date=date(2026, 6, 5),
        generated_at=NOW,
        output_path=tmp_path / "phase7_daily_report.md",
    )

    assert artifact.path.exists()
    markdown = artifact.path.read_text(encoding="utf-8")
    assert artifact.markdown == markdown
    assert "# Phase 7 Paper Operations Daily Report" in markdown
    assert "## Run Metadata" in markdown
    assert "## Portfolio Snapshot Summary" in markdown
    assert "## Open Positions" in markdown
    assert "## Paper Orders" in markdown
    assert "## Paper Fills" in markdown
    assert "## PnL" in markdown
    assert "## Exposure" in markdown
    assert "## Risk Gate Decisions" in markdown
    assert "## Risk Gate Rejection And Halt Reasons" in markdown
    assert "## Operational Warnings" in markdown
    assert "2026-06-05" in markdown
    assert order.order_id in markdown
    assert closed.position_id in markdown
    assert f"{closed.realized_pnl:.4f}" in markdown
    assert f"{portfolio_snapshot.unrealized_pnl:.4f}" in markdown
    assert "Market data is stale for paper risk gate evaluation." in markdown
    assert "Daily drawdown circuit breaker is active." in markdown
    assert "At least one risk gate decision rejected a paper order intent." in markdown
    assert "At least one risk gate decision halted new paper positions." in markdown
    assert "No broker API, live order, scheduler, dashboard, or continuous runner was invoked." in markdown


def test_phase7_daily_report_warns_when_local_data_is_missing(repo, tmp_path):
    artifact = Phase7DailyReportGenerator(repo).generate(
        report_date=date(2026, 6, 5),
        generated_at=NOW,
        output_path=tmp_path / "empty_report.md",
    )

    markdown = artifact.markdown
    assert artifact.path.exists()
    assert "No portfolio snapshot is available for this report." in markdown
    assert "No risk gate decisions are available for audit review." in markdown
    assert "_No open paper positions._" in markdown
    assert "_No paper orders._" in markdown
    assert "_No paper fills._" in markdown
