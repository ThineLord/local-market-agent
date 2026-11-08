"""Read-only workflow projection shared by CLI and dashboard."""
import shlex
from datetime import timedelta

from local_market_agent import __version__
from local_market_agent.config import Settings
from local_market_agent.paper.execution import PaperExecutionService, utc
from local_market_agent.risk.preflight import preflight


def workflow_status(repo, settings=None, *, now=None):
    now = utc(now)
    settings = settings or Settings(db_path=repo.db_path)
    approvals = repo.list_paper_approvals()
    orders = repo.list_paper_orders()
    positions = repo.list_positions()
    rows = []
    for prepared in repo.list_prepared_executions():
        intent = prepared.intent
        order = next((o for o in orders if o.signal_id == intent.signal_id), None)
        approval = next((a for a in approvals if a.intent_id == intent.intent_id), None)
        status, reasons = "pending_manual_approval", ["Review this intent, then approve it explicitly."]
        snapshot = repo.load_market_snapshot(prepared.snapshot_id)
        if order:
            closed = [p for p in positions if p.order_id == order.order_id and not p.is_open]
            status, reasons = ("settled", ["Paper position closed; opening receipt remains replayable."]) if closed else ("completed", ["Paper order filled; no real money was used."])
        elif approval and approval.decision == "rejected":
            status, reasons = "rejected", [approval.reason]
        elif snapshot is None or now - utc(snapshot.as_of) > timedelta(seconds=prepared.config["gates"]["max_market_data_age_seconds"]):
            status, reasons = "expired", ["Observation is stale. Refresh evidence and prepare a new intent."]
        elif approval:
            if utc(approval.created_at) <= now < utc(approval.expires_at):
                status, reasons = "approved", ["Approval is valid; execution still rechecks current risk."]
            else:
                status, reasons = "expired", ["Approval expired; review a current intent again."]
        if order is None and status not in {"rejected", "expired"}:
            try:
                _, current, brief, _, _ = PaperExecutionService(repo, settings)._load(repo, intent.intent_id)
                failures = [c.message for c in preflight(current, brief, settings, now) if not c.passed]
                if failures:
                    status, reasons = "blocked", failures
            except ValueError as exc:
                status, reasons = "blocked", [str(exc)]
        command = ["lma", "paper-status", "--db", str(repo.db_path)]
        if status in {"completed", "settled"}:
            command = ["lma", "paper-replay", "--intent-id", intent.intent_id, "--db", str(repo.db_path)]
        elif status == "approved":
            command = ["lma", "paper-execute", "--intent-id", intent.intent_id, "--db", str(repo.db_path)]
        elif status == "pending_manual_approval":
            command = ["lma", "paper-approve", "--intent-id", intent.intent_id, "--actor", "YOUR_NAME", "--reason", "YOUR_REVIEW_REASON", "--db", str(repo.db_path)]
        rows.append({"intent_id": intent.intent_id, "market_id": intent.market_id, "status": status,
            "observed_at": snapshot.as_of.isoformat() if snapshot else None,
            "side": str(intent.side), "quantity": intent.quantity, "notional": intent.notional,
            "simulation": prepared.simulation, "reasons": reasons, "next_command": shlex.join(command)})
    return {"version": __version__, "as_of": now.isoformat(), "read_only": True,
        "steps": ["Evidence", "Intent", "Approval", "Paper execution", "Replay / settlement"],
        "intents": rows, "empty_message": "Start with a reviewed evidence packet or the isolated synthetic demo."}
