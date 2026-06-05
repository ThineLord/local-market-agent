# Phase 7C PR-D1 - Read-only Market Data Path

## Scope

PR-D1 adds a configurable read-only market data input path for Phase 7 daily
and sandbox workflows. The default remains `fixture`, so normal local demos and
tests stay offline and deterministic.

This is not Phase 8. It does not add broker integrations, live trading,
real-money execution, order execution, private trading endpoints, a scheduler,
a daemon, autostart, a strategy redesign, benchmark comparison, or a direct
LLM-to-order path.

## Market Source Selection

Inspect the selected source without fetching market data:

```bash
lma market-data-audit
```

Default output reports `market_source=fixture`, `data_mode=fixture`,
`network_calls_enabled=false`, and `can_create_orders=false`.

Phase 7 commands accept an explicit read-only source:

```bash
lma phase7-run-daily --market-source fixture

lma phase7-run-daily \
  --market-source polymarket \
  --market-id <polymarket-market-id>

lma phase7-sandbox-run \
  --days 30 \
  --market-source kalshi \
  --market-id <kalshi-market-ticker>

lma phase7-sandbox-run \
  --days 30 \
  --market-source yfinance \
  --market-id SPY
```

The same defaults can be supplied through configuration:

```bash
export LMA_MARKET_SOURCE=fixture
export LMA_MARKET_ID=
```

Non-fixture sources require an explicit market identifier. Phase 7 does not
guess live market identifiers.

## Data Mode Semantics

`fixture` mode uses `data/fixtures/demo_market.json` and
`data/fixtures/demo_evidence.json`. It is deterministic and offline.

`current_snapshot` mode uses an optional read-only network adapter for the
selected source:

- `polymarket`: public Gamma market metadata snapshot.
- `kalshi`: public market metadata snapshot.
- `yfinance`: latest OHLCV row normalized as a market snapshot.

Current snapshot mode is not historical. It may exercise the workflow against a
real current market snapshot, but it does not provide day-by-day historical
market states or settlement outcomes.

No historical profitability evaluation was added in PR-D1. Phase 7C PR-D2 later
adds a local JSONL historical-file mode. A meaningful historical profitability
evaluation still requires time-indexed historical market snapshots, evidence
available at each historical timestamp, realistic fills, position
closing/settlement data, and a benchmark/comparison methodology.

## Sandbox Labels

The sandbox summary now records:

- `market_source`
- `data_mode`
- `market_data.network_calls_enabled`
- `market_data.is_historical`
- `market_data.is_snapshot_only`
- `profitability_claims_meaningful`
- `sandbox_data_semantics.label`

Fixture mode is labeled `fixture replay sandbox`.

Non-fixture mode is labeled `snapshot repeated sandbox`. Repeated current
snapshots validate system integrity and workflow correctness only. They are not
a real backtest and profitability claims are not meaningful.

## Safety Notes

- Default source is `fixture`.
- Network market data is used only when explicitly selected by CLI/config.
- All market adapters used here are read-only.
- Non-fixture Phase 7 research receives no demo fixture evidence.
- No broker API, live order path, scheduler, daemon, or real-money execution is
  added.
- Paper orders still require a saved signal and approved risk decision.
- LLM output cannot create orders directly.
