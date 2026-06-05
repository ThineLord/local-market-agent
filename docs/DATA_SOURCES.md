# Data Sources

## Offline

- `data/fixtures/demo_market.json`
- `data/fixtures/demo_evidence.json`

## Optional Public Network Sources

- Polymarket public market metadata.
- Kalshi public market metadata.
- yfinance OHLCV, normalized in Phase 7C PR-D1 as the latest snapshot only.
- SEC EDGAR submissions metadata.
- GDELT document API.

All network adapters are read-only and optional. Raw public responses may be cached under `data/raw_cache`.

## Phase 7C Market Source Modes

Phase 7 daily and sandbox commands default to `--market-source fixture`.

Supported explicit sources:

- `fixture`: deterministic offline market and evidence fixtures.
- `polymarket`: read-only current public market snapshot; requires `--market-id`.
- `kalshi`: read-only current public market snapshot; requires `--market-id`.
- `yfinance`: latest OHLCV row as a read-only snapshot; requires `--market-id`.

Use `lma market-data-audit` to inspect the selected source without fetching
market data. The audit reports whether network calls are possible, whether the
data is historical, and whether sandbox profitability claims are meaningful.

Current snapshot sandbox runs are not historical backtests. Meaningful
profitability evaluation requires time-indexed historical market snapshots,
time-appropriate evidence, fill/settlement assumptions, and benchmark
methodology that PR-D1 intentionally does not add.
