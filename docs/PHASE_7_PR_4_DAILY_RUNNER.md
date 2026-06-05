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
- Phase 7C PR-D1 read-only market source selector, with `fixture` as the default
- Phase 7 daily report generation through PR-3
- Configured research LLM provider path, with `mock` as the default

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

Inspect the selected research provider without calling it:

```bash
lma llm-provider-audit
```

Use an explicitly configured OpenAI-compatible provider for research only:

```bash
export LMA_OPENAI_COMPATIBLE_API_KEY=optional-local-key

lma phase7-run-daily \
  --llm-provider openai-compatible \
  --llm-model local-model \
  --llm-base-url http://localhost:1234/v1
```

The provider can only draft the research brief. Signal generation, risk
decisions, risk gates, and paper ledger writes remain deterministic code paths.

Inspect the selected market data source without fetching data:

```bash
lma market-data-audit
```

Use an explicit read-only current snapshot source:

```bash
lma phase7-run-daily \
  --market-source polymarket \
  --market-id <polymarket-market-id>
```

Non-fixture sources are read-only snapshot inputs and require an explicit market
identifier. They do not add broker access or order execution.

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
Selected read-only market data
    |
Configured research LLM provider (mock by default)
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

- The runner defaults to fixture/local inputs; non-fixture sources are explicit
  read-only current snapshots added in Phase 7C PR-D1.
- The runner does not schedule itself or run in the background.
- Dry-run mode does not create paper orders, fills, or positions.
- Paper ledger mutation happens only after an approved Phase 7 risk gate decision.
- The default LLM provider remains `mock`; OpenAI-compatible research calls occur
  only when explicitly selected by config or CLI override.
- LLM provider output cannot create orders and cannot bypass strategy, risk, risk
  gate, or repository relationship checks.
- No broker adapter, credential, private trading endpoint, withdrawal path,
  leverage path, dashboard action, live order path, or direct LLM-to-order path
  is introduced.
