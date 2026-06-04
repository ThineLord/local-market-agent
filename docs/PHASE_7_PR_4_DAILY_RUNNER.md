# Phase 7 PR-4 - Paper Daily Runner

## Scope

PR-4 adds a deterministic, paper-only daily runner that performs one local
Phase 7 operation run. It is manually invoked and is not a scheduler, daemon, or
background service.

Included:

- `Phase7DailyRunner`
- `Phase7RunRecord` and `Phase7RunStatus`
- Local SQLite persistence for run records
- `lma phase7-run-daily` CLI command
- Dry-run mode
- Deterministic fixture mode
- Phase 7 daily report generation through PR-3

Out of scope:

- Real scheduler, cron, daemon, or background worker
- Dashboard changes
- Broker APIs
- Live trading code
- Real order execution
- Phase 8 integration
- New strategy logic
- New risk gates
- PR-1 paper ledger rewrite
- PR-2 risk gate evaluator rewrite
- PR-3 report redesign

## Manual Usage

Run one deterministic fixture-backed paper operation:

```bash
lma phase7-run-daily --no-require-manual-approval
```

Run against an explicit local database and report directory:

```bash
lma phase7-run-daily \
  --db data/local_market_agent.sqlite \
  --report-dir data/reports \
  --no-require-manual-approval
```

Run without mutating paper positions:

```bash
lma phase7-run-daily --dry-run
```

Keep the fixture timestamp unchanged to exercise market-data freshness gates:

```bash
lma phase7-run-daily --keep-fixture-timestamp --no-require-manual-approval
```

By default, the command uses:

- `data/fixtures/demo_market.json`
- `data/fixtures/demo_evidence.json`
- `data/reports/phase7_daily_report_YYYY-MM-DD.md`

## Run Flow

```text
Fixture market data
    |
Research brief generation
    |
Existing signal strategy
    |
Existing Phase 0-6 risk decision
    |
Phase 7 risk gate evaluator
    |
Paper ledger only if risk gates approve and not dry-run
    |
Portfolio snapshot
    |
Phase 7 Markdown daily report
    |
Phase 7 run record
```

## Statuses

- `completed`
- `rejected`
- `pending_manual_approval`
- `halted`
- `dry_run`
- `failed`

## Persistence

Run records are stored locally in the `phase7_run_records` SQLite table as JSON
payloads. Each record links the snapshot, brief, signal, risk decision, risk gate
decision, optional paper order, portfolio snapshot, report path, and run reasons.

## Safety Invariants

- The runner uses fixture/read-only local inputs in PR-4.
- The runner does not schedule itself or run in the background.
- Dry-run mode does not create paper orders, fills, or positions.
- Paper ledger mutation happens only after an approved Phase 7 risk gate decision.
- No broker adapter, credential, private trading endpoint, withdrawal path,
  leverage path, dashboard action, live order path, or direct LLM-to-order path
  is introduced.
