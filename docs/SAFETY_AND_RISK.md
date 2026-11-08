# Safety and Risk

The repository is designed to make unsafe behavior hard to add accidentally.

## Defaults

- `REAL_MONEY_ENABLED=false`
- `ALLOW_LIVE_ORDERS=false`
- `HUMAN_APPROVAL_REQUIRED=true`

## Blocked Behaviors

- Live order execution.
- Private trading endpoints.
- Exchange withdrawals.
- API-key trading workflows.
- VPN or geoblock bypass.
- Leverage, derivatives, and shorting.
- Direct LLM-to-order execution.

## Required Chain

```text
ResearchBrief -> Signal -> RiskDecision -> Prepared intent
-> Explicit approval -> Atomic execution recheck -> PaperOrder
```

`PaperOrder` records must reference both `signal_id` and `risk_decision_id`. The ledger refuses to create a paper order without an approved risk decision.

Ordinary opens use `PaperExecutionService` with content-bound approval; direct ledger opens are limited to explicit fixture-only tests. See [approval workflow](users/PAPER_WORKFLOW.md) for expiry, replay, simulation labels and local identity limitations.

The evidence-packet workflow additionally requires a content-bound source review before preparation. Daily and legacy brief workflows do not require an independent `PacketReview`; they still require hard preflight and per-intent order approval.
