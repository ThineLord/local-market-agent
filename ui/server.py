"""Local, read-only dashboard. Run: python ui/server.py."""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import sqlite3
import sys
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from local_market_agent.adapters import FixtureAdapter  # noqa: E402
from local_market_agent.config import load_settings  # noqa: E402
from local_market_agent.operations.watchlist import ScreenReport  # noqa: E402
from local_market_agent.storage import SQLiteRepository  # noqa: E402
from ui.app import _audit_chain_rows, _phase7_operations_view_model  # noqa: E402

STATIC = Path(__file__).parent / "web"
LIMIT = 500
ASSETS = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js",
          "/style.css": "style.css", "/bull.js": "bull.js", "/theme.js": "theme.js",
          "/favicon.svg": "favicon.svg"}


class DashboardRepository(SQLiteRepository):
    """Reuse the validated models without creating or modifying a database."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"{self.db_path.as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _list(self, table, model_cls, market_id=None, limit=None):
        if not self.db_path.exists():
            return []
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
        if not exists:
            return []
        return super()._list(table, model_cls, market_id, limit)


def encode(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported dashboard value: {type(value).__name__}")


def dashboard_payload(settings=None, screen_report_path=None) -> dict:
    settings = settings or load_settings()
    repository = DashboardRepository(settings.db_path)
    snapshots = repository.list_market_snapshots(limit=LIMIT)
    preview = not snapshots
    if preview:
        snapshots = [FixtureAdapter(ROOT / "data/fixtures/demo_market.json").fetch_snapshot()]
    collections = {
        "snapshots": snapshots,
        "briefs": repository.list_briefs(limit=LIMIT),
        "signals": repository.list_signals(limit=LIMIT),
        "risk_decisions": repository.list_risk_decisions(limit=LIMIT),
        "orders": repository.list_paper_orders(limit=LIMIT),
        "positions": repository.list_positions(limit=LIMIT),
        "reports": repository.list_performance_reports(limit=LIMIT),
        "portfolio_snapshots": repository.list_portfolio_snapshots(limit=LIMIT),
    }
    counts = {}
    if repository.db_path.exists():
        with repository._connect() as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in repository.TABLES:
                if table in tables:
                    counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return {
        **collections,
        "audit": _audit_chain_rows(repository),
        "operations": _phase7_operations_view_model(repository),
        "screening": screening_payload(screen_report_path),
        "meta": {
            "loaded_at": datetime.now(UTC).isoformat(),
            "database_available": repository.db_path.exists(),
            "fixture_preview": preview,
            "record_limit": LIMIT,
            "counts": counts,
        },
        # Deliberate allowlist: never serialize the settings object or environment.
        "settings": {
            "db_path": str(settings.db_path),
            "raw_cache_dir": str(settings.raw_cache_dir),
            "research_brief_dir": str(settings.research_brief_dir),
            "real_money_enabled": settings.real_money_enabled,
            "allow_live_orders": settings.allow_live_orders,
            "human_approval_required": settings.human_approval_required,
            "llm_provider": settings.llm_provider,
            "risk": settings.risk.as_dict(),
            "risk_gates": settings.risk_gates.as_dict(),
        },
    }


def screening_payload(path=None) -> dict:
    path = Path(path) if path is not None else ROOT / "data/reports/watchlist/latest.json"
    if not path.exists():
        return {"status": "missing", "report": None}
    try:
        if path.stat().st_size > 5_000_000:
            raise ValueError("Report too large")
        report = ScreenReport.model_validate_json(path.read_bytes())
        json.dumps(report.model_dump(mode="json"), allow_nan=False)
        return {"status": "available", "report": report.model_dump(mode="json")}
    except (OSError, ValueError):
        return {"status": "invalid", "report": None}


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def reply(self, status, body, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        port = self.server.server_port
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in allowed_hosts:
            self.reply(403, b'{"error":"Local access only."}')
            return
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in allowed_hosts}:
            self.reply(403, b'{"error":"Same-origin access only."}')
            return
        route = urlsplit(self.path).path
        if route == "/api/dashboard":
            try:
                body = json.dumps(dashboard_payload(
                    screen_report_path=getattr(self.server, "screen_report_path", None),
                ), default=encode, allow_nan=False).encode()
                self.reply(200, body)
            except Exception:
                logging.exception("Dashboard data read failed")
                self.reply(500, b'{"error":"Unable to read the local workspace. Check the server log and retry."}')
        elif route == "/api/health":
            self.reply(200, b'{"status":"ok","mode":"read-only"}')
        elif route in ASSETS:
            path = STATIC / ASSETS[route]
            self.reply(200, path.read_bytes(), mimetypes.guess_type(path)[0] or "application/octet-stream")
        else:
            self.reply(404, b'{"error":"Not found."}')


def main():
    parser = argparse.ArgumentParser(description="Local Market Agent read-only dashboard")
    parser.add_argument("--port", type=int, default=8502)
    parser.add_argument("--screen-report", type=Path, help="Saved watchlist screening JSON")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler)
    server.screen_report_path = args.screen_report
    print(f"Local Market Agent: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
