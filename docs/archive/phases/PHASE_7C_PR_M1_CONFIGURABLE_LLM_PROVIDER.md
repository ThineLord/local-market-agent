# Phase 7C PR-M1 - Configurable LLM Provider Path

## Scope

PR-M1 routes Phase 7 research brief generation through the existing LLM provider
configuration path. The default remains `mock`, so normal local tests and demos
stay offline and deterministic.

This is not Phase 8. It does not add broker integrations, live trading,
real-money execution, private trading endpoints, a scheduler, a daemon,
autostart, a historical data provider, a strategy redesign, or benchmark
comparison.

## Provider Selection

Inspect the selected provider without making a provider call:

```bash
lma llm-provider-audit
```

Default output reports `provider=mock`, `network_calls_enabled=false`, and
`is_mock=true`.

To enable a local or OpenAI-compatible research provider:

```bash
export LMA_LLM_PROVIDER=openai-compatible
export LMA_OPENAI_COMPATIBLE_BASE_URL=http://localhost:1234/v1
export LMA_OPENAI_COMPATIBLE_MODEL=local-model
export LMA_OPENAI_COMPATIBLE_API_KEY=optional-local-key
```

The Phase 7 commands also accept non-secret overrides:

```bash
lma phase7-run-daily \
  --llm-provider openai-compatible \
  --llm-model local-model \
  --llm-base-url http://localhost:1234/v1

lma phase7-sandbox-run \
  --days 30 \
  --llm-provider openai-compatible \
  --llm-model local-model \
  --llm-base-url http://localhost:1234/v1
```

API keys are intentionally not accepted as command-line plaintext.

## Execution Boundary

```text
Selected read-only market data
    |
Configured research provider
    |
ResearchBriefGenerator
    |
PredictionMarketEdgeStrategy
    |
RiskEngine
    |
RiskGateEvaluator
    |
PaperLedger
```

The provider only drafts structured research JSON. Signals, risk decisions, risk
gate decisions, paper order intents, paper orders, fills, and portfolio snapshots
remain deterministic application code and keep their paper-only validation.

## Safety Notes

- Default provider is `mock`.
- OpenAI-compatible research calls happen only when explicitly selected.
- Provider audit output never prints API key values.
- LLM output cannot create paper orders directly.
- Paper orders still require a saved signal and approved risk decision.
- Phase 7 remains paper-only and local-first.
- Phase 7C PR-D1 keeps the default market source as fixture; optional
  non-fixture sources are read-only snapshots only.
