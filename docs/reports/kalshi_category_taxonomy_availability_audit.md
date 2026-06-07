# Kalshi Category Taxonomy And Source Availability Audit

Scope: PR-CAL-9 local-only calibration taxonomy and availability audit. This report reads existing local PR-CAL-8 artifacts only. It does not collect data, build a new historical dataset, collect or approve evidence, change strategy logic, change acceptance gates, start Phase 8, add broker/live trading, add scheduler behavior, or make paper-PnL, profitability, acceptance, Strategy v2 superiority, or live-readiness claims.

## Inputs

- Source export dir: `data/source_exports/kalshi/kalshi_category_balanced_calibration_20260607_public_probe`
- Historical file: `data/historical/phase7g_kalshi_calibration_kalshi_category_balanced_calibration_20260607_public_probe.jsonl`
- Manifest status: `loaded`
- Markets status: `loaded`
- Candlesticks status: `loaded`

## Source Metadata Summary

| Metric | Value |
| --- | ---: |
| Discovered candidate markets | 11613 |
| Selected markets | 36 |
| Historical rows | 330 |
| Candlestick rows | 330 |
| Target markets | 120 |
| Target rows | 1440 |
| Rows per market target | 12 |
| Max candle-market attempts | 300 |

Raw source category distribution from selected market metadata:

- `fed_policy`: 1
- `major_sports`: 4
- `public_event`: 30
- `weather`: 1

Semantic category distribution from heuristic title/ticker/rules checks:

- `fed_policy`: 1
- `sports`: 34
- `weather`: 1

## Label Comparison Findings

- Suspected category mismatches: 30
- Sports assigned to weather/fed-policy labels: 0
- Weather-looking markets assigned elsewhere: 0
- Fed/macro-looking markets assigned elsewhere: 0
- Public-event catch-all overuse: 30
- Topic keyword mention markets: 2

Heuristic warnings are taxonomy QA signals, not hard truth.

Sample suspected mismatches:

| Ticker | Source | Inferred | Mention | Warnings | Title |
| --- | --- | --- | --- | --- | --- |
| `KXATPCHALLENGERMATCH-26APR07JONSEK-SEK` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Philip Sekulic win the Jones vs Sekulic : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR07SUNCOO-COO` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Ethan Cook win the Sun vs Cook : Round Of 32 match? |
| `KXITFMATCH-26JUN06HARVIL-HAR` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Nick Hardt win the Hardt vs Villanueva: M25 Cuiaba Semifinal match? |
| `KXWTACHALLENGERMATCH-26JUN07EALBAR-EAL` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Alexandra Eala win the Eala vs Bartunkova: Final match? |
| `KXWTAMATCH-26APR07PLISAS-PLI` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Karolina Pliskova win the Pliskova vs Sasnovich : Round Of 32 match? |
| `KXWTAMATCH-26APR07VOLVEK-VEK` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Donna Vekic win the Volynets vs Vekic : Round Of 32 match? |
| `KXWTAMATCH-26APR07VOLVEK-VOL` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Katie Volynets win the Volynets vs Vekic : Round Of 32 match? |
| `KXWTAMATCH-26JUN07VOLZHU-VOL` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Katie Volynets win the Volynets vs Zhu: Qualification Final match? |
| `KXWTAMATCH-26JUN07VOLZHU-ZHU` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Lin Zhu win the Volynets vs Zhu: Qualification Final match? |
| `KXATPCHALLENGERMATCH-26APR06CUIHOL-HOL` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will August Holmgren win the Cui vs Holmgren : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR06RYBDAM-DAM` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Martin Damm Jr win the Rybakov vs Damm Jr : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR07LANARN-LAN` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Martin Landaluce win the Landaluce vs Arnaboldi : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR07MARMAY-MAR` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Dan Martin win the Martin vs Mayo : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR06CLASOT-CLA` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Jay Clarke win the Clarke vs Soto : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR06RYBDAM-RYB` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Alex Rybakov win the Rybakov vs Damm Jr : Round Of 32 match? |

Public-event catch-all samples:

| Ticker | Source | Inferred | Mention | Warnings | Title |
| --- | --- | --- | --- | --- | --- |
| `KXATPCHALLENGERMATCH-26APR07JONSEK-SEK` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Philip Sekulic win the Jones vs Sekulic : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR07SUNCOO-COO` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Ethan Cook win the Sun vs Cook : Round Of 32 match? |
| `KXITFMATCH-26JUN06HARVIL-HAR` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Nick Hardt win the Hardt vs Villanueva: M25 Cuiaba Semifinal match? |
| `KXWTACHALLENGERMATCH-26JUN07EALBAR-EAL` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Alexandra Eala win the Eala vs Bartunkova: Final match? |
| `KXWTAMATCH-26APR07PLISAS-PLI` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Karolina Pliskova win the Pliskova vs Sasnovich : Round Of 32 match? |
| `KXWTAMATCH-26APR07VOLVEK-VEK` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Donna Vekic win the Volynets vs Vekic : Round Of 32 match? |
| `KXWTAMATCH-26APR07VOLVEK-VOL` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Katie Volynets win the Volynets vs Vekic : Round Of 32 match? |
| `KXWTAMATCH-26JUN07VOLZHU-VOL` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Katie Volynets win the Volynets vs Zhu: Qualification Final match? |
| `KXWTAMATCH-26JUN07VOLZHU-ZHU` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Lin Zhu win the Volynets vs Zhu: Qualification Final match? |
| `KXATPCHALLENGERMATCH-26APR06CUIHOL-HOL` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will August Holmgren win the Cui vs Holmgren : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR06RYBDAM-DAM` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Martin Damm Jr win the Rybakov vs Damm Jr : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR07LANARN-LAN` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Martin Landaluce win the Landaluce vs Arnaboldi : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR07MARMAY-MAR` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Dan Martin win the Martin vs Mayo : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR06CLASOT-CLA` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Jay Clarke win the Clarke vs Soto : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR06RYBDAM-RYB` | `public_event` | `sports` | `False` | suspected_category_mismatch, public_event_catch_all_overuse | Will Alex Rybakov win the Rybakov vs Damm Jr : Round Of 32 match? |

Topic keyword mention samples:

| Ticker | Source | Inferred | Mention | Warnings | Title |
| --- | --- | --- | --- | --- | --- |
| `KXFEDGOVMENTION-26APR07-RATE` | `fed_policy` | `fed_policy` | `True` | topic_keyword_mention_market_warning | What will Austan Goolsbee say during Detroit Economic Club: A Conversation on The Economy and Monetary Policy? |
| `KXPERSONMENTION-26APR07-WEAT` | `weather` | `weather` | `True` | topic_keyword_mention_market_warning | What will any NASA Participant say during Daily news conference on Artemis II (April 7, 2026)? |

## Availability Diagnosis

- Primary blocker: `taxonomy_mismatch_or_keyword_mapping`
- True source scarcity: `not_proven_taxonomy_mismatch_present`
- Taxonomy mismatch: `supported`
- Filter bottleneck: `unknown`
- Candlestick bottleneck: `unknown`
- Row-count bottleneck: `supported`
- Warnings: filter_counts_missing_warning, candle_attempt_logs_missing_warning, row_count_bottleneck_warning, suspected_category_mismatch

The selected export supports a category taxonomy or keyword-mapping issue. True non-public source scarcity remains unproven without pre-candle candidate category counts and candle failure logs.

Quota shortfalls:

- `fed_policy` selected=1 quota=30 missing=29
- `major_sports` selected=4 quota=30 missing=26
- `weather` selected=1 quota=30 missing=29

Row-count bottleneck detail:

- Ideal rows for selected markets: 432
- Actual rows: 330
- Shortfall versus selected-market target: 102
- Shortfall versus full target: 1110

## Reference Export

- Status: `loaded`
- Markets: 90
- Suspected mismatches: 85
- Public-event catch-all overuse: 81

## Recommended Next Step

Before another category-balanced calibration-only retry, revise the category taxonomy and collector diagnostics: separate event-format mention markets from topic categories, add sports/tennis taxonomy coverage or an explicit non-major-sports bucket, and log pre-candle candidate category counts plus candle failure reasons. Do not infer true non-public scarcity or a category calibration effect from the PR-CAL-8 selected export alone.

## Guardrails

| Guardrail | Value |
| --- | --- |
| `calibration_taxonomy_audit_only` | `True` |
| `local_only` | `True` |
| `data_collection` | `False` |
| `historical_dataset_built` | `False` |
| `evidence_collection` | `False` |
| `evidence_approval` | `False` |
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
