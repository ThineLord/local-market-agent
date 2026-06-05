# PR-DATA-3 Kalshi Local Public Export Adapter

## Scope

PR-DATA-3 adds a local-only, file-only adapter for manually staged Kalshi-like
public export files. It converts local export directories into the Phase 7G
historical JSONL schema, runs the PR-DATA-1 validator when requested, and writes
source audit artifacts.

This PR does not implement downloader code, call Kalshi APIs, make network
requests, add Polymarket, ImpliedData, or vendor adapters, start Phase 8, add
broker integrations, add live trading, add scheduler/daemon/autostart behavior,
modify strategy logic, modify acceptance gates, or make profitability claims.

## Architecture

New module:

- `local_market_agent.data.kalshi_export_adapter`

Public entry points:

- `import_kalshi_export(export_dir, profile, output_dir, report_dir, source_audit_dir, validate=True, allow_downgrade=False)`
- `KalshiExportImportResult`

The adapter reads local files from one export directory, validates source
manifest safety fields, maps market/candle/evidence records into
`phase7g.historical_dataset.v1`, writes JSONL and manifest artifacts, optionally
runs the existing validator, and writes a Markdown source audit.

The module intentionally imports only standard-library file/parsing utilities
and the local historical validator. It does not import market adapters, network
clients, paper ledger systems, risk engines, strategy modules, or order APIs.

## Input Export Schema

Supported directory layout:

```text
data/source_exports/kalshi/{export_id}/
  source_manifest.json
  markets.jsonl
  candlesticks.jsonl
  evidence.jsonl
  trades.jsonl                  # optional
  market_rules.jsonl            # optional
  settlement_overrides.jsonl    # optional
```

Required `source_manifest.json` fields:

- `export_id`
- `dataset_id`
- `source_name`
- `source_type`
- `source_urls`
- `retrieved_at`
- `exported_at`
- `terms_review`
- `terms_reviewed_by`
- `terms_reviewed_at`
- `private_or_authenticated_source`
- `network_used_by_adapter`
- `raw_file_sha256`
- `notes`

Safety rules:

- `network_used_by_adapter` must be `false`.
- `private_or_authenticated_source` must be `false` for acceptance.
- `terms_review` must equal `reviewed_public_research_local_only` for
  acceptance.
- If terms review, bid/ask, or evidence timestamp coverage blocks acceptance,
  output fails unless `--allow-downgrade` is explicitly passed.
- Missing or ambiguous settlement blocks acceptance.

## Mapping Behavior

Market rows are keyed by `ticker`. Candlestick rows are keyed by
`market_ticker`. Evidence rows are attached by `market_ticker` only when their
`published_at` timestamp is at or before the candle `end_period_ts`.

Acceptance mapping:

- `timestamp` = `candlesticks.end_period_ts`
- `market_id` = `market_ticker`
- `platform` = `kalshi`
- `bid` = `yes_bid.close_dollars`
- `ask` = `yes_ask.close_dollars`
- `last_price` = `price.close_dollars`
- `implied_probability` = midpoint of bid and ask when both exist
- `settlement` = normalized market result, settlement timestamp, and rules
- `source_provenance` = local manifest fields plus transform version/checksum

The adapter does not use candlestick high/low values as point-in-time quotes,
does not infer bid/ask from last price, does not synthesize missing settlement,
and does not attach future evidence as forecast-time evidence.

Calibration-only mapping:

- Forces `bid=null`
- Forces `ask=null`
- Forces `paper_pnl_allowed=false`
- Forces `acceptance_candidate=false`
- Preserves `last_price`
- Records `calibration_only_reason=missing_point_in_time_bid_ask`

Calibration-only outputs can support forecast calibration diagnostics but cannot
support paper PnL claims or Strategy v2 acceptance.

## Output Artifacts

The adapter writes:

- `data/historical/{dataset_id}.jsonl`
- `data/historical/{dataset_id}.manifest.json`
- `data/reports/historical_dataset/{dataset_id}.validation.json`
- `data/reports/historical_dataset/{dataset_id}_audit.md`
- `docs/reports/{dataset_id}_source_audit.md`

The output manifest records source files, input checksums, profile, row counts,
market counts, source terms fields, bid/ask source semantics, local-only safety
flags, downgrade/failure reasons, and validation artifact paths.

The source audit records export id, input checksums, terms review fields, row
count, market count, candle count, evidence count, settlement/evidence coverage
from validation, bid/ask semantics, downgrade/failure reasons, and safety flags.

## CLI Command

```bash
lma import-kalshi-export \
  --export-dir data/fixtures/kalshi_export/sample_acceptance_export \
  --profile acceptance_candidate \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --source-audit-dir docs/reports \
  --validate
```

Optional explicit downgrade:

```bash
lma import-kalshi-export \
  --export-dir data/fixtures/kalshi_export/missing_bid_ask_export \
  --profile acceptance_candidate \
  --allow-downgrade \
  --validate
```

The CLI summary includes:

- `dataset_id`
- `profile`
- `output_jsonl`
- `manifest_path`
- `validation_json_path`
- `validation_markdown_path`
- `source_audit_path`
- `row_count`
- `market_count`
- `validation_valid`
- `error_count`
- `warning_count`
- `downgraded`
- `downgrade_reason`

## Fixtures

Added deterministic local fixtures under `data/fixtures/kalshi_export/`:

- `sample_acceptance_export`
- `missing_bid_ask_export`
- `terms_pending_export`
- `future_evidence_export`
- `calibration_only_export`

The fixtures are synthetic/demo local files shaped like Kalshi public exports.
They are not acceptance-size datasets and contain no credentials, private data,
live endpoints, or real trading records.

## Tests

Added `tests/test_kalshi_export_adapter.py`.

Coverage includes:

- valid local Kalshi acceptance export builds valid Phase 7G JSONL;
- missing candle bid/ask blocks acceptance;
- missing candle bid/ask downgrades only with explicit flag;
- bid greater than ask fails validation;
- missing settlement blocks acceptance;
- pending terms review blocks acceptance;
- private/authenticated source blocks acceptance;
- future evidence is not attached and blocks acceptance when coverage remains
  missing;
- duplicate market/timestamp rows fail validation;
- calibration-only fallback forces no paper PnL;
- source audit report is written;
- CLI import writes JSONL, manifest, validation reports, and source audit;
- no downloader/network/external source-client dependencies;
- no broker/live/order API dependencies.

## Validation

Required validation:

```bash
PYTHONPATH=src .venv/bin/ruff check .
PYTHONPATH=src .venv/bin/pytest
PYTHONPATH=src .venv/bin/lma import-kalshi-export \
  --export-dir data/fixtures/kalshi_export/sample_acceptance_export \
  --profile acceptance_candidate \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --source-audit-dir docs/reports \
  --validate
```

## Safety Notes

PR-DATA-3 remains local-only and file-only. It does not fetch data, scrape
websites, call provider APIs, create market snapshots, generate forecasts, emit
signals, approve risk, create paper orders, mutate the paper ledger, or change
Strategy v1 or Strategy v2 behavior.

The adapter may produce schema-valid acceptance-candidate fixture output, but
small fixtures do not satisfy Strategy v2 acceptance-size requirements and do
not support profitability or superiority claims.

## Remaining Limitations

- No downloader or network capture path exists.
- No acceptance-size dataset is included.
- The adapter trusts manually staged source files and terms-review metadata,
  then validates and audits the transformed output.
- Optional trade rows are counted for manifest/audit context but are not used
  as bid/ask and are not selected as last-price replacements.
- Real acceptance remains gated by source terms, point-in-time bid/ask
  completeness, settlement coverage, evidence timestamp coverage, and the
  Strategy v2 acceptance gate.
