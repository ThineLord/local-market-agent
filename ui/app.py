from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from local_market_agent.adapters import FixtureAdapter  # noqa: E402
from local_market_agent.config import load_settings  # noqa: E402
from local_market_agent.storage import SQLiteRepository  # noqa: E402


def _repo() -> SQLiteRepository:
    settings = load_settings()
    return SQLiteRepository(settings.db_path)


def _frame(items: list[object]) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    return pd.DataFrame([item.model_dump(mode="json") for item in items])


st.set_page_config(page_title="Local Market Agent", layout="wide")
st.title("Local Market Agent")

page = st.sidebar.radio(
    "Page",
    [
        "Watchlist",
        "Market Brief",
        "Signals",
        "Risk Decisions",
        "Paper Ledger",
        "Performance Report",
        "Settings",
    ],
)

repo = _repo()
settings = load_settings()

if page == "Watchlist":
    st.subheader("Watchlist")
    snapshots = repo.list_market_snapshots(limit=50)
    if snapshots:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "market_id": item.market.market_id,
                        "title": item.market.title,
                        "platform": item.market.platform,
                        "status": item.market.status,
                        "market_probability": item.market_implied_probability,
                        "spread": item.spread,
                        "as_of": item.as_of,
                    }
                    for item in snapshots
                ]
            ),
            width="stretch",
        )
    else:
        fixture = FixtureAdapter().fetch_snapshot()
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "market_id": fixture.market.market_id,
                        "title": fixture.market.title,
                        "platform": fixture.market.platform,
                        "status": fixture.market.status,
                        "market_probability": fixture.market_implied_probability,
                        "spread": fixture.spread,
                    }
                ]
            ),
            width="stretch",
        )

elif page == "Market Brief":
    st.subheader("Market Brief")
    briefs = repo.list_briefs(limit=25)
    if briefs:
        selected = st.selectbox("Brief", briefs, format_func=lambda item: item.brief_id)
        st.json(selected.model_dump(mode="json"))
        st.markdown("Evidence")
        st.dataframe(_frame(selected.evidence), width="stretch")
        st.markdown("Counter evidence")
        st.dataframe(_frame(selected.counter_evidence), width="stretch")
    else:
        st.info("No briefs found. Run `lma generate-brief`.")

elif page == "Signals":
    st.subheader("Signals")
    st.dataframe(_frame(repo.list_signals(limit=50)), width="stretch")

elif page == "Risk Decisions":
    st.subheader("Risk Decisions")
    st.dataframe(_frame(repo.list_risk_decisions(limit=50)), width="stretch")

elif page == "Paper Ledger":
    st.subheader("Paper Ledger")
    st.markdown("Orders")
    st.dataframe(_frame(repo.list_paper_orders(limit=100)), width="stretch")
    st.markdown("Positions")
    st.dataframe(_frame(repo.list_positions(limit=100)), width="stretch")

elif page == "Performance Report":
    st.subheader("Performance Report")
    st.dataframe(_frame(repo.list_performance_reports(limit=25)), width="stretch")

elif page == "Settings":
    st.subheader("Settings")
    st.json(
        {
            "db_path": str(settings.db_path),
            "raw_cache_dir": str(settings.raw_cache_dir),
            "research_brief_dir": str(settings.research_brief_dir),
            "real_money_enabled": settings.real_money_enabled,
            "allow_live_orders": settings.allow_live_orders,
            "human_approval_required": settings.human_approval_required,
            "llm_provider": settings.llm_provider,
            "risk": settings.risk.as_dict(),
        }
    )
