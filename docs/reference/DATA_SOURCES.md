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
- `historical-file`: local JSONL historical market rows; requires
  `--historical-file` and may require `--market-id` for multi-market files.
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

PR-D2 adds `historical-file` for local JSONL datasets. This mode uses the row for
a simulated date once that row is visible, and does not reuse a current snapshot
across the range. A date whose explicit timestamp is still ahead uses the latest
row already visible instead of that future row. If no earlier row exists, that
dated row remains the input and its settlement stays hidden. It marks
profitability claims as meaningful only for one selected market whose rows all
permit paper PnL, are not calibration-only, and share a credible unambiguous
settlement. Explicit paper-PnL prohibition, calibration-only rows, pending or
missing settlement, ambiguous settlement, an unspecified market, and a market
id that is not in the file do not. `has_settlement` means a settlement label is
present on that selection. A calibration-only label can still be settled, and
it is not paper-profit proof. Original settlement labels stay visible on the
file-level audit. A day's run record, manifest, and daily report keep only rows
and labels that are already visible: later file rows stay out, and a label with
`resolved_at` or `label_available_at` stays out until that publication time.
A date-only row is visible for that whole UTC date. An explicit `timestamp`
is visible only at or after that UTC instant. The sandbox summary's file
qualification describes the whole file and is separate from each day's report.
See [the historical dataset schema](https://github.com/ThineLord/local-market-agent/blob/v0.5.0/docs/archive/phases/PHASE_7C_PR_D2_HISTORICAL_DATASET.md) for the
schema and backtest boundary.
