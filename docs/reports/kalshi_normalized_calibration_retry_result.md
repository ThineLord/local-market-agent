# Kalshi Normalized-Category Calibration Retry Result

Scope: PR-CAL-11 temporary local-only normalized-category Kalshi calibration
collection. This was calibration-only last-price data collection, not
acceptance evaluation. No evidence was collected or approved, no bid/ask values
were invented, and no strategy, acceptance-gate, Phase 8, broker/live-trading,
scheduler, paper-PnL, profitability, Strategy v2 superiority, acceptance, or
live-readiness claims are made.

## Collection Command

```bash
PYTHONPATH=src .venv/bin/python scripts/local_only/collect_kalshi_normalized_calibration.py \
  --export-id kalshi_normalized_calibration_20260608_public_probe \
  --target-markets 100 \
  --rows-per-market 12 \
  --quota sports_tennis=30 \
  --quota sports_major=20 \
  --quota mention_market=20 \
  --quota weather=10 \
  --quota fed_policy_macro=10 \
  --quota public_event_generic=10 \
  --quota unknown=0 \
  --max-candle-market-attempts 400 \
  --period-interval 60 \
  --timeout-seconds 4
```

Generated local outputs, not committed:

- `data/source_exports/kalshi/kalshi_normalized_calibration_20260608_public_probe/`
- `data/historical/phase7g_kalshi_calibration_kalshi_normalized_calibration_20260608_public_probe.jsonl`
- `data/reports/calibration/phase7g_kalshi_calibration_kalshi_normalized_calibration_20260608_public_probe*`
- `data/reports/calibration/kalshi_normalized_calibration_20260608_public_probe*`

## Collection Result

| Metric | Result |
| --- | ---: |
| Markets discovered pre-filter | 12,000 |
| Markets post-filter resolved/binary | 11,612 |
| Markets selected | 70 |
| Rows collected | 669 |
| Evidence rows | 0 |
| Target markets | 100 |
| Target rows | 1,200 |
| Rows per market target | 12 |
| Candle attempt cap | 400 |
| Target status | `minimum_size_availability_limited` |
| Audit classification | `calibration_minimum` |

## Normalized Category Distribution

| Normalized category | Quota | Selected markets | Rows | Shortfall |
| --- | ---: | ---: | ---: | ---: |
| `sports_tennis` | 30 | 30 | 294 | 0 |
| `sports_major` | 20 | 20 | 200 | 0 |
| `mention_market` | 20 | 20 | 175 | 0 |
| `weather` | 10 | 0 | 0 | 10 |
| `fed_policy_macro` | 10 | 0 | 0 | 10 |
| `public_event_generic` | 10 | 0 | 0 | 10 |
| `unknown` | 0 | 0 | 0 | 0 |

No missing quota was backfilled from unrelated normalized categories. The retry
proved that raw `public_event` sports markets can be selected through normalized
`sports_tennis` and `sports_major` quotas instead of a noisy source-category
quota.

## CollectorDiagnostics Summary

| Diagnostic | Result |
| --- | ---: |
| `discovered_count` | 12,000 |
| `candle_attempt_count` | 400 |
| `candle_success_count` | 70 |
| `candle_failure_count` | 330 |
| `unresolved_loss` | 388 |
| `not_finalized_loss` | 0 |
| `non_binary_loss` | 0 |

Pre-filter normalized category counts:

- `sports_major`: 7,168
- `crypto`: 2,213
- `sports_tennis`: 1,530
- `weather`: 450
- `unknown`: 388
- `mention_market`: 198
- `economics_other`: 53

Post-filter normalized category counts:

- `sports_major`: 6,859
- `crypto`: 2,213
- `sports_tennis`: 1,452
- `weather`: 450
- `unknown`: 387
- `mention_market`: 198
- `economics_other`: 53

Candle failure reasons:

- `insufficient_pre_settlement_last_price_candles`: 329
- `candlestick_request_failed`: 1

Quota shortfalls:

- `fed_policy_macro`: 10 missing; pre-filter and post-filter source count below quota, selected count below quota, candle failures observed.
- `public_event_generic`: 10 missing; pre-filter and post-filter source count below quota, selected count below quota, candle failures observed.
- `weather`: 10 missing; selected count below quota and candle failures observed.

These diagnostics support a specific collection bottleneck story: normalized
weather candidates existed pre- and post-filter, but the bounded retry did not
obtain enough usable pre-settlement last-price candles for weather before the
attempt cap. `fed_policy_macro` and `public_event_generic` were not available in
the discovered normalized candidate set at the requested quota level. These are
availability-limitation diagnostics, not true category-effect evidence.

## Row Shape

The imported historical rows preserved the calibration-only shape:

| Field | Result |
| --- | ---: |
| `profile=calibration_only_last_price` | 669 / 669 |
| `bid=null` | 669 / 669 |
| `ask=null` | 669 / 669 |
| `evidence=[]` | 669 / 669 |
| `paper_pnl_allowed=false` | 669 / 669 |
| `acceptance_candidate=false` | 669 / 669 |
| `last_price` present | 669 / 669 |

## Follow-Up Commands

Calibration audit:

```bash
PYTHONPATH=src .venv/bin/lma audit-calibration-dataset \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_normalized_calibration_20260608_public_probe.jsonl \
  --output-dir data/reports/calibration
```

Bucket QA:

```bash
PYTHONPATH=src .venv/bin/lma calibration-bucket-qa \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_normalized_calibration_20260608_public_probe.jsonl \
  --output-dir data/reports/calibration \
  --gap-threshold 0.15
```

Normalized category calibration analysis:

```bash
PYTHONPATH=src .venv/bin/lma category-calibration-analysis \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_normalized_calibration_20260608_public_probe.jsonl \
  --output-dir data/reports/calibration \
  --docs-report-path data/reports/calibration/phase7g_kalshi_calibration_kalshi_normalized_calibration_20260608_public_probe_category_calibration_analysis.md
```

Normalization check on the new source export:

```bash
PYTHONPATH=src .venv/bin/lma normalize-category-export \
  --source-export-dir data/source_exports/kalshi/kalshi_normalized_calibration_20260608_public_probe \
  --output-dir data/reports/calibration \
  --docs-report-path data/reports/calibration/kalshi_normalized_calibration_20260608_public_probe_category_normalization.md
```

## Calibration Metrics

| Metric | Result |
| --- | ---: |
| Rows | 669 |
| Markets | 70 |
| Resolved markets | 70 |
| Scored rows | 669 |
| Settlement coverage | 100% |
| Last-price coverage | 100% |
| Bid/ask coverage | 0% |
| Evidence timestamp coverage | 0% |
| Overall Brier | 0.19394469 |
| Overall log loss | 0.56594955 |
| Mean forecast | 0.47001495 |
| Observed YES rate | 0.40956652 |
| Overall absolute gap | 0.06044843 |

High-gap buckets at threshold `0.15`:

| Bucket | Rows | Markets | Gap | Brier | Log loss |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0.50-0.60` | 118 | 31 | 0.16618644 | 0.26243475 | 0.71813022 |
| `0.80-0.90` | 17 | 12 | 0.15352941 | 0.28091667 | 0.72011508 |

## Normalized Category Metrics

| Category | Markets | Rows | Row share | Brier | Log loss | Brier loss share | High-gap Brier share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `sports_tennis` | 30 | 294 | 43.946188% | 0.19984796 | 0.58976182 | 45.283817% | 32.375847% |
| `sports_major` | 20 | 200 | 29.895366% | 0.18427350 | 0.54046686 | 28.404612% | 34.574423% |
| `mention_market` | 20 | 175 | 26.158445% | 0.19508000 | 0.55506802 | 26.311571% | 33.049730% |

`category-calibration-analysis` loaded normalized categories successfully and
reported no public-event dominance. The category evidence is now easier to
interpret than PR-CAL-8 because rows are grouped under normalized categories
instead of the noisy raw `public_event` catch-all. It remains calibration-only:
the dataset is last-price-only, evidence-empty, bid/ask-empty, and classified
only as `calibration_minimum`.

## Guardrails

Allowed:

- calibration-only collection
- normalized-category quota diagnostics
- calibration QA diagnostics

Blocked:

- evidence collection or approval
- bid/ask invention
- paper-PnL or profitability claim
- acceptance-gate pass or acceptance-ready claim
- Strategy v2 superiority claim
- broker/live trading
- scheduler, daemon, or autostart behavior
- Phase 8 readiness claim

The audit guardrails kept `acceptance_gate_pass=false`,
`acceptance_gate_evaluation_possible=false`, `strategy_v2_superiority=false`,
and `profitability_claim=false`.

## Recommended Next Step

Use this retry as proof that normalized quotas and CollectorDiagnostics work.
Before any larger calibration-only retry, improve the normalized taxonomy for
`fed_policy_macro` discovery and tune candle-attempt allocation so categories
with available candidates, such as `weather`, are not blocked solely by
pre-settlement last-price candle sparsity.
