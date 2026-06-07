# Kalshi Category Balance Plan

Scope: PR-CAL-7 local-only calibration planning. This report designs a category-balanced calibration-only retry, but it does not collect data, modify strategy logic, modify acceptance gates, start Phase 8, add broker/live trading, add scheduler behavior, or make profitability, acceptance, Strategy v2 superiority, paper-PnL, or live-readiness claims.

## Inputs

- Historical file: `data/historical/phase7g_kalshi_calibration_kalshi_calibration_preferred_20260607_public_probe.jsonl`
- PR-CAL-6 category report: `docs/reports/kalshi_category_calibration_analysis.md`
- Source export root: `data/source_exports/kalshi`
- Dataset id: `phase7g_kalshi_calibration_kalshi_calibration_preferred_20260607_public_probe`
- Category source status: `loaded`

## Current Distribution

| Category | Markets | Rows | Market share | Row share | Brier loss share | High-gap Brier share | Warnings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `public_event` | 82 | 749 | 91.111111% | 91.564792% | 93.307010% | 89.224794% | public_event_overdominance_warning |
| `major_sports` | 5 | 52 | 5.555556% | 6.356968% | 6.159070% | 9.973847% | available_source_limitation_warning, small_category_sample_warning, small_category_market_sample_warning, small_category_row_sample_warning |
| `weather` | 2 | 13 | 2.222222% | 1.589242% | 0.295360% | 0.411873% | available_source_limitation_warning, small_category_sample_warning, small_category_market_sample_warning, small_category_row_sample_warning |
| `fed_policy` | 1 | 4 | 1.111111% | 0.488998% | 0.238560% | 0.389486% | available_source_limitation_warning, small_category_sample_warning, small_category_market_sample_warning, small_category_row_sample_warning |

## Target Plans

### `minimum`

- Target markets: 80
- Target rows: 960
- Rows per market target: 12
- Public-event cap: 40
- Warnings: available_source_limitation_warning

| Category | Target markets | Target rows | Market share | Current markets | Additional markets needed | Availability-limited |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `fed_policy` | 20 | 240 | 25.000000% | 1 | 19 | `True` |
| `major_sports` | 20 | 240 | 25.000000% | 5 | 15 | `True` |
| `public_event` | 20 | 240 | 25.000000% | 82 | 0 | `False` |
| `weather` | 20 | 240 | 25.000000% | 2 | 18 | `True` |

### `preferred`

- Target markets: 120
- Target rows: 1440
- Rows per market target: 12
- Public-event cap: 60
- Warnings: available_source_limitation_warning

| Category | Target markets | Target rows | Market share | Current markets | Additional markets needed | Availability-limited |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `fed_policy` | 30 | 360 | 25.000000% | 1 | 29 | `True` |
| `major_sports` | 30 | 360 | 25.000000% | 5 | 25 | `True` |
| `public_event` | 30 | 360 | 25.000000% | 82 | 0 | `False` |
| `weather` | 30 | 360 | 25.000000% | 2 | 28 | `True` |

### `stretch`

- Target markets: 200
- Target rows: 2400
- Rows per market target: 12
- Public-event cap: 100
- Warnings: available_source_limitation_warning

| Category | Target markets | Target rows | Market share | Current markets | Additional markets needed | Availability-limited |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `fed_policy` | 50 | 600 | 25.000000% | 1 | 49 | `True` |
| `major_sports` | 50 | 600 | 25.000000% | 5 | 45 | `True` |
| `public_event` | 50 | 600 | 25.000000% | 82 | 0 | `False` |
| `weather` | 50 | 600 | 25.000000% | 2 | 48 | `True` |


## Recommended Target

- Recommended plan: `preferred`
- Target markets: 120
- Target rows: 1440
- Rows per market target: 12
- Public-event cap: 60 markets (50.000000%)
- At least 20 markets per major category where available.
- Small-category warnings: < 10 markets or < 100 rows.

The current PR-CAL-5 dataset should be treated as source-skewed, not as evidence of a true category effect. If future non-public categories are unavailable, record an available-source limitation instead of filling the gap with more public-event markets.

## Suggested Future Collector Constraints

- Max public-event markets: 60
- Max public-event market share: 50.000000%
- Desired category quotas: `{'fed_policy': 30, 'major_sports': 30, 'public_event': 30, 'weather': 30}`
- Per-category rows-per-market targets: `{'fed_policy': 12, 'major_sports': 12, 'public_event': 12, 'weather': 12}`

Stop conditions:

- stop when every available category quota is met
- stop if public_event reaches its cap before non-public quotas are met
- stop when target row count is reached with 100% scored settlement coverage
- stop with an availability-limited status if non-public categories cannot be found without broadening scope

Fallback behavior if non-public categories are unavailable:

- do not fill missing non-public quotas with public_event beyond the cap
- emit available_source_limitation rather than category_effect evidence
- preserve calibration_only_last_price shape
- write a planning/collection-limitation report before any retry result is interpreted

## Available-Source Limitations

- `fed_policy` current=1 target=30 additional_needed=29 classification=`available_source_limitation`
- `major_sports` current=5 target=30 additional_needed=25 classification=`available_source_limitation`
- `weather` current=2 target=30 additional_needed=28 classification=`available_source_limitation`

## Guardrails

| Guardrail | Value |
| --- | --- |
| `calibration_planning_only` | `True` |
| `local_only` | `True` |
| `data_collection` | `False` |
| `collector_implemented` | `False` |
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

Use this plan to scope a future category-balanced calibration-only retry. Do not implement collection, acceptance evaluation, Strategy v2 superiority evaluation, profitability analysis, live trading, or Phase 8 work from this PR.
