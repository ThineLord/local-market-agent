# Kalshi Calibration Diagnostics Result

Scope: PR-CAL-3 offline calibration diagnostics on the existing PR-CAL-2
calibration-minimum dataset. No new data was collected.

## Commands Run

Calibration audit:

```bash
PYTHONPATH=src .venv/bin/lma audit-calibration-dataset \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_calibration_20260607_public_probe.jsonl \
  --output-dir data/reports/calibration
```

Offline strategy evaluation:

```bash
PYTHONPATH=src .venv/bin/lma strategy-eval-offline \
  --historical-file data/historical/phase7g_kalshi_calibration_kalshi_calibration_20260607_public_probe.jsonl \
  --output-dir data/reports/strategy_eval
```

Generated local strategy report artifacts:

- `data/reports/strategy_eval/strategy_eval_phase7g_kalshi_calibration_kalshi_calibration_20260607_public_probe_7e4689452af8.json`
- `data/reports/strategy_eval/strategy_eval_phase7g_kalshi_calibration_kalshi_calibration_20260607_public_probe_7e4689452af8.md`

These generated artifacts are local/ignored and were not committed.

## Tool Compatibility

The calibration audit worked unchanged and reclassified the dataset as
`calibration_minimum`.

The offline strategy evaluator did not work unchanged. It initially rejected
the calibration-only dataset because the older Phase 7 historical loader
required `bid` and `ask`, and then because it expected settlement to be a plain
string rather than the Phase 7G settlement object.

Narrow compatibility fixes made:

- allow explicit `profile=calibration_only_last_price` rows to load with
  `bid=null` and `ask=null`;
- parse settlement objects through their `outcome` field;
- evaluate all markets when `strategy-eval-offline` receives a multi-market
  dataset without `--market-id`;
- classify the offline report as `calibration_only_last_price_dataset`;
- block paper PnL when rows have `paper_pnl_allowed=false` or missing bid/ask;
- preserve `superiority_claim_allowed=false`, `paper_pnl_claim_allowed=false`,
  and `acceptance_evaluation_eligible=false`.

No bid/ask values were invented, no evidence was fabricated, no Strategy v2
thresholds were changed, and no acceptance gate was weakened.

## Dataset Metrics

| Metric | Result |
| --- | ---: |
| Audit classification | `calibration_minimum` |
| Offline eval classification | `calibration_only_last_price_dataset` |
| Row count | 545 |
| Market count | 60 |
| Resolved market count | 60 |
| Scored row count | 545 |
| Settlement coverage | 100% |
| Last-price coverage | 100% |
| Bid/ask coverage | 0% |
| Evidence timestamp coverage | 0% |
| Duplicate market/timestamp rows | 0 |
| Missing outcome count | 0 |
| Missing price count | 0 |
| Profile distribution | `calibration_only_last_price`: 545 |

The strategy evaluator selected all 545 rows across all 60 markets because no
`--market-id` was supplied.

## Forecast Diagnostics

| Baseline | Forecast coverage | Structured completeness | Missing probabilities | Brier | Log loss | Scored forecasts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `always_observe` | 0% | 0% | 545 | n/a | n/a | 0 |
| `hint_threshold_policy` | 0% | 0% | 545 | n/a | n/a | 0 |
| `market_implied_probability_only` | 100% | 100% | 0 | 0.21612771 | 0.61879591 | 545 |
| `random_naive_policy` | 100% | 100% | 0 | 0.34268633 | 1.03472765 | 545 |
| `strategy_v1` | 100% | 100% | 0 | 0.21612771 | 0.61879591 | 545 |
| `strategy_v2_candidate` | 100% | 100% | 0 | 0.21612771 | 0.61879591 | 545 |

Probability provenance distribution:

- `strategy_v1`: `market_implied_only` for 545 rows.
- `strategy_v2_candidate`: `market_implied_only` for 545 rows.

Interpretation: on this evidence-empty last-price dataset, Strategy v1 and
Strategy v2 diagnostics collapse to the market-implied/last-price baseline. This
is valid as a calibration diagnostic, but it is not evidence of Strategy v2
superiority.

## Strategy Diagnostics

| Baseline | Evaluated rows | Trades | Closed trades | Abstention rate | Skips | Rejections | Paper PnL interpretation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `always_observe` | 545 | 0 | 0 | 100% | 0 | 545 | `blocked` |
| `hint_threshold_policy` | 545 | 0 | 0 | 100% | 0 | 545 | `blocked` |
| `market_implied_probability_only` | 545 | 0 | 0 | 100% | 0 | 545 | `blocked` |
| `random_naive_policy` | 545 | 0 | 0 | 33.211009% | 0 | 545 | `blocked` |
| `strategy_v1` | 545 | 0 | 0 | 0% | 545 | 545 | `blocked` |
| `strategy_v2_candidate` | 545 | 0 | 0 | 100% | 0 | 545 | `blocked` |

Rejection summaries:

- `strategy_v1`: `missing_bid_ask=545`, `missing_evidence=545`,
  `skip_action=545`.
- `strategy_v2_candidate`: `market_implied_only_baseline=545`,
  `missing_bid_ask=545`, `missing_evidence=545`.
- `market_implied_probability_only`: `missing_bid_ask=545`,
  `missing_evidence=545`.

All paper outcome sections report:

- `paper_pnl_interpretation=blocked`;
- `paper_pnl_claim_allowed=false`;
- `paper_pnl_allowed_row_count=0`;
- `bid_ask_available_row_count=0`;
- `realized_paper_pnl=0`.

The `realized_paper_pnl=0` value is a blocked/no-trade artifact, not a
profitability result.

## Calibration Buckets

The market-implied, Strategy v1, and Strategy v2 candidate bucket tables are the
same because all three use market-implied last price as the structured
probability on this dataset.

| Bucket | Rows | Mean forecast | Observed YES rate | Absolute gap |
| --- | ---: | ---: | ---: | ---: |
| `0.00-0.10` | 25 | 0.05600000 | 0.08000000 | 0.02400000 |
| `0.10-0.20` | 39 | 0.13769231 | 0.05128205 | 0.08641026 |
| `0.20-0.30` | 79 | 0.25240506 | 0.45569620 | 0.20329114 |
| `0.30-0.40` | 44 | 0.34136364 | 0.29545455 | 0.04590909 |
| `0.40-0.50` | 75 | 0.44093333 | 0.22666667 | 0.21426666 |
| `0.50-0.60` | 125 | 0.54864000 | 0.56800000 | 0.01936000 |
| `0.60-0.70` | 50 | 0.63920000 | 0.68000000 | 0.04080000 |
| `0.70-0.80` | 71 | 0.75239437 | 0.63380282 | 0.11859155 |
| `0.80-0.90` | 22 | 0.84727273 | 0.68181818 | 0.16545455 |
| `0.90-1.00` | 15 | 0.94000000 | 0.93333333 | 0.00666667 |

Large calibration-gap buckets reported by the gate diagnostics:

- `0.20-0.30`
- `0.40-0.50`

## Acceptance Gate And Guardrails

Offline gate result:

- `gate_status=not_applicable`
- `acceptance_evaluation_eligible=false`
- `superiority_claim_allowed=false`
- failed gates: `dataset.closed_paper_trades`,
  `dataset.evidence_timestamp_coverage_pct`

Required PR-CAL-3 guardrails:

| Claim | Result |
| --- | --- |
| Acceptance gate pass | `false` |
| Strategy v2 superiority | `false` |
| Profitability claim | `false` |
| Acceptance-ready claim | `false` |
| Acceptance gate evaluation possible | `false` |
| Paper PnL interpretation | `blocked` |

Audit acceptance blockers remain:

- `evidence_timestamp_coverage_below_95_pct`
- `bid_ask_coverage_incomplete`
- `source_terms_pending_or_blocked`
- `paper_pnl_not_allowed_by_dataset`
- `validator_error.missing_required_field`

## Limitations

- The dataset is calibration-minimum, not preferred or stretch.
- Evidence is empty, so strategy forecasts have no timestamp-safe research
  evidence context.
- Bid/ask are absent, so executable paper PnL and profitability diagnostics are
  blocked.
- `terms_review=pending_review` remains an acceptance blocker.
- Strategy v1 and Strategy v2 both fall back to market-implied probability, so
  their Brier/log-loss equality is not a Strategy v2 performance result.
- The offline replay section remains a checksum/report placeholder, as designed
  for the existing offline harness.

## Recommended Next Step

Use this dataset for guarded calibration QA only:

- inspect the two large-gap calibration buckets;
- improve category metadata visibility before relying on segment-level
  calibration conclusions;
- run a separate preferred-size calibration collection or a manually targeted
  acceptance-evidence pilot in a future PR.

Do not use this run to claim acceptance readiness, Strategy v2 superiority,
profitability, live-trading readiness, or Phase 8 readiness.
