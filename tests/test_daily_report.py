from __future__ import annotations

import sqlite3

from local_market_agent.config import RiskConfig
from local_market_agent.paper import PaperLedger
from local_market_agent.reporting import DailyReportService
from local_market_agent.risk import RiskEngine
from local_market_agent.schemas import PerformanceReport
from local_market_agent.strategy import PredictionMarketEdgeStrategy


def _create_approved_order(repo, brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.is_approved
    repo.save_signal(signal)
    repo.save_risk_decision(decision)
    return PaperLedger(repo, simulation_only=True).create_order(
        signal=signal,
        risk_decision=decision,
        snapshot=snapshot,
    )


def test_daily_report_aggregates_paper_orders_positions_and_pnl(repo, brief, snapshot):
    ledger = PaperLedger(repo, simulation_only=True)

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


def _approved_fill(repo, brief, snapshot, config=None):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    assert decision.is_approved
    repo.save_signal(signal)
    repo.save_risk_decision(decision)
    ledger = PaperLedger(repo, config or RiskConfig(), simulation_only=True)
    order = ledger.create_order(signal=signal, risk_decision=decision, snapshot=snapshot)
    fill = next(
        item
        for item in repo.list_paper_fills()
        if item.order_id == order.order_id and not item.is_closing
    )
    position = next(item for item in repo.list_positions() if item.order_id == order.order_id)
    return ledger, order, fill, position


def test_daily_report_fees_count_open_and_close_once(repo, brief, snapshot):
    ledger, order, _fill, position = _approved_fill(repo, brief, snapshot)
    closed = ledger.close_position(position.position_id, close_price=0.60)
    fills = repo.list_paper_fills()
    fill_fees = round(sum(fill.fees for fill in fills), 4)
    orders_before = [item.model_dump(mode="json") for item in repo.list_paper_orders()]
    fills_before = [item.model_dump(mode="json") for item in fills]

    assert len(fills) == 2
    assert fill_fees > order.fees
    assert closed.fees == fill_fees

    report = DailyReportService(repo).build_report()
    again = DailyReportService(repo).build_report()
    snapshot_fees = ledger.snapshot_portfolio(persist=False).total_fees

    assert report.total_fees == fill_fees == snapshot_fees
    assert again.total_fees == report.total_fees
    assert again.report_id != report.report_id
    assert repo.load_performance_report(report.report_id).total_fees == fill_fees
    assert len(repo.list_performance_reports()) == 2
    assert report.orders == 1
    assert report.open_positions == 0
    assert report.realized_pnl == closed.realized_pnl
    assert report.unrealized_pnl == 0
    assert report.ending_cash == round(
        report.starting_cash + report.realized_pnl + report.unrealized_pnl,
        4,
    )
    assert report.starting_cash == RiskConfig().paper_starting_cash
    assert [item.model_dump(mode="json") for item in repo.list_paper_orders()] == orders_before
    assert [item.model_dump(mode="json") for item in repo.list_paper_fills()] == fills_before


def test_daily_report_open_only_fee_matches_the_single_fill(repo, brief, snapshot):
    ledger, order, fill, _position = _approved_fill(repo, brief, snapshot)

    report = DailyReportService(repo).build_report({snapshot.market.market_id: 0.72})

    assert fill.fees == order.fees
    assert report.total_fees == fill.fees
    assert report.total_fees == ledger.snapshot_portfolio(persist=False).total_fees
    assert report.orders == 1
    assert report.open_positions == 1
    assert report.realized_pnl == 0
    assert report.unrealized_pnl == ledger.unrealized_pnl({snapshot.market.market_id: 0.72})
    assert report.ending_cash == round(
        report.starting_cash + report.realized_pnl + report.unrealized_pnl,
        4,
    )


def test_daily_report_zero_fee_stays_zero(repo, brief, snapshot):
    config = RiskConfig(paper_fee_rate=0.0)
    ledger, _order, fill, position = _approved_fill(repo, brief, snapshot, config)
    closed = ledger.close_position(position.position_id, close_price=0.60)

    report = DailyReportService(repo, config).build_report()

    assert fill.fees == 0
    assert closed.fees == 0
    assert report.total_fees == 0
    assert report.orders == 1
    assert report.realized_pnl == closed.realized_pnl
    assert report.ending_cash == round(report.starting_cash + report.realized_pnl, 4)


def test_daily_report_empty_database_has_zero_fees(repo):
    report = DailyReportService(repo).build_report()

    assert report.total_fees == 0
    assert report.orders == 0
    assert report.open_positions == 0
    assert report.realized_pnl == 0
    assert report.unrealized_pnl == 0
    assert report.ending_cash == report.starting_cash


def test_daily_report_keeps_order_fee_when_fill_records_are_incomplete(repo, brief, snapshot):
    _ledger, order, fill, position = _approved_fill(repo, brief, snapshot)
    open_fee = order.fees
    assert open_fee > 0
    assert fill.fees == open_fee
    saved = PerformanceReport(
        starting_cash=10_000,
        ending_cash=10_000,
        realized_pnl=0,
        unrealized_pnl=0,
        total_fees=1.23,
        open_positions=1,
        orders=1,
        notes=["historical report"],
    )
    repo.save_performance_report(saved)

    repo._save("paper_fills", "fill_id", fill.model_copy(update={"fees": 0}))
    zeroed = DailyReportService(repo).build_report()
    assert zeroed.total_fees == open_fee
    assert repo.load_performance_report(saved.report_id).total_fees == 1.23

    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("DELETE FROM paper_fills")
    deleted = DailyReportService(repo).build_report()
    assert repo.list_paper_fills() == []
    assert deleted.total_fees == open_fee
    assert deleted.orders == 1
    assert deleted.open_positions == 1
    assert repo.load_performance_report(saved.report_id).model_dump(mode="json") == saved.model_dump(
        mode="json"
    )
    assert position.position_id == repo.load_position(position.position_id).position_id


def test_daily_report_closed_order_without_fills_keeps_saved_order_fee(repo, brief, snapshot):
    ledger, order, _fill, position = _approved_fill(repo, brief, snapshot)
    closed = ledger.close_position(position.position_id, close_price=0.60)
    assert closed.fees > order.fees
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("DELETE FROM paper_fills")

    report = DailyReportService(repo).build_report()

    assert report.total_fees == order.fees
    assert report.total_fees != closed.fees
    assert report.realized_pnl == closed.realized_pnl
    assert report.orders == 1


def test_daily_report_missing_opening_fill_keeps_closing_fill(repo, brief, snapshot):
    ledger, order, opening, position = _approved_fill(repo, brief, snapshot)
    closed = ledger.close_position(position.position_id, close_price=1.0)
    closing = next(
        fill
        for fill in repo.list_paper_fills()
        if fill.order_id == order.order_id and fill.is_closing
    )
    assert not opening.is_closing
    assert order.fees == opening.fees == 0.1
    assert closing.fees == 0.1957
    orders_before = [item.model_dump(mode="json") for item in repo.list_paper_orders()]
    saved = PerformanceReport(
        starting_cash=10_000,
        ending_cash=10_000,
        realized_pnl=0,
        unrealized_pnl=0,
        total_fees=0.1,
        open_positions=0,
        orders=1,
        notes=["historical report"],
    )
    repo.save_performance_report(saved)

    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("DELETE FROM paper_fills WHERE fill_id = ?", (opening.fill_id,))

    remaining = repo.list_paper_fills()
    assert [fill.fill_id for fill in remaining] == [closing.fill_id]
    assert remaining[0].fees == 0.1957

    report = DailyReportService(repo).build_report()
    again = DailyReportService(repo).build_report()

    assert report.total_fees == 0.2957
    assert again.total_fees == report.total_fees
    assert again.report_id != report.report_id
    assert repo.load_performance_report(report.report_id).total_fees == 0.2957
    assert repo.load_performance_report(saved.report_id).model_dump(mode="json") == saved.model_dump(
        mode="json"
    )
    assert report.orders == 1
    assert report.open_positions == 0
    assert report.realized_pnl == closed.realized_pnl
    assert report.unrealized_pnl == 0
    assert report.ending_cash == round(report.starting_cash + report.realized_pnl, 4)
    assert [item.model_dump(mode="json") for item in repo.list_paper_orders()] == orders_before
    assert repo.list_paper_fills()[0].model_dump(mode="json") == closing.model_dump(mode="json")
    assert ledger.snapshot_portfolio(persist=False).total_fees == closing.fees


def test_daily_report_duplicate_opening_fill_does_not_inflate_fees(repo, brief, snapshot):
    _ledger, order, fill, _position = _approved_fill(repo, brief, snapshot)
    repo.append_paper_fill(fill.model_copy(update={"fill_id": "paper_fill_duplicate"}))

    report = DailyReportService(repo).build_report()
    again = DailyReportService(repo).build_report()

    assert report.total_fees == order.fees
    assert again.total_fees == report.total_fees


def test_daily_report_mixes_complete_fills_with_an_order_that_has_none(repo, brief, snapshot):
    ledger, _complete, _fill, position = _approved_fill(repo, brief, snapshot)
    ledger.close_position(position.position_id, close_price=0.60)
    complete_fees = round(sum(fill.fees for fill in repo.list_paper_fills()), 4)
    _ledger, historical, historical_fill, _position = _approved_fill(repo, brief, snapshot)
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("DELETE FROM paper_fills WHERE fill_id = ?", (historical_fill.fill_id,))

    report = DailyReportService(repo).build_report()

    assert report.total_fees == round(complete_fees + historical.fees, 4)
    assert report.orders == 2
    assert report.total_fees > historical.fees
