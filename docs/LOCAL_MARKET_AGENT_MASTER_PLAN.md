# Local Market Agent Master Plan

This master plan is reconstructed from the implementation task context and is the source of truth for this repository.

## Mission

Build an offline-first local market research agent that can ingest public read-only data, generate structured research briefs, produce paper-only signals, run strict risk checks, maintain a paper ledger, and display the full brief-to-paper-order chain.

## Non-Negotiable Boundaries

- Default mode is read-only data plus paper trading only.
- Do not implement live order execution, private trading endpoints, withdrawals, API-key trading workflows, VPN or geoblock bypass, leverage, derivatives, shorting, or direct LLM-to-order paths.
- All paper orders must require a signal and an approved risk decision.
- Tests must prove live trading attempts are vetoed.

## Batches

0. Preflight and repo hygiene: docs, dependencies, gitignore, safety defaults.
1. Project skeleton and CLI: `lma ingest-demo`, `generate-brief`, `risk-check`, `paper-log`, `report-daily`.
2. Core schemas and SQLite storage: strict Pydantic models and roundtrip persistence.
3. LLM provider abstraction: deterministic mock and OpenAI-compatible structured JSON runtime.
4. Read-only adapters: fixtures, public Polymarket, Kalshi placeholder, yfinance, SEC EDGAR, GDELT.
5. Research brief pipeline: researcher, skeptic, calibrator, reporter, orchestration.
6. Strategy and risk engine: edge strategy, placeholders, and veto rules.
7. Paper ledger: deterministic fills, positions, PnL, JSONL/CSV export, daily reports.
8. Streamlit dashboard: local data inspection with no live trading controls.
9. Hardening, docs, tests, and CI.

## Phase 7 Daily Run

Phase 7 should remain paper-only: ingest public data, generate briefs, produce paper signals, run risk checks, append paper orders, report performance, review logs, and never submit live orders.
