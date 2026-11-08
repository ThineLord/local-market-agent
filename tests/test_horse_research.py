"""Synthetic checkpoint packets: no original predictions or actual tickets are fabricated."""

import hashlib
import json
from datetime import UTC, datetime

import pytest

from local_market_agent.horse_racing.models import HistoricalRecord
from local_market_agent.horse_racing.presentation import workspace_payload
from local_market_agent.horse_racing.research import load_research

NOW = datetime(2026, 1, 2, tzinfo=UTC)


def write_packet(directory, *, reviewed=True):
    directory.mkdir()
    sources = []
    for sid, category, captured in [
        ("facts", "pre_race", "2026-01-01T09:49:30Z"),
        ("odds3", "pre_race", "2026-01-01T09:56:30Z"),
        ("budget", "budget", "2026-01-01T09:00:00Z"),
        ("archive", "availability_evidence", "2026-01-01T11:00:00Z"),
    ]:
        body = ("SYNTHETIC FIXTURE: " + sid).encode()
        (directory / (sid + ".txt")).write_bytes(body)
        sources.append(
            dict(
                source_id=sid,
                path=sid + ".txt",
                sha256=hashlib.sha256(body).hexdigest(),
                category=category,
                captured_at=captured,
                claimed_available_at=captured,
                description="Invented input for offline protocol tests",
            )
        )
    checkpoints = []
    for stage, decision in [("T10", "2026-01-01T09:50:00Z"), ("T3", "2026-01-01T09:57:00Z")]:
        runners = []
        for no in range(1, 8):
            quote = dict(
                notation="gross_decimal_indicative",
                observed_at="2026-01-01T09:49:30Z" if stage == "T10" else "2026-01-01T09:56:30Z",
                low=4,
                high=5,
            )
            runners.append(
                dict(
                    horse_no=no,
                    horse_id=f"S{no}",
                    name=f"Synthetic {no}",
                    draw=no,
                    weight_lb=120,
                    jockey="Synthetic jockey",
                    jockey_evidence="No performance conclusion; synthetic record only",
                    recent_form=[
                        dict(
                            race_date="2025-12-01",
                            available_at="2025-12-02T00:00:00Z",
                            course="ST",
                            surface="AWT",
                            distance_m=1200,
                            finish=no,
                            field_size=7,
                        )
                    ],
                    win_quote=quote,
                    place_quote=quote,
                    source_ids=["facts"] if stage == "T10" else ["facts", "odds3"],
                )
            )
        checkpoints.append(
            dict(
                meeting_date="2026-01-01",
                course="ST",
                race_no=1,
                stage=stage,
                decision_at=decision,
                scheduled_start="2026-01-01T10:00:00Z",
                scheduled_start_known_at="2026-01-01T09:00:00Z",
                surface="AWT",
                distance_m=1200,
                going="GOOD",
                declared_count=7,
                runners=runners,
                source_ids=["facts"] if stage == "T10" else ["facts", "odds3"],
            )
        )
    packet = dict(
        schema_version=1,
        meeting_date="2026-01-01",
        course="ST",
        race_count=1,
        data_kind="synthetic_fixture",
        sources=sources,
        checkpoints=checkpoints,
        budget=dict(
            initial_bankroll="200",
            meeting_cap="40",
            unit_stake=10,
            frozen_at="2026-01-01T09:01:00Z",
            source_id="budget",
        ),
    )
    save_packet(directory, packet, reviewed=reviewed)
    return packet


def save_packet(directory, packet, *, reviewed=True):
    raw = json.dumps(packet).encode()
    (directory / "research.json").write_bytes(raw)
    if reviewed:
        review = dict(
            schema_version=1,
            input_sha256=hashlib.sha256(raw).hexdigest(),
            source_hashes={s["source_id"]: s["sha256"] for s in packet["sources"]},
            reviewer="Synthetic test reviewer",
            reviewed_at="2026-01-01T12:00:00Z",
            conclusion="supported_by_archived_evidence",
            availability_evidence_ids=["archive"],
            rationale="Synthetic test only; not real timing evidence",
        )
        (directory / "availability-review.json").write_text(json.dumps(review))


def test_full_field_two_checkpoint_audit_still_no_bet(tmp_path):
    directory = tmp_path / "research"
    write_packet(directory)
    report = load_research(directory, now=NOW)
    race = report["races"][0]
    assert report["orders_created"] == 0 and race["decision"] == "NO_BET"
    assert race["blockers"] == ["PROBABILITY_MODEL_NOT_VALIDATED", "SYNTHETIC_DATA_ONLY"]
    assert len(race["checkpoints"]["T10"]) == 7 and len(race["checkpoints"]["T3"]) == 7
    first = race["checkpoints"]["T10"][0]
    assert "1/1 recorded top-three" in first["strength_observations"][0]
    assert first["pools"]["WIN"]["validated_probability"] is None
    assert first["pools"]["PLACE"]["original_probability"] is None


@pytest.mark.parametrize(
    "change,reason",
    [
        ("missing_t3", "T3_SNAPSHOT_MISSING"),
        ("unreviewed", "POINT_IN_TIME_AVAILABILITY_UNREVIEWED"),
        ("late_source", "T10_SOURCE_NOT_AVAILABLE_AT_DECISION"),
        ("stale_quote", "T3_HORSE_1_WIN_QUOTE_MISSING_OR_STALE"),
        ("future_form", "T10_HORSE_1_FORM_LOOKAHEAD"),
        ("late_schedule", "T10_SCHEDULE_OR_CHECKPOINT_TIME_INVALID"),
        ("field_change", "FIELD_CHANGE_REQUIRES_REVIEW"),
        ("budget", "PRECOMMITTED_BUDGET_UNKNOWN"),
        ("late_budget", "BUDGET_NOT_EVIDENCED_BEFORE_DECISION"),
        ("withdrawal", "T3_WITHDRAWAL_REQUIRES_REVIEW"),
        ("missing_form", "T10_HORSE_1_FACTS_UNKNOWN"),
        ("schedule_change", "SCHEDULE_CHANGE_REQUIRES_REVIEW"),
    ],
)
def test_meaningful_blockers_survive_rehashed_input(tmp_path, change, reason):
    directory = tmp_path / "research"
    p = write_packet(directory)
    if change == "missing_t3":
        p["checkpoints"].pop()
    if change == "unreviewed":
        (directory / "availability-review.json").unlink()
    if change == "late_source":
        p["sources"][0]["captured_at"] = "2026-01-01T10:01:00Z"
    if change == "stale_quote":
        p["checkpoints"][1]["runners"][0]["win_quote"]["observed_at"] = "2026-01-01T09:50:00Z"
    if change == "future_form":
        p["checkpoints"][0]["runners"][0]["recent_form"][0]["race_date"] = "2026-01-01"
    if change == "late_schedule":
        p["checkpoints"][0]["scheduled_start_known_at"] = "2026-01-01T09:59:00Z"
    if change == "field_change":
        p["checkpoints"][1]["runners"][0]["horse_id"] = "OTHER"
    if change == "budget":
        p["budget"] = None
    if change == "late_budget":
        p["budget"]["frozen_at"] = "2026-01-01T09:59:00Z"
    if change == "withdrawal":
        p["checkpoints"][1]["runners"][0]["status"] = "withdrawn"
    if change == "missing_form":
        p["checkpoints"][0]["runners"][0]["recent_form"] = None
    if change == "schedule_change":
        p["checkpoints"][1]["scheduled_start"] = "2026-01-01T10:01:00Z"
    save_packet(directory, p, reviewed=change != "unreviewed")
    report = load_research(directory, now=NOW)
    assert reason in report["races"][0]["blockers"]
    assert report["races"][0]["decision"] == "NO_BET"


@pytest.mark.parametrize(
    "change",
    [
        "hash",
        "review_hash",
        "path",
        "cross_race",
        "incomplete_field",
        "final_result",
        "naive",
        "net_odds",
        "pool_probability",
        "review_future",
    ],
)
def test_rejects_unbound_or_incompatible_evidence(tmp_path, change):
    directory = tmp_path / "research"
    p = write_packet(directory)
    if change == "hash":
        (directory / "facts.txt").write_text("changed")
    if change == "path":
        p["sources"][0]["path"] = "../outside.txt"
    if change == "cross_race":
        p["checkpoints"][0]["course"] = "HV"
    if change == "incomplete_field":
        p["checkpoints"][0]["runners"].pop()
    if change == "final_result":
        p["checkpoints"][0]["final_dividend"] = 20
    if change == "naive":
        p["checkpoints"][0]["decision_at"] = "2026-01-01T09:50:00"
    if change == "net_odds":
        p["checkpoints"][0]["runners"][0]["win_quote"]["notation"] = "net_decimal"
    if change == "pool_probability":
        runner = p["checkpoints"][0]["runners"][0]
        runner["original_win"] = dict(
            probability=0.8, rationale="Synthetic", method="Synthetic", source_id="facts"
        )
        runner["original_place"] = dict(
            probability=0.2, rationale="Synthetic", method="Synthetic", source_id="facts"
        )
    save_packet(directory, p)
    if change in {"review_hash", "review_future"}:
        path = directory / "availability-review.json"
        review = json.loads(path.read_text())
        review["input_sha256" if change == "review_hash" else "reviewed_at"] = (
            "0" * 64 if change == "review_hash" else "2030-01-01T00:00:00Z"
        )
        path.write_text(json.dumps(review))
    with pytest.raises(ValueError):
        load_research(directory, now=NOW)


def test_original_probability_and_indicative_value_not_model_or_order(tmp_path):
    directory = tmp_path / "research"
    p = write_packet(directory)
    p["checkpoints"][0]["runners"][0]["original_win"] = dict(
        probability=0.5,
        rationale="Original synthetic note",
        method="unvalidated hand estimate",
        source_id="facts",
    )
    save_packet(directory, p)
    report = load_research(directory, now=NOW)
    value = report["races"][0]["checkpoints"]["T10"][0]["pools"]["WIN"]
    assert value["illustrative_ev_lower"] == 1 and value["original_probability"] == 0.5
    assert value["validated_probability"] is None
    assert report["races"][0]["decision"] == "NO_BET"


def test_workspace_missing_invalid_and_source_recomputation(tmp_path):
    assert workspace_payload()["status"] == "missing"
    assert workspace_payload(tmp_path)["status"] == "invalid"
    # No official source: a local claimed payout never becomes official/cash.
    record = HistoricalRecord(
        meeting_date="2026-01-01",
        course="ST",
        initial_bankroll="200",
        unit_stake="10",
        provenance="Synthetic",
        recorded_at=NOW,
        races=[
            dict(
                race_no=1,
                participation="REPORTED_TICKETS",
                tickets=[
                    dict(
                        ticket_id="s",
                        horse_no=1,
                        pool="WIN",
                        stake="10",
                        record_kind="synthetic_fixture",
                    )
                ],
                provisional_gross_return="20",
            )
        ],
    )
    (tmp_path / "user-history.json").write_text(record.model_dump_json())
    (tmp_path / "replay.json").write_text('{"fake_profit": 999999}')
    r = workspace_payload(tmp_path)["report"]
    assert r["official_entitlement"]["net_profit"] is None and r["provisional"]["net_profit"] == 10
    assert r["cash"]["redeemed_balance"] is None
    assert r["research"]["races"][0]["decision"] == "NO_BET"
    assert not list(tmp_path.glob("*.sqlite"))
    packet = write_packet(tmp_path / "research")
    packet["meeting_date"] = "2026-01-02"
    packet["checkpoints"] = []
    save_packet(tmp_path / "research", packet)
    assert workspace_payload(tmp_path)["status"] == "invalid"


def test_unknown_form_finish_is_not_counted_as_observed_failure(tmp_path):
    directory = tmp_path / "research"
    packet = write_packet(directory)
    packet["checkpoints"][0]["runners"][0]["recent_form"][0]["finish"] = None
    save_packet(directory, packet)
    race = load_research(directory, now=NOW)["races"][0]
    runner = race["checkpoints"]["T10"][0]
    assert runner["strength_observations"] == ["UNKNOWN"]
    assert runner["weakness_observations"] == ["UNKNOWN"]
    assert "T10_HORSE_1_FORM_FINISH_UNKNOWN" in race["blockers"]
    assert "1 comparable run finishes UNKNOWN" in runner["uncertainties"]
