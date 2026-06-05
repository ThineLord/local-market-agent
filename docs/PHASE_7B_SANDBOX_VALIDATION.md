# Phase 7B - Historical Sandbox Validation

## Objective

Phase 7B adds a local sandbox runner for Phase 7 paper operations.
It simulates repeated manually invoked Phase 7 daily runs across a historical
date range using local deterministic fixture inputs.

This is not Phase 8. The sandbox does not add broker integrations, live trading,
real-money execution, a scheduler, a daemon, cloud deployment, or autostart.

## CLI

Run a default 30-day sandbox ending on the local fixture snapshot date:

```bash
lma phase7-sandbox-run --days 30
```

Run an explicit inclusive date range:

```bash
lma phase7-sandbox-run \
  --start-date 2026-05-30 \
  --end-date 2026-06-05
```

Run a 7-day offline smoke with paper order execution allowed by the risk gate
configuration override:

```bash
lma phase7-sandbox-run \
  --days 7 \
  --db /tmp/lma-phase7b/phase7b.sqlite \
  --report-dir /tmp/lma-phase7b/reports \
  --no-require-manual-approval
```

Run the sandbox with an explicitly configured OpenAI-compatible research
provider. This affects research brief drafting only:

```bash
lma phase7-sandbox-run \
  --days 7 \
  --llm-provider openai-compatible \
  --llm-model local-model \
  --llm-base-url http://localhost:1234/v1
```

Run the sandbox against an explicit read-only current snapshot source:

```bash
lma phase7-sandbox-run \
  --days 7 \
  --market-source polymarket \
  --market-id <polymarket-market-id>
```

Non-fixture sandbox runs are labeled `snapshot repeated sandbox`. They are not
historical backtests and profitability claims are not meaningful.

The command prints the sandbox summary JSON and writes the same JSON to:

```text
<report-dir>/phase7_sandbox_summary_<sandbox_id>_<start>_<end>.json
```

## Architecture

The sandbox is an orchestration layer around the existing Phase 7 components:

```text
Phase7SandboxRunner
    |
    +-- deterministic model id/time context
    +-- Phase7DailyRunner once per simulated day with configured LLM provider
    +-- immutable per-run Phase 7 manifests
    +-- immutable per-run Phase 7 reports
    +-- Phase7ReplayService sample validation
    +-- sandbox summary JSON artifact
```

Each default simulated day uses the local fixture market and evidence files. The
runner refreshes the market timestamp to the simulated day by default and gives
the refreshed snapshot a run-scoped snapshot id, so generated run records do not
share a mutable snapshot reference.

Phase 7C PR-D1 also allows explicit read-only current snapshot sources. These
sources do not provide historical day-by-day sandbox data in this implementation.

The deterministic model context is only used by the sandbox. Normal Phase 7
daily runs continue to use regular UUID-based ids and the current UTC clock.

## Summary Artifact

The summary includes:

- Sandbox id, date range, simulated day count, input paths, and safety flags.
- Research LLM provider audit metadata.
- Market data audit metadata, including source, data mode, network-call
  possibility, historical/snapshot-only flags, and whether profitability claims
  are meaningful.
- Completed, rejected, failed, pending, halted, and dry-run counts.
- One equity curve point per generated run when a portfolio snapshot exists.
- Total return from configured paper starting cash to ending sandbox equity.
- Max drawdown over the sandbox equity curve.
- Win rate and profit factor for closed positions opened by generated sandbox
  runs. These values are `null` when the sandbox has no closed positions.
- Run success rate, where only failed run records reduce the success rate.
- Per-run ids, report paths, manifest ids, checksums, and replay references.
- Replay validation sample results, including mutation checks against local
  SQLite table counts.

## Replay

Every generated run is a normal Phase 7 run record with a manifest and immutable
report path, so it can be replayed with:

```bash
lma phase7-replay --db /tmp/lma-phase7b/phase7b.sqlite --run-id <run_id>
```

The sandbox summary also replay-validates a configurable sample:

```bash
lma phase7-sandbox-run --days 7 --replay-sample-size 3
```

Replay is read-only. The sample result records `counts_before`, `counts_after`,
and `mutation_detected`.

## Safety Invariants

- Paper-only execution mode.
- Default local fixture and SQLite inputs; optional non-fixture market sources
  are read-only public snapshot inputs only.
- No broker API, private trading endpoint, withdrawal, wallet, leverage,
  derivatives, shorting, scheduler, daemon, autostart, cloud deployment, or
  direct LLM-to-order path.
- The command fails closed if `REAL_MONEY_ENABLED`, `ALLOW_LIVE_ORDERS`, or
  `risk.live_trading_allowed` is enabled.
- Default settings still keep `REAL_MONEY_ENABLED=false`,
  `ALLOW_LIVE_ORDERS=false`, and `HUMAN_APPROVAL_REQUIRED=true`.
- The sandbox inherits the Phase 7 daily runner's configured research provider,
  but the LLM output still cannot create orders or bypass risk gates.

## Limitations

- Fixture mode reuses the existing deterministic fixture market and evidence
  set.
- Non-fixture mode uses current snapshots only; it does not introduce a new
  historical data provider.
- Sandbox total return, drawdown, win rate, and profit factor are workflow
  diagnostics unless backed by true historical market states and settlements.
- A real OpenAI-compatible provider may make research network calls only when
  explicitly selected; default sandbox runs remain mock/offline.
- Win rate and profit factor are `null` unless generated positions are later
  closed in the local paper ledger.
- There is no Sharpe ratio, benchmark comparison, scheduler, daemon, broker
  connection, strategy redesign, or Phase 8 work.
