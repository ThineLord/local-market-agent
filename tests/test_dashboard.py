from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import replace
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from local_market_agent.config import load_settings
from ui.server import DashboardHandler, DashboardRepository, dashboard_payload, encode


def test_dashboard_reads_existing_data_without_writing(repo, snapshot, brief):
    repo.save_market_snapshot(snapshot)
    repo.save_brief(brief)
    before = repo.db_path.read_bytes()
    settings = replace(load_settings(), db_path=repo.db_path)
    payload = json.loads(json.dumps(dashboard_payload(settings), default=encode))
    assert payload["snapshots"][0]["snapshot_id"] == snapshot.snapshot_id
    assert payload["briefs"][0]["brief_id"] == brief.brief_id
    assert payload["audit"][0]["_brief"]["brief_id"] == brief.brief_id
    assert payload["meta"]["counts"]["research_briefs"] == 1
    assert payload["meta"]["fixture_preview"] is False
    assert repo.db_path.read_bytes() == before
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        DashboardRepository(repo.db_path).save_brief(brief)


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / "not-created" / "workspace.sqlite"
    payload = dashboard_payload(replace(load_settings(), db_path=path))
    assert payload["meta"]["database_available"] is False
    assert payload["meta"]["fixture_preview"] is True
    assert payload["briefs"] == []
    assert payload["operations"]["latest_run"] is None
    assert not path.parent.exists()


def test_settings_are_allowlisted_and_old_database_is_supported(tmp_path, monkeypatch):
    path = tmp_path / "older.sqlite"
    sqlite3.connect(path).close()
    monkeypatch.setenv("LMA_OPENAI_COMPATIBLE_API_KEY", "secret-that-must-not-be-returned")
    payload = dashboard_payload(replace(load_settings(), db_path=path))
    serialized = json.dumps(payload, default=encode)
    assert "secret-that-must-not-be-returned" not in serialized
    assert "openai_compatible_api_key" not in serialized
    assert payload["settings"]["real_money_enabled"] is False
    assert payload["settings"]["allow_live_orders"] is False
    assert payload["settings"]["human_approval_required"] is True
    assert payload["meta"]["counts"] == {}


@pytest.fixture
def dashboard_http():
    server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.mark.parametrize("path", ["/", "/app.js", "/bull.js", "/theme.js", "/style.css", "/favicon.svg", "/api/health"])
def test_local_static_routes_and_security_headers(dashboard_http, path):
    connection = HTTPConnection("127.0.0.1", dashboard_http)
    connection.request("GET", path)
    response = connection.getresponse()
    assert response.status == 200
    assert response.getheader("Cache-Control") == "no-store"
    assert "frame-ancestors 'none'" in response.getheader("Content-Security-Policy")
    assert response.read()
    connection.close()


@pytest.mark.parametrize("path", ["/.env", "/../pyproject.toml", "/data/local_market_agent.sqlite", "/api/orders"])
def test_private_files_and_unknown_api_are_not_served(dashboard_http, path):
    connection = HTTPConnection("127.0.0.1", dashboard_http)
    connection.request("GET", path)
    assert connection.getresponse().status == 404
    connection.close()


@pytest.mark.parametrize("headers", [{"Host": "attacker.test"}, {"Origin": "https://attacker.test"}])
def test_foreign_hosts_and_origins_are_rejected(dashboard_http, headers):
    connection = HTTPConnection("127.0.0.1", dashboard_http)
    connection.request("GET", "/api/dashboard", headers=headers)
    assert connection.getresponse().status == 403
    connection.close()


def test_dashboard_has_no_write_routes(dashboard_http):
    connection = HTTPConnection("127.0.0.1", dashboard_http)
    connection.request("POST", "/api/dashboard", body=b"{}")
    assert connection.getresponse().status == 501
    connection.close()
