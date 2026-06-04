from __future__ import annotations

from pathlib import Path

import pytest

from local_market_agent.adapters import FixtureAdapter
from local_market_agent.agents import ResearchBriefGenerator
from local_market_agent.storage import SQLiteRepository


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteRepository:
    return SQLiteRepository(tmp_path / "lma.sqlite")


@pytest.fixture
def fixture_adapter() -> FixtureAdapter:
    return FixtureAdapter()


@pytest.fixture
def snapshot(fixture_adapter: FixtureAdapter):
    return fixture_adapter.fetch_snapshot()


@pytest.fixture
def evidence(fixture_adapter: FixtureAdapter):
    return fixture_adapter.fetch_evidence()


@pytest.fixture
def brief(snapshot, evidence):
    return ResearchBriefGenerator().generate(snapshot, evidence)
