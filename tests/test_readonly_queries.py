"""Status and replay commands must not create or migrate the ledger."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest
from test_paper_authorization import NOW, approve
from typer.testing import CliRunner

from local_market_agent.cli import app
from local_market_agent.config import Settings
from local_market_agent.integrity import verify_execution
from local_market_agent.storage import ReadOnlySQLiteRepository, SQLiteRepository
from local_market_agent.workflow import workflow_status

pytest_plugins = ["test_paper_authorization"]

RECEIPT_MISSING = (
    "No sealed execution receipt; intent is pending or execution is legacy"
)
SPECIAL = "ledger a%b#c?d&.sqlite"


def _tables(path: Path) -> list[str]:
    uri = path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
        return [row[0] for row in rows]


def _siblings(path: Path) -> list[str]:
    return sorted(item.name for item in path.parent.iterdir())


def _invoke(path: Path, *args: str):
    return CliRunner().invoke(app, [*args, "--db", str(path)])


def _assert_read_error(result) -> None:
    assert result.exit_code != 0
    text = result.output.strip()
    if not text:
        assert result.exception is not None
        return
    with pytest.raises(json.JSONDecodeError):
        json.loads(text)


def test_missing_database_stays_missing(tmp_path: Path) -> None:
    path = tmp_path / "missing dir" / SPECIAL
    workflow = _invoke(path, "workflow-status")
    status = _invoke(path, "paper-status")
    replay = _invoke(path, "paper-replay", "--intent-id", "unknown-fixture")

    assert not path.parent.exists()
    assert workflow.exit_code == 0, workflow.output
    payload = json.loads(workflow.output)
    assert payload["read_only"] is True
    assert payload["intents"] == []
    assert payload["empty_message"]
    assert status.exit_code == 0, status.output
    assert json.loads(status.output) == {"approvals": [], "intents": []}
    assert replay.exit_code == 1
    body = json.loads(replay.output)
    assert body == {
        "errors": [RECEIPT_MISSING],
        "intent_id": "unknown-fixture",
        "ok": False,
    }


def test_relative_missing_path_is_not_created(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = Path("missing dir") / SPECIAL
    result = _invoke(path, "paper-status")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"approvals": [], "intents": []}
    assert not path.parent.exists()


def test_sample_table_library_is_not_migrated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    directory = Path("old lib")
    directory.mkdir()
    path = directory / SPECIAL
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
    before = path.read_bytes()
    siblings = _siblings(path)

    workflow = _invoke(path, "workflow-status")
    status = _invoke(path, "paper-status")
    replay = _invoke(path, "paper-replay", "--intent-id", "unknown-fixture")

    assert workflow.exit_code == 0, workflow.output
    assert json.loads(workflow.output)["read_only"] is True
    assert json.loads(workflow.output)["intents"] == []
    assert status.exit_code == 0, status.output
    assert json.loads(status.output) == {"approvals": [], "intents": []}
    assert replay.exit_code == 1
    assert json.loads(replay.output)["errors"] == [RECEIPT_MISSING]
    assert path.read_bytes() == before
    assert _tables(path) == ["sample"]
    assert _siblings(path) == siblings


def test_header_only_and_zero_byte_files_are_not_initialized(tmp_path: Path) -> None:
    header = tmp_path / "header.sqlite"
    sqlite3.connect(header).close()
    empty = tmp_path / "zero.sqlite"
    empty.write_bytes(b"")
    header_bytes = header.read_bytes()

    for path in (header, empty):
        workflow = _invoke(path, "workflow-status")
        status = _invoke(path, "paper-status")
        replay = _invoke(path, "paper-replay", "--intent-id", "unknown-fixture")
        assert workflow.exit_code == 0, workflow.output
        assert json.loads(workflow.output)["intents"] == []
        assert status.exit_code == 0, status.output
        assert json.loads(status.output) == {"approvals": [], "intents": []}
        assert replay.exit_code == 1
        assert json.loads(replay.output)["errors"] == [RECEIPT_MISSING]

    assert header.read_bytes() == header_bytes
    assert _tables(header) == []
    assert empty.read_bytes() == b""


def test_unreadable_paths_are_not_empty_libraries(tmp_path: Path) -> None:
    garbage = tmp_path / "garbage.sqlite"
    garbage.write_bytes(b"not a database")
    directory = tmp_path / "directory.sqlite"
    directory.mkdir()
    link = tmp_path / "link.sqlite"
    link.symlink_to(tmp_path / "absent.sqlite")
    locked = tmp_path / "locked.sqlite"
    with sqlite3.connect(locked) as connection:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
    locked_bytes = locked.read_bytes()
    os.chmod(locked, 0)
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    hidden_db = hidden / "ledger.sqlite"
    with sqlite3.connect(hidden_db) as connection:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
    os.chmod(hidden, 0)

    try:
        cases = [garbage, directory, link, locked, hidden_db]
        for path in cases:
            for args in (
                ("workflow-status",),
                ("paper-status",),
                ("paper-replay", "--intent-id", "unknown-fixture"),
            ):
                _assert_read_error(_invoke(path, *args))
        assert garbage.read_bytes() == b"not a database"
        assert list(directory.iterdir()) == []
        assert not (tmp_path / "absent.sqlite").exists()
        os.chmod(locked, 0o644)
        assert locked.read_bytes() == locked_bytes
        assert _tables(locked) == ["sample"]
    finally:
        os.chmod(locked, 0o644)
        os.chmod(hidden, 0o755)


def test_missing_table_is_reported_and_not_created(repo, prepared) -> None:
    _service, intent = prepared
    path = repo.db_path
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE market_snapshots")
    before = path.read_bytes()
    tables = _tables(path)

    workflow = _invoke(path, "workflow-status")
    status = _invoke(path, "paper-status")
    assert workflow.exit_code == 0, workflow.output
    payload = json.loads(workflow.output)
    assert payload["read_only"] is True
    assert payload["intents"][0]["intent_id"] == intent.intent_id
    assert payload["intents"][0]["status"] == "expired"
    assert payload["intents"][0]["observed_at"] is None
    body = json.loads(status.output)
    assert body["intents"][0]["intent_id"] == intent.intent_id
    assert path.read_bytes() == before
    assert _tables(path) == tables
    assert "market_snapshots" not in tables


def test_populated_queries_keep_status_approval_and_replay(repo, prepared, monkeypatch) -> None:
    service, intent = prepared
    path = repo.db_path
    before = path.read_bytes()

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return NOW.replace(tzinfo=None)
            return NOW.astimezone(tz)

    monkeypatch.setattr("local_market_agent.paper.execution.datetime", _FrozenNow)
    reader = ReadOnlySQLiteRepository(path)
    projected = workflow_status(reader, Settings(db_path=path), now=NOW)
    assert projected["read_only"] is True
    assert projected["intents"][0]["status"] == "pending_manual_approval"
    assert "paper-approve" in projected["intents"][0]["next_command"]
    assert verify_execution(reader, "unknown-fixture") == {
        "errors": [RECEIPT_MISSING],
        "intent_id": "unknown-fixture",
        "ok": False,
    }
    assert path.read_bytes() == before

    workflow = _invoke(path, "workflow-status")
    status = _invoke(path, "paper-status")
    replay = _invoke(path, "paper-replay", "--intent-id", "unknown-fixture")
    assert workflow.exit_code == 0, workflow.output
    payload = json.loads(workflow.output)
    assert payload["intents"][0]["status"] == "pending_manual_approval"
    assert "paper-approve" in payload["intents"][0]["next_command"]
    assert intent.intent_id in payload["intents"][0]["next_command"]
    listed = json.loads(status.output)
    assert listed["intents"][0]["intent_id"] == intent.intent_id
    assert listed["approvals"] == []
    assert replay.exit_code == 1
    assert json.loads(replay.output)["errors"] == [RECEIPT_MISSING]
    assert path.read_bytes() == before

    copied = path.parent / "old lib" / SPECIAL
    copied.parent.mkdir()
    copied.write_bytes(before)
    copied_status = _invoke(copied, "paper-status")
    assert copied_status.exit_code == 0, copied_status.output
    assert json.loads(copied_status.output)["intents"][0]["intent_id"] == intent.intent_id
    assert copied.read_bytes() == before

    approve(service, intent)
    approved_bytes = path.read_bytes()
    approved = _invoke(path, "paper-status")
    assert approved.exit_code == 0, approved.output
    approvals = json.loads(approved.output)["approvals"]
    assert approvals[0]["intent_id"] == intent.intent_id
    assert approvals[0]["decision"] == "approved"
    assert path.read_bytes() == approved_bytes

    service.execute(intent.intent_id, now=NOW)
    executed = path.read_bytes()
    success = _invoke(path, "paper-replay", "--intent-id", intent.intent_id)
    assert success.exit_code == 0, success.output
    body = json.loads(success.output)
    assert body["ok"] is True
    assert body["intent_id"] == intent.intent_id
    assert "receipt" in body
    done = _invoke(path, "workflow-status")
    assert done.exit_code == 0, done.output
    row = json.loads(done.output)["intents"][0]
    assert row["status"] == "completed"
    assert "paper-replay" in row["next_command"]
    assert path.read_bytes() == executed

    special = path.parent / "replay lib" / SPECIAL
    special.parent.mkdir()
    special.write_bytes(executed)
    special_replay = _invoke(special, "paper-replay", "--intent-id", intent.intent_id)
    assert special_replay.exit_code == 0, special_replay.output
    assert json.loads(special_replay.output)["ok"] is True
    assert special.read_bytes() == executed

    fill = repo.list_paper_fills()[0]
    repo._save("paper_fills", "fill_id", fill.model_copy(update={"fees": fill.fees + 1}))
    mutated = path.read_bytes()
    failed = _invoke(path, "paper-replay", "--intent-id", intent.intent_id)
    assert failed.exit_code == 1
    errors = json.loads(failed.output)["errors"]
    assert any("checksum" in error for error in errors)
    assert path.read_bytes() == mutated


def test_readonly_connection_rejects_writes(repo, brief) -> None:
    before = repo.db_path.read_bytes()
    siblings = _siblings(repo.db_path)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        ReadOnlySQLiteRepository(repo.db_path).save_brief(brief)
    assert repo.db_path.read_bytes() == before
    assert _siblings(repo.db_path) == siblings


def test_write_commands_still_initialize_a_missing_database(tmp_path: Path) -> None:
    path = tmp_path / "created" / "ledger.sqlite"
    assert not path.parent.exists()
    result = CliRunner().invoke(app, ["ingest-demo", "--db", str(path)])
    assert result.exit_code == 0, result.output
    assert path.is_file()
    tables = _tables(path)
    assert "market_snapshots" in tables
    assert "prepared_executions" in tables

    partial = tmp_path / "partial.sqlite"
    with sqlite3.connect(partial) as connection:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
    SQLiteRepository(partial)
    migrated = _tables(partial)
    assert "sample" in migrated
    assert "paper_orders" in migrated
    assert "prepared_executions" in migrated
