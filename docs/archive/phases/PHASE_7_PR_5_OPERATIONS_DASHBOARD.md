# Phase 7 PR-5 - Operations Dashboard

## Scope

PR-5 adds a read-only Streamlit operations view for Phase 7 paper trading state.
It summarizes local SQLite records produced by the paper portfolio engine, risk
gate framework, daily report generator, and manually invoked paper daily runner.

Included:

- A separated `Phase 7 Operations` dashboard page
- Latest Phase 7 run status and report path
- Recent Phase 7 run records
- Latest portfolio snapshot summary
- Open paper positions
- Recent paper orders and fills
- Recent risk gate decisions
- Basic PnL and exposure summary from the latest portfolio snapshot
- Import/render helper smoke tests

Out of scope:

- Broker APIs
- Live trading code
- Order buttons
- Approve or reject buttons
- Dashboard-triggered paper trading
- Scheduler, cron, daemon, or background worker
- Phase 8 integration
- New strategy logic
- New risk gates
- PR-1, PR-2, PR-3, or PR-4 subsystem rewrites

## Usage

Start the local dashboard:

```bash
streamlit run ui/app.py
```

Select `Phase 7 Operations` from the sidebar.

To point the dashboard at an explicit local database:

```bash
LMA_DB_PATH=data/local_market_agent.sqlite streamlit run ui/app.py
```

## View Sections

- Safety label: confirms the page is paper-only and read-only.
- Latest run metrics: latest status, open position count, portfolio value, and
  exposure percentage.
- Latest report path: path recorded by the latest Phase 7 run record.
- Recent Phase 7 runs: local `phase7_run_records` rows.
- Latest portfolio snapshot: local `portfolio_snapshots` summary.
- Open paper positions: currently open local `positions` rows.
- Recent paper orders: local `paper_orders` rows.
- Recent paper fills: local `paper_fills` rows.
- Recent risk gate decisions: local `risk_gate_decisions` rows.

## Data Sources

The view reads through `SQLiteRepository` only:

- `phase7_run_records`
- `portfolio_snapshots`
- `positions`
- `paper_orders`
- `paper_fills`
- `risk_gate_decisions`

The dashboard does not call the Phase 7 daily runner, paper ledger mutation
methods, risk gate evaluator, report generator, broker adapters, or any live
trading endpoint.

## Safety Invariants

- The view contains no order, approval, reject, runner, scheduler, or broker
  controls.
- The view does not create paper orders, fills, positions, risk gate decisions,
  reports, or run records.
- Existing harmless Streamlit startup and repository initialization may create a
  local SQLite file when `LMA_DB_PATH` points at a new path.
- No broker adapter, credential, private trading endpoint, withdrawal path,
  leverage path, scheduler, daemon, live order path, or direct LLM-to-order path
  is introduced.
