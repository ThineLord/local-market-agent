from __future__ import annotations

import os

import pytest

from local_market_agent.adapters import PolymarketAdapter

pytestmark = pytest.mark.network


@pytest.mark.skipif(
    os.getenv("LMA_RUN_NETWORK_TESTS", "false").lower() != "true",
    reason="network tests are optional",
)
def test_polymarket_search_read_only():
    results = PolymarketAdapter().search("election", limit=1)
    assert isinstance(results, list)
