# Kalshi Calibration Dataset Collection Result

Scope: PR-CAL-2 temporary local public-data collection helper. This is a
calibration-only dataset result, not an acceptance-candidate dataset result.

## Collection Summary

| Field | Result |
| --- | --- |
| Export id | `kalshi_calibration_20260607_public_probe` |
| Export path | `data/source_exports/kalshi/kalshi_calibration_20260607_public_probe/` |
| Historical output | `data/historical/phase7g_kalshi_calibration_kalshi_calibration_20260607_public_probe.jsonl` |
| Audit JSON | `data/reports/calibration/phase7g_kalshi_calibration_kalshi_calibration_20260607_public_probe.calibration_audit.json` |
| Markets discovered | 11,621 |
| Markets selected | 60 |
| Rows collected | 545 |
| Scored rows | 545 |
| Calibration audit classification | `calibration_minimum` |
| Target status | Minimum met; preferred and stretch missed |

The successful collection command was:

```bash
PYTHONPATH=src .venv/bin/python scripts/local_only/collect_kalshi_calibration_dataset.py \
  --export-id kalshi_calibration_20260607_public_probe \
  --min-markets 25 \
  --max-markets 60 \
  --rows-per-market 12 \
  --max-candle-market-attempts 90 \
  --period-interval 60 \
  --timeout-seconds 4
```

The calibration audit was also run through the CLI:

```bash
PYTHONPATH=src .venv/bin/lma audit-calibration-dataset \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_calibration_20260607_public_probe.jsonl \
  --output-dir data/reports/calibration
```

## Dataset Shape

| Metric | Result |
| --- | --- |
| `row_count` | 545 |
| `market_count` | 60 |
| `resolved_market_count` | 60 |
| `scored_row_count` | 545 |
| `settlement_coverage_pct` | 100% |
| `last_price_coverage_pct` | 100% |
| `bid_ask_coverage_pct` | 0% |
| `evidence_timestamp_coverage_pct` | 0% |
| `duplicate_market_timestamp_rows` | 0 |
| `missing_outcome_count` | 0 |
| `missing_price_count` | 0 |

The Phase 7G historical rows are explicitly calibration-only:

- `profile=calibration_only_last_price`
- `bid=null`
- `ask=null`
- `paper_pnl_allowed=false`
- `acceptance_candidate=false`
- `last_price` populated from Kalshi candlestick close price
- `settlement` populated for scored rows
- `evidence=[]`

Bid/ask values were intentionally unavailable in the calibration output. The
collector does not invent bid/ask from last price or candle high/low fields.
Evidence was intentionally not collected for this PR, so timestamp-safe evidence
coverage is expected to remain 0%.

## Distribution

Collector category distribution from `source_manifest.json`:

| Category | Markets |
| --- | ---: |
| `major_sports` | 5 |
| `public_event` | 53 |
| `weather` | 2 |

Audit platform and source distribution:

| Distribution | Rows |
| --- | ---: |
| `platform=kalshi` | 545 |
| `source=kalshi_public_market_and_candlestick_api` | 545 |

The calibration audit reports `category_count=0` because the current Phase 7G
Kalshi import path does not lift staged collector category metadata into
row-level `category`, `market_category`, or `event_category` fields. The staged
source manifest still preserves the collection-side category counts above.

## Target Result

| Target | Requirement | Result |
| --- | --- | --- |
| Minimum | 25 markets, 250 rows, 100% settlement coverage | Met |
| Preferred | 60 markets, 720 rows, 100% settlement coverage | Missed: 545 rows |
| Stretch | 150 markets, 2,000+ rows, 100% settlement coverage | Missed |

This dataset is large enough for minimum calibration diagnostics. It is not
large enough for the preferred or stretch calibration tiers.

## Claim Guardrails

Allowed by audit:

- `forecast_calibration_diagnostics=true`
- `strategy_comparison_diagnostics=true`
- `paper_simulation_diagnostics=true`

Blocked by audit:

- `acceptance_gate_pass=false`
- `strategy_v2_superiority=false`
- `profitability_claim=false`
- `acceptance_gate_evaluation_possible=false`

Acceptance blockers reported by the audit:

- `evidence_timestamp_coverage_below_95_pct`
- `bid_ask_coverage_incomplete`
- `source_terms_pending_or_blocked`
- `paper_pnl_not_allowed_by_dataset`
- `validator_error.missing_required_field`

Calibration warnings reported by the audit:

- `timestamp_safe_evidence_incomplete_acceptance_blocker_only`
- `bid_ask_incomplete_paper_pnl_blocked`
- `category_count_below_minimum_target`
- `source_terms_not_fully_reviewed_for_acceptance`
- `validator_warning.last_price_only`
- `validator_warning.missing_evidence`
- `validator_warning.source_terms_pending`
- `validator_warning.thin_liquidity`

## Failure Notes And Retry

An earlier default public-endpoint run was too slow in the current network
conditions, so the successful run used `--timeout-seconds 4` and
`--max-candle-market-attempts 90`. The preferred tier was missed because only
545 usable settled last-price rows were available across the selected 60 markets
under that run.

Retry command for a larger calibration-only attempt:

```bash
PYTHONPATH=src .venv/bin/python scripts/local_only/collect_kalshi_calibration_dataset.py \
  --export-id kalshi_calibration_20260607_retry \
  --min-markets 25 \
  --max-markets 60 \
  --rows-per-market 12 \
  --max-candle-market-attempts 150 \
  --period-interval 60 \
  --timeout-seconds 4
```

The retry still must not collect evidence, mutate terms review, invent bid/ask,
or make acceptance, Strategy v2 superiority, or profitability claims.

## Safety Result

PR-CAL-2 used public/read-only Kalshi market and candlestick endpoints and wrote
local files only. It added no private/authenticated endpoint use, API keys,
cookies, browser sessions, trading endpoint, account endpoint, broker path,
live-order path, scheduler, daemon, autostart, Phase 8 work, strategy logic
change, acceptance-gate change, automatic evidence approval, source terms
approval, acceptance claim, Strategy v2 superiority claim, or profitability
claim.
