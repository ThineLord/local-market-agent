from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

from local_market_agent.adapters.base import cache_json, evidence_from_text, safe_get_json
from local_market_agent.schemas import EvidenceItem


class GdeltAdapter:
    """Read-only GDELT document API adapter."""

    BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, raw_cache_dir: str | Path = "data/raw_cache") -> None:
        self.raw_cache_dir = Path(raw_cache_dir)

    def search_evidence(self, query: str, limit: int = 5) -> list[EvidenceItem]:
        url = (
            f"{self.BASE_URL}?query={quote_plus(query)}&mode=ArtList&format=json"
            f"&maxrecords={limit}"
        )
        payload = safe_get_json(url)
        cache_json(self.raw_cache_dir, url, payload)
        if not isinstance(payload, dict):
            return []
        articles = payload.get("articles", [])
        if not isinstance(articles, list):
            return []
        evidence: list[EvidenceItem] = []
        for article in articles[:limit]:
            if not isinstance(article, dict):
                continue
            evidence.append(
                evidence_from_text(
                    source="gdelt",
                    title=str(article.get("title") or "Untitled GDELT article"),
                    summary=str(article.get("seendate") or "GDELT article match"),
                    url=str(article.get("url")) if article.get("url") else None,
                    relevance_score=0.55,
                    credibility_score=0.55,
                )
            )
        return evidence
