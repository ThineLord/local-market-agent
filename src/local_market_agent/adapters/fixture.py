from __future__ import annotations

import json
from pathlib import Path

from local_market_agent.schemas import EvidenceItem, Market, MarketSnapshot


class FixtureAdapter:
    def __init__(
        self,
        market_fixture: str | Path = "data/fixtures/demo_market.json",
        evidence_fixture: str | Path = "data/fixtures/demo_evidence.json",
    ) -> None:
        self.market_fixture = Path(market_fixture)
        self.evidence_fixture = Path(evidence_fixture)

    def fetch_snapshot(self, market_id: str | None = None) -> MarketSnapshot:
        payload = json.loads(self.market_fixture.read_text(encoding="utf-8"))
        market = Market.model_validate(payload["market"])
        if market_id is not None and market.market_id != market_id:
            msg = f"fixture market_id mismatch: expected {market_id}, got {market.market_id}"
            raise ValueError(msg)
        snapshot_payload = dict(payload["snapshot"])
        snapshot_payload["market"] = market.model_dump(mode="json")
        return MarketSnapshot.model_validate(snapshot_payload)

    def fetch_evidence(self, market_id: str | None = None) -> list[EvidenceItem]:
        if market_id is not None:
            self.fetch_snapshot(market_id)
        payload = json.loads(self.evidence_fixture.read_text(encoding="utf-8"))
        return [EvidenceItem.model_validate(item) for item in payload]
