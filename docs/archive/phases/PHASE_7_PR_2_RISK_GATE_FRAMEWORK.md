# Phase 7 PR-2 - Risk Gate Framework

## Scope

PR-2 adds a configurable paper-only risk gate evaluator for continuous paper
trading workflows. It evaluates candidate paper order intents before they reach
the paper portfolio engine.

Included:

- `RiskGateConfig` for Phase 7 gate thresholds
- `PaperOrderIntent` for candidate paper order metadata
- `RiskGateCheck` and `RiskGateDecision` audit models
- `RiskGateEvaluator` for structured paper gate decisions
- Local SQLite persistence and JSONL export for risk gate decisions
- Unit tests for every Phase 7 PR-2 gate

Out of scope:

- Broker APIs
- Live trading code
- Scheduler or continuous runner
- Dashboard changes
- Report generator changes
- Paper ledger rewrite
- Phase 8 broker integration

## Gate Decisions

The evaluator returns one of:

- `APPROVED`
- `REJECTED`
- `PENDING_MANUAL_APPROVAL`
- `HALTED`

`HALTED` is reserved for circuit breakers that should pause new paper positions,
such as drawdown breach or consecutive loss cooldown. `PENDING_MANUAL_APPROVAL`
is returned only after all other configured gates pass and manual approval mode
is enabled.

## Inputs

```text
PaperOrderIntent
PortfolioSnapshot
current Position records
recent PaperFill records
market data timestamp
optional Signal
```

The evaluator does not create orders, fills, or positions. It only returns and
optionally persists the gate decision for auditability.

## Gates

- Market data freshness
- Max daily new positions
- Max position size percentage
- Max total portfolio exposure
- Daily drawdown circuit breaker
- Consecutive loss circuit breaker and cooldown
- Manual approval mode

## Persistence

Risk gate decisions are stored locally in the `risk_gate_decisions` SQLite table
as JSON payloads. Each decision includes reasons, per-gate checks, config
snapshot, and evaluation metadata.

## Safety Invariants

- `PaperOrderIntent` and `RiskGateDecision` reject live execution mode.
- The evaluator only approves paper-mode candidate intents.
- No broker adapter, credential, private trading endpoint, withdrawal path,
  leverage path, scheduler, dashboard action, report generator, or direct
  LLM-to-order path is introduced.
