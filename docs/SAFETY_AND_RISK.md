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
ResearchBrief -> Signal -> RiskDecision -> PaperOrder
```

`PaperOrder` records must reference both `signal_id` and `risk_decision_id`. The ledger refuses to create a paper order without an approved risk decision.
