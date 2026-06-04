from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

import httpx

from local_market_agent.schemas import EvidenceItem, MarketSnapshot


class ReadOnlyMarketAdapter(Protocol):
    def fetch_snapshot(self, market_id: str) -> MarketSnapshot:
        """Fetch public/read-only market data."""


def cache_json(cache_dir: Path, key: str, payload: object) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    path = cache_dir / f"{digest}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def safe_get_json(url: str, *, headers: dict[str, str] | None = None) -> object:
    try:
        response = httpx.get(url, headers=headers, timeout=20.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        msg = f"read-only HTTP request failed with status {exc.response.status_code}: {url}"
        raise RuntimeError(msg) from exc
    except httpx.TimeoutException as exc:
        msg = f"read-only HTTP request timed out: {url}"
        raise RuntimeError(msg) from exc
    except httpx.HTTPError as exc:
        msg = f"read-only HTTP request failed: {url}"
        raise RuntimeError(msg) from exc


def evidence_from_text(
    *,
    source: str,
    title: str,
    summary: str,
    url: str | None,
    relevance_score: float = 0.5,
    credibility_score: float = 0.5,
) -> EvidenceItem:
    return EvidenceItem(
        source=source,
        title=title,
        summary=summary,
        url=url,
        relevance_score=relevance_score,
        credibility_score=credibility_score,
    )
