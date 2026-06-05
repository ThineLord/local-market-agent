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
