# PR-CAL-1 Calibration Dataset Audit

## Scope

PR-CAL-1 adds a local-only audit/reporting layer for Phase 7G historical
datasets that may be useful for calibration diagnostics. It classifies datasets
by calibration size and evidence/settlement readiness while explicitly blocking
acceptance, Strategy v2 superiority, and profitability claims from
calibration-only data.

This PR does not implement new data collection, downloader code, strategy logic
changes, acceptance-gate changes, Phase 8, broker integrations, live trading,
real-money execution, scheduler, daemon, or autostart behavior.

## Architecture

New module:

- `local_market_agent.eval.calibration_audit`

Public entry points:

- `audit_calibration_dataset(path)`
- `write_calibration_audit_reports(result, output_dir)`
- `CalibrationAuditResult`
- `CalibrationAuditArtifacts`

The audit reads a local Phase 7G JSONL file, runs the existing historical
dataset validator, computes calibration-specific metrics, classifies the
dataset, and writes deterministic JSON and Markdown audit reports. It does not
fetch data, create market snapshots, emit signals, approve risk, create paper
orders, or call external systems.

## CLI Command

```bash
PYTHONPATH=src .venv/bin/lma audit-calibration-dataset \
  --historical-file data/historical/example.jsonl \
  --output-dir data/reports/calibration
```

The CLI writes:

- `{dataset_id}.calibration_audit.json`
- `{dataset_id}_calibration_audit.md`

The CLI summary includes:

- dataset id;
- classification;
- row, market, resolved-market, and scored-row counts;
- settlement and evidence timestamp coverage;
- acceptance blockers;
- calibration warnings;
- claim guardrails;
- JSON and Markdown artifact paths.

## Classification Rules

The audit emits one classification:

| Classification | Rule |
| --- | --- |
| `calibration_unusable` | Fewer than 25 markets, fewer than 250 rows, fewer than 25 resolved markets, incomplete settlement, missing last-price data, duplicate market/timestamp rows, or calibration-fatal validator errors. |
| `calibration_minimum` | At least 25 markets and 250 rows, 100% settlement coverage for rows, 25+ resolved binary markets, and complete last-price coverage. |
| `calibration_preferred` | At least 60 markets and 720 rows, with the same settlement and price requirements. |
| `calibration_stretch` | At least 150 markets and 2,000 rows, with the same settlement and price requirements. |
| `acceptance_candidate_possible` | Acceptance profile dataset that also has 25+ markets, 250+ rows, 50+ candidate forecast rows, 95%+ evidence timestamp coverage, complete bid/ask coverage, complete source provenance, reviewed terms, no private/authenticated source flag, no validator errors, and validator `acceptance_candidate=true`. |

Missing timestamp-safe evidence is an acceptance blocker but not a calibration
blocker. Missing bid/ask is also an acceptance and paper-PnL blocker, but it is
not a calibration blocker when last-price coverage and settlement are complete.

## Metrics

The JSON and Markdown reports include:

- `row_count`
- `market_count`
- `resolved_market_count`
- `scored_row_count`
- `settlement_coverage_pct`
- `evidence_timestamp_coverage_pct`
- `bid_ask_coverage_pct`
- `last_price_coverage_pct`
- `category_count`
- `platform_distribution`
- `source_distribution`
- `duplicate_market_timestamp_rows`
- `missing_outcome_count`
- `missing_price_count`
- `acceptance_blockers`
- `calibration_warnings`
- `claim_guardrails`
- validator summary fields

## Claim Guardrails

The audit reports these booleans:

- `forecast_calibration_diagnostics`
- `strategy_comparison_diagnostics`
- `paper_simulation_diagnostics`
- `acceptance_gate_evaluation_possible`
- `acceptance_gate_pass`
- `strategy_v2_superiority`
- `profitability_claim`

For every calibration-only dataset:

- `acceptance_gate_pass=false`
- `strategy_v2_superiority=false`
- `profitability_claim=false`

Even for `acceptance_candidate_possible`, this audit only says that the dataset
appears shaped for a later acceptance-gate run. It does not mark the acceptance
gate as passed.

## Tests

Added `tests/test_calibration_audit.py`.

Coverage includes:

- tiny fixture classified `calibration_unusable`;
- generated minimum fixture classified `calibration_minimum`;
- generated preferred fixture classified `calibration_preferred`;
- generated stretch fixture classified `calibration_stretch`;
- missing settlement blocks calibration;
- missing evidence blocks acceptance but not calibration;
- calibration-only data blocks superiority and profitability claims;
- acceptance-shaped fixture classified `acceptance_candidate_possible`;
- CLI writes JSON and Markdown reports;
- report writer smoke;
- no broker/live/order API added by the audit module.

All threshold fixtures are generated deterministically inside tests and are not
committed as large fixture files.

## Safety Notes

PR-CAL-1 is audit/reporting only. It does not add or call:

- downloader code;
- source collection automation;
- broker APIs;
- private trading endpoints;
- live orders;
- real-money execution;
- scheduler, daemon, or autostart behavior;
- strategy logic;
- acceptance gate logic;
- risk approval;
- risk gate mutation;
- paper ledger mutation;
- Phase 8 behavior;
- direct LLM-to-order paths.

## Validation

Required validation:

```bash
PYTHONPATH=src .venv/bin/ruff check .
PYTHONPATH=src .venv/bin/pytest
git diff --check
```

Optional smoke command:

```bash
PYTHONPATH=src .venv/bin/lma audit-calibration-dataset \
  --historical-file data/fixtures/historical_validator/valid_calibration_only.jsonl \
  --output-dir data/reports/calibration
```

The tiny built-in calibration fixture is expected to classify as
`calibration_unusable` because it is below the 25-market and 250-row minimum.

## Next Step

After PR-CAL-1 review, the project may use the audit on a larger local
calibration-only dataset. Do not start data collection, downloader work,
acceptance-gate changes, Phase 8, broker integration, live trading, scheduler,
daemon, autostart, or Strategy v2 production replacement work from this PR.
