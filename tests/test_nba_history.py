import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from local_market_agent.nba_history import collect_nba_history
from local_market_agent.nba_probability import MODEL_SPEC, TEAM_IDS, load_history


def history_files(directory):
    directory.mkdir()
    (directory / "protocol.json").write_text(
        json.dumps({**MODEL_SPEC, "frozen_at": "2026-11-08T18:00:00Z"})
    )
    receipts = []
    for season in (2024, 2025, 2026, 2027):
        for team in TEAM_IDS:
            name = f"{season}-{team}.json"
            raw = json.dumps({"team": {"id": team}, "events": []}).encode()
            (directory / name).write_bytes(raw)
            receipts.append(
                {
                    "season": season,
                    "team_id": team,
                    "path": name,
                    "retrieved_at": "2026-11-08T18:01:00Z",
                    "url": f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team}/schedule?season={season}&seasontype=2",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
    (directory / "receipts.json").write_text(json.dumps(receipts))
    return receipts


def test_history_empty_coverage_cannot_claim_complete(tmp_path):
    p = tmp_path / "history"
    history_files(p)
    games, audit = load_history(p)
    assert games == [] and not audit["complete_historical_seasons"]
    assert audit["source_count"] == 120


@pytest.mark.parametrize("mutation", ["hash", "escape", "receipt_missing", "future", "protocol"])
def test_history_receipts_fail_closed(tmp_path, mutation):
    p = tmp_path / "history"
    receipts = history_files(p)
    if mutation == "hash":
        (p / receipts[0]["path"]).write_text("{}")
    elif mutation == "escape":
        receipts[0]["path"] = "../outside.json"
    elif mutation == "receipt_missing":
        receipts.pop()
    elif mutation == "future":
        receipts[0]["retrieved_at"] = "2099-01-01T00:00:00Z"
    else:
        protocol = json.loads((p / "protocol.json").read_text())
        protocol["k"] = 40
        (p / "protocol.json").write_text(json.dumps(protocol))
    (p / "receipts.json").write_text(json.dumps(receipts))
    with pytest.raises(ValueError):
        load_history(p)


def test_collector_has_fixed_budget_no_overwrite_or_implicit_network(tmp_path, monkeypatch):
    calls = []

    def fetch(url):
        calls.append(url)
        team = Path(urlparse(url).path).parts[-2]
        year = parse_qs(urlparse(url).query)["season"][0]
        assert year in {"2024", "2025", "2026", "2027"}
        return {"team": {"id": team}, "events": []}

    monkeypatch.setattr("local_market_agent.nba_history.safe_get_json", fetch)
    with pytest.raises(ValueError, match="allow-network"):
        collect_nba_history(tmp_path / "history")
    assert calls == []
    collect_nba_history(tmp_path / "history", allow_network=True)
    assert len(calls) == 120 and len(set(calls)) == 120
    with pytest.raises(FileExistsError):
        collect_nba_history(tmp_path / "history", allow_network=True)
    assert len(calls) == 120


def test_source_cannot_contain_final_game_starting_after_its_retrieval(tmp_path):
    from datetime import UTC, datetime

    from test_nba_probability import final_event

    p = tmp_path / "history"
    receipts = history_files(p)
    event = final_event()
    event["date"] = "2026-11-08T18:02:00Z"
    for receipt in receipts:
        if receipt["season"] == 2027 and receipt["team_id"] in {"1", "2"}:
            raw = json.dumps({"team": {"id": receipt["team_id"]}, "events": [event]}).encode()
            (p / receipt["path"]).write_bytes(raw)
            receipt["sha256"] = hashlib.sha256(raw).hexdigest()
    (p / "receipts.json").write_text(json.dumps(receipts))
    with pytest.raises(ValueError, match="future"):
        load_history(p, now=datetime(2026, 11, 8, 19, tzinfo=UTC))
