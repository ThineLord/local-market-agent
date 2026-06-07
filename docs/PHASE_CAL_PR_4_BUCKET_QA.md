# PR-CAL-4 Calibration Bucket QA And Segment Analysis

## Scope

PR-CAL-4 adds a local-only calibration QA/reporting layer for inspecting
calibration bucket gaps in existing Phase 7G historical JSONL datasets.

This PR does not collect data, modify strategy logic, modify acceptance gates,
start Phase 8, add broker integrations, add live trading, add real-money
execution, add scheduler/daemon/autostart behavior, fabricate evidence, invent
bid/ask, or make acceptance, Strategy v2 superiority, profitability, or
trading-readiness claims.

## Architecture

New module:

- `local_market_agent.eval.calibration_bucket_qa`

Public entry points:

- `run_calibration_bucket_qa(path, gap_threshold=0.15)`
- `write_calibration_bucket_qa_reports(result, output_dir)`
- `CalibrationBucketQAResult`
- `CalibrationBucketQAArtifacts`

The QA module reads a local JSONL historical file, computes bucket-level
forecast/outcome metrics, enriches rows with local staged Kalshi market metadata
when available, analyzes segment distributions, and writes deterministic JSON
and Markdown reports.

The module is file-only. It does not fetch data, create market snapshots, emit
signals, approve risk, mutate paper ledgers, create orders, or call external
systems.

## CLI Command

```bash
PYTHONPATH=src .venv/bin/lma calibration-bucket-qa \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_calibration_20260607_public_probe.jsonl \
  --output-dir data/reports/calibration \
  --gap-threshold 0.15
```

The CLI writes:

- `{dataset_id}.calibration_bucket_qa.json`
- `{dataset_id}_calibration_bucket_qa.md`

The CLI summary includes:

- dataset id;
- gap threshold;
- high-gap buckets;
- per-bucket row and market counts;
- per-bucket absolute gaps;
- per-bucket warnings;
- claim guardrails;
- JSON and Markdown artifact paths.

## Metrics

Overall bucket stats include:

- bucket;
- row count;
- market count;
- mean forecast;
- observed YES rate;
- absolute gap;
- Brier score;
- log loss.

For every high-gap bucket, the report includes:

- top markets by row count;
- top markets by Brier loss;
- observed outcome split;
- market dominance summary;
- small-sample status;
- calibration-only last-price status;
- row-category missing count;
- source-manifest category missing count;
- evidence missing count;
- bid/ask missing count;
- liquidity missing and thin-liquidity counts;
- segment summaries;
- representative rows limited to row id, market id, timestamp, forecast,
  outcome, loss metrics, category, volume, and liquidity.

## Segment Dimensions

The QA report analyzes high-gap bucket rows by:

- `market_id`
- `platform`
- `source`
- `profile`
- `settlement_outcome`
- `timestamp_date`
- `hour_of_day`
- `price_decile`
- `row_recency_within_market`
- `source_manifest_category`
- `liquidity_segment`
- `volume_segment`

When rows contain a Kalshi `export_id` and the local staged export is still
present, the QA tool reads
`data/source_exports/kalshi/{export_id}/markets.jsonl` to recover
`metadata.calibration_category` by market. Missing local staged exports do not
block QA; the category segment is reported as missing instead.

## Diagnostics

The report can emit:

- `small_sample_warning`
- `market_concentration_warning`
- `category_missing_warning`
- `liquidity_missing_warning`
- `thin_liquidity_warning`
- `evidence_missing_warning`
- `bid_ask_missing_warning`
- `settlement_imbalance_warning`
- `repeated_market_sampling_warning`

These are diagnostic warnings only. They do not change acceptance gates,
Strategy v2 thresholds, or production behavior.

## Claim Guardrails

The report always sets:

- `acceptance_gate_pass=false`
- `strategy_v2_superiority=false`
- `profitability_claim=false`
- `acceptance_ready_claim=false`
- `trading_readiness_claim=false`

`forecast_calibration_diagnostics=true` only means the report may be used for
calibration QA. It does not imply acceptance readiness, paper-PnL validity,
Strategy v2 superiority, profitability, or live-trading readiness.

## Tests

Added `tests/test_calibration_bucket_qa.py`.

Coverage includes:

- high-gap bucket detection;
- market concentration warning;
- small sample warning;
- missing category warning;
- bid/ask and evidence missing warnings;
- JSON and Markdown report writing;
- CLI artifact writing;
- no broker/live/order API dependency in the QA module.

Fixtures are generated deterministically inside tests and no large fixtures are
committed.

## Validation

Required validation:

```bash
PYTHONPATH=src .venv/bin/ruff check .
PYTHONPATH=src .venv/bin/pytest
git diff --check
```

## Safety Notes

PR-CAL-4 is local-only and reporting-only. It does not collect more data,
modify strategies, modify acceptance gates, fabricate evidence, invent bid/ask,
start Phase 8, add broker integrations, add live trading, add account/order
paths, add scheduler/daemon/autostart behavior, mutate paper trading state, or
make acceptance, Strategy v2 superiority, profitability, or trading-readiness
claims.
