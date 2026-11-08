"""Generate explicitly synthetic, fresh evidence packets for isolated demos."""
import hashlib
from datetime import timedelta
from pathlib import Path

from local_market_agent.adapters import FixtureAdapter
from local_market_agent.agents import ResearchBriefGenerator
from local_market_agent.evidence_packet import EvidencePacket, SourceReceipt
from local_market_agent.paper.execution import utc
from local_market_agent.schemas.models import deterministic_model_context


def demo_packet(directory, *, now=None, market_id="synthetic-workflow-demo"):
    now = utc(now)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    adapter = FixtureAdapter()
    snapshot = adapter.fetch_snapshot()
    snapshot = snapshot.model_copy(update={"snapshot_id": market_id+"-snapshot", "as_of": now,
        "market": snapshot.market.model_copy(update={"market_id": market_id, "title": "Synthetic workflow demonstration — not a real market", "close_time": now+timedelta(days=1)})})
    sources = []
    def source(source_id, content, retrieved_at, published_at=None):
        path = directory / (source_id+".json")
        path.write_text(content)
        receipt = SourceReceipt(source_id=source_id, url="synthetic://"+source_id,
            path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            retrieved_at=retrieved_at, published_at=published_at)
        sources.append(receipt)
        return receipt
    source("market", snapshot.model_dump_json(indent=2), now)
    evidence = []
    for i, item in enumerate(adapter.fetch_evidence()):
        sid = f"evidence-{i}"
        published = now-timedelta(hours=2)
        retrieved = now-timedelta(minutes=1)
        item = item.model_copy(update={"evidence_id": market_id+"-"+sid,
            "url": "synthetic://"+sid, "published_at": published, "retrieved_at": retrieved,
            "metadata": {**item.metadata, "source_id": sid, "synthetic": True}})
        source(sid, item.model_dump_json(indent=2), retrieved, published)
        evidence.append(item)
    with deterministic_model_context(seed=market_id, now=now):
        brief = ResearchBriefGenerator().generate(snapshot, evidence)
    packet = EvidencePacket(snapshot=snapshot, market_source_id="market", evidence=evidence,
        sources=sources, resolution_source=brief.resolution_source, brief=brief)
    path = directory / "packet.json"
    path.write_text(packet.model_dump_json(indent=2))
    return path


def demo_settlement(packet_path, *, now=None):
    import json
    now = utc(now)
    path = Path(packet_path)
    payload = json.loads(path.read_text())
    if payload["snapshot"]["market"]["platform"] != "fixture":
        raise ValueError("Synthetic settlement helper only accepts fixture packets")
    payload["snapshot"]["market"]["status"] = "settled"
    payload["snapshot"]["as_of"] = now.isoformat()
    payload["snapshot"]["snapshot_id"] += "-settled"
    payload["brief"] = None
    payload["settlement"] = {"market_id": payload["snapshot"]["market"]["market_id"],
        "outcome": "yes", "source_id": "resolution", "resolved_at": now.isoformat()}
    source = path.parent / "settlement.json"
    with source.open("x") as handle:
        json.dump(payload["snapshot"], handle)
    payload["sources"][0].update(path=source.name, sha256=hashlib.sha256(source.read_bytes()).hexdigest(), retrieved_at=now.isoformat())
    final_source = path.parent / "final-resolution.json"
    with final_source.open("x") as handle:
        json.dump(payload["settlement"], handle)
    payload["sources"].append({"source_id": "resolution", "url": payload["resolution_source"],
        "path": final_source.name, "sha256": hashlib.sha256(final_source.read_bytes()).hexdigest(),
        "retrieved_at": now.isoformat(), "published_at": now.isoformat()})
    target = path.parent / "settlement-packet.json"
    with target.open("x") as handle:
        json.dump(payload, handle, indent=2)
    return target
