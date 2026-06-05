# Phase 7 PR-H1 - Replay, Manifests, Immutable Reports, And Metrics

## Scope

PR-H1 closes the highest-priority Phase 7 completion audit gaps without
starting Phase 8. It remains paper-only and local-only.

Included:

- Read-only Phase 7 replay command
- Immutable Phase 7 run manifest persistence
- Run-id-based Phase 7 report artifact paths
- Failed run persistence
- Local metrics rollup foundation
- Metrics section in Phase 7 daily reports

Out of scope:

- Broker APIs
- Live trading code
- Scheduler, cron, daemon, or background service
- Dashboard redesign
- Strategy changes
- Benchmarking
- Sharpe ratio
- Phase 8 integration

## Replay Command

Replay a stored Phase 7 run:

```bash
lma phase7-replay --run-id phase7_run_example
```

Replay against an explicit local database:

```bash
lma phase7-replay \
  --db data/local_market_agent.sqlite \
  --run-id phase7_run_example
```

Replay is read-only. It does not call the runner, paper ledger, risk gate
evaluator, report generator, broker adapters, or mutation methods.

Replay validates:

- Run record exists
- Manifest exists and matches the run id
- Manifest execution mode is paper
- Manifest configuration snapshot, CLI arguments, and fixture paths exist
- Stored run references can be loaded
- Report artifact exists when required
- Report SHA-256 checksum matches the manifest

The command returns JSON with `ok`, `errors`, `warnings`, `artifacts`,
`manifest`, `report_path`, and `report_checksum`.

## Manifest Schema

Each Phase 7 runner invocation stores a `Phase7RunManifest` in local SQLite,
keyed by `run_id`.

Fields:

- `run_id`
- `created_at`
- `code_version`
- `configuration_snapshot`
- `cli_arguments`
- `fixture_paths`
- `report_path`
- `report_checksum`
- `execution_mode`
- `metadata`

Configuration snapshots exclude secrets and broker credentials. The manifest is
linked from `Phase7RunRecord.manifest_id`.

## Immutable Reports

Runner-created Phase 7 daily reports now use:

```text
phase7_daily_report_<run_id>.md
```

This prevents same-date report overwrites. The run record stores the exact path,
and the manifest stores the exact path plus checksum.

## Failed Runs

If the Phase 7 runner catches an exception, it persists:

- `Phase7RunRecord` with `status=failed`
- `completed_at`
- error type and message
- partial context captured before failure
- linked manifest

Failed run persistence is best effort. Repository-level failures can still
prevent persistence.

## Metrics Foundation

`Phase7MetricsCalculator` computes local metrics from existing SQLite records:

- Equity curve series from portfolio snapshots
- Win rate from closed positions
- Profit factor from closed positions
- Max drawdown from the equity curve
- Run success rate from Phase 7 run records

Metrics are generated on demand and do not mutate portfolio state.

The Phase 7 daily report includes a `Phase 7 Metrics` section with the local
rollup.

## Safety Invariants

- All new records use paper execution mode.
- Replay is read-only.
- Metrics are read-only.
- No broker adapter, private trading endpoint, credential path, withdrawal path,
  leverage path, scheduler, daemon, live order path, or direct LLM-to-order path
  is introduced.

## Remaining Known Gaps

- No built-in scheduler, cron, daemon, or background monitor.
- No Sharpe ratio.
- No benchmark comparison.
- No strategy redesign or multi-market scanner hardening.
- Failed run persistence is best effort when the local repository is writable.
