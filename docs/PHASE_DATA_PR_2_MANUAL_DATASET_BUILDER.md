# PR-DATA-2 Manual Local Historical Dataset Builder

## Scope

PR-DATA-2 adds a local-only manual dataset builder/importer for Phase 7G
historical datasets. It converts curator-provided CSV, JSON, or JSONL files
into the `phase7g.historical_dataset.v1` JSONL schema and can immediately run
the PR-DATA-1 validator.

This PR does not implement downloader code, source-specific public export
adapters, Kalshi or Polymarket API integration, network automation, Phase 8,
broker integrations, live trading, real-money execution, scheduler, daemon,
autostart, Strategy v2 policy changes, threshold tuning, acceptance-size
dataset construction, or profitability claims.

## Architecture

New module:

- `local_market_agent.data.historical_builder`

Public entry points:

- `build_historical_dataset(input_path, input_format, profile, output_dir, report_dir=None, validate=True)`
- `HistoricalDatasetBuildResult`

The builder reads one local manual input file, normalizes rows into the Phase 7G
schema, writes deterministic local output artifacts, and optionally calls
`validate_historical_dataset` plus `write_historical_validation_reports`.

The module intentionally imports only standard-library file/parsing utilities
and the local historical validator. It does not import market adapters, network
clients, paper ledger systems, risk engines, strategy modules, or broker/order
APIs.

## Input Formats

Supported formats:

- `csv`: one row per point-in-time observation using simple manual columns.
- `jsonl`: one JSON object per line, with either flat manual fields or nested
  `evidence`, `settlement`, and `source_provenance` objects.
- `json`: either a list of row objects or an object with a `rows` array and
  optional top-level defaults.

Manual input may provide:

- dataset fields: `dataset_id`, `dataset_label`, `profile`;
- timing fields: `timestamp` or `date`;
- market fields: `market_id`, `platform`, `title`, `market_type`,
  `outcome_side`, `category`, `split`, `metadata`;
- price fields: `bid`, `ask`, `last_price`, `implied_probability`,
  `liquidity`, `volume`;
- evidence fields: nested `evidence`, `evidence_json`, or flat
  `evidence_*` columns;
- settlement fields: nested `settlement`, `settlement_json`, or flat
  `settlement_*` columns;
- provenance fields: nested `source_provenance`, `source_provenance_json`, or
  flat `source_*` columns.

## Deterministic Behavior

The builder is deterministic:

- generates a stable `dataset_id` when missing from input;
- generates stable `row_id` values when missing;
- generates stable `evidence_id` values when missing;
- sorts output rows by `timestamp`, `platform`, `market_id`, and `row_id`;
- writes compact sorted-key JSONL rows;
- writes a manifest containing the input checksum and local-only safety flags.

Date-only manual rows are normalized to `16:00:00Z` for a deterministic
point-in-time timestamp. The builder does not fabricate evidence timestamps.

## Profile Rules

`acceptance_candidate`:

- preserves curator-provided bid/ask values;
- sets `paper_pnl_allowed=true` and `acceptance_candidate=true` only when both
  bid and ask are present;
- never invents bid/ask from `last_price`;
- does not emit top-level `settlement_outcome` close signals for forecast rows.

`calibration_only_last_price`:

- forces `bid=null` and `ask=null`;
- forces `paper_pnl_allowed=false`;
- forces `acceptance_candidate=false`;
- records `calibration_only_reason`;
- cannot support paper PnL or Strategy v2 acceptance claims.

Both profiles preserve nested settlement metadata when supplied, but the
builder does not synthesize settlement labels.

## Output Artifacts

The builder writes:

- `data/historical/{dataset_id}.jsonl`
- `data/historical/{dataset_id}.manifest.json`

When `--validate` is used, it also writes validator artifacts:

- `{dataset_id}.validation.json`
- `{dataset_id}_audit.md`

Generated historical outputs under `data/historical/` are ignored by default
except for `.gitkeep`, so local curator exports do not get committed
accidentally.

## CLI Command

```bash
lma build-historical-dataset \
  --input data/fixtures/historical_builder/manual_acceptance_sample.csv \
  --input-format csv \
  --profile acceptance_candidate \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --validate
```

The CLI summary includes:

- `dataset_id`
- `output_jsonl`
- `manifest_path`
- `validation_json_path`
- `validation_markdown_path`
- `row_count`
- `market_count`
- `profile`
- `validation_valid`
- `error_count`
- `warning_count`

## Fixtures

Added deterministic fixtures under `data/fixtures/historical_builder/`:

- `manual_acceptance_sample.csv`
- `manual_acceptance_sample.jsonl`
- `manual_calibration_sample.csv`
- `malformed_manual_sample.csv`

These fixtures are intentionally small. They are for builder and validator
coverage only and are not acceptance-size datasets.

## Tests

Added `tests/test_historical_dataset_builder.py`.

Coverage includes:

- CSV acceptance input builds valid Phase 7G JSONL;
- JSONL acceptance input builds valid Phase 7G JSONL;
- calibration-only input forces `bid=null`, `ask=null`, and no paper PnL;
- missing `row_id` and `evidence_id` values are generated deterministically;
- output rows are sorted deterministically;
- builder runs the validator and reports JSON/Markdown artifacts;
- malformed manual input fails with a clear error;
- CLI build command writes JSONL, manifest, and validation reports;
- no downloader, network client, or source-specific adapter dependencies;
- no broker, live trading, paper order, risk gate, or order API dependencies.

## Safety Notes

PR-DATA-2 is manual-input-only file conversion. It does not fetch data, scrape
websites, call public provider APIs, create market snapshots, generate
forecasts, emit signals, approve risk, create paper orders, mutate the paper
ledger, or change Strategy v1 or Strategy v2 behavior.

Any generated dataset remains subject to PR-DATA-1 validation and the Strategy
v2 acceptance gate. A small fixture that validates as schema-correct is still
not sufficient for acceptance evaluation or profitability claims.

## Validation

Required validation:

```bash
PYTHONPATH=src .venv/bin/ruff check .
PYTHONPATH=src .venv/bin/pytest
PYTHONPATH=src .venv/bin/lma build-historical-dataset \
  --input data/fixtures/historical_builder/manual_acceptance_sample.csv \
  --input-format csv \
  --profile acceptance_candidate \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --validate
```

## Remaining Limitations

- No downloader or source-specific public export adapter exists yet.
- No acceptance-size dataset is constructed.
- The builder trusts curator-provided evidence and settlement fields, then uses
  the validator to detect schema, provenance, leakage, and safety issues.
- Calibration-only outputs are useful for forecast calibration diagnostics but
  cannot support paper PnL claims or pass Strategy v2 acceptance.

## Next Action

PR-DATA-3 may add a source-specific public export adapter after review. Do not
start Phase 8, broker integration, live trading, scheduler, daemon, autostart,
or Strategy v2 production replacement work from PR-DATA-2.
