# Kalshi Normalized Availability Audit

Scope: PR-CAL-12 local-only normalized availability and candle allocation audit. Default mode reads existing local PR-CAL-11 artifacts only. Optional probe mode may perform bounded public/read-only metadata and candlestick checks, but it does not build a historical dataset, import rows, collect or approve evidence, invent bid/ask, change strategy logic, change acceptance gates, start Phase 8, add broker/live trading, add scheduler behavior, or make paper-PnL, profitability, acceptance, Strategy v2 superiority, or live-readiness claims.

## Inputs

- Source export dir: `data/source_exports/kalshi/kalshi_normalized_calibration_20260608_public_probe`
- Manifest status: `loaded`
- Markets status: `loaded`
- Candlesticks status: `loaded`
- Collector diagnostics status: `loaded_from_export_json`

## PR-CAL-11 Counts

| Metric | Value |
| --- | ---: |
| Discovered markets | 12000 |
| Selected markets | 70 |
| Candlestick rows | 669 |
| Candle attempts | 400 |
| Candle successes | 70 |
| Candle failures | 330 |
| Candle success rate | 17.500000% |
| Candle failure rate | 82.500000% |

Pre-filter normalized category counts:

- `crypto`: 2213
- `economics_other`: 53
- `mention_market`: 198
- `sports_major`: 7168
- `sports_tennis`: 1530
- `unknown`: 388
- `weather`: 450

Post-filter normalized category counts:

- `crypto`: 2213
- `economics_other`: 53
- `mention_market`: 198
- `sports_major`: 6859
- `sports_tennis`: 1452
- `unknown`: 387
- `weather`: 450

Selected normalized category counts:

- `mention_market`: 20
- `sports_major`: 20
- `sports_tennis`: 30

Quota shortfalls:

- `fed_policy_macro`: 10
- `public_event_generic`: 10
- `weather`: 10

Candle failure reasons:

- `candlestick_request_failed`: 1
- `insufficient_pre_settlement_last_price_candles`: 329

## Category Availability

| Category | Quota | Pre-filter | Post-filter | Selected | Shortfall | Rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `economics_other` | 0 | 53 | 53 | 0 | 0 | 0 |
| `fed_policy_macro` | 10 | 0 | 0 | 0 | 10 | 0 |
| `mention_market` | 20 | 198 | 198 | 20 | 0 | 175 |
| `public_event_generic` | 10 | 0 | 0 | 0 | 10 | 0 |
| `sports_major` | 20 | 7168 | 6859 | 20 | 0 | 200 |
| `sports_tennis` | 30 | 1530 | 1452 | 30 | 0 | 294 |
| `unknown` | 0 | 388 | 387 | 0 | 0 | 0 |
| `weather` | 10 | 450 | 450 | 0 | 10 | 0 |

## Weather Diagnosis

- Primary diagnosis: `weather_candle_sparsity_supported_by_probe`
- Weather quota target: 10
- Weather post-filter candidates: 450
- Weather selected markets: 0
- Weather shortfall: 10
- Interpretation: Weather candidates can be discovered, but the bounded probe found no markets with enough usable pre-settlement last-price candles.
- True weather source scarcity proven: False

Weather selected examples:

- none retained in the local selected export/probe output

## Fed/Macro Diagnosis

- Primary diagnosis: `taxonomy_coverage_or_candidate_persistence_gap`
- Fed/macro quota target: 10
- Fed/macro pre-filter candidates: 0
- Fed/macro post-filter candidates: 0
- Economics-other post-filter candidates: 53
- Unknown post-filter candidates: 387
- False-negative examples surfaced from selected local metadata: 0
- Source scarcity proven: False
- Interpretation: PR-CAL-11 reported zero fed_policy_macro candidates but many adjacent economics_other/unknown candidates. Because unselected examples were not persisted, true source scarcity is not proven.

Fed/macro false-negative examples:

- none retained in the local selected export/probe output

Suggested normalization diagnostics:

- persist unselected economics_other and unknown candidate examples before changing rules
- keep fed_policy_macro separate from generic economics_other unless deterministic Fed/rate/CPI/FOMC signals are present

## Optional Probe

- Probe enabled: True
- Probe category: `weather`
- Network used: True
- Attempted markets: 50
- Successful markets: 0
- Success rate: 0.000000%
- Insufficient-candle failures: 50
- Request failures: 0
- Historical dataset written: False
- Historical rows imported: False

Probe sample attempts:

- `KXTEMPNYCH-26APR0817-T46.99` (weather): Will the temp in NYC be above 46.99° on Apr 8, 2026 at 5pm EDT?
- `KXTEMPNYCH-26APR0817-T45.99` (weather): Will the temp in NYC be above 45.99° on Apr 8, 2026 at 5pm EDT?
- `KXTEMPNYCH-26APR0815-T48.99` (weather): Will the temp in NYC be above 48.99° on Apr 8, 2026 at 3pm EDT?
- `KXTEMPNYCH-26APR0815-T49.99` (weather): Will the temp in NYC be above 49.99° on Apr 8, 2026 at 3pm EDT?
- `KXTEMPNYCH-26APR0816-T49.99` (weather): Will the temp in NYC be above 49.99° on Apr 8, 2026 at 4pm EDT?
- `KXTEMPNYCH-26APR0817-T47.99` (weather): Will the temp in NYC be above 47.99° on Apr 8, 2026 at 5pm EDT?
- `KXTEMPNYCH-26APR0818-T43.99` (weather): Will the temp in NYC be above 43.99° on Apr 8, 2026 at 6pm EDT?
- `KXTEMPNYCH-26APR0818-T44.99` (weather): Will the temp in NYC be above 44.99° on Apr 8, 2026 at 6pm EDT?
- `KXTEMPNYCH-26APR0815-T46.99` (weather): Will the temp in NYC be above 46.99° on Apr 8, 2026 at 3pm EDT?
- `KXTEMPNYCH-26APR0815-T47.99` (weather): Will the temp in NYC be above 47.99° on Apr 8, 2026 at 3pm EDT?

## Conclusions

- Weather failure explained by: `weather_candle_sparsity_supported_by_probe`
- Fed/macro failure explained by: `taxonomy_coverage_or_candidate_persistence_gap`
- Larger retry justified: False
- Larger retry condition: Justified only after PR-CAL-13 adds candidate persistence and per-category candle allocation diagnostics; do not interpret this audit as category-effect evidence.
- Recommended PR-CAL-13 action: Add candidate-level normalized discovery persistence, per-category candle attempt/failure logging, and deterministic fed/macro rule tests before a larger calibration-only retry.

## Guardrails

- `acceptance_claim`: False
- `acceptance_gate_changed`: False
- `bid_ask_invention`: False
- `broker_or_live_trading_added`: False
- `evidence_approval`: False
- `evidence_collection`: False
- `historical_dataset_built`: False
- `historical_rows_imported`: False
- `live_readiness_claim`: False
- `network_used_only_when_probe_enabled`: True
- `normalized_availability_audit_only`: True
- `offline_by_default`: True
- `paper_pnl_claim`: False
- `phase8_started`: False
- `profitability_claim`: False
- `scheduler_or_daemon_added`: False
- `strategy_logic_changed`: False
- `strategy_v2_superiority_claim`: False
