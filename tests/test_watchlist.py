from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from local_market_agent.cli import app
from local_market_agent.config import Settings
from local_market_agent.operations.watchlist import (
    ScreenReport,
    screen_watchlist,
    write_screen_report,
)
from ui.server import screening_payload

DEMO = Path("data/fixtures/watchlist/demo.json")
REVIEW = datetime(2026, 6, 5, 0, 2, tzinfo=UTC)


def local_watchlist(tmp_path, *, snapshot_change=None, brief_change=None):
    snapshot = json.loads((DEMO.parent / "candidate.json").read_text())
    brief = json.loads((DEMO.parent / "candidate-brief.json").read_text())
    if snapshot_change:
        snapshot_change(snapshot)
    if brief_change:
        brief_change(brief)
    (tmp_path / "snapshot.json").write_text(json.dumps(snapshot))
    (tmp_path / "brief.json").write_text(json.dumps(brief))
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({"name": "test", "entries": [{
        "source": "file", "market_id": "demo-candidate",
        "snapshot_file": "snapshot.json", "brief_file": "brief.json",
    }]}))
    return path


def test_demo_is_deterministic_and_never_opens_database(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Screening must not open a database or use network/LLM")

    monkeypatch.setattr("sqlite3.connect", forbidden)
    monkeypatch.setattr("httpx.get", forbidden)
    monkeypatch.setattr("httpx.post", forbidden)
    settings = Settings(db_path=tmp_path / "never.sqlite")
    first = screen_watchlist(DEMO, settings=settings, as_of=REVIEW)
    second = screen_watchlist(DEMO, settings=settings, as_of=REVIEW)
    assert first == second
    assert first.counts == {"research_candidate": 1, "needs_research": 1, "blocked": 3}
    assert first.rows[0].signal_action == "paper_buy_yes"
    assert first.rows[0].edge > 0.08
    assert first.orders_created == 0
    assert first.execution_authorized is False
    assert not settings.db_path.exists()


@pytest.mark.parametrize(("change", "code"), [
    (lambda b: b.update(snapshot_id="another-snapshot"), "brief_identity"),
    (lambda b: b.update(market_id="another-market"), "brief_identity"),
    (lambda b: b.update(created_at="2026-06-05T00:03:00Z"), "brief_time"),
    (lambda b: b.update(created_at="2026-06-04T00:00:00Z"), "brief_time"),
    (lambda b: b["evidence"][0].update(published_at="2026-06-05T00:01:00Z"), "evidence_time"),
    (lambda b: b["evidence"][0].update(published_at=None), "evidence_time"),
    (lambda b: b.update(evidence=[], counter_evidence=[]), "evidence_count"),
    (lambda b: b.update(must_not_trade_reasons=["Unresolved source concern"]), "brief_veto"),
    (lambda b: b.update(resolution_source=None), "resolution"),
])
def test_research_gates_block_unsafe_candidates(tmp_path, change, code):
    path = local_watchlist(tmp_path, brief_change=change)
    row = screen_watchlist(path, as_of=REVIEW).rows[0]
    assert row.status == "blocked"
    assert code in {check.code for check in row.checks if not check.passed}
    assert row.signal_action is None


@pytest.mark.parametrize(("change", "code"), [
    (lambda s: s["market"].update(market_id="wrong"), "market_identity"),
    (lambda s: s["market"].update(status="closed"), "market_open"),
    (lambda s: s["market"].update(close_time="2026-06-05T00:02:00Z"), "before_close"),
    (lambda s: s["market"].update(outcomes=["no", "yes"]), "binary_market"),
    (lambda s: s["snapshot"].update(as_of="2026-06-05T00:03:00Z"), "snapshot_age"),
    (lambda s: s["snapshot"].update(liquidity=None), "liquidity"),
    (lambda s: s["snapshot"].update(market_implied_probability=0.9), "probability_consistent"),
])
def test_snapshot_quality_checks(tmp_path, change, code):
    path = local_watchlist(tmp_path, snapshot_change=change)
    row = screen_watchlist(path, as_of=REVIEW).rows[0]
    assert row.status == "blocked"
    assert code in {check.code for check in row.checks if not check.passed}


@pytest.mark.parametrize("field", ["as_of", "snapshot_id"])
def test_missing_snapshot_provenance_cannot_be_fabricated(tmp_path, field):
    path = local_watchlist(tmp_path, snapshot_change=lambda s: s["snapshot"].pop(field))
    row = screen_watchlist(path, as_of=REVIEW).rows[0]
    assert row.status == "error"


def test_low_confidence_uses_existing_strategy(tmp_path):
    path = local_watchlist(tmp_path, brief_change=lambda b: b.update(confidence=0.2))
    row = screen_watchlist(path, as_of=REVIEW).rows[0]
    assert row.status == "observe"
    assert row.signal_action == "skip"
    assert "Confidence" in row.strategy_reason


def test_infinite_liquidity_is_rejected_before_screening(tmp_path):
    path = local_watchlist(tmp_path, snapshot_change=lambda s: s["snapshot"].update(liquidity="Infinity"))
    row = screen_watchlist(path, as_of=REVIEW).rows[0]
    assert row.status == "error"
    assert row.snapshot is None


def test_error_isolated_redacted_and_cli_exit_nonzero(tmp_path):
    path = local_watchlist(tmp_path)
    payload = json.loads(path.read_text())
    payload["entries"].append({"source": "file", "market_id": "bad", "snapshot_file": "bad.json"})
    path.write_text(json.dumps(payload))
    (tmp_path / "bad.json").write_text('{"snapshot": "do-not-expose-payload", "market": {}}')
    result = CliRunner().invoke(app, ["watchlist-screen", "--watchlist", str(path),
                                    "--as-of", REVIEW.isoformat(), "--output-dir", str(tmp_path / "out")])
    assert result.exit_code == 1, result.output
    report = ScreenReport.model_validate_json(Path(json.loads(result.output)["report_path"]).read_bytes())
    assert report.counts == {"research_candidate": 1, "error": 1}
    assert "do-not-expose-payload" not in report.model_dump_json()


def test_network_requires_opt_in_and_cannot_be_backdated(tmp_path, monkeypatch, snapshot):
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({"name": "public", "entries": [{
        "source": "kalshi", "market_id": snapshot.market.market_id,
    }]}))
    calls = []

    def fetch(self, market_id):
        calls.append(market_id)
        return snapshot.model_copy(update={"as_of": datetime.now(UTC)})

    monkeypatch.setattr("local_market_agent.operations.watchlist.KalshiAdapter.fetch_snapshot", fetch)
    report = screen_watchlist(path)
    assert report.counts == {"blocked": 1}
    assert not calls
    with pytest.raises(ValueError, match="backdated"):
        screen_watchlist(path, allow_network=True, as_of=REVIEW)
    report = screen_watchlist(path, allow_network=True)
    assert calls == [snapshot.market.market_id]
    assert report.rows[0].timestamp_basis == "retrieval_only"
    assert report.rows[0].status == "needs_research"


def test_bad_config_is_rejected_before_fetch(tmp_path, monkeypatch):
    entry = {"source": "kalshi", "market_id": "KXTEST"}
    path = tmp_path / "watchlist.json"
    for entries in ([entry, entry], [entry] * 51, []):
        path.write_text(json.dumps({"name": "invalid", "entries": entries}))
        with pytest.raises(ValueError):
            screen_watchlist(path, allow_network=True)
    with pytest.raises(ValueError, match="timezone"):
        screen_watchlist(DEMO, as_of=datetime(2026, 6, 5))


def test_saved_reports_are_preserved_and_dashboard_is_read_only(tmp_path):
    report = screen_watchlist(DEMO, as_of=REVIEW)
    first = write_screen_report(report, tmp_path)
    original = first.read_bytes()
    second = write_screen_report(report, tmp_path)
    assert first != second
    assert first.read_bytes() == original == second.read_bytes()
    latest = tmp_path / "latest.json"
    payload = screening_payload(latest)
    assert payload["status"] == "available"
    assert payload["report"]["counts"] == report.counts
    assert latest.read_bytes() == original
    assert "No orders" in first.with_suffix(".md").read_text()
    assert screening_payload(tmp_path / "absent.json")["status"] == "missing"
    latest.write_text('{"api_key":"do-not-display"}')
    assert screening_payload(latest) == {"status": "invalid", "report": None}


def test_cli_demo_runs_without_side_effects_outside_report_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LMA_DB_PATH", str(tmp_path / "no-database.sqlite"))
    result = CliRunner().invoke(app, ["watchlist-screen", "--as-of", REVIEW.isoformat(),
                                    "--output-dir", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["counts"]["research_candidate"] == 1
    assert not (tmp_path / "no-database.sqlite").exists()
