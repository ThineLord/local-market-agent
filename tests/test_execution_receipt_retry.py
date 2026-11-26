import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from test_ledger_atomicity import business_hash
from typer.testing import CliRunner

from local_market_agent.cli import app
from local_market_agent.config import Settings
from local_market_agent.demo import demo_packet, demo_settlement
from local_market_agent.evidence_packet import prepare_packet, review_packet, settle_packet
from local_market_agent.integrity import verify_execution
from local_market_agent.paper.execution import PaperExecutionService

NOW = datetime(2026, 6, 5, 12, tzinfo=UTC)
LEDGER = (
    "paper_orders",
    "paper_fills",
    "positions",
    "paper_approvals",
    "paper_execution_receipts",
)


def _counts(repo):
    return [repo.count(name) for name in LEDGER]


def _review(path, scope="research", now=NOW):
    review = review_packet(
        path, actor="synthetic-reviewer", reason="Fixture test", scope=scope, now=now
    )
    target = path.parent / f"{scope}-review.json"
    target.write_text(review.model_dump_json())
    return target


def _open(repo, tmp_path):
    path = demo_packet(tmp_path / "packet", now=NOW)
    settings = Settings(db_path=repo.db_path)
    intent = prepare_packet(repo, settings, path, _review(path), now=NOW)
    service = PaperExecutionService(repo, settings)
    service.approve(
        intent.intent_id,
        actor="synthetic-order-reviewer",
        reason="Explicit fixture approval",
        now=NOW,
    )
    executed = service.execute(intent.intent_id, now=NOW)
    assert executed["status"] == "completed"
    return service, intent, executed, path, settings


def _later_quote(repo, intent_id):
    receipt = repo.load_execution_receipt(intent_id)
    snapshot = repo.load_market_snapshot(receipt.references["snapshot"])
    repo.save_market_snapshot(
        snapshot.model_copy(
            update={
                "snapshot_id": snapshot.snapshot_id + "-later",
                "as_of": snapshot.as_of + timedelta(seconds=1),
            }
        )
    )


def _retry_cli(repo, intent_id):
    runner = CliRunner()
    database = ["--db", str(repo.db_path)]
    replay = runner.invoke(app, ["paper-replay", "--intent-id", intent_id, *database])
    retry = runner.invoke(app, ["paper-execute", "--intent-id", intent_id, *database])
    again = runner.invoke(app, ["paper-replay", "--intent-id", intent_id, *database])
    return replay, retry, again


def test_verified_retry_after_later_quote_returns_original_order(repo, tmp_path):
    _service, intent, executed, _path, _settings = _open(repo, tmp_path)
    assert _counts(repo) == [1, 1, 1, 1, 1]
    _later_quote(repo, intent.intent_id)
    before = business_hash(repo)
    replay, retry, again = _retry_cli(repo, intent.intent_id)
    assert replay.exit_code == 0 and json.loads(replay.output)["ok"]
    assert retry.exit_code == 0, retry.output
    payload = json.loads(retry.output)
    assert payload["status"] == "completed"
    assert payload["order_id"] == executed["order_id"]
    assert payload["reasons"] == ["Already executed; no duplicate fill"]
    assert again.exit_code == 0 and json.loads(again.output)["ok"]
    assert verify_execution(repo, intent.intent_id)["ok"]
    assert business_hash(repo) == before
    assert _counts(repo) == [1, 1, 1, 1, 1]


def test_verified_retry_after_settlement_and_later_quote(repo, tmp_path):
    _service, intent, executed, path, settings = _open(repo, tmp_path)
    settled_at = NOW + timedelta(seconds=1)
    settled = demo_settlement(path, now=settled_at)
    settle_packet(
        repo, settings, settled, _review(settled, "settlement", settled_at), now=settled_at
    )
    assert _counts(repo) == [1, 2, 1, 1, 1]
    assert verify_execution(repo, intent.intent_id)["ok"]
    _later_quote(repo, intent.intent_id)
    before = business_hash(repo)
    replay, retry, again = _retry_cli(repo, intent.intent_id)
    assert replay.exit_code == 0 and json.loads(replay.output)["ok"]
    assert retry.exit_code == 0, retry.output
    payload = json.loads(retry.output)
    assert payload["status"] == "completed" and payload["order_id"] == executed["order_id"]
    assert again.exit_code == 0 and json.loads(again.output)["ok"]
    assert business_hash(repo) == before
    assert _counts(repo) == [1, 2, 1, 1, 1]


def test_unexecuted_intent_still_rejects_a_later_quote(repo, tmp_path):
    path = demo_packet(tmp_path / "packet", now=NOW)
    settings = Settings(db_path=repo.db_path)
    intent = prepare_packet(repo, settings, path, _review(path), now=NOW)
    service = PaperExecutionService(repo, settings)
    service.approve(
        intent.intent_id, actor="synthetic-order-reviewer", reason="Not yet executed", now=NOW
    )
    snapshot = repo.load_market_snapshot(intent.snapshot_id)
    repo.save_market_snapshot(
        snapshot.model_copy(
            update={
                "snapshot_id": snapshot.snapshot_id + "-later",
                "as_of": snapshot.as_of + timedelta(seconds=1),
            }
        )
    )
    before = business_hash(repo)
    with pytest.raises(ValueError, match="Newer market observation exists"):
        service.execute(intent.intent_id, now=NOW)
    assert business_hash(repo) == before
    assert _counts(repo) == [0, 0, 0, 1, 0]


def test_damaged_receipt_is_not_executed(repo, tmp_path):
    service, intent, _executed, _path, _settings = _open(repo, tmp_path)
    receipt = repo.load_execution_receipt(intent.intent_id)
    repo.save_execution_receipt(
        receipt.model_copy(update={"hashes": {**receipt.hashes, "order": "0" * 64}})
    )
    before = business_hash(repo)
    result = service.execute(intent.intent_id, now=NOW)
    assert result["status"] == "rejected" and "order_id" not in result
    assert any("checksum" in reason for reason in result["reasons"])
    assert business_hash(repo) == before
    assert _counts(repo) == [1, 1, 1, 1, 1]
    assert not verify_execution(repo, intent.intent_id)["ok"]


def test_legacy_order_without_receipt_stays_on_the_order_path(repo, tmp_path):
    service, intent, executed, _path, _settings = _open(repo, tmp_path)
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("DELETE FROM paper_execution_receipts")
    retry = service.execute(intent.intent_id, now=NOW)
    assert retry["status"] == "completed" and retry["order_id"] == executed["order_id"]
    assert repo.count("paper_execution_receipts") == 0
    assert _counts(repo) == [1, 1, 1, 1, 0]
    snapshot = repo.load_market_snapshot(intent.snapshot_id)
    repo.save_market_snapshot(
        snapshot.model_copy(
            update={
                "snapshot_id": snapshot.snapshot_id + "-later",
                "as_of": snapshot.as_of + timedelta(seconds=1),
            }
        )
    )
    before = business_hash(repo)
    with pytest.raises(ValueError, match="Newer market observation exists"):
        service.execute(intent.intent_id, now=NOW)
    assert business_hash(repo) == before
    assert _counts(repo) == [1, 1, 1, 1, 0]


def test_other_intent_cannot_claim_receipt(repo, tmp_path):
    _service, intent, executed, _path, _settings = _open(repo, tmp_path)
    receipt = repo.load_execution_receipt(intent.intent_id)
    repo.save_execution_receipt(receipt.model_copy(update={"intent_id": "other-intent"}))
    before = business_hash(repo)
    result = _service.execute("other-intent", now=NOW)
    assert result["status"] == "rejected" and "order_id" not in result
    assert executed["order_id"] not in json.dumps(result)
    assert business_hash(repo) == before
    assert verify_execution(repo, intent.intent_id)["ok"]
    assert not verify_execution(repo, "other-intent")["ok"]
    assert _counts(repo) == [1, 1, 1, 1, 2]
