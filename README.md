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

## Dashboard

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
