from __future__ import annotations

from local_market_agent.paper import PaperLedger
from local_market_agent.reporting import DailyReportService
from local_market_agent.risk import RiskEngine
from local_market_agent.strategy import PredictionMarketEdgeStrategy


def _create_approved_order(repo, brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.is_approved
    repo.save_signal(signal)
    repo.save_risk_decision(decision)
    return PaperLedger(repo).create_order(
        signal=signal,
        risk_decision=decision,
        snapshot=snapshot,
    )


def test_daily_report_aggregates_paper_orders_positions_and_pnl(repo, brief, snapshot):
    ledger = PaperLedger(repo)

    _create_approved_order(repo, brief, snapshot)
    first_position = repo.list_positions()[0]
    closed = ledger.close_position(first_position.position_id, close_price=0.60)

    _create_approved_order(repo, brief, snapshot)
    mark = 0.72
    expected_unrealized = ledger.unrealized_pnl({snapshot.market.market_id: mark})

    report = DailyReportService(repo).build_report(marks={snapshot.market.market_id: mark})

    assert report.orders == 2
    assert report.open_positions == 1
    assert report.realized_pnl == closed.realized_pnl
    assert report.unrealized_pnl == expected_unrealized
    assert report.ending_cash == round(
        report.starting_cash + report.realized_pnl + report.unrealized_pnl,
        4,
    )
    assert repo.list_performance_reports(limit=1)[0].report_id == report.report_id


def test_daily_report_notes_are_paper_only_mark_to_market_not_cash_accounting(
    repo,
    brief,
    snapshot,
):
    _create_approved_order(repo, brief, snapshot)

    report = DailyReportService(repo).build_report()
    notes = " ".join(report.notes).lower()

    assert "paper-only" in notes
    assert "no live orders" in notes
    assert "mark-to-market" in notes
    assert "not cash-accounting" in notes
