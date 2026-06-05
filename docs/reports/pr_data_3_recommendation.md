# PR-DATA-3 Recommendation

Date: 2026-06-05

Scope: proposed future PR only. Do not implement this in DATA-RESEARCH-1.

## Decision

PR-DATA-3 is justified, but only as a **local Kalshi public-export adapter**.

It should not be a downloader. It should not make network requests. It should
read manually staged local exports that a human has already collected and
terms-reviewed, then convert those files into the Phase 7G JSONL schema and run
the PR-DATA-1 validator.

## Why Kalshi First

Kalshi is the best first acceptance-candidate source because the official docs
show:

- settled/historical markets through live and historical market tiers;
- candlesticks with `yes_bid`, `yes_ask`, `price`, `volume_fp`, and
  `open_interest_fp`;
- market settlement lifecycle and `result`/`settlement_ts` style metadata;
- trade history that can support last-price and volume audit.

This gives the project a realistic path to Phase 7G bid/ask rows without
requiring full historical orderbook snapshots.

## PR-DATA-3 Scope

Name:

- `PR-DATA-3 Kalshi Local Public Export Adapter`

Goal:

- Convert manually staged local Kalshi public export files into
  `phase7g.historical_dataset.v1` JSONL.
- Run the PR-DATA-1 validator.
- Produce audit artifacts proving whether the result is
  `acceptance_candidate` or `calibration_only_last_price`.

## Exact Inputs

The adapter should accept a local export directory, for example:

```text
data/source_exports/kalshi/{export_id}/
  source_manifest.json
  markets.jsonl
  candlesticks.jsonl
  trades.jsonl
  evidence.jsonl
```

Required input files:

- `source_manifest.json`
- `markets.jsonl`
- `candlesticks.jsonl`
- `evidence.jsonl`

Optional input files:

- `trades.jsonl`
- `market_rules.jsonl`
- `settlement_overrides.jsonl`

### `source_manifest.json`

Required fields:

- `export_id`
- `dataset_id`
- `source_name`
- `source_type`
- `source_urls`
- `retrieved_at`
- `exported_at`
- `terms_review`
- `terms_reviewed_by`
- `terms_reviewed_at`
- `private_or_authenticated_source`
- `network_used_by_adapter`
- `raw_file_sha256`
- `notes`

Rules:

- `network_used_by_adapter` must be `false`.
- `private_or_authenticated_source` must be `false` for acceptance.
- `terms_review` must equal `reviewed_public_research_local_only` for
  acceptance.
- If terms review is pending or blocked, output must be
  `calibration_only_last_price` or fail before writing acceptance rows.

### `markets.jsonl`

Each row should be a raw or lightly normalized Kalshi market record containing:

- `ticker`
- `series_ticker` when available
- `event_ticker`
- `title`
- `subtitle`
- `status`
- `result`
- `open_time`
- `close_time`
- `expected_expiration_time`
- `latest_expiration_time`
- `settlement_ts`
- `settlement_value_dollars`
- `rules_primary`
- `rules_secondary`
- `can_close_early`
- `volume_fp`
- `liquidity_dollars`

### `candlesticks.jsonl`

Each row should contain one market ticker plus one candle:

- `market_ticker`
- `period_interval`
- `end_period_ts`
- `yes_bid.open_dollars`
- `yes_bid.low_dollars`
- `yes_bid.high_dollars`
- `yes_bid.close_dollars`
- `yes_ask.open_dollars`
- `yes_ask.low_dollars`
- `yes_ask.high_dollars`
- `yes_ask.close_dollars`
- `price.open_dollars`
- `price.low_dollars`
- `price.high_dollars`
- `price.close_dollars`
- `price.mean_dollars`
- `price.previous_dollars`
- `volume_fp`
- `open_interest_fp`

Acceptance rule:

- use `end_period_ts` as the row timestamp;
- use `yes_bid.close_dollars` as `bid`;
- use `yes_ask.close_dollars` as `ask`;
- use `price.close_dollars` as `last_price` unless a trade at or before the
  same timestamp is explicitly selected;
- compute `implied_probability` from the bid/ask midpoint when both bid and ask
  are present.

Do not use candle high/low values as point-in-time executable quotes.

### `trades.jsonl`

Optional trade rows should contain:

- `trade_id`
- `ticker`
- `created_time`
- `yes_price_dollars`
- `no_price_dollars`
- `count_fp`
- `is_block_trade`

Trades may support volume and last-price audit. They must not be used as
bid/ask.

### `evidence.jsonl`

Each evidence row should contain:

- `market_ticker`
- `evidence_id`
- `source`
- `title`
- `url`
- `published_at`
- `retrieved_at`
- `summary`
- `relevance_score`
- `credibility_score`
- `metadata`

Evidence must be published at or before each forecast row timestamp. Settlement
articles published after the forecast row must not be attached as
forecast-time evidence.

## Exact Outputs

The adapter should write:

```text
data/historical/{dataset_id}.jsonl
data/historical/{dataset_id}.manifest.json
data/reports/historical_dataset/{dataset_id}.validation.json
data/reports/historical_dataset/{dataset_id}_audit.md
docs/reports/{dataset_id}_source_audit.md
```

The manifest should include:

- dataset id and label;
- input file paths and checksums;
- row count;
- market count;
- selected profile;
- source names;
- source terms review;
- whether bid/ask came from candle close fields;
- validation artifact paths;
- safety flags.

## Safety Constraints

PR-DATA-3 must remain:

- local-only;
- file-only;
- source-export conversion only;
- validation-only after conversion;
- no network requests;
- no API credentials;
- no cookies;
- no browser data;
- no private account data;
- no broker API;
- no live trading;
- no order placement or cancellation;
- no portfolio/fill/user endpoints;
- no scheduler, daemon, or autostart;
- no Phase 8;
- no strategy changes;
- no acceptance-gate changes;
- no profitability claims.

The adapter must not invent missing fields:

- do not infer bid/ask from last price;
- do not infer bid/ask from a fixed spread;
- do not synthesize settlement outcomes;
- do not fabricate evidence timestamps;
- do not fill terms review automatically.

## Validation Requirements

Required validation commands:

```bash
PYTHONPATH=src .venv/bin/ruff check .
PYTHONPATH=src .venv/bin/pytest
PYTHONPATH=src .venv/bin/lma validate-historical-dataset \
  --historical-file data/historical/{dataset_id}.jsonl \
  --output-dir data/reports/historical_dataset
```

PR-DATA-3 tests should cover:

- valid local Kalshi acceptance export;
- missing candle bid or ask downgrades or fails acceptance;
- bid greater than ask fails validation;
- settlement missing fails acceptance;
- terms review pending blocks acceptance;
- private/authenticated source blocks acceptance;
- future evidence leakage fails;
- duplicate market/timestamp rows fail;
- calibration-only fallback forces no paper PnL;
- source audit report is written;
- no downloader/network/source API caller added;
- no broker/live/order API added.

## Acceptance Gates Before Strategy Evaluation

Before any Strategy v2 evaluation run, the built dataset must pass:

- at least 25 resolved binary markets;
- at least 250 point-in-time rows;
- at least 50 candidate forecast rows;
- 100% settlement coverage for scored markets;
- at least 95% evidence timestamp coverage;
- zero duplicate market/timestamp rows;
- zero missing bid/ask rows for acceptance profile;
- zero future evidence leakage;
- `private_or_authenticated_source=false`;
- `terms_review=reviewed_public_research_local_only`;
- no secret-like fields.

If any of these fail, the dataset must not be used for Strategy v2 acceptance
claims.

## Work Breakdown

Recommended PR-DATA-3 steps:

1. Add a local Kalshi export schema reader.
2. Map market, candle, settlement, and evidence rows into Phase 7G JSONL.
3. Add a source audit Markdown report.
4. Add deterministic small fixtures under `data/fixtures/kalshi_export/`.
5. Add validator-backed tests.
6. Update implementation log with validation results.

## Out Of Scope

Do not include:

- live Kalshi API calls;
- historical endpoint downloader;
- websocket capture;
- Polymarket adapter;
- ImpliedData adapter;
- third-party vendor adapter;
- strategy evaluation run on an acceptance-size dataset;
- live/paper order creation beyond existing tests;
- Phase 8.

## Proceed/Stop Criteria

Proceed with PR-DATA-3 if:

- a human agrees that terms review can be represented in the local source
  manifest;
- a small manually staged Kalshi export sample contains populated
  `yes_bid.close_dollars` and `yes_ask.close_dollars`;
- the adapter remains local-only and file-only.

Stop or defer PR-DATA-3 if:

- Kalshi terms review blocks local research storage;
- candle bid/ask fields are unavailable or too sparse for settled markets;
- evidence curation cannot meet timestamp coverage;
- the implementation would require API credentials or network automation.
