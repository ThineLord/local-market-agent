"""Market snapshot lists order by absolute time before LIMIT."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from local_market_agent.agents import ResearchBriefGenerator
from local_market_agent.config import Settings
from local_market_agent.paper.execution import PaperExecutionService
from local_market_agent.paper.ledger import PaperLedger
from local_market_agent.risk import RiskEngine, RiskGateEvaluator
from local_market_agent.schemas import (
    MarketSnapshot,
    PaperOrder,
    RiskGateCheck,
    RiskGateDecision,
    RiskGateDecisionStatus,
)
from local_market_agent.schemas.models import OrderSide
from local_market_agent.strategy import PredictionMarketEdgeStrategy
from ui.server import DashboardRepository

CANDIDATE = Path(__file__).parents[1] / "data/fixtures/watchlist/candidate.json"
PLUS_8 = timezone(timedelta(hours=8))


def _payload(snapshot_id: str, as_of: str, market_id: str = "demo-candidate") -> dict:
    raw = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    body = dict(raw["snapshot"])
    market = dict(raw["market"])
    market["market_id"] = market_id
    body["snapshot_id"] = snapshot_id
    body["as_of"] = as_of
    body["market"] = market
    return body


def _insert(repo, snapshot_id: str, as_of: str, market_id: str = "demo-candidate") -> None:
    payload = _payload(snapshot_id, as_of, market_id)
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute(
            """
            INSERT INTO market_snapshots (snapshot_id, market_id, created_at, payload)
            VALUES (?, ?, ?, ?)
            """,
            (snapshot_id, market_id, as_of, json.dumps(payload, sort_keys=True)),
        )


def _stored(repo) -> list[tuple]:
    with sqlite3.connect(repo.db_path) as conn:
        return conn.execute(
            """
            SELECT snapshot_id, market_id, created_at, payload
            FROM market_snapshots
            ORDER BY rowid
            """
        ).fetchall()


def _ids(repo, market_id: str | None = None, limit: int | None = None) -> list[str]:
    return [item.snapshot_id for item in repo.list_market_snapshots(market_id, limit)]


def _insert_row(repo, table: str, key_name: str, key: str, created_at: str, payload: dict) -> None:
    body = dict(payload)
    body[key_name] = key
    body["created_at"] = created_at
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute(
            f"INSERT INTO {table} ({key_name}, market_id, created_at, payload) VALUES (?, ?, ?, ?)",
            (key, body.get("market_id"), created_at, json.dumps(body, sort_keys=True)),
        )


def _order_body() -> dict:
    return PaperOrder(
        order_id="placeholder",
        signal_id="signal-synthetic",
        risk_decision_id="risk-synthetic",
        market_id="demo-candidate",
        created_at=datetime(2026, 6, 5, 2, tzinfo=UTC),
        side=OrderSide.BUY_YES,
        quantity=1,
        limit_price=0.4,
        fill_price=0.4,
    ).model_dump(mode="json")


def _gate_body() -> dict:
    approved = RiskGateDecisionStatus.APPROVED
    return RiskGateDecision(
        risk_gate_decision_id="placeholder",
        intent_id="intent-synthetic",
        signal_id="signal-synthetic",
        market_id="demo-candidate",
        created_at=datetime(2026, 6, 5, 2, tzinfo=UTC),
        status=approved,
        reasons=["synthetic paper gate"],
        checks=[
            RiskGateCheck(
                gate="synthetic",
                status=approved,
                passed=True,
                reason="synthetic paper gate",
            )
        ],
    ).model_dump(mode="json")


def test_latest_snapshot_uses_absolute_time(repo):
    _insert(repo, "A", "2026-06-05T09:00:00+08:00")
    _insert(repo, "B", "2026-06-05T02:00:00Z")
    before = _stored(repo)
    assert _ids(repo, "demo-candidate", 1) == ["B"]
    assert [item.snapshot_id for item in DashboardRepository(repo.db_path).list_market_snapshots(limit=1)] == ["B"]

    _insert(repo, "C", "2026-06-04T23:00:00-04:00")
    stored = _stored(repo)
    db_bytes = repo.db_path.read_bytes()
    assert _ids(repo, "demo-candidate", 1) == ["C"]
    assert _ids(repo, "demo-candidate", 3) == ["C", "B", "A"]
    dashboard = DashboardRepository(repo.db_path)
    assert [item.snapshot_id for item in dashboard.list_market_snapshots(limit=1)] == ["C"]
    listed = repo.list_market_snapshots("demo-candidate")
    by_id = {item.snapshot_id: item for item in listed}
    assert by_id["A"].as_of.isoformat() == "2026-06-05T09:00:00+08:00"
    assert by_id["A"].as_of.utcoffset() == timedelta(hours=8)
    assert by_id["C"].as_of.isoformat() == "2026-06-04T23:00:00-04:00"
    assert by_id["C"].as_of.utcoffset() == timedelta(hours=-4)
    assert by_id["B"].as_of.utcoffset() == timedelta(0)
    assert stored == _stored(repo)
    assert before == stored[:2]
    assert repo.db_path.read_bytes() == db_bytes
    raw = {row[0]: (row[2], json.loads(row[3])["as_of"]) for row in stored}
    assert raw["A"] == ("2026-06-05T09:00:00+08:00", "2026-06-05T09:00:00+08:00")
    assert raw["B"] == ("2026-06-05T02:00:00Z", "2026-06-05T02:00:00Z")
    assert raw["C"] == ("2026-06-04T23:00:00-04:00", "2026-06-04T23:00:00-04:00")


def test_equivalent_timezone_literals_tie_break_on_rowid(repo):
    _insert(repo, "z", "2026-06-05T02:00:00Z")
    _insert(repo, "plus", "2026-06-05T02:00:00+00:00")
    assert _ids(repo, "demo-candidate", 1) == ["plus"]
    _insert(repo, "basic", "2026-06-05T02:00:00+0000")
    _insert(repo, "hour", "2026-06-05T03:00:00+01:00")
    _insert(repo, "eight", "2026-06-05T10:00:00+08:00")
    assert _ids(repo, "demo-candidate", 1) == ["eight"]
    assert _ids(repo, "demo-candidate") == ["eight", "hour", "basic", "plus", "z"]
    exported = [item["snapshot_id"] for item in repo.export_payloads("market_snapshots")]
    assert exported == ["z", "plus", "basic", "hour", "eight"]

    _insert(repo, "eight-first", "2026-06-05T10:00:00+08:00", "other-tie")
    _insert(repo, "z-later", "2026-06-05T02:00:00Z", "other-tie")
    assert _ids(repo, "other-tie", 1) == ["z-later"]
    assert [row[2] for row in _stored(repo) if row[0] == "z-later"] == ["2026-06-05T02:00:00Z"]


def test_adjacent_microseconds_ignore_later_insert(repo):
    _insert(repo, "newer", "2026-06-05T02:00:00.000100Z")
    _insert(repo, "older", "2026-06-05T02:00:00.000099+00:00")
    _insert(repo, "older-offset", "2026-06-05T10:00:00.000099+08:00")
    assert _ids(repo, "demo-candidate", 1) == ["newer"]
    assert _ids(repo, "demo-candidate", 2) == ["newer", "older-offset"]
    assert repo.list_market_snapshots("demo-candidate", 1)[0].as_of.microsecond == 100


def test_limit_and_market_filter_use_absolute_time(repo):
    _insert(repo, "A", "2026-06-05T09:00:00+08:00")
    _insert(repo, "B", "2026-06-05T02:00:00Z")
    _insert(repo, "C", "2026-06-04T23:00:00-04:00")
    _insert(repo, "X", "2026-06-05T09:30:00+08:00", "other-market")
    _insert(repo, "Y", "2026-06-05T00:30:00Z", "other-market")
    assert _ids(repo, "demo-candidate", 1) == ["C"]
    assert _ids(repo, "demo-candidate", 2) == ["C", "B"]
    assert _ids(repo, "other-market", 1) == ["X"]
    assert _ids(repo, "other-market", 2) == ["X", "Y"]
    assert _ids(repo, None, 1) == ["C"]
    assert _ids(repo, None, 3) == ["C", "B", "X"]
    assert _ids(repo, "missing", 1) == []


def test_timezone_less_and_empty_timestamps_keep_text_order(repo):
    rows = [
        ("empty-early", ""),
        ("naive-sec", "2026-06-05T02:00:00"),
        ("naive-hi", "2026-06-05T02:00:00.000100"),
        ("naive-lo", "2026-06-05T02:00:00.000099"),
        ("empty-late", ""),
        ("naive-3", "2026-06-05T03:00:00"),
    ]
    for snapshot_id, created_at in rows:
        as_of = created_at or "2026-06-05T00:00:00"
        _insert(repo, snapshot_id, as_of)
        if created_at != as_of:
            with sqlite3.connect(repo.db_path) as conn:
                conn.execute(
                    "UPDATE market_snapshots SET created_at = ? WHERE snapshot_id = ?",
                    (created_at, snapshot_id),
                )
    before = _stored(repo)
    db_bytes = repo.db_path.read_bytes()
    assert _ids(repo, "demo-candidate") == [
        "naive-3",
        "naive-hi",
        "naive-lo",
        "naive-sec",
        "empty-late",
        "empty-early",
    ]
    assert _ids(repo, "demo-candidate", 1) == ["naive-3"]
    exported_ids = [item["snapshot_id"] for item in repo.export_payloads("market_snapshots")]
    assert exported_ids == [
        "empty-early",
        "empty-late",
        "naive-sec",
        "naive-lo",
        "naive-hi",
        "naive-3",
    ]
    assert [item.snapshot_id for item in DashboardRepository(repo.db_path).list_market_snapshots()] == _ids(repo)
    assert _stored(repo) == before
    assert repo.db_path.read_bytes() == db_bytes


def test_export_uses_absolute_time_oldest_first(repo):
    _insert(repo, "A", "2026-06-05T09:00:00+08:00")
    _insert(repo, "E", "2026-06-05T03:00:00+08:00")
    _insert(repo, "B", "2026-06-05T02:00:00Z")
    before = _stored(repo)
    assert _ids(repo, "demo-candidate") == ["B", "A", "E"]
    by_id = {row[0]: json.loads(row[3]) for row in before}
    exported = list(repo.export_payloads("market_snapshots"))
    assert exported == [by_id["E"], by_id["A"], by_id["B"]]
    assert exported[0]["as_of"] == "2026-06-05T03:00:00+08:00"
    assert exported[1]["as_of"] == "2026-06-05T09:00:00+08:00"
    assert exported[2]["as_of"] == "2026-06-05T02:00:00Z"
    assert _stored(repo) == before


def test_public_exports_follow_absolute_time_oldest_first(repo, tmp_path: Path):
    older = "2026-06-05T09:00:00+08:00"
    newer = "2026-06-05T02:00:00Z"
    order_body = _order_body()
    gate_body = _gate_body()
    _insert_row(repo, "paper_orders", "order_id", "A", older, order_body)
    _insert_row(repo, "paper_orders", "order_id", "B", newer, order_body)
    _insert_row(repo, "risk_gate_decisions", "risk_gate_decision_id", "A", older, gate_body)
    _insert_row(repo, "risk_gate_decisions", "risk_gate_decision_id", "B", newer, gate_body)
    before = repo.db_path.read_bytes()

    assert [item.order_id for item in repo.list_paper_orders()] == ["B", "A"]
    dashboard = DashboardRepository(repo.db_path)
    assert [item.order_id for item in dashboard.list_paper_orders()] == ["B", "A"]
    listed_gates = repo.list_risk_gate_decisions()
    assert [item.risk_gate_decision_id for item in listed_gates] == ["B", "A"]

    ledger = PaperLedger(repo)
    jsonl = ledger.export_jsonl(tmp_path / "paper_orders.jsonl")
    csv_path = ledger.export_csv(tmp_path / "paper_orders.csv")
    orders = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
    assert [item["order_id"] for item in orders] == ["A", "B"]
    assert [item["created_at"] for item in orders] == [older, newer]
    with csv_path.open(encoding="utf-8", newline="") as handle:
        assert [row["order_id"] for row in csv.DictReader(handle)] == ["B", "A"]

    gate_path = RiskGateEvaluator(repository=repo).export_jsonl(tmp_path / "risk_gates.jsonl")
    gates = [json.loads(line) for line in gate_path.read_text(encoding="utf-8").splitlines()]
    assert [item["risk_gate_decision_id"] for item in gates] == ["A", "B"]
    assert [item["created_at"] for item in gates] == [older, newer]
    assert repo.db_path.read_bytes() == before


def test_public_export_same_instant_follows_ascending_rowid(repo, tmp_path: Path):
    older_row = "2026-06-05T10:00:00+08:00"
    newer_row = "2026-06-05T02:00:00Z"
    order_body = _order_body()
    _insert_row(repo, "paper_orders", "order_id", "A", older_row, order_body)
    _insert_row(repo, "paper_orders", "order_id", "B", newer_row, order_body)
    before = repo.db_path.read_bytes()
    assert [item.order_id for item in repo.list_paper_orders()] == ["B", "A"]
    jsonl = PaperLedger(repo).export_jsonl(tmp_path / "paper_orders.jsonl")
    orders = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
    assert [item["order_id"] for item in orders] == ["A", "B"]
    assert [item["created_at"] for item in orders] == [older_row, newer_row]
    assert repo.db_path.read_bytes() == before


def test_uniform_utc_offset_uses_stored_text_order(repo):
    _insert(repo, "early", "2026-06-05T01:00:00+00:00")
    _insert(repo, "micro", "2026-06-05T02:00:00.000100+00:00")
    _insert(repo, "later", "2026-06-05T02:00:00.000100+00:00")
    _insert(repo, "whole", "2026-06-05T02:00:00+00:00")
    with repo._connection() as conn:
        assert repo._timestamp_order_key(conn, "market_snapshots", "", []) == "created_at"
        filtered = repo._timestamp_order_key(
            conn, "market_snapshots", "WHERE market_id = ?", ["demo-candidate"]
        )
        assert filtered == "created_at"
    assert _ids(repo) == ["later", "micro", "whole", "early"]
    assert _ids(repo, limit=1) == ["later"]
    exported = [item["snapshot_id"] for item in repo.export_payloads("market_snapshots")]
    assert exported == ["early", "whole", "micro", "later"]

    _insert(repo, "offset", "2026-06-05T09:00:00+08:00", "other-market")
    with repo._connection() as conn:
        assert repo._timestamp_order_key(conn, "market_snapshots", "", []) != "created_at"
        filtered = repo._timestamp_order_key(
            conn, "market_snapshots", "WHERE market_id = ?", ["demo-candidate"]
        )
        assert filtered == "created_at"
    assert _ids(repo, "demo-candidate", 1) == ["later"]


def test_zero_fraction_utc_tie_stays_on_absolute_rowid(repo):
    _insert(repo, "padded", "2026-06-05T02:00:00.000000+00:00")
    _insert(repo, "plain", "2026-06-05T02:00:00+00:00")
    with repo._connection() as conn:
        assert repo._timestamp_order_key(conn, "market_snapshots", "", []) != "created_at"
    assert _ids(repo, limit=1) == ["plain"]
    exported = [item["snapshot_id"] for item in repo.export_payloads("market_snapshots")]
    assert exported == ["padded", "plain"]
    raw = {row[0]: row[2] for row in _stored(repo)}
    assert raw == {
        "padded": "2026-06-05T02:00:00.000000+00:00",
        "plain": "2026-06-05T02:00:00+00:00",
    }


def _prepare(repo, snapshot, evidence, as_of, now):
    snapshot = snapshot.model_copy(update={"snapshot_id": "snapshot-current", "as_of": as_of})
    brief = ResearchBriefGenerator().generate(snapshot, evidence).model_copy(update={"created_at": now})
    signal = PredictionMarketEdgeStrategy().generate_signal(brief, snapshot)
    risk = RiskEngine().evaluate_signal(signal)
    service = PaperExecutionService(repo, Settings(db_path=repo.db_path))
    intent = service.prepare(signal, risk, snapshot, brief, now=now, simulation=True)
    return service, intent


def test_lexically_greater_offset_is_not_a_newer_observation(repo, snapshot, evidence):
    now = datetime(2026, 6, 5, 2, tzinfo=UTC)
    service, intent = _prepare(repo, snapshot, evidence, now, now)
    older = repo.load_market_snapshot(intent.snapshot_id).model_copy(
        update={"snapshot_id": "offset-older", "as_of": datetime(2026, 6, 5, 9, tzinfo=PLUS_8)}
    )
    repo.save_market_snapshot(older)
    loaded, current, _, _, _ = service._load(repo, intent.intent_id)
    assert current.snapshot_id == "snapshot-current"
    assert loaded.snapshot_id == intent.snapshot_id
    assert repo.count("paper_orders") == 0
    with sqlite3.connect(repo.db_path) as conn:
        created_at = conn.execute(
            "SELECT created_at FROM market_snapshots WHERE snapshot_id = 'offset-older'"
        ).fetchone()[0]
    assert created_at == "2026-06-05T09:00:00+08:00"


def test_absolutely_newer_snapshot_still_blocks_the_saved_intent(repo, snapshot, evidence):
    as_of = datetime(2026, 6, 5, 9, tzinfo=PLUS_8)
    now = datetime(2026, 6, 5, 1, 2, tzinfo=UTC)
    service, intent = _prepare(repo, snapshot, evidence, as_of, now)
    newer = repo.load_market_snapshot(intent.snapshot_id).model_copy(
        update={"snapshot_id": "utc-newer", "as_of": datetime(2026, 6, 5, 2, tzinfo=UTC)}
    )
    repo.save_market_snapshot(newer)
    with pytest.raises(ValueError, match="Newer market observation exists"):
        service._load(repo, intent.intent_id)
    assert repo.count("paper_orders") == 0
    with sqlite3.connect(repo.db_path) as conn:
        rows = dict(conn.execute("SELECT snapshot_id, created_at FROM market_snapshots"))
    assert rows["snapshot-current"] == "2026-06-05T09:00:00+08:00"
    assert rows["utc-newer"] == "2026-06-05T02:00:00+00:00"


def test_saved_candidate_copies_use_absolute_time(repo):
    raw = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    for snapshot_id, as_of in (
        ("A", "2026-06-05T09:00:00+08:00"),
        ("B", "2026-06-05T02:00:00Z"),
    ):
        body = dict(raw["snapshot"])
        body.update(snapshot_id=snapshot_id, as_of=as_of, market=raw["market"])
        repo.save_market_snapshot(MarketSnapshot.model_validate(body))
    before = _stored(repo)
    assert _ids(repo, "demo-candidate", 1) == ["B"]
    assert [item.snapshot_id for item in DashboardRepository(repo.db_path).list_market_snapshots(limit=1)] == ["B"]
    assert _stored(repo) == before
    created = {row[0]: row[2] for row in before}
    assert created["A"] == "2026-06-05T09:00:00+08:00"
    assert created["B"] == "2026-06-05T02:00:00+00:00"
    assert json.loads(before[0][3])["as_of"] == "2026-06-05T09:00:00+08:00"
