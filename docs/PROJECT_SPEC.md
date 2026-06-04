# Project Specification

Local Market Agent is a Python 3.11+ package with a Typer CLI, SQLite persistence, deterministic fixtures, read-only public data adapters, strict schemas, and a Streamlit dashboard.

## Functional Requirements

- Generate structured market research briefs from snapshots and evidence.
- Convert eligible briefs into paper-only signals.
- Veto unsafe or low-quality signals through a risk engine.
- Create deterministic simulated paper fills only after risk approval.
- Track positions, realized and unrealized PnL, and daily reports.
- Support offline demos without API keys.

## Architecture

- `src/local_market_agent/schemas`: Pydantic contracts.
- `src/local_market_agent/storage`: SQLite object repository.
- `src/local_market_agent/adapters`: read-only data adapters.
- `src/local_market_agent/agents`: research, skeptic, calibration, reporting pipeline.
- `src/local_market_agent/strategy`: strategy rules.
- `src/local_market_agent/risk`: risk controls.
- `src/local_market_agent/paper`: paper ledger.
- `src/local_market_agent/reporting`: daily reports.
- `ui/app.py`: local dashboard.
