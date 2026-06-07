# Kalshi Calibration Preferred Retry Result

Scope: PR-CAL-5 preferred-size calibration-only retry. This used the existing
temporary local Kalshi public-data collector and did not modify strategy logic,
acceptance gates, Phase 8, broker/live trading, scheduler behavior, evidence
approval, source terms review, bid/ask values, or acceptance/profitability
claims.

## Collection Command

```bash
PYTHONPATH=src .venv/bin/python scripts/local_only/collect_kalshi_calibration_dataset.py \
  --export-id kalshi_calibration_preferred_20260607_public_probe \
  --min-markets 60 \
  --max-markets 90 \
  --rows-per-market 12 \
  --max-candle-market-attempts 200 \
  --period-interval 60 \
  --timeout-seconds 4
```

No collector code changes were required for this retry.

Generated local outputs, not committed:

- Source export:
  `data/source_exports/kalshi/kalshi_calibration_preferred_20260607_public_probe/`
- Historical JSONL:
  `data/historical/phase7g_kalshi_calibration_kalshi_calibration_preferred_20260607_public_probe.jsonl`
- Calibration audit artifacts:
  `data/reports/calibration/phase7g_kalshi_calibration_kalshi_calibration_preferred_20260607_public_probe*`
- Strategy evaluation artifacts:
  `data/reports/strategy_eval/strategy_eval_phase7g_kalshi_calibration_kalshi_calibration_preferred_20260607_public_probe_019ad2df9d91.*`

## Follow-Up Commands

Calibration audit:

```bash
PYTHONPATH=src .venv/bin/lma audit-calibration-dataset \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_calibration_preferred_20260607_public_probe.jsonl \
  --output-dir data/reports/calibration
```

Offline strategy evaluation:

```bash
PYTHONPATH=src .venv/bin/lma strategy-eval-offline \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_calibration_preferred_20260607_public_probe.jsonl \
  --output-dir data/reports/strategy_eval
```

Calibration bucket QA:

```bash
PYTHONPATH=src .venv/bin/lma calibration-bucket-qa \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_calibration_preferred_20260607_public_probe.jsonl \
  --output-dir data/reports/calibration \
  --gap-threshold 0.15
```

## Dataset Result

| Metric | Result |
| --- | ---: |
| Markets discovered | 11,613 |
| Markets selected | 90 |
| Rows collected | 818 |
| Scored rows | 818 |
| Resolved markets | 90 |
| Settlement coverage | 100% |
| Last-price coverage | 100% |
| Bid/ask coverage | 0% |
| Evidence timestamp coverage | 0% |
| Duplicate market/timestamp rows | 0 |
| Missing outcome count | 0 |
| Missing price count | 0 |
| Audit classification | `calibration_preferred` |
| Collector target status | `preferred` |
| Evaluation classification | `calibration_only_last_price_dataset` |

The preferred calibration target was met: at least 60 markets, at least 720
rows, and 100% settlement coverage for scored rows.

Shape check result:

- `profile=calibration_only_last_price`
- `bid=null`
- `ask=null`
- `evidence=[]`
- `paper_pnl_allowed=false`
- `acceptance_candidate=false`
- `bad_shape_rows=0`

## Category Distribution

Collection-side category distribution from the local source manifest:

| Category | Markets |
| --- | ---: |
| `public_event` | 82 |
| `major_sports` | 5 |
| `weather` | 2 |
| `fed_policy` | 1 |

The retry preserved category metadata in the staged source export and market
metadata, and PR-CAL-4 bucket QA could read it from:

`data/source_exports/kalshi/kalshi_calibration_preferred_20260607_public_probe/markets.jsonl`

The Phase 7G audit still reported `category_count=0` because row-level category
fields are not lifted into historical rows by the current import path. Category
visibility improved for QA through local source-manifest enrichment, but the
dataset remains category-skewed toward public-event markets.

## Offline Evaluation Summary

The market-implied baseline, Strategy v1, and Strategy v2 candidate all
collapsed to the same last-price probability diagnostic because the dataset has
no evidence records.

| Baseline | Brier | Log loss | Forecast coverage | Scored forecasts | Paper PnL |
| --- | ---: | ---: | ---: | ---: | --- |
| `market_implied_probability_only` | 0.21307555 | 0.61282262 | 100% | 818 | `blocked` |
| `strategy_v1` | 0.21307555 | 0.61282262 | 100% | 818 | `blocked` |
| `strategy_v2_candidate` | 0.21307555 | 0.61282262 | 100% | 818 | `blocked` |

Acceptance gate status remained `not_applicable`, and Strategy v2 superiority
remained blocked.

## Bucket QA Summary

At `--gap-threshold 0.15`, the preferred retry flagged four high-gap buckets.

| Bucket | Rows | Markets | Mean forecast | Observed YES rate | Gap | Brier | Log loss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0.20-0.30` | 114 | 32 | 0.25394737 | 0.48245614 | 0.22850877 | 0.30448158 | 0.82081044 |
| `0.40-0.50` | 101 | 28 | 0.44495050 | 0.25742574 | 0.18752476 | 0.22238020 | 0.63755837 |
| `0.70-0.80` | 114 | 31 | 0.74745614 | 0.57894737 | 0.16850877 | 0.27683947 | 0.76113890 |
| `0.80-0.90` | 36 | 20 | 0.84750000 | 0.69444444 | 0.15305556 | 0.22883611 | 0.66943940 |

Each high-gap bucket reported:

- `category_missing_warning`
- `thin_liquidity_warning`
- `evidence_missing_warning`
- `bid_ask_missing_warning`

No high-gap bucket was dominated by a few markets under the PR-CAL-4 dominance
rule.

## Comparison With PR-CAL-2/3/4 Dataset

| Metric | PR-CAL-2/3/4 dataset | PR-CAL-5 retry |
| --- | ---: | ---: |
| Audit classification | `calibration_minimum` | `calibration_preferred` |
| Markets | 60 | 90 |
| Rows | 545 | 818 |
| Brier | 0.21612771 | 0.21307555 |
| Log loss | 0.61879591 | 0.61282262 |
| Settlement coverage | 100% | 100% |
| Last-price coverage | 100% | 100% |
| Evidence timestamp coverage | 0% | 0% |
| Bid/ask coverage | 0% | 0% |

High-gap comparison:

| Bucket | PR-CAL-2/3/4 rows/markets/gap | PR-CAL-5 rows/markets/gap | Assessment |
| --- | --- | --- | --- |
| `0.20-0.30` | 79 rows, 19 markets, gap 0.20329114 | 114 rows, 32 markets, gap 0.22850877 | More robust sample and larger gap |
| `0.40-0.50` | 75 rows, 19 markets, gap 0.21426666 | 101 rows, 28 markets, gap 0.18752476 | More robust sample but weaker gap |
| `0.70-0.80` | 71 rows, 21 markets, gap 0.11859155 | 114 rows, 31 markets, gap 0.16850877 | New high-gap bucket in retry |
| `0.80-0.90` | 22 rows, 13 markets, gap 0.16545455 | 36 rows, 20 markets, gap 0.15305556 | Less small-sample fragile, still near threshold |

## Concentration Notes

Overall per-market sampling remained capped by `--rows-per-market 12`.
Several markets reached 12 rows, but the high-gap bucket analysis did not flag
market concentration:

| Bucket | Top market row share | Top three row share |
| --- | ---: | ---: |
| `0.20-0.30` | 9.649123% | 26.315789% |
| `0.40-0.50` | 10.891089% | 28.712871% |
| `0.70-0.80` | 8.771930% | 26.315789% |
| `0.80-0.90` | 13.888889% | 33.333333% |

The retry reduced single-market dominance risk relative to the larger sample,
but it did not solve category skew or thin-liquidity warnings.

## Robustness Interpretation

The preferred retry makes the `0.20-0.30` and `0.40-0.50` bucket findings less
sample-fragile because both now span more than 100 rows and at least 28
markets. The `0.20-0.30` gap strengthened, while the `0.40-0.50` gap weakened
but remained above the configured threshold.

The new `0.70-0.80` bucket needs follow-up QA because it crossed the threshold
with 114 rows across 31 markets. The `0.80-0.90` bucket is no longer as fragile
as the 22-row PR-CAL-4 result, but 36 rows is still a smaller sample than the
main high-gap buckets.

The results remain inconclusive for broader market calibration because the
dataset is public-event-heavy, last-price-only, evidence-empty, bid/ask-empty,
and thin-liquidity flagged.

## Guardrails

Allowed:

- forecast calibration diagnostics
- strategy-comparison diagnostics labeled calibration-only

Blocked:

- acceptance gate pass
- acceptance-ready claim
- executable paper-PnL claim
- Strategy v2 superiority claim
- profitability claim
- live-trading readiness claim

Acceptance blockers remained:

- `evidence_timestamp_coverage_below_95_pct`
- `bid_ask_coverage_incomplete`
- `source_terms_pending_or_blocked`
- `paper_pnl_not_allowed_by_dataset`
- `validator_error.missing_required_field`

## Recommended Next Step

Use this preferred-size dataset as the new calibration QA baseline. The next
useful task is a category-balance or import-metadata visibility improvement,
not acceptance evaluation. Acceptance work should remain a separate manually
targeted evidence pilot with timestamp-safe evidence, bid/ask support where
paper PnL is claimed, and source terms review.
