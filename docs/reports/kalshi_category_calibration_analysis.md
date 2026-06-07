# Kalshi Category Calibration Analysis

Scope: PR-CAL-6 local-only calibration QA. This report does not collect data, modify strategy logic, modify acceptance gates, start Phase 8, add broker/live trading, add scheduler behavior, or make profitability, acceptance, Strategy v2 superiority, paper-PnL, or live-readiness claims.

## Report Inputs

- Report id: `category_calibration_phase7g_kalshi_calibration_kalshi_calibration_preferred_20260607_public_probe_0.15`
- Historical file: `data/historical/phase7g_kalshi_calibration_kalshi_calibration_preferred_20260607_public_probe.jsonl`
- Gap threshold: 0.15
- Dataset id: `phase7g_kalshi_calibration_kalshi_calibration_preferred_20260607_public_probe`
- Category source status: `loaded`
- Category source paths: `data/source_exports/kalshi/kalshi_calibration_preferred_20260607_public_probe/markets.jsonl`

## Dataset Summary

| Metric | Result |
| --- | ---: |
| Rows | 818 |
| Markets | 90 |
| Scored rows | 818 |
| Overall Brier | 0.21307555 |
| Overall log loss | 0.61282262 |
| Overall mean forecast | 0.48017115 |
| Overall observed YES rate | 0.46821516 |
| Overall absolute gap | 0.01195599 |

Category market distribution:

- `fed_policy`: 1
- `major_sports`: 5
- `public_event`: 82
- `weather`: 2

Category row distribution:

- `fed_policy`: 4
- `major_sports`: 52
- `public_event`: 749
- `weather`: 13

## Category Metrics

| Category | Rows | Markets | Row share | Market share | Mean forecast | Observed YES | Gap | Brier | Log loss | Brier loss share | Warnings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `public_event` | 749 | 82 | 91.564792% | 91.111111% | 0.48512684 | 0.50200267 | 0.01687583 | 0.21712977 | 0.62282836 | 93.307010% | public_event_dominance_warning |
| `major_sports` | 52 | 5 | 6.356968% | 5.555556% | 0.41000000 | 0.00000000 | 0.41000000 | 0.20644231 | 0.58629841 | 6.159070% | top_three_market_concentration_warning |
| `weather` | 13 | 2 | 1.589242% | 2.222222% | 0.52769231 | 0.53846154 | 0.01076923 | 0.03960000 | 0.21410006 | 0.295360% | small_category_sample_warning, small_category_row_sample_warning, small_category_market_sample_warning, market_concentration_warning, top_three_market_concentration_warning |
| `fed_policy` | 4 | 1 | 0.488998% | 1.111111% | 0.31000000 | 0.00000000 | 0.31000000 | 0.10395000 | 0.37991073 | 0.238560% | small_category_sample_warning, small_category_row_sample_warning, small_category_market_sample_warning, market_concentration_warning, top_three_market_concentration_warning |

## High-Gap Category Buckets

### `public_event`

| Bucket | Rows | Markets | Mean forecast | Observed YES | Gap | Brier | Brier loss sum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0.20-0.30` | 108 | 29 | 0.25444444 | 0.50925926 | 0.25481482 | 0.31803148 | 34.34740000 |
| `0.50-0.60` | 132 | 32 | 0.54727273 | 0.73484848 | 0.18757575 | 0.22389242 | 29.55380000 |
| `0.70-0.80` | 110 | 30 | 0.74654545 | 0.56363636 | 0.18290909 | 0.28501636 | 31.35180000 |

### `major_sports`

| Bucket | Rows | Markets | Mean forecast | Observed YES | Gap | Brier | Brier loss sum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0.20-0.30` | 1 | 1 | 0.26000000 | 0.00000000 | 0.26000000 | 0.06760000 | 0.06760000 |
| `0.30-0.40` | 3 | 3 | 0.33333333 | 0.00000000 | 0.33333333 | 0.11273333 | 0.33820000 |
| `0.40-0.50` | 13 | 3 | 0.43538462 | 0.00000000 | 0.43538462 | 0.18972308 | 2.46640000 |
| `0.50-0.60` | 21 | 4 | 0.54523810 | 0.00000000 | 0.54523810 | 0.29768095 | 6.25130000 |
| `0.60-0.70` | 2 | 1 | 0.60500000 | 0.00000000 | 0.60500000 | 0.36605000 | 0.73210000 |
| `0.80-0.90` | 1 | 1 | 0.89000000 | 0.00000000 | 0.89000000 | 0.79210000 | 0.79210000 |

### `weather`

| Bucket | Rows | Markets | Mean forecast | Observed YES | Gap | Brier | Brier loss sum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0.20-0.30` | 3 | 1 | 0.24666667 | 0.00000000 | 0.24666667 | 0.06166667 | 0.18500000 |
| `0.70-0.80` | 4 | 1 | 0.77250000 | 1.00000000 | 0.22750000 | 0.05197500 | 0.20790000 |
| `0.80-0.90` | 2 | 1 | 0.85000000 | 1.00000000 | 0.15000000 | 0.02340000 | 0.04680000 |

### `fed_policy`

| Bucket | Rows | Markets | Mean forecast | Observed YES | Gap | Brier | Brier loss sum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `0.20-0.30` | 2 | 1 | 0.23500000 | 0.00000000 | 0.23500000 | 0.05545000 | 0.11090000 |
| `0.30-0.40` | 1 | 1 | 0.32000000 | 0.00000000 | 0.32000000 | 0.10240000 | 0.10240000 |
| `0.40-0.50` | 1 | 1 | 0.45000000 | 0.00000000 | 0.45000000 | 0.20250000 | 0.20250000 |


## Public Event Versus Non-Public Event

| Segment | Rows | Markets | Row share | Market share | Brier | Log loss | Gap | Brier loss share | High-gap Brier share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `public_event` | 749 | 82 | 91.564792% | 91.111111% | 0.21712977 | 0.62282836 | 0.01687583 | 93.307010% | 89.224794% |
| `non_public_event` | 69 | 8 | 8.435208% | 8.888889% | 0.16906667 | 0.50420958 | 0.32492753 | 6.692990% | 10.775206% |

- Public-event dominance detected: `True`
- Public-event Brier-loss dominance detected: `True`
- Non-public-event evidence sparse: `True`
- Non-public-event high-gap bucket detected: `True`
- Public-event aggregate-weight explanation: `True`
- Public-event gap-origin explanation: `False`
- Assessment: Public-event dominance explains most aggregate weighting, but it does not prove the gaps are public-event-specific because sparse non-public categories also show high-gap buckets.

Category contribution to total Brier loss:

| Category | Rows | Markets | Brier loss sum | Share |
| --- | ---: | ---: | ---: | ---: |
| `public_event` | 749 | 82 | 162.63020000 | 93.307010% |
| `major_sports` | 52 | 5 | 10.73500000 | 6.159070% |
| `weather` | 13 | 2 | 0.51480000 | 0.295360% |
| `fed_policy` | 4 | 1 | 0.41580000 | 0.238560% |

Category contribution to high-gap category buckets:

| Category | High-gap rows | High-gap Brier loss sum | Row share | Brier share |
| --- | ---: | ---: | ---: | ---: |
| `public_event` | 350 | 95.25300000 | 86.633663% | 89.224794% |
| `major_sports` | 41 | 10.64770000 | 10.148515% | 9.973847% |
| `weather` | 9 | 0.43970000 | 2.227723% | 0.411873% |
| `fed_policy` | 4 | 0.41580000 | 0.990099% | 0.389486% |

## Top Markets By Category

### `public_event`

Top by row count:
- `KXATPCHALLENGERMATCH-26APR07DUTTAB-TAB` rows=12 row_share=1.602136% brier_loss_sum=7.04650000 brier=0.58720833
- `KXATPCHALLENGERMATCH-26APR07DUTTAB-DUT` rows=12 row_share=1.602136% brier_loss_sum=6.88110000 brier=0.57342500
- `KXWTAMATCH-26APR07PLISAS-SAS` rows=12 row_share=1.602136% brier_loss_sum=6.59710000 brier=0.54975833
- `KXWTAMATCH-26APR07PLISAS-PLI` rows=12 row_share=1.602136% brier_loss_sum=6.29400000 brier=0.52450000
- `KXATPMATCH-26JUN07SAFGAL-SAF` rows=12 row_share=1.602136% brier_loss_sum=5.86730000 brier=0.48894167

Top by Brier loss:
- `KXATPCHALLENGERMATCH-26APR07DUTTAB-TAB` rows=12 row_share=1.602136% brier_loss_sum=7.04650000 brier=0.58720833
- `KXATPCHALLENGERMATCH-26APR07DUTTAB-DUT` rows=12 row_share=1.602136% brier_loss_sum=6.88110000 brier=0.57342500
- `KXWTAMATCH-26APR07PLISAS-SAS` rows=12 row_share=1.602136% brier_loss_sum=6.59710000 brier=0.54975833
- `KXATPCHALLENGERMATCH-26APR06RYBDAM-DAM` rows=11 row_share=1.468625% brier_loss_sum=6.41950000 brier=0.58359091
- `KXWTAMATCH-26APR07PLISAS-PLI` rows=12 row_share=1.602136% brier_loss_sum=6.29400000 brier=0.52450000

### `major_sports`

Top by row count:
- `KXMLBTOTAL-26APR071510BALCWS-7` rows=12 row_share=23.076923% brier_loss_sum=3.32120000 brier=0.27676667
- `KXMLBTOTAL-26APR071310KCCLE-7` rows=12 row_share=23.076923% brier_loss_sum=2.83730000 brier=0.23644167
- `KXMLBTOTAL-26APR071610AZNYM-8` rows=12 row_share=23.076923% brier_loss_sum=2.24690000 brier=0.18724167
- `KXNBASPREAD-26APR06PORDEN-POR8` rows=10 row_share=19.230769% brier_loss_sum=0.38960000 brier=0.03896000
- `KXFOXNEWSMENTION-26APR06B-IRAN` rows=6 row_share=11.538462% brier_loss_sum=1.94000000 brier=0.32333333

Top by Brier loss:
- `KXMLBTOTAL-26APR071510BALCWS-7` rows=12 row_share=23.076923% brier_loss_sum=3.32120000 brier=0.27676667
- `KXMLBTOTAL-26APR071310KCCLE-7` rows=12 row_share=23.076923% brier_loss_sum=2.83730000 brier=0.23644167
- `KXMLBTOTAL-26APR071610AZNYM-8` rows=12 row_share=23.076923% brier_loss_sum=2.24690000 brier=0.18724167
- `KXFOXNEWSMENTION-26APR06B-IRAN` rows=6 row_share=11.538462% brier_loss_sum=1.94000000 brier=0.32333333
- `KXNBASPREAD-26APR06PORDEN-POR8` rows=10 row_share=19.230769% brier_loss_sum=0.38960000 brier=0.03896000

### `weather`

Top by row count:
- `KXITFWMATCH-26JUN06LIXRAI-LIX` rows=7 row_share=53.846154% brier_loss_sum=0.26470000 brier=0.03781429
- `KXITFWMATCH-26JUN06LIXRAI-RAI` rows=6 row_share=46.153846% brier_loss_sum=0.25010000 brier=0.04168333

Top by Brier loss:
- `KXITFWMATCH-26JUN06LIXRAI-LIX` rows=7 row_share=53.846154% brier_loss_sum=0.26470000 brier=0.03781429
- `KXITFWMATCH-26JUN06LIXRAI-RAI` rows=6 row_share=46.153846% brier_loss_sum=0.25010000 brier=0.04168333

### `fed_policy`

Top by row count:
- `KXATPCHALLENGERMATCH-26APR07LANARN-ARN` rows=4 row_share=100.000000% brier_loss_sum=0.41580000 brier=0.10395000

Top by Brier loss:
- `KXATPCHALLENGERMATCH-26APR07LANARN-ARN` rows=4 row_share=100.000000% brier_loss_sum=0.41580000 brier=0.10395000


## Guardrails

| Guardrail | Value |
| --- | --- |
| `calibration_qa_only` | `True` |
| `local_only` | `True` |
| `data_collection` | `False` |
| `strategy_logic_changed` | `False` |
| `acceptance_gate_changed` | `False` |
| `phase8_started` | `False` |
| `broker_or_live_trading_added` | `False` |
| `scheduler_or_daemon_added` | `False` |
| `paper_pnl_claim` | `False` |
| `profitability_claim` | `False` |
| `acceptance_ready_claim` | `False` |
| `strategy_v2_superiority_claim` | `False` |
| `trading_readiness_claim` | `False` |

## Recommended Next Step

Treat this as evidence that PR-CAL-5 is too category-skewed for broad category conclusions. The next useful step is a category-balance or metadata-visibility QA task, or a separate manually targeted acceptance-evidence pilot. Do not use this report for acceptance, profitability, Strategy v2 superiority, paper-PnL, live-trading, or Phase 8 readiness claims.
