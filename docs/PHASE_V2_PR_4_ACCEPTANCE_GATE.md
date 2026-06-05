# PR-V2-4 Strategy v2 Comparison Report And Acceptance Gate

## Scope

PR-V2-4 adds a paper-only, local-only, evaluation-only acceptance gate for the
Strategy v2 candidate. It extends the existing offline evaluation report with a
machine-readable gate result and a Markdown comparison section.

This PR does not start Phase 8, add broker integrations, add live trading, add
real-money execution, add a scheduler, add a daemon, add autostart, replace
Strategy v1 in production Phase 7 daily runs, add new Strategy v2 policy logic,
tune thresholds, download data, mutate the paper ledger, or make a superiority
claim from the five-row fixture.

## Architecture

Updated module:

- `local_market_agent.eval.offline_strategy`

The offline evaluator now builds:

- Existing dataset summary.
- Existing baseline metric sections.
- Existing safety summary.
- New top-level `acceptance_gate` object.

The gate is computed from already-produced offline metrics. It does not create
signals in repository storage, approve risk, create risk gate decisions, mutate
paper trading state, create orders, or call any broker.

## Acceptance Gate Fields

The JSON report now includes:

- `gate_status`: `pass`, `fail`, or `not_applicable`.
- `superiority_claim_allowed`.
- `dataset_label`.
- `failed_gates`.
- `warning_gates`.
- `metric_deltas`.
- `strategy_v1_summary`.
- `strategy_v2_summary`.
- `baseline_summaries`.
- `gate_checks`.
- `recommendation`.

`superiority_claim_allowed` is true only when `gate_status=pass`.

## Gate Behavior

The gate evaluates dataset preconditions:

- Resolved binary market count.
- Evaluation row count.
- Candidate forecast count.
- Closed paper trade count.
- Settlement coverage.
- Evidence timestamp coverage.

The gate evaluates forecast quality:

- Strategy v2 Brier score improvement versus Strategy v1.
- Strategy v2 Brier score improvement versus market-implied probability.
- Calibration bucket improvement versus Strategy v1.
- Large calibration-gap buckets.
- Structured probability completeness.
- Missing structured probability never producing a paper-buy action.

The gate evaluates paper outcomes:

- Total return delta versus Strategy v1.
- Realized paper PnL delta versus Strategy v1.
- Max drawdown no worse than Strategy v1.
- Profit factor at least Strategy v1 and at least `1.0` when applicable.
- Benchmark-relative return.

The gate evaluates activity and safety:

- Strategy v2 abstention rate must stay inside the declared first-run bounds.
- Paper-only, local-only, evaluation-only flags must remain intact.
- Strategy v2 must not be production-enabled.
- Phase 8, live trading, scheduler, broker/order, and direct LLM-to-order flags
  must remain false.
- Replay placeholders must be present and checksum availability must remain true
  when full replay is not applicable.

If safety invariants fail, `gate_status=fail` regardless of metrics.

If dataset preconditions are missing, `gate_status=not_applicable` and
superiority claims are blocked even when diagnostic metrics are favorable.

If dataset preconditions pass but forecast, paper outcome, activity, or replay
checks fail, `gate_status=fail`.

## Five-Row Fixture Behavior

For `data/fixtures/phase7_historical_5d.jsonl`, the gate returns:

- `gate_status=not_applicable`.
- `dataset_label=fixture_smoke`.
- `superiority_claim_allowed=false`.

The fixture fails minimum requirements for resolved markets, evaluation rows,
candidate forecasts, and closed paper trades. This blocks Strategy v2
superiority claims regardless of paper PnL or calibration diagnostics.

## Report Changes

The Markdown report now includes a dedicated Strategy v2 acceptance section
with:

- Gate verdict.
- Superiority-claim status.
- Dataset label.
- Recommendation.
- Failed gates.
- Warning gates.
- Strategy v2 deltas versus Strategy v1 and market-implied baseline.
- Minimum requirement table.

The CLI summary for `lma strategy-eval-offline` now includes:

- `gate_status`.
- `failed_gates`.
- `warning_gates`.
- `recommendation`.
- `superiority_claim_allowed` from the acceptance gate.

No separate CLI command was added because extending the existing offline
evaluation command keeps the workflow deterministic and narrow.

## Tests

Added tests cover:

- Five-row fixture gate blocks superiority claims.
- Missing settlement blocks acceptance.
- Insufficient sample size blocks acceptance.
- Strategy v2 not better than Strategy v1 fails the gate.
- Safety invariant failure blocks the gate.
- Markdown report includes the gate verdict.
- JSON report includes required gate fields.
- Strategy v2 remains absent from the Phase 7 daily runner.
- No broker/live/order APIs added by the offline evaluator.

## Safety Notes

PR-V2-4 does not add or call:

- Broker APIs.
- Private trading endpoints.
- Live orders.
- Real-money execution.
- Scheduler, daemon, or autostart.
- Production Strategy v2 replacement.
- Risk approval mutation.
- Risk gate mutation.
- Paper ledger mutation.
- Data downloader.
- Direct LLM-to-order paths.

Strategy v1 remains the production/default Phase 7 strategy.

## Validation

Required validation:

- `PYTHONPATH=src .venv/bin/ruff check .`
- `PYTHONPATH=src .venv/bin/pytest`
- `PYTHONPATH=src .venv/bin/lma strategy-eval-offline --historical-file data/fixtures/phase7_historical_5d.jsonl --output-dir data/reports/strategy_eval`

The smoke command must show `gate_status=not_applicable` or `fail` and
`superiority_claim_allowed=false` for the five-row fixture.

## Next Step

After PR-V2-4 review, the project may collect a larger local historical dataset
for acceptance evaluation. Do not start Phase 8, broker integration, live
trading, scheduler, daemon, autostart, or production Strategy v2 replacement
work.
