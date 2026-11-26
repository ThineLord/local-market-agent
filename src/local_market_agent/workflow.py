"""Read-only workflow projection shared by CLI and dashboard."""
import shlex
import sqlite3
from datetime import timedelta

from local_market_agent import __version__
from local_market_agent.config import Settings
from local_market_agent.paper.execution import PaperExecutionService, utc
from local_market_agent.risk.preflight import preflight

_NO_RECEIPT = "No sealed execution receipt is stored for this intent, so paper-replay cannot verify it."


def workflow_status(repo, settings=None, *, now=None):
    now = utc(now)
    settings = settings or Settings(db_path=repo.db_path)
    approvals = repo.list_paper_approvals()
    orders = repo.list_paper_orders()
    positions = repo.list_positions()
    prepared_rows = repo.list_prepared_executions()
    orders_by_id = {order.order_id: order for order in orders}
    # One primary-key read per prepared intent. Do not rehash receipts or walk the ledger again.
    stored, located_owner = _execution_references(repo, prepared_rows, orders_by_id)
    signal_counts = {}
    for prepared in prepared_rows:
        signal_id = prepared.intent.signal_id
        signal_counts[signal_id] = signal_counts.get(signal_id, 0) + 1
    rows = []
    for prepared in prepared_rows:
        intent = prepared.intent
        approval = next((item for item in approvals if item.intent_id == intent.intent_id), None)
        snapshot = repo.load_market_snapshot(prepared.snapshot_id)
        status, reasons, command = _project_intent(
            repo, settings, now, prepared, approval, snapshot, orders, positions,
            orders_by_id, stored.get(intent.intent_id), located_owner, signal_counts,
        )
        rows.append({
            "intent_id": intent.intent_id, "market_id": intent.market_id, "status": status,
            "observed_at": snapshot.as_of.isoformat() if snapshot else None,
            "side": str(intent.side), "quantity": intent.quantity, "notional": intent.notional,
            "simulation": prepared.simulation, "reasons": reasons, "next_command": shlex.join(command),
        })
    return {
        "version": __version__, "as_of": now.isoformat(), "read_only": True,
        "steps": ["Evidence", "Intent", "Approval", "Paper execution", "Replay / settlement"],
        "intents": rows, "empty_message": "Start with a reviewed evidence packet or the isolated synthetic demo.",
    }


def _execution_references(repo, prepared_rows, orders_by_id):
    stored = {}
    located_owner = {}
    for prepared in prepared_rows:
        receipt = _load_receipt(repo, prepared.intent_id)
        if receipt is None:
            continue
        stored[prepared.intent_id] = receipt
        order = _located_order(receipt, prepared.intent, orders_by_id)
        if order is not None and order.order_id not in located_owner:
            located_owner[order.order_id] = prepared.intent_id
    return stored, located_owner


def _load_receipt(repo, intent_id):
    try:
        return repo.load_execution_receipt(intent_id)
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise
        return None


def _names_intent(receipt, intent_id):
    return (
        receipt is not None
        and receipt.intent_id == intent_id
        and receipt.references.get("prepared") == intent_id
    )


def _located_order(receipt, intent, orders_by_id):
    if not _names_intent(receipt, intent.intent_id):
        return None
    order_id = receipt.references.get("order")
    order = orders_by_id.get(order_id) if order_id else None
    if order is None or order.signal_id != intent.signal_id:
        return None
    return order


def _position_closed(positions, order):
    return any(position.order_id == order.order_id and not position.is_open for position in positions)


def _db_command(repo, *parts):
    return ["lma", *parts, "--db", str(repo.db_path)]


def _project_intent(repo, settings, now, prepared, approval, snapshot, orders, positions, orders_by_id, receipt, located_owner, signal_counts):
    intent = prepared.intent
    own_order = _located_order(receipt, intent, orders_by_id)
    if own_order is not None:
        if _position_closed(positions, own_order):
            status, reasons = "settled", ["Paper position closed; opening receipt remains replayable."]
        else:
            status, reasons = "completed", ["Paper order filled; no real money was used."]
        return status, reasons, _db_command(repo, "paper-replay", "--intent-id", intent.intent_id)
    if receipt is not None:
        return "unavailable", [_unlocated_reason(receipt, intent, orders_by_id)], _db_command(repo, "paper-status")
    signal_orders = [order for order in orders if order.signal_id == intent.signal_id]
    owned = next((order for order in signal_orders if located_owner.get(order.order_id) not in {None, intent.intent_id}), None)
    if owned is not None:
        owner = located_owner[owned.order_id]
        state = "closed" if _position_closed(positions, owned) else "open"
        reason = (
            f"Intent {intent.intent_id} has no execution record. "
            f"Intent {owner} completed the paper order for this signal. "
            f"That position is {state}."
        )
        return "not_executed", [reason], _db_command(repo, "paper-replay", "--intent-id", owner)
    unowned = next((order for order in signal_orders if order.order_id not in located_owner), None)
    if unowned is not None and signal_counts.get(intent.signal_id) == 1:
        if _position_closed(positions, unowned):
            status, reasons = "settled", ["Paper position closed.", _NO_RECEIPT]
        else:
            status, reasons = "completed", ["Paper order filled; no real money was used.", _NO_RECEIPT]
        return status, reasons, _db_command(repo, "paper-status")
    if unowned is not None:
        reason = (
            f"Intent {intent.intent_id} has no execution record. "
            "A paper order exists for this signal, but no execution receipt names the intent that completed it."
        )
        return "not_executed", [reason], _db_command(repo, "paper-status")
    return _unexecuted(repo, settings, now, prepared, approval, snapshot)


def _unlocated_reason(receipt, intent, orders_by_id):
    if not _names_intent(receipt, intent.intent_id):
        return "An execution receipt is stored for this intent, but it does not name this intent."
    order_id = receipt.references.get("order")
    order = orders_by_id.get(order_id) if order_id else None
    if order is None:
        return "This intent's execution receipt does not reference a paper order in this ledger."
    return "This intent's execution receipt references a paper order for a different signal."


def _unexecuted(repo, settings, now, prepared, approval, snapshot):
    intent = prepared.intent
    status, reasons = "pending_manual_approval", ["Review this intent, then approve it explicitly."]
    if approval and approval.decision == "rejected":
        status, reasons = "rejected", [approval.reason]
    elif snapshot is None or now - utc(snapshot.as_of) > timedelta(seconds=prepared.config["gates"]["max_market_data_age_seconds"]):
        status, reasons = "expired", ["Observation is stale. Refresh evidence and prepare a new intent."]
    elif approval:
        if utc(approval.created_at) <= now < utc(approval.expires_at):
            status, reasons = "approved", ["Approval is valid; execution still rechecks current risk."]
        else:
            status, reasons = "expired", ["Approval expired; review a current intent again."]
    if status not in {"rejected", "expired"}:
        try:
            _, current, brief, _, _ = PaperExecutionService(repo, settings)._load(repo, intent.intent_id)
            failures = [check.message for check in preflight(current, brief, settings, now) if not check.passed]
            if failures:
                status, reasons = "blocked", failures
        except ValueError as exc:
            status, reasons = "blocked", [str(exc)]
    command = _db_command(repo, "paper-status")
    if status == "approved":
        command = _db_command(repo, "paper-execute", "--intent-id", intent.intent_id)
    elif status == "pending_manual_approval":
        command = _db_command(
            repo, "paper-approve", "--intent-id", intent.intent_id, "--actor", "YOUR_NAME",
            "--reason", "YOUR_REVIEW_REASON",
        )
    return status, reasons, command
