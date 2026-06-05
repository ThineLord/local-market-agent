# Phase 7 Gap Analysis

Date: 2026-06-05

Branch audited: `main` at `0892413c99cef115501dd93020da59d109f8c51e`

## Summary

Phase 7 is complete for the narrow PR-1 through PR-5 deliverables, but not fully
complete against the original Phase 7 plan. The system is safe and paper-only,
but the operational layer is not yet strong enough to prove 30-day or 60-day
paper operation without manual process controls.

Central completion estimate: 75%.

The remaining gaps are Phase 7 gaps, not Phase 8 work. None require broker
integration, live trading, or real-money capability.

## Missing Items

| Missing item | Impact | Evidence | Recommended action |
| --- | --- | --- | --- |
| Weekly PnL metric | Cannot review weekly portfolio performance from generated artifacts. | Metrics grep found only point-in-time realized/unrealized PnL and no weekly aggregation. | Add a Phase 7 metrics rollup from local SQLite snapshots/fills. |
| Monthly PnL metric | Cannot review monthly portfolio performance from generated artifacts. | No monthly aggregation in source or report. | Add monthly aggregation to the same local metrics rollup. |
| Explicit equity curve artifact | Portfolio values exist in snapshots but are not exported as a series or chart. | `PortfolioSnapshot.as_of` and `portfolio_value` exist; dashboard only renders latest summary. | Export a deterministic local equity-curve table from snapshots. |
| Historical max drawdown metric | Risk gates evaluate current drawdown, but no historical maximum is reported. | `RiskGateEvaluator._evaluate_daily_drawdown` checks current snapshot only. | Compute max drawdown from portfolio snapshots in a Phase 7 metrics/report enhancement. |
| Win rate metric | Strategy outcome quality cannot be summarized. | Closed positions store `realized_pnl`, but no win-rate aggregation exists. | Compute win rate from closed paper positions. |
| Profit factor metric | Profit/loss quality cannot be summarized. | No gross profit/gross loss aggregation exists. | Compute profit factor from closed paper positions. |
| Sharpe ratio metric | Risk-adjusted return quality cannot be summarized. | No return series or Sharpe calculation exists. | Compute only after an explicit local return series exists. |
| Skipped-run status | Missed or intentionally skipped days cannot be represented. | `Phase7RunStatus` has no `skipped` value. | Add a paper-only skipped-run record type or status if skipped runs are part of Phase 7 operations. |
| Replay command | Historical replay is not an actual workflow. | Run records can be inspected, but no replay CLI/service exists. | Add a local replay/audit command that reconstructs a run from stored records without mutating state. |
| Immutable run manifest | Exact historical reconstruction lacks settings, inputs, code hash, and checksums. | `Phase7RunRecord.metadata` records fixture mode and safety flag, but not a full manifest. | Persist per-run manifest metadata in Phase 7 run records or adjacent local artifacts. |
| Report immutability per run | Same-day reports can overwrite earlier same-day reports. | Runner writes `phase7_daily_report_YYYY-MM-DD.md`. | Include run ID or timestamp in report artifact paths. |

## Partial Items

| Partial item | Current state | Gap |
| --- | --- | --- |
| Continuous operation workflow | `lma phase7-run-daily` can perform a complete paper-only run when manually invoked. | No built-in scheduler, retry, lock, duplicate-run guard, or failure monitor. |
| Market scan | Runner processes one fixture market. | No Phase 7 multi-market scan/candidate list is persisted. |
| Market data freshness/completeness | Freshness is enforced by risk gate; fixture data is Pydantic-validated. | No explicit completeness gate or market-universe validation. |
| Daily PnL | Daily report displays realized and unrealized PnL from current records. | It does not compute day-over-day PnL for the report date. |
| Daily run success rate | Run records persist statuses for successful/pending/rejected/halted/dry-run outcomes. | No aggregate success-rate metric. |
| Failed runs | `Phase7RunStatus.FAILED` exists. | Runner does not catch exceptions and persist failure records. |
| Report generation success | Successful run record stores report path. | No aggregate report success metric and no persisted failed-report event. |
| Historical replay | Audit reconstruction is possible from SQLite JSON payloads and linked IDs. | Deterministic replay is not implemented and lacks immutable manifests. |
| 30-day readiness | Manually repeated fixture-backed operation is possible. | Requires operator discipline, backups, external scheduling, and manual gap tracking. |
| 60-day readiness | Same manual process can be repeated in principle. | Missing metrics, replay, failure persistence, and alerting make proof of continuous operation weak. |

## Not Gaps

The following were audited and are not current Phase 7 gaps:

- Paper-only execution mode enforcement
- Paper portfolio open/close/snapshot accounting
- Simulated paper orders and fills
- Local SQLite persistence for paper records
- Seven configured risk gates
- Risk gate decision metadata and persistence
- Local Markdown daily report generation
- Manual paper daily runner
- Dry-run mode
- Read-only operations dashboard
- Safety defaults for real money, live orders, and human approval

## Recommended Next Actions

1. Decide whether Phase 7 can be accepted as "core functional complete" with
   documented operational gaps, or whether the gaps must be closed before
   calling Phase 7 complete.
2. If Phase 7 must be truly complete, open a Phase 7 hardening task limited to:
   replay manifest, immutable report path, failed/skipped run records, and local
   metrics rollups.
3. Keep the scope paper-only and local-only. Do not start Phase 8 and do not add
   broker integrations.
4. Before any 30-day paper run, define an operator runbook for daily invocation,
   SQLite backup, smoke validation, report retention, and gap review.

## Validation

Validation commands run for this audit:

- `.venv/bin/ruff check .`
- `PYTHONPATH=src .venv/bin/pytest`
- `PYTHONPATH=src .venv/bin/lma phase7-run-daily --db "$tmpdir/phase7-audit-smoke.sqlite" --report-dir "$tmpdir/reports" --no-require-manual-approval`

Validation results:

- Ruff passed.
- Pytest passed with 57 passed and 1 skipped.
- Offline `phase7-run-daily` smoke passed with `status=completed`, simulated
  paper order id `paper_order_385804329f1f46b799b8033d66666cd9`, risk gate
  decision id `risk_gate_c1e0721295e440538503bcf0c104a4d7`, and local report
  path `/var/folders/n0/gymfsr8n0b35p6t0yk01yr080000gn/T/tmp.LsqgTLTS42/reports/phase7_daily_report_2026-06-05.md`.

Environment note:

- Plain `.venv/bin/pytest` and `.venv/bin/lma` initially failed before test
  execution because the local editable install did not expose `src` on
  `sys.path` in this shell. The successful validation used explicit
  `PYTHONPATH=src`; no repository source code was changed.
