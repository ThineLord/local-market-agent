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


def _audit_chain_rows(repository: SQLiteRepository) -> list[dict[str, object]]:
    briefs = repository.list_briefs(limit=100)
    signals = repository.list_signals(limit=100)
    decisions = repository.list_risk_decisions(limit=100)
    orders = repository.list_paper_orders(limit=100)

    brief_by_id = {brief.brief_id: brief for brief in briefs}
    signal_by_id = {signal.signal_id: signal for signal in signals}
    decision_by_id = {decision.risk_decision_id: decision for decision in decisions}
    decisions_by_signal: dict[str, list[object]] = {}
    orders_by_signal: dict[str, list[object]] = {}
    orders_by_decision: dict[str, list[object]] = {}

    for decision in decisions:
        decisions_by_signal.setdefault(decision.signal_id, []).append(decision)
    for order in orders:
        orders_by_signal.setdefault(order.signal_id, []).append(order)
        orders_by_decision.setdefault(order.risk_decision_id, []).append(order)

    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_row(brief: object | None, signal: object | None, decision: object | None, order: object | None) -> None:
        brief_id = getattr(brief, "brief_id", "") or getattr(signal, "brief_id", "")
        signal_id = getattr(signal, "signal_id", "") or getattr(decision, "signal_id", "") or getattr(order, "signal_id", "")
        risk_decision_id = getattr(decision, "risk_decision_id", "") or getattr(order, "risk_decision_id", "")
        paper_order_id = getattr(order, "order_id", "")
        key = (str(brief_id), str(signal_id), str(risk_decision_id), str(paper_order_id))
        if key in seen:
            return
        seen.add(key)
        market_id = (
            getattr(brief, "market_id", "")
            or getattr(signal, "market_id", "")
            or getattr(order, "market_id", "")
        )
        rows.append(
            {
                "brief_id": brief_id,
                "signal_id": signal_id,
                "risk_decision_id": risk_decision_id,
                "paper_order_id": paper_order_id,
                "market_id": market_id,
                "recommended_action": str(getattr(brief, "recommended_action", "")),
                "signal_action": str(getattr(signal, "action", "")),
                "risk_approved": getattr(decision, "is_approved", None),
                "veto_reasons": "; ".join(getattr(decision, "veto_reasons", [])),
                "order_side": str(getattr(order, "side", "")),
                "order_status": str(getattr(order, "status", "")),
                "_brief": brief,
                "_signal": signal,
                "_risk_decision": decision,
                "_paper_order": order,
            }
        )

    for signal in signals:
        brief = brief_by_id.get(signal.brief_id)
        linked_decisions = decisions_by_signal.get(signal.signal_id, [])
        if linked_decisions:
            for decision in linked_decisions:
                for order in orders_by_decision.get(decision.risk_decision_id, [None]):
                    add_row(brief, signal, decision, order)
        else:
            for order in orders_by_signal.get(signal.signal_id, [None]):
                add_row(brief, signal, None, order)

    signaled_brief_ids = {signal.brief_id for signal in signals}
    for brief in briefs:
        if brief.brief_id not in signaled_brief_ids:
            add_row(brief, None, None, None)

    for decision in decisions:
        if decision.signal_id not in signal_by_id:
            for order in orders_by_decision.get(decision.risk_decision_id, [None]):
                add_row(None, None, decision, order)

    for order in orders:
        if order.signal_id not in signal_by_id and order.risk_decision_id not in decision_by_id:
            add_row(None, None, None, order)

    return rows


def _row_label(row: dict[str, object]) -> str:
    return " | ".join(
        str(part)
        for part in [
            row["market_id"],
            row["brief_id"] or "no brief",
            row["signal_id"] or "no signal",
            row["risk_decision_id"] or "no risk",
            row["paper_order_id"] or "no order",
        ]
        if part
    )


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
        "Audit Chain",
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

elif page == "Audit Chain":
    st.subheader("Audit Chain")
    rows = _audit_chain_rows(repo)
    if not rows:
        st.info("No audit chain data found. Run the offline CLI chain first.")
    else:
        columns = [
            "brief_id",
            "signal_id",
            "risk_decision_id",
            "paper_order_id",
            "market_id",
            "recommended_action",
            "signal_action",
            "risk_approved",
            "veto_reasons",
            "order_side",
            "order_status",
        ]
        st.dataframe(pd.DataFrame([{key: row[key] for key in columns} for row in rows]), width="stretch")
        selected_index = st.selectbox(
            "Audit row",
            range(len(rows)),
            format_func=lambda index: _row_label(rows[index]),
        )
        selected = rows[selected_index]
        for label, key in [
            ("Brief JSON", "_brief"),
            ("Signal JSON", "_signal"),
            ("Risk Decision JSON", "_risk_decision"),
            ("Paper Order JSON", "_paper_order"),
        ]:
            with st.expander(label):
                item = selected[key]
                if item is None:
                    st.info("No linked object for this row.")
                else:
                    st.json(item.model_dump(mode="json"))

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
