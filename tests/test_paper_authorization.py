import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from test_ledger_atomicity import business_hash
from typer.testing import CliRunner

from local_market_agent.cli import app
from local_market_agent.config import Settings
from local_market_agent.paper import PaperLedger
from local_market_agent.paper.execution import PaperExecutionService
from local_market_agent.risk import RiskEngine
from local_market_agent.strategy import PredictionMarketEdgeStrategy

NOW = datetime(2026, 6, 5, 0, 2, tzinfo=UTC)

@pytest.fixture
def prepared(repo, snapshot, brief):
    brief = brief.model_copy(update={"created_at": NOW})
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    risk = RiskEngine().evaluate_signal(signal)
    service = PaperExecutionService(repo, Settings(db_path=repo.db_path))
    intent = service.prepare(signal, risk, snapshot, brief, now=NOW, simulation=True)
    return service, intent


def approve(service, intent, **kwargs):
    return service.approve(intent.intent_id, actor="test-reviewer", reason="Synthetic fixture review", now=NOW, **kwargs)


def test_pending_and_default_ledger_cannot_bypass(repo, prepared):
    service, intent = prepared
    assert service.execute(intent.intent_id, now=NOW)["status"] == "pending_manual_approval"
    assert repo.count("paper_orders") == 0
    _, snapshot, _, signal, risk = service._load(repo, intent.intent_id)
    with pytest.raises(ValueError, match="per-intent approval"):
        PaperLedger(repo).create_order(signal=signal, risk_decision=risk, snapshot=snapshot)


@pytest.mark.parametrize("mode", ["expired", "rejected", "changed", "future", "stale", "config", "live"])
def test_approval_cannot_override_hard_checks(repo, prepared, mode):
    service, intent = prepared
    approve(service, intent, reject=mode == "rejected", expires_seconds=1 if mode == "expired" else 3600)
    when = NOW
    if mode == "expired":
        when += timedelta(seconds=1)
    if mode == "future":
        when -= timedelta(seconds=1)
    if mode == "stale":
        when += timedelta(minutes=6)
    if mode == "changed":
        brief = repo.load_brief(intent.brief_id)
        repo.save_brief(brief.model_copy(update={"must_not_trade_reasons": ["new veto"]}))
    if mode == "config":
        service.settings = replace(service.settings, risk=replace(service.settings.risk, max_position_pct=.001))
    if mode == "live":
        service.settings = replace(service.settings, allow_live_orders=True)
    before = business_hash(repo)
    if mode in {"changed", "config", "live"}:
        with pytest.raises(ValueError, match="changed"):
            service.execute(intent.intent_id, now=when)
    else:
        assert service.execute(intent.intent_id, now=when)["status"] == "rejected"
    assert business_hash(repo) == before


def test_approved_concurrent_retry_is_one_fill(repo, prepared):
    service, intent = prepared
    approval = approve(service, intent)
    assert approval.content_hash == intent.content_hash and approval.actor == "test-reviewer"
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.execute(intent.intent_id, now=NOW), range(4)))
    assert {r["status"] for r in results} == {"completed"}
    assert len({r["order_id"] for r in results}) == 1
    assert [repo.count(t) for t in ("paper_orders", "paper_fills", "positions")] == [1,1,1]


def test_failed_execution_rolls_back_approval_consumption_and_equity(repo, prepared, monkeypatch):
    service, intent = prepared
    approve(service, intent)
    before = business_hash(repo)
    original = type(repo).append_paper_fill
    def fail(self, fill):
        original(self, fill)
        raise RuntimeError("injected execution failure")
    with monkeypatch.context() as patch:
        patch.setattr(type(repo), "append_paper_fill", fail)
        with pytest.raises(RuntimeError):
            service.execute(intent.intent_id, now=NOW)
    assert business_hash(repo) == before
    assert service.execute(intent.intent_id, now=NOW)["status"] == "completed"


def test_legacy_cli_uses_pending_approval_and_explicit_execution(repo, snapshot, brief, monkeypatch):
    # Dynamic synthetic times keep the CLI workflow independent of the calendar.
    now = datetime.now(UTC)
    snapshot = snapshot.model_copy(update={"as_of": now, "market": snapshot.market.model_copy(update={"close_time": now + timedelta(days=1)})})
    brief = brief.model_copy(update={"created_at": now})
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    risk = RiskEngine().evaluate_signal(signal)
    for obj, saver in [(snapshot, repo.save_market_snapshot),(brief, repo.save_brief),(signal,repo.save_signal),(risk,repo.save_risk_decision)]:
        saver(obj)
    runner = CliRunner()
    db = ["--db", str(repo.db_path)]
    pending = runner.invoke(app, ["paper-log", *db])
    assert pending.exit_code == 4, pending.output
    intent_id = json.loads(pending.output)["intent_id"]
    accepted = runner.invoke(app, ["paper-approve", "--intent-id", intent_id, "--actor", "fixture-reviewer", "--reason", "synthetic review", *db])
    assert accepted.exit_code == 0, accepted.output
    executed = runner.invoke(app, ["paper-execute", "--intent-id", intent_id, *db])
    assert executed.exit_code == 0, executed.output
    assert json.loads(executed.output)["status"] == "completed"
    assert repo.count("paper_orders") == 1


def test_newer_market_observation_invalidates_prior_approval(repo, prepared):
    service, intent = prepared
    approve(service, intent)
    snapshot = repo.load_market_snapshot(intent.snapshot_id)
    repo.save_market_snapshot(snapshot.model_copy(update={"snapshot_id": "new-observation", "as_of": NOW}))
    with pytest.raises(ValueError, match="Newer market"):
        service.execute(intent.intent_id, now=NOW)
    assert repo.count("paper_orders") == 0


def test_unmarked_other_holding_blocks_execution(repo, prepared):
    service, intent = prepared
    _, snapshot, _, signal, risk = service._load(repo, intent.intent_id)
    other = signal.model_copy(update={"signal_id": "other-signal", "market_id": "other-market"})
    other_risk = risk.model_copy(update={"signal_id": other.signal_id, "risk_decision_id": "other-risk"})
    other_snapshot = snapshot.model_copy(update={"market": snapshot.market.model_copy(update={"market_id": "other-market"})})
    repo.save_signal(other)
    repo.save_risk_decision(other_risk)
    PaperLedger(repo, simulation_only=True).create_order(signal=other, risk_decision=other_risk, snapshot=other_snapshot)
    approve(service, intent)
    before = business_hash(repo)
    result = service.execute(intent.intent_id, now=NOW)
    assert result["status"] == "rejected" and "Fresh valid mark" in result["reasons"][0]
    assert business_hash(repo) == before
