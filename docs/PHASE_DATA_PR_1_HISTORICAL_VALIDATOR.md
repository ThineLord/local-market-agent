# PR-DATA-1 Historical Dataset Schema Validator

## Scope

PR-DATA-1 adds a local-only, file-only validator for Phase 7G historical JSONL
datasets. It validates schema shape, timestamp integrity, settlement labels,
evidence timestamp coverage, source provenance, duplicate rows, warning/error
codes, and report generation before a dataset is used by the Strategy v2
evaluation loop.

This PR does not implement downloader code, source-specific export adapters,
network automation, Phase 8, broker integrations, live trading, real-money
execution, scheduler, daemon, autostart, Strategy v2 policy changes, threshold
tuning, acceptance-size dataset construction, or profitability claims.

## Architecture

New module:

- `local_market_agent.data.historical_validator`

Public entry points:

- `validate_historical_dataset(path)`
- `write_historical_validation_reports(result, output_dir)`
- `HistoricalDatasetValidationResult`
- `HistoricalDatasetValidationArtifacts`
- `ValidationIssue`

The validator reads a local `.jsonl` file, validates each non-empty line as a
single JSON object, accumulates structured errors and warnings, computes
dataset-level quality metrics, and can write deterministic JSON and Markdown
audit artifacts. Invalid datasets still produce structured validation results;
missing files or non-JSONL paths are rejected before validation.

The module intentionally avoids market adapters, paper ledger systems, risk
engines, strategy modules, and network clients.

## Row-Level Validation

The validator implements the Phase 7G schema from
`docs/reports/historical_dataset_builder_spec.md`.

It validates:

- valid JSONL and one object per line,
- required fields for every row,
- required fields for `acceptance_candidate`,
- required fields for `calibration_only_last_price`,
- `phase7g.historical_dataset.v1` schema version,
- timezone-aware ISO 8601 timestamps,
- optional `date` alias matching `timestamp`,
- probability fields in `[0, 1]`,
- `bid`, `ask`, and `bid <= ask`,
- `market_type=binary_prediction` for acceptance rows,
- nested settlement object and unambiguous `yes` or `no` outcome,
- evidence array shape,
- evidence `published_at` and `retrieved_at` timestamps,
- future evidence leakage,
- source provenance object and required provenance fields,
- source terms review,
- `private_or_authenticated_source=false` for acceptance,
- secret-like key or value patterns in any row payload.

## Dataset-Level Metrics

The JSON report includes:

- `dataset_id`
- `profile`
- `row_count`
- `market_count`
- `resolved_binary_market_count`
- `candidate_forecast_row_count`
- `settlement_coverage_pct`
- `evidence_timestamp_coverage_pct`
- `duplicate_row_count`
- `duplicate_market_timestamp_count`
- `missing_bid_ask_count`
- `bid_exceeds_ask_count`
- `future_evidence_leakage_count`
- `missing_source_provenance_count`
- `warning_counts`
- `error_counts`
- `paper_pnl_allowed`
- `acceptance_candidate`
- `source_names`
- `raw_export_checksums`
- detailed `errors`
- detailed `warnings`

Small fixtures may validate as schema-correct without satisfying Strategy v2
acceptance-size requirements. The Strategy v2 acceptance gate remains
responsible for sample-size and superiority-claim decisions.

## Error And Warning Codes

The validator uses the codes from the builder spec.

Implemented error codes include:

- `invalid_json`
- `row_not_object`
- `missing_required_field`
- `invalid_schema_version`
- `invalid_timestamp`
- `date_timestamp_mismatch`
- `unsupported_market_type`
- `invalid_probability`
- `bid_exceeds_ask`
- `missing_bid_ask_for_acceptance`
- `duplicate_market_timestamp`
- `duplicate_row_id`
- `future_evidence_leakage`
- `evidence_timestamp_missing_for_acceptance`
- `missing_settlement_for_scored_market`
- `ambiguous_settlement`
- `post_settlement_forecast_row`
- `missing_source_provenance`
- `source_terms_blocked`
- `private_source_detected`
- `secret_pattern_detected`

Implemented warning codes include:

- `missing_evidence`
- `single_source_evidence`
- `timestamp_unknown`
- `date_only_evidence_timestamp`
- `wide_spread`
- `thin_liquidity`
- `missing_volume`
- `missing_liquidity`
- `last_price_only`
- `source_terms_pending`

The module reserves the remaining documented warning categories for future
dataset-audit expansion.

## CLI Command

New command:

```bash
lma validate-historical-dataset \
  --historical-file data/fixtures/historical_validator/valid_acceptance_candidate.jsonl \
  --output-dir data/reports/historical_dataset
```

The CLI writes:

- `{dataset_id}.validation.json`
- `{dataset_id}_audit.md`

The CLI summary includes:

- `valid`
- `profile`
- `acceptance_candidate`
- `paper_pnl_allowed`
- `row_count`
- `market_count`
- `error_count`
- `warning_count`
- `json_path`
- `markdown_path`

## Fixtures

Added deterministic fixtures under `data/fixtures/historical_validator/`:

- `valid_acceptance_candidate.jsonl`
- `valid_calibration_only.jsonl`
- `invalid_future_evidence.jsonl`
- `invalid_missing_bid_ask.jsonl`
- `invalid_ambiguous_settlement.jsonl`
- `invalid_secret_like_field.jsonl`
- `invalid_duplicate_row_timestamp.jsonl`

These fixtures are small and local. They do not require network access and are
not acceptance-size datasets.

## Tests

Added `tests/test_historical_dataset_validator.py`.

Coverage includes:

- valid acceptance fixture,
- valid calibration-only fixture,
- missing required field,
- invalid timestamp,
- bid greater than ask,
- future evidence leakage,
- missing settlement,
- ambiguous settlement,
- private/authenticated source,
- secret-like field,
- duplicate row and timestamp,
- CLI JSON and Markdown report writing,
- no downloader/source adapter/network automation dependencies,
- no paper ledger, risk engine, broker, live, or order API dependencies.

## Safety Notes

PR-DATA-1 is validation-only. It does not fetch data, create market snapshots,
generate forecasts, emit signals, approve risk, create paper orders, mutate the
paper ledger, or change Strategy v1 or Strategy v2 behavior.

The validator may report `paper_pnl_allowed=true` only for schema-valid
`acceptance_candidate` files with complete bid/ask and settlement metadata. It
does not claim profitability or Strategy v2 superiority.

## Validation

Required validation:

```bash
PYTHONPATH=src .venv/bin/ruff check .
PYTHONPATH=src .venv/bin/pytest
PYTHONPATH=src .venv/bin/lma validate-historical-dataset \
  --historical-file data/fixtures/historical_validator/valid_acceptance_candidate.jsonl \
  --output-dir data/reports/historical_dataset
```

The smoke command should return `valid=true`, `profile=acceptance_candidate`,
`paper_pnl_allowed=true`, and paths to JSON and Markdown validation artifacts.

## Next Step

PR-DATA-2 may add a manual local dataset builder/importer. Do not implement
downloaders, source-specific adapters, network automation, Phase 8, broker
integrations, live trading, scheduler, daemon, autostart, or strategy changes as
part of PR-DATA-1.
