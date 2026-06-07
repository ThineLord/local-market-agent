# Kalshi Category Normalization Result

Scope: PR-CAL-10 taxonomy/diagnostics infrastructure only. This report normalizes an existing local source export and does not collect data, build a new historical dataset, collect or approve evidence, modify strategy logic, modify acceptance gates, start Phase 8, add broker/live trading, add scheduler behavior, or make paper-PnL, profitability, acceptance, Strategy v2 superiority, or live-readiness claims.

## Inputs

- Source export dir: `data/source_exports/kalshi/kalshi_category_balanced_calibration_20260607_public_probe`
- Markets path: `data/source_exports/kalshi/kalshi_category_balanced_calibration_20260607_public_probe/markets.jsonl`
- Market count: 36

## Normalized Category Findings

| Category | Count | Share |
| --- | ---: | ---: |
| `sports_tennis` | 28 | 77.777778% |
| `sports_major` | 6 | 16.666667% |
| `weather` | 0 | 0.000000% |
| `fed_policy_macro` | 0 | 0.000000% |
| `public_event_generic` | 0 | 0.000000% |
| `mention_market` | 2 | 5.555556% |
| `crypto` | 0 | 0.000000% |
| `politics_government` | 0 | 0.000000% |
| `entertainment` | 0 | 0.000000% |
| `economics_other` | 0 | 0.000000% |
| `unknown` | 0 | 0.000000% |

Source category counts:

- `fed_policy`: 1
- `major_sports`: 4
- `public_event`: 30
- `weather`: 1

Semantic category counts:

- `fed_policy_macro`: 1
- `sports_major`: 6
- `sports_tennis`: 28
- `weather`: 1

## Public Event And Mention Diagnostics

- Public-event mismatch count: 30
- Mention-market count: 2
- Unknown normalized count: 0
- Future retry taxonomy usable: `True`

Public-event mismatch samples:

| Ticker | Source | Normalized | Semantic | Mention | Warnings | Title |
| --- | --- | --- | --- | --- | --- | --- |
| `KXNCAAMBSPREAD-26APR06CONNMICH-MICH6` | `public_event` | `sports_major` | `sports_major` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Michigan wins by over 6.5 Points? |
| `KXITFWMATCH-26JUN06LIXRAI-RAI` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Ankita Raina win the Li vs Raina: W100 Wuning Round of 32 match? |
| `KXITFWMATCH-26JUN06LIXRAI-LIX` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Zongyu Li win the Li vs Raina: W100 Wuning Round of 32 match? |
| `KXWTAMATCH-26APR07VOLVEK-VEK` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Donna Vekic win the Volynets vs Vekic : Round Of 32 match? |
| `KXITFMATCH-26JUN06HARVIL-VIL` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Gonzalo Villanueva win the Hardt vs Villanueva: M25 Cuiaba Semifinal match? |
| `KXITFWMATCH-26JUN06YEXYAS-YAS` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Ekaterina Yashina win the Ye vs Yashina: W100 Wuning Round of 32 match? |
| `KXATPCHALLENGERMATCH-26APR07DEVSAR-DEV` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Murkel Dellien win the Dellien vs Saraiva Dos Santos : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR07JONSEK-JON` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Maximus Jones win the Jones vs Sekulic : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR06RYBDAM-DAM` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Martin Damm Jr win the Rybakov vs Damm Jr : Round Of 32 match? |
| `KXWTAMATCH-26APR07VOLVEK-VOL` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Katie Volynets win the Volynets vs Vekic : Round Of 32 match? |
| `KXWTACHALLENGERMATCH-26JUN07EALBAR-EAL` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Alexandra Eala win the Eala vs Bartunkova: Final match? |
| `KXATPCHALLENGERMATCH-26APR06RYBDAM-RYB` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Alex Rybakov win the Rybakov vs Damm Jr : Round Of 32 match? |
| `KXATPCHALLENGERMATCH-26APR07MARMAY-MAY` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Aidan Mayo win the Martin vs Mayo : Round Of 32 match? |
| `KXITFWMATCH-26JUN06YEXYAS-YEX` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Shiyu Ye win the Ye vs Yashina: W100 Wuning Round of 32 match? |
| `KXATPCHALLENGERMATCH-26APR06CLASOT-CLA` | `public_event` | `sports_tennis` | `sports_tennis` | `False` | source_semantic_mismatch_warning, public_event_source_label_overridden_warning | Will Jay Clarke win the Clarke vs Soto : Round Of 32 match? |

Mention-market samples:

| Ticker | Source | Normalized | Semantic | Mention | Warnings | Title |
| --- | --- | --- | --- | --- | --- | --- |
| `KXFEDGOVMENTION-26APR07-RATE` | `fed_policy` | `mention_market` | `fed_policy_macro` | `True` | mention_market_format_warning | What will Austan Goolsbee say during Detroit Economic Club: A Conversation on The Economy and Monetary Policy? |
| `KXPERSONMENTION-26APR07-WEAT` | `weather` | `mention_market` | `weather` | `True` | mention_market_format_warning | What will any NASA Participant say during Daily news conference on Artemis II (April 7, 2026)? |

## Warning Counts

- `mention_market_format_warning`: 2
- `public_event_source_label_overridden_warning`: 30
- `source_semantic_mismatch_warning`: 30

## Collector Diagnostics Schema

PR-CAL-10 also adds a reusable collector diagnostics schema for future local calibration collectors. It records discovered counts, pre-filter, post-filter, and selected normalized category counts, resolved/finalized/binary filter losses, candle attempt success and failure counts, candle failure reasons, quota targets, quota fills, quota shortfalls, and availability-limitation reasons. The schema is not wired into a new collection run in this PR.

## Recommended Next Step

Use the normalized taxonomy and diagnostics schema to prepare the next calibration-only retry design. Future collection should quota on normalized categories rather than raw Kalshi `public_event`, and should log pre-candle candidate counts plus candle failure reasons before interpreting any availability shortfall.

## Guardrails

| Guardrail | Value |
| --- | --- |
| `taxonomy_infrastructure_only` | `True` |
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
