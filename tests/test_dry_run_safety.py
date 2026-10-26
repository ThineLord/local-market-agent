from __future__ import annotations

import json
import socket
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from test_ledger_atomicity import business_hash

from local_market_agent.config import RiskGateConfig, Settings
from local_market_agent.operations import Phase7DailyRunner, Phase7SandboxRunner
from local_market_agent.paper import PaperLedger
from local_market_agent.risk import RiskEngine
from local_market_agent.schemas.models import Phase7RunStatus, RecommendedAction
from local_market_agent.strategy import PredictionMarketEdgeStrategy

NOW = datetime(2026, 6, 5, 16, tzinfo=UTC)


@pytest.fixture
def synthetic_portfolio(repo, brief, snapshot):
    ledger = PaperLedger(repo)
    for is_yes in [True, False]:
        research = brief if is_yes else brief.model_copy(update={
            'estimated_probability': 0.35,
            'recommended_action': RecommendedAction.PAPER_BUY_NO,
        })
        signal = PredictionMarketEdgeStrategy().generate_signal(research, snapshot)
        decision = RiskEngine().evaluate_signal(signal)
        repo.save_signal(signal)
        repo.save_risk_decision(decision)
        ledger.open_position(signal=signal, risk_decision=decision, snapshot=snapshot)
    ledger.snapshot_portfolio()
    return ledger


@pytest.mark.parametrize('outcome', ['yes', 'no'])
@pytest.mark.parametrize('mode', ['approved', 'manual', 'rejected', 'failed'])
def test_dry_run_existing_holdings_and_all_business_tables_unchanged(
    repo, synthetic_portfolio, snapshot, tmp_path, monkeypatch, outcome, mode,
):
    def forbidden(*args, **kwargs):
        raise AssertionError('dry-run must not execute a ledger transition or external call')

    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(PaperLedger, 'create_order', forbidden)
    monkeypatch.setattr(PaperLedger, 'close_position', forbidden)
    historical = tmp_path / 'synthetic-history.jsonl'
    historical.write_text(json.dumps({
        'date': '2026-06-05', 'market_id': snapshot.market.market_id,
        'bid': 0.49, 'ask': 0.51, 'last_price': 0.5, 'implied_probability': 0.5,
        'settlement': {'outcome': outcome, 'source': 'synthetic-test'},
    }) + '\n')
    settings = Settings(
        db_path=repo.db_path,
        risk_gates=RiskGateConfig(require_manual_approval=mode == 'manual'),
    )
    runner = Phase7DailyRunner(
        repository=repo, settings=settings, report_dir=tmp_path / 'reports',
        market_source='historical-file', historical_file=historical,
        market_id=snapshot.market.market_id,
    )
    if mode == 'rejected':
        original = RiskEngine.evaluate_signal

        def reject(self, signal, **kwargs):
            return original(self, signal.model_copy(update={'confidence': 0.0}), **kwargs)

        monkeypatch.setattr(RiskEngine, 'evaluate_signal', reject)
    elif mode == 'failed':
        monkeypatch.setattr(
            'local_market_agent.operations.phase7_daily.build_llm_provider',
            lambda settings: (_ for _ in ()).throw(RuntimeError('synthetic provider failure')),
        )
    before = business_hash(repo)
    cash = synthetic_portfolio.snapshot_portfolio(persist=False).cash_balance
    record = runner.run(dry_run=True, now=NOW)
    assert record.status != Phase7RunStatus.FAILED or mode == 'failed', record.reasons
    assert business_hash(repo) == before
    assert synthetic_portfolio.snapshot_portfolio(persist=False).cash_balance == cash
    assert len(synthetic_portfolio.open_positions()) == 2
    assert record.paper_order_id is None
    assert record.metadata.get('settled_position_ids', []) == []
    assert repo.load_phase7_run_record(record.run_id) is None
    preview_record = tmp_path / 'reports' / 'dry_run' / f'{record.run_id}.json'
    assert json.loads(preview_record.read_text())['dry_run'] is True
    if mode != 'failed':
        assert 'temporary preview' in Path(record.report_path).read_text()
    # Repeating a preview is also state-neutral.
    runner.run(dry_run=True, now=NOW)
    assert business_hash(repo) == before


def test_fixture_preview_is_approved_and_state_neutral(repo, tmp_path):
    runner = Phase7DailyRunner(
        repo, Settings(db_path=repo.db_path, risk_gates=RiskGateConfig(require_manual_approval=False)),
        report_dir=tmp_path / 'reports',
    )
    before = business_hash(repo)
    result = runner.run(dry_run=True, now=NOW)
    assert result.status == Phase7RunStatus.DRY_RUN
    assert business_hash(repo) == before


def test_sandbox_preview_preserves_equity_and_replay_without_writes(repo, tmp_path):
    runner = Phase7SandboxRunner(
        repo, Settings(db_path=repo.db_path, risk_gates=RiskGateConfig(require_manual_approval=False)),
        report_dir=tmp_path / 'reports', summary_dir=tmp_path / 'summaries',
    )
    before = business_hash(repo)
    result = runner.run(start_date=date(2026, 6, 5), days=2, dry_run=True)
    assert business_hash(repo) == before
    assert len(result.summary['equity_curve']) == 2
    assert all(item['ok'] for item in result.summary['replay_validation_sample_results'])
    assert 'dry_run' in result.summary_path.parts
    assert all('dry_run' in Path(record.report_path).parts for record in result.records)


def test_normal_historical_settlement_still_closes_existing_holdings(
    repo, synthetic_portfolio, snapshot, tmp_path,
):
    history = tmp_path / 'history.jsonl'
    history.write_text(json.dumps({
        'date': '2026-06-05', 'market_id': snapshot.market.market_id,
        'bid': 0.49, 'ask': 0.51, 'last_price': 0.5,
        'settlement': {'outcome': 'yes', 'source': 'synthetic-test'},
    }) + '\n')
    runner = Phase7DailyRunner(
        repo, Settings(db_path=repo.db_path), report_dir=tmp_path / 'reports',
        market_source='historical-file', historical_file=history,
        market_id=snapshot.market.market_id,
    )
    record = runner.run(now=NOW)
    assert record.status != Phase7RunStatus.FAILED, record.reasons
    assert len(record.metadata['settled_position_ids']) == 2
    assert synthetic_portfolio.open_positions() == []
    before = len(repo.list_paper_fills())
    replace(runner).run(now=NOW)
    assert len(repo.list_paper_fills()) == before
