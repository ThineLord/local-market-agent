# Local Market Agent

Local Market Agent is an offline-first research, risk-control, and paper-trading system for public market data. It is designed for deterministic local demos and safety review before any future expansion.

The default mode is read-only data plus paper trading only. Live order execution, withdrawals, leverage, derivatives, shorting, private trading APIs, and direct LLM-to-order flows are out of scope and blocked by code and tests.

## Setup

Use Python 3.11 or newer.

```bash
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

If `uv` is available, this project is also compatible with:

```bash
uv sync
```

## Offline Demo

```bash
lma ingest-demo
lma generate-brief --fixture data/fixtures/demo_market.json
lma risk-check
lma paper-log
lma report-daily
```

All commands work without API keys and use deterministic fixtures.

## LLM Provider

The default provider is `mock`, which is deterministic, offline, and requires no
API key:

```bash
lma llm-provider-audit
```

To use a local or OpenAI-compatible research provider, explicitly select it and
configure the endpoint/model. API keys come from environment/config, not from a
plain command-line option:

```bash
export LMA_LLM_PROVIDER=openai-compatible
export LMA_OPENAI_COMPATIBLE_BASE_URL=http://localhost:1234/v1
export LMA_OPENAI_COMPATIBLE_MODEL=local-model
export LMA_OPENAI_COMPATIBLE_API_KEY=optional-local-key

lma phase7-run-daily --llm-provider openai-compatible --llm-model local-model
```

The configured LLM provider can draft research JSON only. Signals, risk
decisions, risk gates, and paper orders remain rule-based and paper-only.

## Phase 7 Market Data

Phase 7 daily and sandbox runs default to deterministic fixture market data:

```bash
lma market-data-audit
lma phase7-run-daily --market-source fixture
```

Optional read-only snapshot sources can be selected explicitly:

```bash
lma phase7-run-daily --market-source polymarket --market-id <market-id>
lma phase7-sandbox-run --days 30 --market-source yfinance --market-id SPY
```

Non-fixture sandbox runs are labeled as snapshot-repeated workflows. They check
workflow correctness against read-only current data, not historical strategy
profitability. Phase 7 still does not execute real trades.

Local historical JSONL datasets can be used for sandbox validation:

```bash
lma phase7-sandbox-run \
  --market-source historical-file \
  --historical-file data/fixtures/phase7_historical_5d.jsonl \
  --days 5
```

Historical-file mode is local-only and uses date-specific rows. Profitability
claims are marked meaningful only when settlement/outcome data is present.

## Dashboard

Launch the redesigned local dashboard from the repository root with your Python
environment activated:

```bash
python ui/server.py
```

Open **http://127.0.0.1:8502** in Chrome. Use `--port 8503` to choose another
local port. The server binds to loopback only and opens the SQLite database in
read-only mode. Missing databases show an explicitly labeled fixture preview.

The interface includes a quiet overview, all nine original dashboard sections,
searchable, filterable and sortable record tables, CSV export, complete record drawers,
research evidence/counterpoints, and the linked audit trail. Phase 7 operations
are grouped into runs, portfolio, positions, orders, fills, and risk gates.
The original procedural 3D bull is rendered locally with Canvas; there are no
remote assets or frontend build dependencies. Page and detail transitions move
the scene smoothly. Background motion can be paused and respects the system's
reduced-motion setting. Narrow screens use a collapsible navigation and
independently scrolling tables.

The API loads up to 500 records per main category and reports total counts.
The existing Phase 7 view retains its limits of 25 runs / 100 execution records.
All displayed prices and timestamps are saved observations, not a live feed.
Settings are read-only and explicitly allowlisted; there are no order or
approval endpoints. Refresh rereads local data, without running a collection.

The original Streamlit interface remains available:

```bash
streamlit run ui/app.py
```

The dashboard reads local SQLite data and fixtures. It has no live trading buttons and never displays secrets.

## Validation

```bash
ruff check .
pytest
```

Optional network adapters are read-only and are covered by tests marked `network`; they are skipped unless `LMA_RUN_NETWORK_TESTS=true`.

## Safety Model

- `REAL_MONEY_ENABLED=false`
- `ALLOW_LIVE_ORDERS=false`
- `HUMAN_APPROVAL_REQUIRED=true`
- All paper orders require a valid signal and approved risk decision.
- The LLM provider can produce research JSON only. It cannot create orders.
- Risk rules veto live trading attempts, leverage, derivatives, shorting, weak evidence, low confidence, wide spreads, and insufficient edge.
