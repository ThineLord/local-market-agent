"""Offline evidence handoff with explicit local review and provenance."""
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field

from local_market_agent.config import Settings
from local_market_agent.integrity import content_hash
from local_market_agent.paper.execution import PaperExecutionService, utc
from local_market_agent.paper.ledger import PaperLedger
from local_market_agent.risk import RiskEngine
from local_market_agent.risk.equity import (
    loss_metrics,
    observe_equity,
    observe_equity_in_transaction,
)
from local_market_agent.risk.preflight import portfolio_marks, preflight, snapshot_checks
from local_market_agent.schemas.models import (
    EvidenceItem,
    MarketSnapshot,
    ResearchBrief,
    StrictBaseModel,
)
from local_market_agent.strategy import PredictionMarketEdgeStrategy


class SourceReceipt(StrictBaseModel):
    source_id: str = Field(min_length=1)
    url: str
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: datetime
    published_at: datetime | None = None


class Settlement(StrictBaseModel):
    market_id: str
    outcome: Literal["yes", "no"]
    source_id: str
    resolved_at: datetime


class EvidencePacket(StrictBaseModel):
    schema_version: Literal[1] = 1
    snapshot: MarketSnapshot
    market_source_id: str
    evidence: list[EvidenceItem]
    sources: list[SourceReceipt] = Field(min_length=1)
    resolution_source: str = Field(min_length=1)
    brief: ResearchBrief | None = None
    settlement: Settlement | None = None


class PacketReview(StrictBaseModel):
    packet_hash: str
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    reviewed_at: datetime
    scope: Literal["research", "settlement"]
    simulation: bool


def load_packet(path, *, now=None):
    import hashlib
    path = Path(path).resolve()
    now = utc(now)
    if path.stat().st_size > 5_000_000:
        raise ValueError("Packet exceeds 5 MB")
    packet = EvidencePacket.model_validate_json(path.read_text())
    sources = {s.source_id: s for s in packet.sources}
    if len(sources) != len(packet.sources) or packet.market_source_id not in sources:
        raise ValueError("Unique source IDs and market source receipt required")
    for source in packet.sources:
        url = urlparse(source.url)
        if url.scheme not in {"https", "http", "synthetic"} or url.username or url.password:
            raise ValueError("Source URL must be public or explicitly synthetic")
        source_path = (path.parent / source.path).resolve()
        if not source_path.is_relative_to(path.parent) or not source_path.is_file():
            raise ValueError("Source file must be inside the packet directory")
        if source_path.stat().st_size > 5_000_000:
            raise ValueError("Source file exceeds 5 MB")
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != source.sha256:
            raise ValueError(f"Source checksum mismatch: {source.source_id}")
        if utc(source.retrieved_at) > now:
            raise ValueError("Source retrieval cannot be in the future")
        if source.published_at and utc(source.published_at) > utc(source.retrieved_at):
            raise ValueError("Publication cannot follow source retrieval")
    if utc(packet.snapshot.as_of) > now:
        raise ValueError("Snapshot cannot be future-dated")
    if utc(sources[packet.market_source_id].retrieved_at) > utc(packet.snapshot.as_of):
        raise ValueError("Market source was unavailable at the snapshot time")
    if len({e.evidence_id for e in packet.evidence}) != len(packet.evidence):
        raise ValueError("Evidence IDs must be unique")
    for item in packet.evidence:
        source = sources.get(item.metadata.get("source_id"))
        if source is None or item.url != source.url or item.published_at is None:
            raise ValueError("Every evidence item requires its matching source receipt and publication time")
        if source.published_at != item.published_at or utc(item.retrieved_at) != utc(source.retrieved_at):
            raise ValueError("Evidence times must match the source receipt")
        if utc(item.published_at) > utc(packet.snapshot.as_of) or utc(item.retrieved_at) > utc(packet.snapshot.as_of):
            raise ValueError("Evidence was unavailable at the snapshot time")
    if packet.brief:
        brief_items = packet.brief.evidence + packet.brief.counter_evidence
        if sorted(content_hash(e) for e in brief_items) != sorted(content_hash(e) for e in packet.evidence):
            raise ValueError("Brief evidence must match the reviewed packet exactly")
        if packet.brief.resolution_source != packet.resolution_source:
            raise ValueError("Brief resolution source must match the packet")
    if packet.settlement:
        settlement = packet.settlement
        if settlement.market_id != packet.snapshot.market.market_id or settlement.source_id not in sources:
            raise ValueError("Settlement market/source mismatch")
        if packet.snapshot.market.status != "settled" or utc(settlement.resolved_at) > utc(packet.snapshot.as_of):
            raise ValueError("Settlement requires a settled snapshot after resolution")
    return packet


def packet_status(path, settings=None, *, now=None):
    now = utc(now)
    packet = load_packet(path, now=now)
    checks = preflight(packet.snapshot, packet.brief, settings or Settings(), now) if packet.brief else snapshot_checks(packet.snapshot, packet.snapshot.market.market_id, settings or Settings(), now)
    blockers = [f"{c.code}: {c.message}" for c in checks if not c.passed]
    if packet.brief is None:
        blockers.append("Reviewed research brief required before preparing an intent")
    return {"valid": True, "packet_hash": content_hash(packet), "market_id": packet.snapshot.market.market_id,
            "observed_at": packet.snapshot.as_of.isoformat(), "source_count": len(packet.sources),
            "evidence_count": len(packet.evidence), "blockers": blockers,
            "research_ready": not blockers, "review_required": True,
            "settlement_available": packet.settlement is not None,
            "note": "Hashes/times verified; source meaning and probability estimates require reviewer judgment"}


def review_packet(path, *, actor, reason, scope="research", now=None):
    now = utc(now)
    packet = load_packet(path, now=now)
    if not actor.strip() or not reason.strip():
        raise ValueError("Reviewer and rationale required")
    if scope == "settlement" and packet.settlement is None:
        raise ValueError("No settlement evidence to review")
    return PacketReview(packet_hash=content_hash(packet), actor=actor.strip(), reason=reason.strip(),
        reviewed_at=now, scope=scope, simulation=packet.snapshot.market.platform == "fixture")


def checked_review(packet, review_path, scope, now):
    review = PacketReview.model_validate_json(Path(review_path).read_text())
    if review.scope != scope or review.packet_hash != content_hash(packet) or utc(review.reviewed_at) > now:
        raise ValueError("Review scope, time or packet content mismatch")
    if utc(review.reviewed_at) < max(utc(s.retrieved_at) for s in packet.sources):
        raise ValueError("Review predates collected sources")
    return review


def prepare_packet(repo, settings, path, review_path, *, now=None):
    now = utc(now)
    packet = load_packet(path, now=now)
    review = checked_review(packet, review_path, "research", now)
    if repo.load_settlement_receipt(packet.snapshot.market.market_id):
        raise ValueError("Market already settled in this paper ledger")
    status = packet_status(path, settings, now=now)
    if status["blockers"]:
        raise ValueError("; ".join(status["blockers"]))
    signal = PredictionMarketEdgeStrategy(settings.risk).generate_signal(packet.brief, packet.snapshot)
    signal.metadata.update({"packet_hash": content_hash(packet), "evidence_review": review.model_dump(mode="json")})
    marks = portfolio_marks(repo, packet.snapshot, settings, now)
    portfolio = observe_equity(repo, PaperLedger(repo, settings.risk).snapshot_portfolio(marks, persist=False), now)
    risk = RiskEngine(settings.risk).evaluate_signal(signal, open_positions=portfolio.open_positions, **loss_metrics(portfolio))
    return PaperExecutionService(repo, settings).prepare(signal, risk, packet.snapshot, packet.brief,
        now=now, simulation=packet.snapshot.market.platform == "fixture")


def settle_packet(repo, settings, path, review_path, *, now=None):
    from local_market_agent.schemas.models import SettlementReceipt, deterministic_model_context
    now = utc(now)
    packet = load_packet(path, now=now)
    review = checked_review(packet, review_path, "settlement", now)
    settlement = packet.settlement
    if settlement is None:
        raise ValueError("Settlement evidence required")
    packet_hash = content_hash(packet)
    with deterministic_model_context(seed="settlement:"+packet_hash, now=now), repo.transaction() as bound:
        existing = bound.load_settlement_receipt(settlement.market_id)
        if existing:
            if existing.packet_hash != packet_hash:
                raise ValueError("Market already settled with a different packet")
            return existing
        ledger = PaperLedger(bound, settings.risk)
        positions = [p for p in bound.list_positions(settlement.market_id) if p.is_open]
        if not positions:
            raise ValueError("No open paper positions for this settlement")
        closed = []
        for position in positions:
            if position.side not in {"BUY_YES", "BUY_NO"}:
                raise ValueError("Unsupported position side")
            price = float((position.side == "BUY_YES") == (settlement.outcome == "yes"))
            closed.append(ledger._close_in_transaction(position.position_id, price))
        fills = [f for f in bound.list_paper_fills() if f.is_closing and f.position_id in {p.position_id for p in closed}]
        receipt = SettlementReceipt(receipt_id=settlement.market_id, market_id=settlement.market_id, created_at=now,
            packet_hash=packet_hash, review=review.model_dump(mode="json"), outcome=settlement.outcome,
            source_hashes={s.source_id: s.sha256 for s in packet.sources},
            closing_hashes={f.fill_id: content_hash(f) for f in fills})
        bound.save_settlement_receipt(receipt)
        if not ledger.open_positions():
            bound.save_portfolio_snapshot(observe_equity_in_transaction(bound,
                ledger._snapshot_in_transaction({}, persist=False), now))
    return receipt
