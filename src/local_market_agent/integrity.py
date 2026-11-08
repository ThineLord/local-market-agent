"""Local content integrity, not signatures or strategy recomputation."""
import hashlib
import json


def content_hash(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def position_opening(position):
    return position.model_dump(mode="json", exclude={"closed_at", "close_price", "realized_pnl", "fees"})


def run_artifacts(repo, record, manifest):
    core = manifest.model_dump(mode="json")
    core["metadata"].pop("integrity", None)
    artifacts = {"run_record": record, "manifest_core": core}
    for name, key, loader in [
        ("market_snapshot", record.snapshot_id, repo.load_market_snapshot),
        ("research_brief", record.brief_id, repo.load_brief),
        ("signal", record.signal_id, repo.load_signal),
        ("risk_decision", record.risk_decision_id, repo.load_risk_decision),
        ("risk_gate_decision", record.risk_gate_decision_id, repo.load_risk_gate_decision),
        ("paper_order", record.paper_order_id, repo.load_paper_order),
        ("portfolio_snapshot", record.portfolio_snapshot_id, repo.load_portfolio_snapshot),
        ("prepared_intent", record.metadata.get("intent_id"), repo.load_prepared_execution),
    ]:
        if key:
            artifacts[name] = loader(key)
    approval_id = record.metadata.get("approval_id")
    if approval_id:
        artifacts["approval"] = next((a for a in repo.list_paper_approvals() if a.approval_id == approval_id), None)
    if record.paper_order_id:
        fills = [f for f in repo.list_paper_fills() if f.order_id == record.paper_order_id and not f.is_closing]
        artifacts["opening_fills"] = [f.model_dump(mode="json") for f in sorted(fills, key=lambda f: f.fill_id)]
        positions = [p for p in repo.list_positions() if p.order_id == record.paper_order_id]
        artifacts["position_openings"] = [position_opening(p) for p in sorted(positions, key=lambda p: p.position_id)]
    return artifacts


def seal_run(repo, record, manifest):
    hashes = {k: content_hash(v) for k, v in run_artifacts(repo, record, manifest).items()}
    return manifest.model_copy(update={"metadata": {**manifest.metadata, "integrity": {"schema": 1, "hashes": hashes}}})


def verify_run(repo, record, manifest):
    seal = manifest.metadata.get("integrity")
    if not seal:
        return [], ["Legacy unsealed run: only reference/report checks are available; content integrity is not verified."]
    if seal.get("schema") != 1 or not isinstance(seal.get("hashes"), dict):
        return ["Unsupported or malformed integrity seal"], []
    artifacts = run_artifacts(repo, record, manifest)
    current = {k: content_hash(v) for k, v in artifacts.items()}
    expected = seal["hashes"]
    errors = [f"Content checksum mismatch: {key}" for key in sorted(current.keys() | expected.keys()) if current.get(key) != expected.get(key)]
    snapshot, brief, signal, risk, gate, order = [artifacts.get(k) for k in ("market_snapshot", "research_brief", "signal", "risk_decision", "risk_gate_decision", "paper_order")]
    links = []
    if snapshot and brief:
        links.extend([brief.snapshot_id == snapshot.snapshot_id, brief.market_id == snapshot.market.market_id])
    if signal and brief:
        links.extend([signal.brief_id == brief.brief_id, signal.market_id == brief.market_id])
    if risk and signal:
        links.append(risk.signal_id == signal.signal_id)
    if gate and signal:
        links.extend([gate.signal_id == signal.signal_id, gate.market_id == signal.market_id])
    if order and risk and signal:
        links.extend([order.signal_id == signal.signal_id, order.risk_decision_id == risk.risk_decision_id, risk.is_approved])
        fills = artifacts["opening_fills"]
        positions = artifacts["position_openings"]
        links.append(len(fills) == len(positions) == 1)
        for f in fills:
            links.extend([f["signal_id"] == signal.signal_id, f["risk_decision_id"] == risk.risk_decision_id, f["market_id"] == order.market_id])
        if fills and positions:
            links.append(fills[0]["position_id"] == positions[0]["position_id"])
    intent = artifacts.get("prepared_intent")
    approval = artifacts.get("approval")
    if intent and gate:
        links.append(gate.intent_id == intent.intent_id)
    if approval and intent:
        links.extend([approval.intent_id == intent.intent_id, approval.content_hash == intent.content_hash, approval.decision == "approved"])
    if order and intent and approval and artifacts.get("opening_fills") and artifacts.get("position_openings"):
        values = dict(prepared=intent, snapshot=snapshot, brief=brief, signal=signal,
            risk=risk, gate=gate, approval=approval, order=order,
            fill=artifacts["opening_fills"][0], position=artifacts["position_openings"][0])
        links.append(opening_links(values, intent.intent_id, order.created_at))
    if not all(links):
        errors.append("Artifact relationship mismatch in replay chain")
    return errors, []


EXECUTION_FIELDS = {"prepared", "snapshot", "brief", "signal", "risk", "gate", "approval", "order", "fill", "position"}


def execution_artifacts(repo, refs):
    loaders = {
        "prepared": repo.load_prepared_execution, "snapshot": repo.load_market_snapshot,
        "brief": repo.load_brief, "signal": repo.load_signal, "risk": repo.load_risk_decision,
        "gate": repo.load_risk_gate_decision, "order": repo.load_paper_order,
        "fill": repo.load_paper_fill, "position": repo.load_position,
        "approval": lambda key: next((a for a in repo.list_paper_approvals() if a.approval_id == key), None),
    }
    values = {name: loader(refs[name]) for name, loader in loaders.items() if name in refs}
    if values.get("position") is not None:
        values["position"] = position_opening(values["position"])
    return values


def seal_execution(repo, prepared, approval, gate, order, fill, position, now):
    from local_market_agent.schemas.models import PaperExecutionReceipt
    refs = dict(prepared=prepared.intent_id, snapshot=prepared.snapshot_id, brief=prepared.brief_id,
                signal=prepared.intent.signal_id, risk=prepared.risk_decision_id,
                gate=gate.risk_gate_decision_id, approval=approval.approval_id,
                order=order.order_id, fill=fill.fill_id, position=position.position_id)
    values = execution_artifacts(repo, refs)
    receipt = PaperExecutionReceipt(intent_id=prepared.intent_id, created_at=now,
        references=refs, hashes={k: content_hash(v) for k,v in values.items()})
    repo.save_execution_receipt(receipt)
    return receipt


def verify_execution(repo, intent_id):
    receipt = repo.load_execution_receipt(intent_id)
    errors = []
    if receipt is None:
        return {"ok": False, "intent_id": intent_id, "errors": ["No sealed execution receipt; intent is pending or execution is legacy"]}
    if set(receipt.references) != EXECUTION_FIELDS or set(receipt.hashes) != EXECUTION_FIELDS:
        errors.append("Execution receipt reference/hash inventory mismatch")
    values = execution_artifacts(repo, receipt.references)
    for key in EXECUTION_FIELDS:
        if values.get(key) is None or content_hash(values.get(key)) != receipt.hashes.get(key):
            errors.append(f"Execution content checksum mismatch: {key}")
    if not errors and not opening_links(values, intent_id, receipt.created_at):
        errors.append("Execution relationship mismatch")
    return {"ok": not errors, "intent_id": intent_id, "errors": errors,
            "checks": "content hashes and links; not signatures or strategy recomputation",
            "receipt": receipt.model_dump(mode="json")}


def opening_links(values, intent_id, executed_at):
    try:
        return _opening_links(values, intent_id, executed_at)
    except (KeyError, TypeError, ValueError):
        return False


def _opening_links(values, intent_id, executed_at):
    if any(values.get(k) is None for k in EXECUTION_FIELDS):
        return False
    d = {k: (v.model_dump(mode="json") if hasattr(v, "model_dump") else v) for k,v in values.items()}
    p,s,b,sig,r,g,a,o,f,pos = [d[k] for k in ("prepared","snapshot","brief","signal","risk","gate","approval","order","fill","position")]
    from datetime import datetime
    def time(value):
        return datetime.fromisoformat(value)
    market = s["market"]["market_id"]
    signal_id = sig["signal_id"]
    risk_id = r["risk_decision_id"]
    expected_side = {"paper_buy_yes": "BUY_YES", "paper_buy_no": "BUY_NO"}.get(sig["action"])
    bound_content = {"inputs": [p["intent"],s,b,sig,r], "config": p["config"], "simulation": p["simulation"]}
    return all([
        p["intent_id"] == p["intent"]["intent_id"] == intent_id == a["intent_id"] == g["intent_id"],
        p["snapshot_id"] == s["snapshot_id"] == b["snapshot_id"],
        p["brief_id"] == b["brief_id"] == sig["brief_id"],
        p["risk_decision_id"] == risk_id == o["risk_decision_id"] == f["risk_decision_id"] == pos["risk_decision_id"],
        p["intent"]["signal_id"] == signal_id == r["signal_id"] == g["signal_id"] == o["signal_id"] == f["signal_id"] == pos["signal_id"],
        all(x["market_id"] == market for x in [p["intent"],b,sig,g,o,f,pos]),
        o["order_id"] == f["order_id"] == pos["order_id"], f["position_id"] == pos["position_id"],
        expected_side == p["intent"]["side"] == o["side"] == f["side"] == pos["side"],
        o["quantity"] == f["quantity"] == pos["quantity"] == p["intent"]["quantity"],
        o["fill_price"] == f["price"] == pos["average_price"] == p["intent"]["metadata"]["fill_price"],
        o["limit_price"] == p["intent"]["limit_price"], o["fees"] == f["fees"] == p["intent"]["metadata"]["fees"],
        a["decision"] == "approved", r["status"] == "approved", g["status"] == "approved",
        not f["is_closing"], o["status"] == "filled",
        time(a["created_at"]) <= executed_at < time(a["expires_at"]),
        a["content_hash"] == p["content_hash"] == content_hash(bound_content),
    ])
