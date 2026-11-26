"""Same-signal status must not describe an intent that has no execution receipt."""

from __future__ import annotations

import json
import shlex
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from test_paper_authorization import NOW, approve
from typer.testing import CliRunner

from local_market_agent.cli import app
from local_market_agent.config import Settings, load_settings
from local_market_agent.demo import demo_packet, demo_settlement
from local_market_agent.paper.execution import PaperExecutionService
from local_market_agent.risk import RiskEngine
from local_market_agent.strategy import PredictionMarketEdgeStrategy
from local_market_agent.workflow import workflow_status
from ui.server import dashboard_payload

pytest_plugins = ["test_paper_authorization"]


def _cli(db: Path, *args: str, expected: int = 0) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "local_market_agent.cli", *args, "--db", str(db)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    return json.loads(result.stdout)


def _run_suggested(command: str, *, expected: int = 0) -> dict:
    parts = shlex.split(command)
    assert parts[0] == "lma"
    result = subprocess.run(
        [sys.executable, "-m", "local_market_agent.cli", *parts[1:]],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    return json.loads(result.stdout)


def _row(payload: dict, intent_id: str) -> dict:
    return next(row for row in payload["intents"] if row["intent_id"] == intent_id)


def _counts(path: Path) -> list[int]:
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        return [
            connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in ("paper_orders", "paper_approvals", "paper_execution_receipts", "prepared_executions")
        ]


def test_cli_same_signal_open_and_settled_status(tmp_path: Path) -> None:
    root = tmp_path / "ledger dir"
    root.mkdir()
    db = root / "demo.sqlite"
    packet = demo_packet(root / "packet")
    review = root / "research-review.json"
    reviewed = subprocess.run(
        [
            sys.executable, "-m", "local_market_agent.cli", "packet-review",
            "--packet", str(packet), "--output", str(review),
            "--actor", "synthetic-demo", "--reason", "Synthetic source review",
        ],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert reviewed.returncode == 0, reviewed.stdout + reviewed.stderr
    prepared = _cli(db, "packet-prepare", "--packet", str(packet), "--review", str(review), expected=4)
    logged = _cli(db, "paper-log", expected=4)
    intent_a = prepared["intent_id"]
    intent_b = logged["intent_id"]
    assert intent_a != intent_b

    pending = _cli(db, "workflow-status")
    for intent_id in (intent_a, intent_b):
        row = _row(pending, intent_id)
        assert row["status"] == "pending_manual_approval"
        assert "paper-approve" in row["next_command"]
        assert intent_id in row["next_command"]
        assert "paper-replay" not in row["next_command"]

    _cli(
        db, "paper-approve", "--intent-id", intent_a, "--actor", "synthetic-demo",
        "--reason", "Explicit synthetic paper-order approval",
    )
    _cli(db, "paper-execute", "--intent-id", intent_a)
    assert _counts(db) == [1, 1, 1, 2]
    before = db.read_bytes()

    opened = _cli(db, "workflow-status")
    assert db.read_bytes() == before
    owner = _row(opened, intent_a)
    other = _row(opened, intent_b)
    assert owner["status"] == "completed"
    assert owner["reasons"] == ["Paper order filled; no real money was used."]
    assert "paper-replay" in owner["next_command"] and intent_a in owner["next_command"]
    assert other["status"] == "not_executed"
    assert other["reasons"] == [
        f"Intent {intent_b} has no execution record. "
        f"Intent {intent_a} completed the paper order for this signal. "
        "That position is open."
    ]
    assert "filled" not in other["reasons"][0]
    assert "approved" not in other["reasons"][0]
    assert "paper-approve" not in other["next_command"]
    assert "paper-execute" not in other["next_command"]
    assert intent_b not in other["next_command"]
    assert intent_a in other["next_command"] and "paper-replay" in other["next_command"]
    assert _run_suggested(owner["next_command"])["ok"] is True
    assert _run_suggested(other["next_command"])["intent_id"] == intent_a
    failed = _run_suggested(
        f"lma paper-replay --intent-id {intent_b} --db {shlex.quote(str(db))}", expected=1
    )
    assert failed["ok"] is False
    assert db.read_bytes() == before
    assert _counts(db) == [1, 1, 1, 2]

    settings = replace(load_settings(), db_path=db)
    projected = dashboard_payload(settings)["workflow"]
    assert _row(projected, intent_b)["status"] == "not_executed"
    assert _row(projected, intent_b)["reasons"] == other["reasons"]
    assert _row(projected, intent_b)["next_command"] == other["next_command"]
    assert _row(projected, intent_a)["status"] == "completed"
    assert db.read_bytes() == before

    settled_packet = demo_settlement(packet)
    settlement_review = root / "settlement-review.json"
    reviewed = subprocess.run(
        [
            sys.executable, "-m", "local_market_agent.cli", "packet-review",
            "--packet", str(settled_packet), "--output", str(settlement_review),
            "--scope", "settlement", "--actor", "synthetic-demo",
            "--reason", "Synthetic final outcome",
        ],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert reviewed.returncode == 0, reviewed.stdout + reviewed.stderr
    _cli(db, "packet-settle", "--packet", str(settled_packet), "--review", str(settlement_review))
    settled_bytes = db.read_bytes()
    settled = _cli(db, "workflow-status")
    owner = _row(settled, intent_a)
    other = _row(settled, intent_b)
    assert owner["status"] == "settled"
    assert owner["reasons"] == ["Paper position closed; opening receipt remains replayable."]
    assert other["status"] == "not_executed"
    assert other["reasons"] == [
        f"Intent {intent_b} has no execution record. "
        f"Intent {intent_a} completed the paper order for this signal. "
        "That position is closed."
    ]
    assert "filled" not in other["reasons"][0] and "approved" not in other["reasons"][0]
    assert "paper-approve" not in other["next_command"] and "paper-execute" not in other["next_command"]
    assert _run_suggested(owner["next_command"])["ok"] is True
    assert _run_suggested(other["next_command"])["ok"] is True
    assert db.read_bytes() == settled_bytes
    assert _counts(db) == [1, 1, 1, 2]


def test_historical_single_intent_without_receipt_stays_explained(repo, prepared) -> None:
    service, intent = prepared
    pending = workflow_status(repo, Settings(db_path=repo.db_path), now=NOW)
    assert pending["intents"][0]["status"] == "pending_manual_approval"
    assert "paper-approve" in pending["intents"][0]["next_command"]
    approve(service, intent)
    approved = workflow_status(repo, Settings(db_path=repo.db_path), now=NOW)
    assert approved["intents"][0]["status"] == "approved"
    assert "paper-execute" in approved["intents"][0]["next_command"]
    service.execute(intent.intent_id, now=NOW)
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("DELETE FROM paper_execution_receipts")
    before = repo.db_path.read_bytes()
    opened = workflow_status(repo, Settings(db_path=repo.db_path), now=NOW)
    row = opened["intents"][0]
    assert row["status"] == "completed"
    assert row["reasons"] == [
        "Paper order filled; no real money was used.",
        "No sealed execution receipt is stored for this intent, so paper-replay cannot verify it.",
    ]
    assert "replayable" not in " ".join(row["reasons"])
    assert row["next_command"].startswith("lma paper-status ")
    assert "paper-replay" not in row["next_command"]
    assert "paper-approve" not in row["next_command"]
    assert "paper-execute" not in row["next_command"]
    listed = _run_suggested(row["next_command"])
    assert listed["intents"][0]["intent_id"] == intent.intent_id
    assert repo.db_path.read_bytes() == before

    position = repo.list_positions()[0]
    repo.save_position(position.model_copy(update={"closed_at": NOW, "close_price": 1}))
    closed_bytes = repo.db_path.read_bytes()
    settled = workflow_status(repo, Settings(db_path=repo.db_path), now=NOW)["intents"][0]
    assert settled["status"] == "settled"
    assert settled["reasons"][0] == "Paper position closed."
    assert "replayable" not in settled["reasons"][1]
    assert "paper-replay" not in settled["next_command"]
    assert settled["next_command"].startswith("lma paper-status ")
    assert repo.db_path.read_bytes() == closed_bytes


def test_unlocated_receipt_suggests_a_read_only_query(repo, prepared) -> None:
    service, intent = prepared
    approve(service, intent)
    service.execute(intent.intent_id, now=NOW)
    receipt = repo.load_execution_receipt(intent.intent_id)
    repo.save_execution_receipt(receipt.model_copy(update={
        "references": {**receipt.references, "order": "missing-order"},
    }))
    before = repo.db_path.read_bytes()
    row = workflow_status(repo, Settings(db_path=repo.db_path), now=NOW)["intents"][0]
    assert row["status"] == "unavailable"
    assert row["reasons"] == [
        "This intent's execution receipt does not reference a paper order in this ledger."
    ]
    assert "paper-replay" not in row["next_command"]
    assert "paper-approve" not in row["next_command"]
    assert "paper-execute" not in row["next_command"]
    assert _run_suggested(row["next_command"])["intents"][0]["intent_id"] == intent.intent_id
    replay = CliRunner().invoke(app, ["paper-replay", "--intent-id", intent.intent_id, "--db", str(repo.db_path)])
    assert replay.exit_code == 1
    assert repo.db_path.read_bytes() == before

    order = repo.list_paper_orders()[0]
    other = order.model_copy(update={"order_id": "other-order", "signal_id": "other-signal", "market_id": "other-market"})
    repo._save("paper_orders", "order_id", other)
    current = repo.load_execution_receipt(intent.intent_id)
    repo.save_execution_receipt(current.model_copy(update={
        "references": {**current.references, "order": other.order_id},
    }))
    mismatched = workflow_status(repo, Settings(db_path=repo.db_path), now=NOW)["intents"][0]
    assert mismatched["status"] == "unavailable"
    assert mismatched["reasons"] == [
        "This intent's execution receipt references a paper order for a different signal."
    ]
    assert "paper-replay" not in mismatched["next_command"]


def test_two_intents_without_receipts_are_not_called_filled(repo, prepared) -> None:
    service, intent = prepared
    approve(service, intent)
    service.execute(intent.intent_id, now=NOW)
    signal = repo.load_signal(intent.intent.signal_id)
    risk = repo.load_risk_decision(intent.risk_decision_id)
    snapshot = repo.load_market_snapshot(intent.snapshot_id)
    brief = repo.load_brief(intent.brief_id)
    second = service.prepare(signal, risk, snapshot, brief, now=NOW, simulation=True)
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("DELETE FROM paper_execution_receipts")
    before = repo.db_path.read_bytes()
    rows = workflow_status(repo, Settings(db_path=repo.db_path), now=NOW)["intents"]
    assert {row["intent_id"] for row in rows} == {intent.intent_id, second.intent_id}
    for row in rows:
        assert row["status"] == "not_executed"
        assert "filled" not in row["reasons"][0]
        assert "approved" not in row["reasons"][0]
        assert "no execution receipt names the intent" in row["reasons"][0]
        assert row["next_command"].startswith("lma paper-status ")
        assert "paper-replay" not in row["next_command"]
        assert "paper-approve" not in row["next_command"]
        assert "paper-execute" not in row["next_command"]
        assert _run_suggested(row["next_command"])["intents"]
    assert repo.db_path.read_bytes() == before
    assert repo.count("paper_execution_receipts") == 0


def test_missing_receipt_table_does_not_invent_an_execution(repo, snapshot, brief) -> None:
    brief = brief.model_copy(update={"created_at": NOW})
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    risk = RiskEngine().evaluate_signal(signal)
    service = PaperExecutionService(repo, Settings(db_path=repo.db_path))
    intent = service.prepare(signal, risk, snapshot, brief, now=NOW, simulation=True)
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute("DROP TABLE paper_execution_receipts")
    before = repo.db_path.read_bytes()
    payload = dashboard_payload(replace(load_settings(), db_path=repo.db_path))
    row = payload["workflow"]["intents"][0]
    assert row["intent_id"] == intent.intent_id
    assert row["status"] == "expired"
    assert "paper-replay" not in row["next_command"]
    assert "paper-execute" not in row["next_command"]
    matched = workflow_status(repo, Settings(db_path=repo.db_path), now=NOW)["intents"][0]
    assert matched["status"] == "pending_manual_approval"
    assert "paper-approve" in matched["next_command"]
    assert repo.db_path.read_bytes() == before


def test_dashboard_marks_an_intent_that_did_not_execute() -> None:
    script = Path("ui/web/app.js").read_text()
    style = Path("ui/web/style.css").read_text()
    assert "Intent ${esc(r.intent_id)}" in script
    assert "/^(not_executed|unavailable)$/" in script
    assert "overflow-wrap:anywhere" in style


def test_receipt_that_does_not_name_the_intent_is_not_replayed(repo, prepared) -> None:
    service, intent = prepared
    approve(service, intent)
    service.execute(intent.intent_id, now=NOW)
    receipt = repo.load_execution_receipt(intent.intent_id)
    body = receipt.model_dump(mode="json")
    body["intent_id"] = "other-intent"
    with sqlite3.connect(repo.db_path) as connection:
        connection.execute(
            "UPDATE paper_execution_receipts SET payload = ? WHERE intent_id = ?",
            (json.dumps(body), intent.intent_id),
        )
    row = workflow_status(repo, Settings(db_path=repo.db_path), now=NOW)["intents"][0]
    assert row["intent_id"] == intent.intent_id
    assert row["status"] == "unavailable"
    assert row["reasons"] == [
        "An execution receipt is stored for this intent, but it does not name this intent."
    ]
    assert "paper-replay" not in row["next_command"]
