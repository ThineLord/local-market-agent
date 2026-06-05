# Kalshi Sprint 1 Collection Result

Date: 2026-06-05

Scope: DATA-SCRIPT-1 temporary local public-data collection helper. This was
not a production integration, downloader service, scheduler, daemon, broker
path, live-trading path, account path, portfolio path, fill path, or Phase 8
work.

## Command Used

```bash
PYTHONPATH=src .venv/bin/python scripts/local_only/collect_kalshi_sprint1.py \
  --export-id kalshi_sprint1_20260605_public_probe \
  --max-markets 10 \
  --rows-per-market 10 \
  --period-interval 1
```

Dry-run probe before writing:

```bash
PYTHONPATH=src .venv/bin/python scripts/local_only/collect_kalshi_sprint1.py \
  --export-id kalshi_sprint1_20260605_public_probe \
  --max-markets 10 \
  --rows-per-market 10 \
  --period-interval 1 \
  --dry-run
```

The script keeps `--period-interval` defaulting to `60`, but this run used
`1` minute because the public markets that returned usable bid/ask/price
candles during the probe were short-window markets.

## Endpoint Families Used

- `GET /markets` with `status=settled` and `mve_filter=exclude`.
- `GET /historical/markets` with `mve_filter=exclude`.
- `GET /markets/candlesticks` for selected live/recent settled markets.
- `GET /historical/markets/{ticker}/candlesticks` support exists in the
  script, but this run selected only live/recent settled markets.

Only unauthenticated public/read-only market and candlestick endpoints were
used. No account, portfolio, order, fill, private, authenticated, cookie, or
browser/session endpoints were used.

Official endpoint references checked during implementation:

- https://docs.kalshi.com/api-reference/market/get-markets
- https://docs.kalshi.com/api-reference/market/batch-get-market-candlesticks
- https://docs.kalshi.com/api-reference/market/get-market-candlesticks
- https://docs.kalshi.com/api-reference/historical/get-historical-markets
- https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks
- https://docs.kalshi.com/getting_started/historical_data

## Collection Counts

| Metric | Value |
| --- | ---: |
| Candidate markets discovered | 9,407 |
| Markets selected | 10 |
| Candles collected | 100 |
| Evidence rows collected | 0 |
| Distinct source families in selected rows | 1 |
| Distinct series tickers selected | 3 |
| Selected market statuses | finalized |
| Selected market results | 5 yes, 5 no |

Export directory:

```text
data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/
```

Files written:

```text
source_manifest.json
markets.jsonl
candlesticks.jsonl
evidence.jsonl
```

The real export directory is ignored by Git and should remain local unless a
future explicit review decides it is safe to share.

## Fields Available

Market rows included these fields:

```text
can_close_early, close_time, event_ticker, expected_expiration_time,
latest_expiration_time, liquidity_dollars, metadata, open_time, result,
rules_primary, rules_secondary, series_ticker, settlement_ts,
settlement_value_dollars, status, subtitle, ticker, title, volume_fp
```

Candlestick rows included these fields:

```text
end_period_ts, market_ticker, metadata, open_interest_fp, period_interval,
price, volume_fp, yes_ask, yes_bid
```

The selected candles had `yes_bid.close_dollars`, `yes_ask.close_dollars`, and
`price.close_dollars`. Candle high/low/open values were preserved only as raw
export fields and were not used as point-in-time quotes by the importer.

Kalshi did not return `series_ticker` in the selected market rows, so the
script derived it from `event_ticker` and marked that in row metadata.

## Import And Validation

Acceptance import command:

```bash
PYTHONPATH=src .venv/bin/lma import-kalshi-export \
  --export-dir data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe \
  --profile acceptance_candidate \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --source-audit-dir docs/reports \
  --validate
```

Result: failed before acceptance output, as expected.

Blockers:

- `terms_review` is `pending_review`.
- `evidence.jsonl` is intentionally empty.
- Evidence timestamp coverage is 0%.

Downgrade import command:

```bash
PYTHONPATH=src .venv/bin/lma import-kalshi-export \
  --export-dir data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe \
  --profile acceptance_candidate \
  --allow-downgrade \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --source-audit-dir docs/reports \
  --validate
```

Result:

- Output profile: `calibration_only_last_price`.
- Downgraded: `true`.
- Rows: 100.
- Markets: 10.
- Validation valid: `false`.
- Validation errors: 100 `missing_required_field` errors for `evidence`.
- Validation warnings: 400 warnings across `source_terms_pending`,
  `missing_evidence`, `thin_liquidity`, and `last_price_only`.
- Settlement coverage: 100%.
- Evidence timestamp coverage: 0%.
- Paper PnL allowed: `false`.
- Acceptance candidate: `false`.

## Classification

The dataset is not an acceptance candidate.

Although the explicit downgrade path produced a `calibration_only_last_price`
output artifact, validation is still invalid because evidence rows are absent.
Treat this Sprint 1 export as not usable yet except as a local field-availability
diagnostic.

## Blockers

- Human terms review remains required before any acceptance labeling.
- Public, timestamped evidence curation remains required.
- The first selected public markets are concentrated in a few event families;
  a future acceptance attempt should enforce category and event-family
  diversity.
- Some useful public candle rows required 1-minute intervals; the 60-minute
  default may be sparse for short-window markets.
- Thin-liquidity warnings appeared in validation.

## Safety Result

No live trading, order placement, account access, portfolio access, fill access,
private/authenticated API use, API key use, cookies, browser/session data,
geoblock bypass, scheduler, daemon, autostart, broker code, direct
LLM-to-order path, Phase 8 work, or profitability claim was added.
