from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from local_market_agent.adapters.base import cache_json, evidence_from_text, safe_get_json
from local_market_agent.schemas import EvidenceItem


@dataclass
class SecEdgarAdapter:
    """Read-only SEC EDGAR submissions metadata adapter."""

    user_agent: str = "local-market-agent@example.com"
    raw_cache_dir: Path = Path("data/raw_cache")

    def company_submissions(self, cik: str) -> dict[str, Any]:
        normalized = cik.zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{normalized}.json"
        payload = safe_get_json(url, headers={"User-Agent": self.user_agent})
        cache_json(self.raw_cache_dir, url, payload)
        if not isinstance(payload, dict):
            msg = "unexpected SEC EDGAR response"
            raise RuntimeError(msg)
        return payload

    def latest_filing_evidence(self, cik: str) -> EvidenceItem:
        payload = self.company_submissions(cik)
        filings = payload.get("filings", {})
        recent = filings.get("recent", {}) if isinstance(filings, dict) else {}
        forms = recent.get("form", []) if isinstance(recent, dict) else []
        accession = recent.get("accessionNumber", []) if isinstance(recent, dict) else []
        form = forms[0] if forms else "unknown filing"
        accession_number = accession[0] if accession else "unknown accession"
        name = str(payload.get("name") or cik)
        return evidence_from_text(
            source="sec-edgar",
            title=f"{name} latest SEC filing: {form}",
            summary=f"Latest public EDGAR submission accession {accession_number}.",
            url=f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json",
            relevance_score=0.60,
            credibility_score=0.90,
        )
