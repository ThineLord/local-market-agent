from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from local_market_agent.paper import PaperLedger
from local_market_agent.risk import RiskEngine
from local_market_agent.storage import SQLiteRepository
from local_market_agent.strategy import PredictionMarketEdgeStrategy


def business_hash(repo):
    with sqlite3.connect(repo.db_path) as conn:
        payload = {
            table: conn.execute(f'SELECT * FROM {table} ORDER BY {key}').fetchall()
            for table, key in repo.TABLES.items()
        }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@pytest.fixture
def approved(repo, brief, snapshot):
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    decision = RiskEngine().evaluate_signal(signal)
    repo.save_signal(signal)
    repo.save_risk_decision(decision)
    return dict(signal=signal, risk_decision=decision, snapshot=snapshot)


@pytest.mark.parametrize('failure_at', [1, 2, 3])
@pytest.mark.parametrize('error', [RuntimeError, KeyboardInterrupt])
def test_open_rolls_back_every_write(repo, approved, monkeypatch, failure_at, error):
    before = business_hash(repo)
    original = SQLiteRepository._save
    writes = 0

    def fail(self, *args):
        nonlocal writes
        original(self, *args)
        writes += 1
        if writes == failure_at:
            raise error('injected after write')

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteRepository, '_save', fail)
        with pytest.raises(error):
            PaperLedger(repo).create_order(**approved)
    assert business_hash(repo) == before
    # Retry after reconnect must succeed once, without orphan orders/fills.
    reopened = SQLiteRepository(repo.db_path)
    ledger = PaperLedger(reopened)
    order = ledger.create_order(**approved)
    assert ledger.create_order(**approved) == order
    assert [reopened.count(t) for t in ('paper_orders', 'positions', 'paper_fills')] == [1, 1, 1]


@pytest.mark.parametrize('failure_at', [1, 2])
def test_close_rolls_back_every_write(repo, approved, monkeypatch, failure_at):
    ledger = PaperLedger(repo)
    position = ledger.open_position(**approved)
    before = business_hash(repo)
    original = SQLiteRepository._save
    writes = 0

    def fail(self, *args):
        nonlocal writes
        original(self, *args)
        writes += 1
        if writes == failure_at:
            raise sqlite3.OperationalError('injected storage failure')

    with monkeypatch.context() as patch:
        patch.setattr(SQLiteRepository, '_save', fail)
        with pytest.raises(sqlite3.OperationalError):
            ledger.close_position(position.position_id, 1)
    assert business_hash(repo) == before
    closed = ledger.close_position(position.position_id, 1)
    assert ledger.close_position(position.position_id, 1) == closed
    assert repo.count('paper_fills') == 2


def test_duplicate_open_after_close_does_not_reopen(repo, approved):
    ledger = PaperLedger(repo)
    position = ledger.open_position(**approved)
    closed = ledger.close_position(position.position_id, 1)
    before = business_hash(repo)
    assert ledger.open_position(**approved) == closed
    assert business_hash(repo) == before


def test_conflicting_risk_decision_retry_is_rejected(repo, approved):
    PaperLedger(repo).create_order(**approved)
    before = business_hash(repo)
    changed = approved | {'risk_decision': approved['risk_decision'].model_copy(
        update={'risk_decision_id': 'different-approval'}
    )}
    with pytest.raises(ValueError, match='conflicting'):
        PaperLedger(repo).create_order(**changed)
    assert business_hash(repo) == before


def test_concurrent_open_and_close_are_idempotent(repo, approved):
    barrier = Barrier(2)

    def open_once(_):
        local = SQLiteRepository(repo.db_path)
        barrier.wait(timeout=10)
        return PaperLedger(local).open_position(**approved)

    with ThreadPoolExecutor(max_workers=2) as pool:
        positions = list(pool.map(open_once, range(2)))
    assert positions[0] == positions[1]
    assert repo.count('paper_fills') == 1

    def close_once(_):
        local = SQLiteRepository(repo.db_path)
        barrier.wait(timeout=10)
        return PaperLedger(local).close_position(positions[0].position_id, 1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        closed = list(pool.map(close_once, range(2)))
    assert closed[0] == closed[1]
    assert repo.count('paper_fills') == 2


@pytest.mark.parametrize('operation,write_number', [('open', 1), ('open', 2), ('open', 3), ('close', 1), ('close', 2)])
def test_process_exit_recovery(repo, approved, tmp_path, operation, write_number):
    if operation == 'close':
        PaperLedger(repo).open_position(**approved)
    before = business_hash(repo)
    payload = tmp_path / 'synthetic.json'
    payload.write_text(json.dumps({k: v.model_dump(mode='json') for k, v in approved.items()}))
    code = '''
import json, os, sys
from local_market_agent.storage import SQLiteRepository
from local_market_agent.paper import PaperLedger
from local_market_agent.schemas import Signal, RiskDecision, MarketSnapshot
repo = SQLiteRepository(sys.argv[1])
original = SQLiteRepository._save
writes = 0
def crash(self, *args):
    global writes
    original(self, *args)
    writes += 1
    if writes == int(sys.argv[4]):
        os._exit(73)
SQLiteRepository._save = crash
ledger = PaperLedger(repo)
payload = json.load(open(sys.argv[2]))
if sys.argv[3] == 'open':
    ledger.create_order(signal=Signal(**payload['signal']), risk_decision=RiskDecision(**payload['risk_decision']), snapshot=MarketSnapshot(**payload['snapshot']))
else:
    ledger.close_position(repo.list_positions()[0].position_id, 1)
'''
    result = subprocess.run(
        [sys.executable, '-c', code, str(repo.db_path), str(payload), operation, str(write_number)],
        env=os.environ.copy(), capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 73, result.stderr
    reopened = SQLiteRepository(repo.db_path)
    assert business_hash(reopened) == before
    with sqlite3.connect(repo.db_path) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
    ledger = PaperLedger(reopened)
    position = ledger.open_position(**approved)
    ledger.close_position(position.position_id, 1)
    ledger.close_position(position.position_id, 1)
    assert reopened.count('paper_fills') == 2


def test_transaction_read_your_writes_and_rollback(repo, approved):
    before = business_hash(repo)
    with pytest.raises(RuntimeError, match='rollback'), repo.transaction() as transaction:
        transaction.save_signal(approved['signal'].model_copy(update={'signal_id': 'new'}))
        assert transaction.load_signal('new') is not None
        assert repo.load_signal('new') is None
        raise RuntimeError('rollback')
    assert business_hash(repo) == before


def test_commit_failure_rolls_back_transition(repo, approved, monkeypatch):
    class FailingCommit(sqlite3.Connection):
        def commit(self):
            raise sqlite3.OperationalError('injected commit failure')

    def connect():
        conn = sqlite3.connect(repo.db_path, factory=FailingCommit)
        conn.row_factory = sqlite3.Row
        return conn

    before = business_hash(repo)
    with monkeypatch.context() as patch:
        patch.setattr(repo, '_connect', connect)
        with pytest.raises(sqlite3.OperationalError, match='commit failure'):
            PaperLedger(repo).create_order(**approved)
    assert business_hash(repo) == before
    assert PaperLedger(repo).create_order(**approved) is not None


def test_read_only_portfolio_snapshot(repo, approved):
    from ui.server import DashboardRepository

    PaperLedger(repo).open_position(**approved)
    before = business_hash(repo)
    portfolio = PaperLedger(DashboardRepository(repo.db_path)).snapshot_portfolio(persist=False)
    assert portfolio.open_positions == 1
    assert portfolio.cash_balance < portfolio.starting_cash
    assert business_hash(repo) == before
