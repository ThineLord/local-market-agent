"""All fixtures in this file are invented; no real user's ticket history."""

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from local_market_agent.horse_racing.models import HistoricalRecord
from local_market_agent.horse_racing.replay import replay_history
from local_market_agent.horse_racing.results import (
    collect_results,
    load_results,
    parse_starters,
    result_url,
    starters_url,
)

DAY = date(2026, 1, 1)
NOW = datetime(2026, 1, 2, tzinfo=UTC)


def result_html(race=1):
    rows = "".join(
        f"<tr><td>{n}</td><td>{n}</td><td>SYNTHETIC HORSE {n} (S00{n})</td><td>Test Jockey</td><td>Test Trainer</td><td>120</td><td>1000</td><td>{n}</td><td>0</td><td>1</td><td>1:00</td><td>8</td></tr>"
        for n in range(1, 8)
    )
    return f"""<div class="raceMeeting_select"><span class="f_fl">Race Meeting: 01/01/2026 Sha Tin</span></div>
    <div class="race_tab"><table><thead><tr><td>RACE {race} (100)</td></tr></thead><tbody><tr><td>Class 4 - 1200M - (60-40)</td><td>Going :</td><td>GOOD</td></tr><tr><td>SYNTHETIC HANDICAP</td><td>Course :</td><td>ALL WEATHER TRACK</td></tr></tbody></table></div>
    <table><thead><tr><td>Pla. Horse No. Horse Jockey Trainer Act. Wt. Declar. Horse Wt. Dr. LBW Running Position Finish Time Win Odds</td></tr></thead><tbody>{rows}</tbody></table>
    <table><thead><tr><td>Dividend Pool Winning Combination Dividend (HK$)</td></tr></thead><tbody><tr><td rowspan="1">WIN</td><td>1</td><td>20.00</td></tr><tr><td rowspan="3">PLACE</td><td>1</td><td>10.00</td></tr><tr><td>2</td><td>15.00</td></tr><tr><td>3</td><td>12.00</td></tr></tbody></table>""".encode()


def starters_html(races=4):
    header = [
        "No",
        "Horse",
        "Brand No.",
        "Draw",
        "Gear",
        "Jockey",
        "Handicap Wt.",
        "Rtg",
        "Horse Wt.",
        "Last Winning Wt.",
        "Last Winning Date",
        "Trainer",
    ]
    parts = ['<h2 class="meetingInfo">FOR RACE MEETING ON 01/01/2026 SHA TIN - AWT -</h2>']
    for race in range(1, races + 1):
        rows = "<tr>" + "".join(f"<td>{x}</td>" for x in header) + "</tr>"
        for n in range(1, 8):
            values = [
                str(n),
                f"SYNTHETIC HORSE {n}",
                f"(S00{n})",
                str(n),
                "",
                "Test Jockey",
                "120",
                "40",
                "1000",
                "",
                "",
                "Test Trainer",
            ]
            rows += "<tr>" + "".join(f"<td>{x}</td>" for x in values) + "</tr>"
        parts.append(
            f'<div id="ST{race:02d}"><h3 class="raceInfo">RACE {race} - 6:45 PM 1200Metres</h3><table class="tbRace">{rows}</table>7 Starters</div>'
        )
    return "".join(parts).encode()


def source_directory(directory, races=4):
    directory.mkdir()
    sources = []
    for sid, url, raw in [
        (f"result-{n}", result_url(DAY, "ST", n), result_html(n)) for n in range(1, races + 1)
    ] + [("starters", starters_url(DAY, "ST"), starters_html(races))]:
        name = sid + ".html"
        (directory / name).write_bytes(raw)
        sources.append(
            {
                "source_id": sid,
                "path": name,
                "url": url,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "retrieved_at": NOW.isoformat(),
                "published_at": None,
            }
        )
    manifest = {
        "schema_version": 1,
        "meeting_date": DAY.isoformat(),
        "course": "ST",
        "race_count": races,
        "sources": sources,
        "errors": [],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def historical_record():
    def ticket(tid, no, pool):
        return {
            "ticket_id": tid,
            "horse_no": no,
            "pool": pool,
            "stake": "10",
            "record_kind": "synthetic_fixture",
        }

    return HistoricalRecord(
        meeting_date=DAY,
        course="ST",
        initial_bankroll="200",
        unit_stake="10",
        provenance="Invented deterministic fixture",
        recorded_at=NOW,
        races=[
            {"race_no": 1, "participation": "NOT_PLACED"},
            {
                "race_no": 2,
                "participation": "REPORTED_TICKETS",
                "tickets": [ticket("a", 1, "WIN"), ticket("b", 2, "PLACE")],
                "provisional_gross_return": "35",
            },
            {
                "race_no": 3,
                "participation": "REPORTED_TICKETS",
                "tickets": [ticket("c", 7, "WIN")],
                "provisional_gross_return": "0",
            },
            {
                "race_no": 4,
                "participation": "REPORTED_TICKETS",
                "tickets": [ticket("d", 2, "PLACE")],
                "provisional_gross_return": "15",
            },
        ],
    )


def test_complete_official_replay_keeps_cash_and_prediction_unknown(tmp_path):
    source_directory(tmp_path / "sources")
    official = load_results(tmp_path / "sources", now=NOW)
    report = replay_history(historical_record(), official)
    assert report["ticket_count"] == 4 and report["bet_races"] == 3
    assert report["wins"] == 3 and report["hit_rate"] == 0.75
    assert report["pools"]["WIN"]["hit_rate"] == 0.5 and report["pools"]["PLACE"]["hit_rate"] == 1
    metrics = report["official_entitlement"]
    assert (
        metrics["balance"] == 210 and metrics["gross_return"] == 50 and metrics["net_profit"] == 10
    )
    assert metrics["roi"] == 0.25 and metrics["bankroll_return"] == 0.05
    assert metrics["max_drawdown"] == 10 and metrics["max_drawdown_fraction"] == pytest.approx(
        10 / 215
    )
    assert [p["balance"] for p in metrics["curve"]] == [200, 200, 215, 205, 210]
    assert report["cash"]["redeemed_balance"] is None
    assert report["risk"]["budget_adherence"] == "UNKNOWN"
    assert (
        not report["strategy_backtest"]["eligible"] and report["calibration"]["win_brier"] is None
    )
    assert report["races"][0]["historical_no_bet_recommendation"] == "UNKNOWN"
    assert (
        len(official.declarations["2"]["runners"]) == 7
        and not official.declarations["2"]["pre_race_eligible"]
    )


def test_missing_or_unsupported_results_do_not_invent_losses(tmp_path):
    record = historical_record()
    report = replay_history(record)
    assert report["official_entitlement"]["balance"] is None and report["wins"] is None
    assert report["races"][2]["tickets"][0]["official_outcome"] == "UNKNOWN"
    source_directory(tmp_path / "sources")
    official = load_results(tmp_path / "sources", now=NOW)
    official.races[1].supported = False
    assert replay_history(record, official)["official_entitlement"]["balance"] is None
    official.meeting_date = date(2026, 1, 3)
    with pytest.raises(ValueError, match="does not match"):
        replay_history(record, official)


def test_provisional_disagreement_is_preserved_and_cash_requires_evidence(tmp_path):
    source_directory(tmp_path / "sources")
    official = load_results(tmp_path / "sources", now=NOW)
    record = historical_record()
    record.races[1].provisional_gross_return = "99"
    report = replay_history(record, official)
    assert (
        report["provisional"]["balance"] == 274 and report["official_entitlement"]["balance"] == 210
    )
    assert report["races"][1]["payout_agrees"] is False
    payload = record.model_dump(mode="json")
    payload["races"][1]["redeemed_cash"] = "35"
    with pytest.raises(ValueError, match="documentary reference"):
        HistoricalRecord.model_validate(payload)
    payload["races"][1]["redemption_evidence"] = "local receipt reference (synthetic)"
    assert (
        replay_history(HistoricalRecord.model_validate(payload), official)["cash"]["status"]
        == "UNKNOWN"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "negative",
        "nan",
        "bool_horse",
        "unbet_ticket",
        "budget",
        "missing_race",
        "naive",
    ],
)
def test_historical_record_rejects_invalid_or_ambiguous_input(mutation):
    data = historical_record().model_dump(mode="json")
    if mutation == "duplicate":
        data["races"][2]["tickets"][0]["ticket_id"] = "a"
    if mutation == "negative":
        data["races"][1]["tickets"][0]["stake"] = "-10"
    if mutation == "nan":
        data["initial_bankroll"] = "NaN"
    if mutation == "bool_horse":
        data["races"][1]["tickets"][0]["horse_no"] = True
    if mutation == "unbet_ticket":
        data["races"][1]["participation"] = "NOT_PLACED"
    if mutation == "budget":
        data["precommitted_meeting_budget"] = "40"
    if mutation == "missing_race":
        data["races"].pop(0)
    if mutation == "naive":
        data["recorded_at"] = "2026-01-02T00:00:00"
    with pytest.raises(ValueError):
        HistoricalRecord.model_validate(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "path",
        "url",
        "missing",
        "future",
        "date",
        "race",
        "dividend",
        "runner",
        "starter_count",
    ],
)
def test_source_bound_results_fail_closed(tmp_path, mutation):
    directory = tmp_path / "sources"
    manifest = source_directory(directory)
    receipt = manifest["sources"][0]
    path = directory / receipt["path"]
    if mutation == "hash":
        path.write_text("changed")
    elif mutation == "path":
        receipt["path"] = "../outside"
    elif mutation == "url":
        receipt["url"] = "https://example.com"
    elif mutation == "missing":
        manifest["sources"].pop()
    elif mutation == "future":
        receipt["retrieved_at"] = "2099-01-01T00:00:00Z"
    else:
        if mutation == "starter_count":
            receipt = manifest["sources"][-1]
            path = directory / receipt["path"]
        raw = path.read_text()
        if mutation == "date":
            raw = raw.replace("Race Meeting: 01/01/2026", "Race Meeting: 02/01/2026")
        if mutation == "race":
            raw = raw.replace("RACE 1 (100)", "RACE 2 (100)")
        if mutation == "dividend":
            raw = raw.replace("<td>2</td><td>15.00</td>", "<td>1</td><td>15.00</td>")
        if mutation == "runner":
            raw = raw.replace("SYNTHETIC HORSE 1 (S001)", "WRONG HORSE")
        if mutation == "starter_count":
            raw = raw.replace("7 Starters", "8 Starters")
        path.write_text(raw)
        receipt["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        load_results(directory, now=NOW)


def test_dead_heat_is_explicitly_unsupported(tmp_path):
    directory = tmp_path / "sources"
    manifest = source_directory(directory)
    receipt = manifest["sources"][0]
    path = directory / receipt["path"]
    path.write_bytes(
        path.read_bytes().replace(
            b"<td>1</td><td>1</td><td>SYNTHETIC", b"<td>1 DH</td><td>1</td><td>SYNTHETIC"
        )
    )
    receipt["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (directory / "manifest.json").write_text(json.dumps(manifest))
    race = load_results(directory, now=NOW).races[0]
    assert not race.supported and race.blockers


def test_network_collection_is_opt_in_bounded_and_never_overwrites(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        raw = (
            starters_html(2)
            if "dstr/" in str(request.url)
            else result_html(int(request.url.params["RaceNo"]))
        )
        return httpx.Response(200, content=raw)

    client = httpx.Client
    monkeypatch.setattr(
        "local_market_agent.horse_racing.results.httpx.Client",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )
    with pytest.raises(ValueError, match="allow-network"):
        collect_results(tmp_path / "capture", DAY, races=2)
    assert calls == []
    result = collect_results(tmp_path / "capture", DAY, races=2, allow_network=True)
    assert len(result.races) == 2 and len(calls) == 3
    with pytest.raises(FileExistsError):
        collect_results(tmp_path / "capture", DAY, races=2, allow_network=True)
    assert len(calls) == 3 and not list(tmp_path.rglob("*.sqlite"))


def test_duplicate_navigation_id_does_not_hide_full_declarations():
    raw = b'<a id="ST01">ST - 01</a>' + starters_html(1)
    parsed = parse_starters(raw, DAY, "ST", 1)
    assert parsed["1"]["declared_count"] == 7


def test_fractional_unit_stake_needs_manual_settlement(tmp_path):
    record = historical_record()
    record.races[1].tickets[0].stake = Decimal("15")
    directory = tmp_path / "official"
    source_directory(directory)
    report = replay_history(record, load_results(directory))
    assert report["races"][1]["official_gross_return"] is None
    assert report["official_entitlement"]["status"] == "UNKNOWN"


def test_missing_final_race_is_not_a_complete_meeting(tmp_path):
    directory = tmp_path / "official"
    source_directory(directory)
    record = historical_record()
    record.races.pop()
    with pytest.raises(ValueError, match="every official"):
        replay_history(record, load_results(directory))
    with pytest.raises(ValueError, match="race count"):
        parse_starters(starters_html(4), DAY, "ST", 3)


def test_truncated_place_pool_cannot_turn_winner_into_loss(tmp_path):
    directory = tmp_path / "official"
    manifest = source_directory(directory)
    path = directory / "result-2.html"
    raw = (
        path.read_bytes()
        .replace(b'rowspan="3"', b'rowspan="2"')
        .replace(b"<tr><td>3</td><td>12.00</td></tr>", b"")
    )
    path.write_bytes(raw)
    manifest["sources"][1]["sha256"] = hashlib.sha256(raw).hexdigest()
    (directory / "manifest.json").write_text(json.dumps(manifest))
    official = load_results(directory)
    assert not official.races[1].supported
    record = historical_record()
    record.races[1].tickets[1].horse_no = 3
    report = replay_history(record, official)
    assert report["races"][1]["tickets"][1]["official_outcome"] == "UNKNOWN"
