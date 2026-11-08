import json
from datetime import UTC, datetime, timedelta

import pytest
from test_ledger_atomicity import business_hash

from local_market_agent.config import Settings
from local_market_agent.demo import demo_packet, demo_settlement
from local_market_agent.evidence_packet import (
    packet_status,
    prepare_packet,
    review_packet,
    settle_packet,
)
from local_market_agent.integrity import verify_execution
from local_market_agent.paper.execution import PaperExecutionService
from local_market_agent.workflow import workflow_status

NOW = datetime(2026, 6, 5, 12, tzinfo=UTC)


def reviewed(path, scope="research", now=NOW):
    review = review_packet(path, actor="synthetic-reviewer", reason="Fixture test", scope=scope, now=now)
    target = path.parent / (scope+"-review.json")
    target.write_text(review.model_dump_json())
    return target


def settlement_packet(path, now):
    return demo_settlement(path, now=now)


def test_evidence_to_review_approval_execution_settlement(repo, tmp_path):
    path = demo_packet(tmp_path / "packet", now=NOW)
    status = packet_status(path, now=NOW)
    assert status["valid"] and status["research_ready"]
    review = reviewed(path)
    settings = Settings(db_path=repo.db_path)
    intent = prepare_packet(repo, settings, path, review, now=NOW)
    service = PaperExecutionService(repo, settings)
    assert service.execute(intent.intent_id, now=NOW)["status"] == "pending_manual_approval"
    service.approve(intent.intent_id, actor="synthetic-order-reviewer", reason="Fixture test", now=NOW)
    assert service.execute(intent.intent_id, now=NOW)["status"] == "completed"
    assert verify_execution(repo, intent.intent_id)["ok"]
    settlement = settlement_packet(path, NOW+timedelta(seconds=1))
    review = reviewed(settlement, "settlement", now=NOW+timedelta(seconds=1))
    receipt = settle_packet(repo, settings, settlement, review, now=NOW+timedelta(seconds=1))
    assert receipt.closing_hashes and repo.list_positions()[0].close_price == 1
    assert settle_packet(repo, settings, settlement, review, now=NOW+timedelta(seconds=1)) == receipt
    assert repo.count("paper_fills") == 2
    assert verify_execution(repo, intent.intent_id)["ok"]
    assert workflow_status(repo, now=NOW+timedelta(seconds=1))["intents"][0]["status"] == "settled"
    with pytest.raises(ValueError, match="already settled"):
        prepare_packet(repo, settings, path, reviewed(path), now=NOW+timedelta(seconds=1))


@pytest.mark.parametrize("mutation", ["source", "escape", "future", "review", "brief"])
def test_packet_fails_closed(repo, tmp_path, mutation):
    path = demo_packet(tmp_path / "packet", now=NOW)
    review = reviewed(path)
    payload = json.loads(path.read_text())
    if mutation == "source":
        (path.parent / "market.json").write_text("changed")
    elif mutation == "escape":
        payload["sources"][0]["path"] = "../outside.json"
    elif mutation == "future":
        payload["evidence"][0]["published_at"] = (NOW+timedelta(days=1)).isoformat()
    elif mutation == "review":
        payload["resolution_source"] = "synthetic://changed"
        payload["brief"]["resolution_source"] = "synthetic://changed"
    else:
        payload["brief"]["evidence"][0]["summary"] = "not reviewed"
    path.write_text(json.dumps(payload))
    before = business_hash(repo)
    with pytest.raises(ValueError):
        prepare_packet(repo, Settings(db_path=repo.db_path), path, review, now=NOW)
    assert business_hash(repo) == before


def test_packet_missing_liquidity_is_explicit_blocker(tmp_path):
    path = demo_packet(tmp_path / "packet", now=NOW)
    payload = json.loads(path.read_text())
    payload["snapshot"]["liquidity"] = None
    path.write_text(json.dumps(payload))
    assert any("liquidity" in x for x in packet_status(path, now=NOW)["blockers"])


def test_settlement_failure_rolls_back_receipt_and_close(repo, tmp_path, monkeypatch):
    path = demo_packet(tmp_path / "packet", now=NOW)
    settings = Settings(db_path=repo.db_path)
    intent = prepare_packet(repo, settings, path, reviewed(path), now=NOW)
    service = PaperExecutionService(repo, settings)
    service.approve(intent.intent_id, actor="synthetic", reason="test", now=NOW)
    service.execute(intent.intent_id, now=NOW)
    settled = settlement_packet(path, NOW)
    review = reviewed(settled, "settlement")
    before = business_hash(repo)
    original = type(repo).save_settlement_receipt
    def fail(self, receipt):
        original(self, receipt)
        raise RuntimeError("injected settlement failure")
    monkeypatch.setattr(type(repo), "save_settlement_receipt", fail)
    with pytest.raises(RuntimeError):
        settle_packet(repo, settings, settled, review, now=NOW)
    assert business_hash(repo) == before


def test_workflow_projection_is_read_only(repo, tmp_path):
    path = demo_packet(tmp_path / "packet", now=NOW)
    prepare_packet(repo, Settings(db_path=repo.db_path), path, reviewed(path), now=NOW)
    before = business_hash(repo)
    status = workflow_status(repo, now=NOW)
    assert status["read_only"] and "paper-approve" in status["intents"][0]["next_command"]
    assert status["intents"][0]["status"] == "pending_manual_approval"
    assert business_hash(repo) == before


def test_workflow_displays_content_changes_as_blocked(repo, tmp_path):
    path = demo_packet(tmp_path / "packet", now=NOW)
    prepared = prepare_packet(repo, Settings(db_path=repo.db_path), path, reviewed(path), now=NOW)
    brief = repo.load_brief(prepared.brief_id)
    repo.save_brief(brief.model_copy(update={"thesis": "changed after review"}))
    status = workflow_status(repo, now=NOW)
    assert status["intents"][0]["status"] == "blocked"
    assert "changed" in status["intents"][0]["reasons"][0]


@pytest.mark.parametrize("mutation", ["wrong_source", "old_retrieval", "old_publication"])
def test_old_research_cannot_be_used_as_final_settlement(repo, tmp_path, mutation):
    path = demo_packet(tmp_path / "packet", now=NOW)
    settings = Settings(db_path=repo.db_path)
    intent = prepare_packet(repo, settings, path, reviewed(path), now=NOW)
    service = PaperExecutionService(repo, settings)
    service.approve(intent.intent_id, actor="synthetic", reason="test", now=NOW)
    service.execute(intent.intent_id, now=NOW)
    settled = settlement_packet(path, NOW)
    payload = json.loads(settled.read_text())
    final_source = next(s for s in payload["sources"] if s["source_id"] == "resolution")
    if mutation == "wrong_source":
        payload["settlement"]["source_id"] = "evidence-0"
    elif mutation == "old_retrieval":
        final_source["retrieved_at"] = (NOW-timedelta(minutes=1)).isoformat()
        final_source["published_at"] = (NOW-timedelta(minutes=2)).isoformat()
    else:
        final_source["published_at"] = (NOW-timedelta(minutes=1)).isoformat()
    settled.write_text(json.dumps(payload))
    before = business_hash(repo)
    with pytest.raises(ValueError, match="settlement"):
        reviewed(settled, "settlement", now=NOW)
    assert business_hash(repo) == before
    assert repo.list_positions()[0].is_open
