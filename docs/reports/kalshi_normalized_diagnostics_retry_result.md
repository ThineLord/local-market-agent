# Kalshi Normalized Diagnostics Retry Result

Scope: PR-CAL-14 bounded diagnostics-first normalized calibration-only retry.
This was a small public/read-only Kalshi last-price collection to validate
diagnostics completeness. It was not an acceptance evaluation and does not make
paper-PnL, profitability, Strategy v2 superiority, acceptance, or live-readiness
claims.

## Command

```bash
PYTHONPATH=src .venv/bin/python scripts/local_only/collect_kalshi_normalized_calibration.py \
  --export-id kalshi_normalized_diagnostics_retry_20260608_public_probe \
  --target-markets 50 \
  --rows-per-market 12 \
  --quota sports_tennis=10 \
  --quota sports_major=10 \
  --quota mention_market=10 \
  --quota weather=10 \
  --quota fed_policy_macro=5 \
  --quota economics_other=5 \
  --quota public_event_generic=0 \
  --quota unknown=0 \
  --max-candle-market-attempts 300 \
  --period-interval 60 \
  --timeout-seconds 4
```

Generated local outputs, not committed:

- `data/source_exports/kalshi/kalshi_normalized_diagnostics_retry_20260608_public_probe/`
- `data/historical/phase7g_kalshi_calibration_kalshi_normalized_diagnostics_retry_20260608_public_probe.jsonl`
- generated JSON/Markdown artifacts under `data/reports/calibration/`

## Required Export Files

All required files were written:

| File | Rows/size |
| --- | ---: |
| `source_manifest.json` | present |
| `markets.jsonl` | 30 rows |
| `candlesticks.jsonl` | 304 rows |
| `collector_diagnostics.json` | present |
| `unselected_candidates.jsonl` | 159 rows |
| `unselected_candidates_summary.md` | present |
| `evidence.jsonl` | 0 bytes |

## Retry Result

| Metric | Result |
| --- | ---: |
| Discovered markets | 12,000 |
| Post-filter markets | 11,848 |
| Target markets | 50 |
| Selected markets | 30 |
| Rows imported | 304 |
| Candle attempts | 300 |
| Candle successes | 30 |
| Candle failures | 270 |
| Target status | `minimum_size_availability_limited` |
| Audit classification | `calibration_minimum` |

Selected normalized categories:

| Category | Markets | Rows |
| --- | ---: | ---: |
| `sports_tennis` | 10 | 93 |
| `sports_major` | 10 | 114 |
| `mention_market` | 10 | 97 |
| `weather` | 0 | 0 |
| `fed_policy_macro` | 0 | 0 |
| `economics_other` | 0 | 0 |

Quota shortfalls were `weather=10`, `fed_policy_macro=5`, and
`economics_other=5`. No missing quota was backfilled from unrelated categories.

## Diagnostics Completeness

Diagnostics completeness succeeded for this bounded retry.

- Unselected candidates were persisted with the PR-CAL-13 cap of 25 examples per
  retained normalized category.
- Per-category candle attempts, successes, failures, failure reasons, selected
  market counts, and selected row counts were present.
- Weather shortfall is explainable from per-category candle failure data, not
  only aggregate failures.
- Fed/macro shortfall is explainable as clear absence from retained discovery
  diagnostics: `fed_policy_macro` pre-filter and post-filter counts were zero,
  and retained unselected candidates did not surface deterministic
  Fed/rate/CPI/FOMC examples.
- Unselected diagnostic candidates were not imported as historical rows.

## Unselected Candidate Summary

Retained unselected examples:

| Category | Retained examples |
| --- | ---: |
| `crypto` | 25 |
| `mention_market` | 25 |
| `politics_government` | 9 |
| `sports_major` | 25 |
| `sports_tennis` | 25 |
| `unknown` | 25 |
| `weather` | 25 |

Available unselected counts from the manifest were much larger for several
categories, including `weather=360`, `unknown=504`, `sports_major=7,965`,
`sports_tennis=230`, and `crypto=2,638`. The retained examples are diagnostics
only and are not historical rows.

## Per-Category Candle Diagnostics

| Category | Attempts | Successes | Failures | Failure reasons |
| --- | ---: | ---: | ---: | --- |
| `weather` | 268 | 0 | 268 | `insufficient_pre_settlement_last_price_candles=268` |
| `sports_tennis` | 10 | 10 | 0 | none |
| `sports_major` | 11 | 10 | 1 | `insufficient_pre_settlement_last_price_candles=1` |
| `mention_market` | 11 | 10 | 1 | `insufficient_pre_settlement_last_price_candles=1` |

## Weather Diagnosis

Weather had 360 pre-filter and 360 post-filter normalized candidates, but 0
selected markets. Per-category diagnostics showed 268 weather candle attempts,
0 successes, and 268 insufficient pre-settlement last-price candle failures.

Diagnosis: `weather_candle_sparsity_supported_by_per_category_diagnostics`.
This supports candle sparsity for the bounded retry. It is not proof of a true
weather calibration category effect.

## Fed/Macro Diagnosis

`fed_policy_macro` had 0 pre-filter candidates, 0 post-filter candidates, and 0
selected markets against a quota of 5. The retained unselected diagnostics
included `unknown` examples but did not surface deterministic Fed/rate/CPI/FOMC
examples.

Diagnosis: `fed_policy_candidates_absent_in_retained_diagnostics`. This supports
clear absence in the bounded discovery diagnostics, not a calibration
category-effect claim. `economics_other` also had 0 pre-filter/post-filter
candidates in this run.

## Calibration Metrics

The imported rows preserved calibration-only shape:

- `profile=calibration_only_last_price`: 304 / 304
- `bid=null`: 304 / 304
- `ask=null`: 304 / 304
- `evidence=[]`: 304 / 304
- `paper_pnl_allowed=false`: 304 / 304
- `acceptance_candidate=false`: 304 / 304
- unselected candidate overlap with imported market IDs: 0

Overall calibration metrics:

| Metric | Result |
| --- | ---: |
| Brier score | 0.24346743 |
| Log loss | 0.68868068 |
| Mean forecast | 0.52384868 |
| Observed YES rate | 0.49342105 |
| Absolute calibration gap | 0.03042763 |

High-gap buckets at threshold `0.15` were `0.30-0.40`, `0.50-0.60`,
`0.80-0.90`, and `0.90-1.00`. These are calibration QA diagnostics only and do
not support acceptance, paper-PnL, profitability, Strategy v2 superiority, or
live-readiness claims.

## Follow-Up Commands

```bash
PYTHONPATH=src .venv/bin/lma audit-calibration-dataset \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_normalized_diagnostics_retry_20260608_public_probe.jsonl \
  --output-dir data/reports/calibration

PYTHONPATH=src .venv/bin/lma calibration-bucket-qa \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_normalized_diagnostics_retry_20260608_public_probe.jsonl \
  --output-dir data/reports/calibration \
  --gap-threshold 0.15

PYTHONPATH=src .venv/bin/lma category-calibration-analysis \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_normalized_diagnostics_retry_20260608_public_probe.jsonl \
  --output-dir data/reports/calibration \
  --docs-report-path data/reports/calibration/kalshi_normalized_diagnostics_retry_20260608_public_probe_category_calibration_analysis.md

PYTHONPATH=src .venv/bin/lma normalize-category-export \
  --source-export-dir data/source_exports/kalshi/kalshi_normalized_diagnostics_retry_20260608_public_probe \
  --output-dir data/reports/calibration \
  --docs-report-path data/reports/calibration/kalshi_normalized_diagnostics_retry_20260608_public_probe_category_normalization.md

PYTHONPATH=src .venv/bin/lma normalized-availability-audit \
  --source-export-dir data/source_exports/kalshi/kalshi_normalized_diagnostics_retry_20260608_public_probe \
  --output-dir data/reports/calibration \
  --docs-report-path data/reports/calibration/kalshi_normalized_diagnostics_retry_20260608_public_probe_normalized_availability_audit.md
```

## Safety

This PR used only the existing public/read-only Kalshi market and candlestick
endpoints. It did not collect or approve evidence, invent bid/ask, modify
strategy logic, modify acceptance gates, start Phase 8, add broker/live trading,
add scheduler behavior, or make paper-PnL, profitability, acceptance, Strategy
v2 superiority, or live-readiness claims.
