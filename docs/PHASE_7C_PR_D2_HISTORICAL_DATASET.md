# Phase 7C PR-D2 - Local Historical Dataset Importer

## Scope

PR-D2 adds a local JSONL historical dataset mode for Phase 7 sandbox validation.
The default remains `fixture`, and the new mode is local-only, deterministic,
paper-only, and replayable.

This is not Phase 8. It does not add broker integrations, live trading,
real-money execution, order execution, private trading endpoints, a scheduler,
a daemon, autostart, automatic data downloads, paid dataset ingestion, strategy
redesign, benchmark comparison, or direct LLM-to-order execution.

## JSONL Format

Use `--market-source historical-file --historical-file <path>.jsonl`.

Each non-empty line must be one JSON object:

```json
{
  "date": "2026-05-01",
  "market_id": "example-market",
  "bid": 0.48,
  "ask": 0.5,
  "last_price": 0.49,
  "implied_probability": 0.49,
  "liquidity": 1500,
  "volume": 12000,
  "evidence": [
    {
      "source": "local-dataset",
      "title": "Evidence known before the close",
      "published_at": "2026-05-01T10:00:00Z",
      "summary": "Short evidence summary.",
      "relevance_score": 0.9,
      "credibility_score": 0.9,
      "metadata": {"probability_hint": 0.68}
    }
  ],
  "settlement_outcome": "yes"
}
```

Required fields:

- `date` or `timestamp`
- `market_id`
- `bid`
- `ask`
- `last_price`

Optional fields:

- `implied_probability`; defaults to the bid/ask midpoint when omitted.
- `liquidity`
- `volume`
- `title`
- `platform`
- `evidence`
- `settlement_outcome`, `outcome`, or `settlement`; supported values are `yes`
  and `no`.

## Validation

The importer:

- Sorts records explicitly by timestamp and market id.
- Rejects duplicate `date + market_id` rows.
- Rejects missing bid/ask/last price.
- Rejects bid greater than ask.
- Rejects probabilities outside `[0, 1]`.
- Rejects future evidence leakage when `published_at` is after the market row
  timestamp.
- Warns when evidence is absent.
- Warns when settlement/outcome fields are absent.

If a file contains multiple market ids, pass `--market-id`.

## Sandbox Semantics

Fixture mode is still labeled `fixture replay sandbox`.

Non-fixture current-source mode remains `snapshot repeated sandbox`.

Historical JSONL mode is labeled either:

- `historical local dataset with settlement`
- `historical local dataset without settlement`

One simulated day uses the matching historical row for that date. Historical rows
are not blindly reused across the range. If evidence is present on a row, only
that row's time-appropriate evidence is passed to research. If evidence is
missing, research runs with no evidence and the summary reports missing/limited
historical evidence.

When a historical row includes `settlement_outcome`, open local paper positions
for that market are closed by the paper ledger at deterministic settlement
prices. This is paper-only local accounting, not order execution.

## Backtest Boundary

This mode is closer to a backtest than fixture replay or repeated current
snapshots, but it is still limited. A profitability result is meaningful only
inside the supplied local dataset and paper-fill assumptions.

It does not qualify as a production-grade real backtest unless the dataset has:

- Time-indexed market prices for every simulated day.
- Evidence that was available at or before each historical timestamp.
- Settlement/outcome data for final resolution.
- Explicit fill, fee, slippage, and position-closing assumptions.
- Benchmark methodology if comparison claims are needed.

Without settlement/outcome fields, final profitability claims remain not
meaningful.

## Example

```bash
lma market-data-audit \
  --market-source historical-file \
  --historical-file data/fixtures/phase7_historical_5d.jsonl

lma phase7-sandbox-run \
  --market-source historical-file \
  --historical-file data/fixtures/phase7_historical_5d.jsonl \
  --days 5 \
  --no-require-manual-approval
```

## Safety Notes

- Default source remains `fixture`.
- Historical datasets are local files only.
- No network call is made for `historical-file`.
- No broker API, private endpoint, live order, real-money execution, scheduler,
  daemon, autostart, leverage, withdrawal, or direct LLM-to-order path is added.
- Paper orders still require a saved signal and approved risk decision.
