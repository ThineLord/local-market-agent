# Kalshi Category-Balanced Calibration Retry Result

Scope: PR-CAL-8 temporary local-only category-balanced Kalshi calibration
collection. This was calibration-only data collection, not acceptance
evaluation. No evidence was collected or approved, no bid/ask values were
invented, and no strategy, acceptance-gate, Phase 8, broker/live-trading,
scheduler, paper-PnL, profitability, Strategy v2 superiority, acceptance, or
live-readiness claims are made.

## Collection Command

```bash
PYTHONPATH=src .venv/bin/python scripts/local_only/collect_kalshi_category_balanced_calibration.py \
  --export-id kalshi_category_balanced_calibration_20260607_public_probe \
  --target-markets 120 \
  --rows-per-market 12 \
  --quota public_event=30 \
  --quota major_sports=30 \
  --quota weather=30 \
  --quota fed_policy=30 \
  --public-event-cap 60 \
  --max-candle-market-attempts 300 \
  --period-interval 60 \
  --timeout-seconds 4
```

The initial run exposed a collector ordering bug: scarce non-public categories
consumed the candle-attempt budget before `public_event` could be sampled. The
script was fixed to cycle through quota categories with per-category offsets,
then the same command was rerun.

Generated local outputs, not committed:

- `data/source_exports/kalshi/kalshi_category_balanced_calibration_20260607_public_probe/`
- `data/historical/phase7g_kalshi_calibration_kalshi_category_balanced_calibration_20260607_public_probe.jsonl`
- `data/reports/calibration/phase7g_kalshi_calibration_kalshi_category_balanced_calibration_20260607_public_probe*`

## Collection Result

| Metric | Result |
| --- | ---: |
| Markets discovered | 11,613 |
| Markets selected | 36 |
| Rows collected | 330 |
| Evidence rows | 0 |
| Target markets | 120 |
| Target rows | 1,440 |
| Rows per market target | 12 |
| Public-event cap | 60 |
| Target status | `minimum_size_availability_limited` |
| Audit classification | `calibration_minimum` |

The preferred PR-CAL-7 target was not met. The retry met only the calibration
minimum tier by size, and it remained availability-limited for non-public
categories.

## Category Distribution

| Category | Selected markets | Rows | Quota | Missing markets | Availability result |
| --- | ---: | ---: | ---: | ---: | --- |
| `public_event` | 30 | 286 | 30 | 0 | quota met |
| `major_sports` | 4 | 20 | 30 | 26 | `available_source_limitation` |
| `weather` | 1 | 12 | 30 | 29 | `available_source_limitation` |
| `fed_policy` | 1 | 12 | 30 | 29 | `available_source_limitation` |

Unavailable non-public quotas were not backfilled with extra public-event
markets. `public_event` stayed at the requested 30-market quota, below the
60-market cap.

## Row Shape

The imported historical rows preserved the calibration-only shape:

| Field | Result |
| --- | ---: |
| `profile=calibration_only_last_price` | 330 / 330 |
| `bid=null` | 330 / 330 |
| `ask=null` | 330 / 330 |
| `evidence=[]` | 330 / 330 |
| `paper_pnl_allowed=false` | 330 / 330 |
| `acceptance_candidate=false` | 330 / 330 |
| `last_price` present | 330 / 330 |

## Follow-Up Commands

Calibration audit:

```bash
PYTHONPATH=src .venv/bin/lma audit-calibration-dataset \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_category_balanced_calibration_20260607_public_probe.jsonl \
  --output-dir data/reports/calibration
```

Bucket QA:

```bash
PYTHONPATH=src .venv/bin/lma calibration-bucket-qa \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_category_balanced_calibration_20260607_public_probe.jsonl \
  --output-dir data/reports/calibration \
  --gap-threshold 0.15
```

Category calibration analysis:

```bash
PYTHONPATH=src .venv/bin/lma category-calibration-analysis \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_category_balanced_calibration_20260607_public_probe.jsonl \
  --output-dir data/reports/calibration \
  --docs-report-path data/reports/calibration/phase7g_kalshi_calibration_kalshi_category_balanced_calibration_20260607_public_probe_category_calibration_analysis.md
```

Category balance plan rerun:

```bash
PYTHONPATH=src .venv/bin/lma category-balance-plan \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_category_balanced_calibration_20260607_public_probe.jsonl \
  --output-dir data/reports/calibration \
  --category-report-path data/reports/calibration/phase7g_kalshi_calibration_kalshi_category_balanced_calibration_20260607_public_probe_category_calibration_analysis.md \
  --docs-report-path data/reports/calibration/phase7g_kalshi_calibration_kalshi_category_balanced_calibration_20260607_public_probe_category_balance_plan.md
```

The category-analysis and balance-plan docs paths were redirected to ignored
local report files to avoid overwriting the committed PR-CAL-6 and PR-CAL-7
reports.

## Calibration Metrics

| Metric | Result |
| --- | ---: |
| Rows | 330 |
| Markets | 36 |
| Resolved markets | 36 |
| Scored rows | 330 |
| Settlement coverage | 100% |
| Last-price coverage | 100% |
| Bid/ask coverage | 0% |
| Evidence timestamp coverage | 0% |
| Overall Brier | 0.20961030 |
| Overall log loss | 0.60648358 |
| Mean forecast | 0.50927273 |
| Observed YES rate | 0.59090909 |
| Overall absolute gap | 0.08163636 |

High-gap buckets at threshold `0.15`:

| Bucket | Rows | Markets | Gap | Brier | Log loss |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0.00-0.10` | 9 | 7 | 0.18555555 | 0.18867778 | 0.58220215 |
| `0.20-0.30` | 36 | 10 | 0.35861111 | 0.36331389 | 0.94783800 |
| `0.30-0.40` | 29 | 10 | 0.17379311 | 0.17926207 | 0.54850057 |
| `0.60-0.70` | 53 | 15 | 0.26320755 | 0.15525094 | 0.49849970 |
| `0.80-0.90` | 6 | 5 | 0.18166666 | 0.28091667 | 0.84587747 |

## Category Metrics

| Category | Markets | Rows | Market share | Row share | Brier | Log loss | Brier loss share | High-gap Brier share | Warnings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `public_event` | 30 | 286 | 83.333333% | 86.666667% | 0.20707972 | 0.60564926 | 85.620358% | 74.003179% | `public_event_dominance_warning` |
| `major_sports` | 4 | 20 | 11.111111% | 6.060606% | 0.12728500 | 0.38099936 | 3.680278% | 6.646604% | small sample |
| `weather` | 1 | 12 | 2.777778% | 3.636364% | 0.29903333 | 0.77828149 | 5.187693% | 9.382010% | small sample |
| `fed_policy` | 1 | 12 | 2.777778% | 3.636364% | 0.31770833 | 0.83037735 | 5.511671% | 9.968206% | small sample |

Category-level interpretation remains limited. The retry reduced public-event
market count from PR-CAL-5's 82 markets to 30 markets, but because non-public
quotas were availability-limited, `public_event` still dominated by row share
and loss share. Sparse non-public categories also showed high-gap contribution,
so this remains an available-source limitation, not evidence of a true category
effect.

## Guardrails

Allowed:

- calibration-only collection
- calibration diagnostics
- category QA diagnostics

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

Treat PR-CAL-8 as a bounded availability-limited calibration retry. Do not use
it for acceptance, paper-PnL, profitability, Strategy v2 superiority, or
live-readiness claims. The next useful action is to revise category discovery
or source targeting for non-public categories before another balanced
calibration-only retry.
