# Historical Dataset Builder Specification

Date: 2026-06-05

Scope: dataset-builder specification only. This document defines the local JSONL
schema, validation rules, warning categories, output naming, and examples for a
future historical dataset builder. It does not implement downloader code, start
Phase 8, add broker integrations, add live trading, add private trading
endpoints, add a scheduler, add a daemon, add autostart, change strategy logic,
or make profitability claims.

## Design Goals

The builder must produce local JSONL datasets large enough to test Strategy v2
only when the data itself is good enough:

- At least 25 resolved binary markets.
- At least 250 point-in-time rows.
- At least 50 forecastable candidate rows before policy abstention.
- Enough accepted rows to allow 30 closed paper trades without forcing trades.
- 100% settlement coverage for scored markets.
- At least 95% evidence timestamp coverage for scored rows.

The schema has two profiles:

- `acceptance_candidate`: bid/ask, settlement, evidence timestamps, and source
  provenance are complete enough for Strategy v2 acceptance evaluation.
- `calibration_only_last_price`: close, last price, or OHLCV data exists, but
  point-in-time bid/ask is missing or unproven. This profile may support Brier
  score and calibration diagnostics only. It must not support paper PnL claims
  or Strategy v2 acceptance.

The current `historical-file` importer accepts the compact fields documented in
`docs/PHASE_7C_PR_D2_HISTORICAL_DATASET.md`. This Phase 7G schema is a superset:
future builders should keep the compact top-level fields for compatibility and
add richer provenance fields for validation and audit.

## JSONL Row Contract

Each non-empty line must be one JSON object. Timestamps must be ISO 8601 strings
with timezone. Probability fields must be on the YES probability scale from `0`
to `1`.

### Required Fields For Every Row

| Field | Type | Rule |
| --- | --- | --- |
| `schema_version` | string | Must equal `phase7g.historical_dataset.v1` for this spec. |
| `row_id` | string | Stable deterministic row id, unique within the dataset. |
| `dataset_id` | string | Stable dataset id shared by all rows in one export. |
| `dataset_label` | string | Examples: `kalshi_historical_local_v1`, `calibration_only_last_price`. |
| `profile` | string | `acceptance_candidate` or `calibration_only_last_price`. |
| `timestamp` | string | Point-in-time row timestamp before settlement for forecast rows. |
| `market_id` | string | Stable source market id, ticker, or token id. |
| `platform` | string | `kalshi`, `polymarket`, `manual_jsonl`, `public_dataset`, or other explicit source label. |
| `title` | string | Human-readable market title. |
| `market_type` | string | Must be `binary_prediction` for acceptance. |
| `outcome_side` | string | Must be `yes` for price fields in this schema. |
| `last_price` | number | Last YES price at or before `timestamp`; required for both profiles. |
| `implied_probability` | number | YES implied probability at or before `timestamp`; midpoint when bid/ask is valid. |
| `evidence` | array | Evidence objects. May be empty only outside acceptance or with warnings. |
| `source_provenance` | object | Source provenance object. Required for every row. |

### Required Fields For `acceptance_candidate`

| Field | Type | Rule |
| --- | --- | --- |
| `bid` | number | Best YES bid at or before `timestamp`, `0 <= bid <= 1`. |
| `ask` | number | Best YES ask at or before `timestamp`, `0 <= ask <= 1`, and `bid <= ask`. |
| `settlement` | object | Market-level settlement object with unambiguous final outcome. |
| `paper_pnl_allowed` | bool | Must be `true` only when bid/ask and settlement gates pass. |
| `acceptance_candidate` | bool | Must be `true` only when all data-level acceptance gates pass. |

### Required Fields For `calibration_only_last_price`

| Field | Type | Rule |
| --- | --- | --- |
| `bid` | number or null | Must be null when point-in-time bid is unavailable or unproven. |
| `ask` | number or null | Must be null when point-in-time ask is unavailable or unproven. |
| `settlement` | object | Required for scored calibration rows. |
| `paper_pnl_allowed` | bool | Must be `false`. |
| `acceptance_candidate` | bool | Must be `false`. |
| `calibration_only_reason` | string | Required reason, for example `missing_point_in_time_bid_ask`. |

### Optional Fields

| Field | Type | Purpose |
| --- | --- | --- |
| `date` | string | Date alias for compatibility; if present, must match `timestamp` date. |
| `market_url` | string | Public market URL. |
| `series_id` | string | Source event/series identifier. |
| `category` | string | Source or local category label. |
| `market_status_at_timestamp` | string | `open`, `closed`, `settled`, or `unknown` as of row timestamp. |
| `close_time` | string | Market close timestamp when available. |
| `volume` | number | Source volume at or before timestamp; semantics recorded in provenance. |
| `liquidity` | number | Source liquidity/depth at or before timestamp. |
| `spread` | number | May be derived as `ask - bid`; validator should recompute. |
| `orderbook_depth` | object | Optional point-in-time depth summary. |
| `trade_count` | number | Optional trade count for the row interval. |
| `counter_evidence` | array | Evidence objects that argue against the YES side. |
| `split` | string | `train`, `validation`, or `holdout` after split assignment. |
| `metadata` | object | Non-secret extra fields. |
| `settlement_outcome` | string | Compatibility field for current importer; use only on settlement/closing rows. |

For direct compatibility with the current `historical-file` importer, include
top-level `bid`, `ask`, `last_price`, `implied_probability`, `market_id`,
`platform`, `title`, and `evidence`. Include top-level `settlement_outcome` only
on the row that should close local paper positions. The nested `settlement`
object is for dataset audit and forecast scoring labels; it must not be passed
as forecast-time evidence.

## Evidence Object Schema

Evidence objects should use the current `EvidenceItem` fields where possible.
Extra attributes should be placed under `metadata` until a future validator
supports them directly.

### Required For Acceptance

| Field | Type | Rule |
| --- | --- | --- |
| `evidence_id` | string | Stable id unique within the dataset. |
| `source` | string | Source label, for example `official_stat_release`, `news_archive`, `market_rule`. |
| `title` | string | Short title. |
| `summary` | string | Short local summary, not hidden reasoning. |
| `published_at` | string | Must be at or before row `timestamp` for forecast rows. |
| `retrieved_at` | string | Retrieval/export timestamp. May be after the row timestamp if archival. |
| `relevance_score` | number | `0 <= relevance_score <= 1`. |
| `credibility_score` | number | `0 <= credibility_score <= 1`. |

### Optional Evidence Fields

| Field | Type | Purpose |
| --- | --- | --- |
| `url` | string | Public source URL when available. |
| `metadata.evidence_type` | string | `primary`, `official`, `news`, `market_rule`, `archive`, or `other`. |
| `metadata.timestamp_status` | string | `known`, `date_only`, `unknown`, or `inferred`. |
| `metadata.archived_url` | string | Archive URL if used. |
| `metadata.supports_side` | string | `yes`, `no`, `neutral`, or `settlement_only`. |
| `metadata.probability_hint` | number | Optional local hint; must be labeled and never treated as model alpha. |
| `metadata.availability_note` | string | Explanation when availability differs from retrieval. |

Evidence with missing or unknown `published_at` may be kept only in
non-acceptance diagnostics or as a warning. It must not count toward the 95%
evidence timestamp coverage requirement.

## Settlement Object Schema

The settlement object is label metadata. It is not forecast-time evidence.

### Required For Acceptance

| Field | Type | Rule |
| --- | --- | --- |
| `outcome` | string | `yes` or `no`. |
| `status` | string | `settled`, `determined`, or another explicit final status. |
| `resolved_at` | string | Resolution timestamp or best available date with timezone. |
| `label_available_at` | string | Time the outcome label became publicly knowable. |
| `source` | string | Resolution source label. |
| `source_url` | string | Public URL for resolution source when available. |
| `resolution_rule` | string | Short rule or source rule reference. |
| `verified_at` | string | Time the builder verified the label. |
| `ambiguous` | bool | Must be `false` for acceptance. |

### Optional Settlement Fields

| Field | Type | Purpose |
| --- | --- | --- |
| `method` | string | `official_market`, `official_external_source`, `manual_verification`, or `dataset_export`. |
| `settlement_price` | number | Final paper close price if explicitly sourced or locally defined. |
| `notes` | string | Short audit note. |
| `raw_outcome_value` | string | Source-native outcome label. |

Rules:

- `settlement.outcome` may be present on all rows for label audit, but the
  forecast builder must treat it as withheld label data.
- `settlement_outcome` at the top level should be present only on settlement or
  closing rows when using the current sandbox importer.
- Rows after `settlement.label_available_at` must not be used as forecast rows.

## Source Provenance Schema

`source_provenance` must be present on every row.

| Field | Type | Rule |
| --- | --- | --- |
| `source_name` | string | Human-readable source name. |
| `source_type` | string | `official_api`, `manual_jsonl`, `public_dataset`, `csv_export`, or `derived_local`. |
| `source_url` | string | Public source URL or local source descriptor. |
| `source_record_id` | string | Source-native row/market/trade/orderbook id when available. |
| `retrieved_at` | string | Time this source record was retrieved or exported. |
| `exported_at` | string | Time the local JSONL row was produced. |
| `raw_sha256` | string or null | Checksum of raw source record when available. |
| `transform_version` | string | Local builder or manual transform version. |
| `terms_review` | string | `reviewed_public_research_local_only`, `pending_review`, or `blocked`. |
| `network_used_by_builder` | bool | Whether the future builder used network while creating the local export. |
| `private_or_authenticated_source` | bool | Must be `false` for acceptance. |

Acceptance rows must have `terms_review=reviewed_public_research_local_only`,
`private_or_authenticated_source=false`, and no credential-like material in any
source field.

## Validation Errors

Validation errors must fail acceptance-candidate export.

| Code | Meaning |
| --- | --- |
| `invalid_json` | JSONL line is not valid JSON. |
| `row_not_object` | JSONL line is not an object. |
| `missing_required_field` | Required field missing for the selected profile. |
| `invalid_schema_version` | `schema_version` is unsupported. |
| `invalid_timestamp` | Timestamp cannot be parsed or has no timezone. |
| `date_timestamp_mismatch` | `date` alias does not match `timestamp` date. |
| `unsupported_market_type` | Market is not binary YES/NO for acceptance. |
| `invalid_probability` | Probability field is outside `[0, 1]` or not numeric. |
| `bid_exceeds_ask` | `bid > ask`. |
| `missing_bid_ask_for_acceptance` | Acceptance profile lacks proven bid/ask. |
| `duplicate_market_timestamp` | Duplicate `platform + market_id + timestamp`. |
| `duplicate_row_id` | Duplicate row id. |
| `future_evidence_leakage` | Evidence `published_at` is after row `timestamp`. |
| `evidence_timestamp_missing_for_acceptance` | Evidence lacks timestamp in an acceptance row. |
| `missing_settlement_for_scored_market` | Settlement object missing for scored market. |
| `ambiguous_settlement` | Settlement is disputed, ambiguous, canceled, or unsupported. |
| `post_settlement_forecast_row` | Forecast row timestamp is after outcome label availability. |
| `missing_source_provenance` | Source provenance is missing or incomplete. |
| `source_terms_blocked` | Terms review blocks local research export. |
| `private_source_detected` | Private/authenticated/user source is marked or detected. |
| `secret_pattern_detected` | Credential-like material found in row, provenance, or metadata. |

## Warning Categories

Warnings do not automatically fail calibration-only exports, but acceptance
validation may promote them to errors.

| Code | Meaning |
| --- | --- |
| `missing_evidence` | No evidence objects on the row. |
| `single_source_evidence` | Only one evidence source supports the row. |
| `timestamp_unknown` | Evidence timestamp is unknown or inferred. |
| `date_only_evidence_timestamp` | Evidence timestamp has date but not time. |
| `stale_evidence` | Latest evidence is older than the configured horizon. |
| `wide_spread` | Spread exceeds configured quality threshold. |
| `thin_liquidity` | Liquidity/depth below configured quality threshold. |
| `missing_volume` | Volume is missing. |
| `missing_liquidity` | Liquidity is missing. |
| `derived_bid_ask` | Bid/ask was derived from reciprocal book semantics; acceptable only with source proof. |
| `last_price_only` | Row cannot support paper PnL acceptance. |
| `source_terms_pending` | Source terms review not completed. |
| `coarse_timestamp` | Source timestamp is coarser than sampling cadence. |
| `calendar_gap` | Expected sampled timestamp missing. |
| `category_concentration` | Too many rows from one category. |
| `market_concentration` | Too many rows from one market. |

## Dataset-Level Quality Metrics

The builder manifest must report:

- `dataset_id`.
- `profile`.
- `row_count`.
- `market_count`.
- `resolved_binary_market_count`.
- `candidate_forecast_row_count`.
- `settlement_coverage_pct`.
- `evidence_timestamp_coverage_pct`.
- `duplicate_row_count`.
- `duplicate_market_timestamp_count`.
- `missing_bid_ask_count`.
- `bid_exceeds_ask_count`.
- `future_evidence_leakage_count`.
- `missing_source_provenance_count`.
- `warning_counts`.
- `error_counts`.
- `paper_pnl_allowed`.
- `acceptance_candidate`.
- `source_names`.
- `raw_export_checksums`.

## Output Naming Convention

Recommended local artifact names:

- Dataset JSONL:
  `data/historical/{dataset_id}.jsonl`
- Manifest JSON:
  `data/historical/{dataset_id}.manifest.json`
- Validation JSON:
  `data/historical/{dataset_id}.validation.json`
- Audit Markdown:
  `data/reports/historical_dataset/{dataset_id}_audit.md`

`dataset_id` format:

`phase7g_{source}_{profile}_{YYYYMMDD}_{markets}m_{rows}r_{short_hash}`

Examples:

- `phase7g_kalshi_acceptance_candidate_20260605_32m_480r_a1b2c3d4`
- `phase7g_polymarket_calibration_only_20260605_40m_960r_b4c5d6e7`
- `phase7g_manual_mixed_acceptance_candidate_20260605_25m_250r_c7d8e9f0`

## Example JSONL Rows

Example rows are illustrative and are not claims about real markets.

```jsonl
{"schema_version":"phase7g.historical_dataset.v1","row_id":"row_kalshi_demo_001_2026-05-01T20:00:00Z","dataset_id":"phase7g_kalshi_acceptance_candidate_demo","dataset_label":"kalshi_historical_local_v1","profile":"acceptance_candidate","timestamp":"2026-05-01T20:00:00Z","date":"2026-05-01","market_id":"KXDEMO-26MAY05-Y55","platform":"kalshi","title":"Will the demo metric exceed 55 by settlement?","market_type":"binary_prediction","outcome_side":"yes","bid":0.42,"ask":0.44,"last_price":0.43,"implied_probability":0.43,"liquidity":820.0,"volume":10450.0,"market_status_at_timestamp":"open","paper_pnl_allowed":true,"acceptance_candidate":true,"evidence":[{"evidence_id":"ev_kalshi_demo_001_a","source":"official_stat_release","title":"Demo metric preliminary release","url":"https://example.org/demo/prelim","published_at":"2026-05-01T16:00:00Z","retrieved_at":"2026-06-05T08:00:00Z","summary":"Preliminary public release was available before the market snapshot.","relevance_score":0.86,"credibility_score":0.9,"metadata":{"evidence_type":"official","timestamp_status":"known","supports_side":"yes"}}],"settlement":{"outcome":"yes","status":"settled","resolved_at":"2026-05-06T15:00:00Z","label_available_at":"2026-05-06T15:00:00Z","source":"official_market_resolution","source_url":"https://example.org/demo/resolution","resolution_rule":"YES if the final demo metric is above 55.","verified_at":"2026-06-05T08:30:00Z","ambiguous":false,"method":"manual_verification"},"source_provenance":{"source_name":"Kalshi public historical export","source_type":"official_api","source_url":"https://external-api.kalshi.com/trade-api/v2","source_record_id":"KXDEMO-26MAY05-Y55:2026-05-01T20:00:00Z","retrieved_at":"2026-06-05T08:00:00Z","exported_at":"2026-06-05T08:31:00Z","raw_sha256":null,"transform_version":"manual_phase7g_v1","terms_review":"reviewed_public_research_local_only","network_used_by_builder":true,"private_or_authenticated_source":false}}
{"schema_version":"phase7g.historical_dataset.v1","row_id":"row_kalshi_demo_001_2026-05-04T20:00:00Z","dataset_id":"phase7g_kalshi_acceptance_candidate_demo","dataset_label":"kalshi_historical_local_v1","profile":"acceptance_candidate","timestamp":"2026-05-04T20:00:00Z","date":"2026-05-04","market_id":"KXDEMO-26MAY05-Y55","platform":"kalshi","title":"Will the demo metric exceed 55 by settlement?","market_type":"binary_prediction","outcome_side":"yes","bid":0.61,"ask":0.64,"last_price":0.62,"implied_probability":0.625,"liquidity":1180.0,"volume":18200.0,"market_status_at_timestamp":"open","paper_pnl_allowed":true,"acceptance_candidate":true,"evidence":[{"evidence_id":"ev_kalshi_demo_001_b","source":"news_archive","title":"Demo metric update before close","url":"https://example.org/demo/update","published_at":"2026-05-04T14:00:00Z","retrieved_at":"2026-06-05T08:05:00Z","summary":"Public update was available before the sampled market timestamp.","relevance_score":0.78,"credibility_score":0.82,"metadata":{"evidence_type":"news","timestamp_status":"known","supports_side":"yes"}}],"settlement":{"outcome":"yes","status":"settled","resolved_at":"2026-05-06T15:00:00Z","label_available_at":"2026-05-06T15:00:00Z","source":"official_market_resolution","source_url":"https://example.org/demo/resolution","resolution_rule":"YES if the final demo metric is above 55.","verified_at":"2026-06-05T08:30:00Z","ambiguous":false,"method":"manual_verification"},"source_provenance":{"source_name":"Kalshi public historical export","source_type":"official_api","source_url":"https://external-api.kalshi.com/trade-api/v2","source_record_id":"KXDEMO-26MAY05-Y55:2026-05-04T20:00:00Z","retrieved_at":"2026-06-05T08:05:00Z","exported_at":"2026-06-05T08:31:00Z","raw_sha256":null,"transform_version":"manual_phase7g_v1","terms_review":"reviewed_public_research_local_only","network_used_by_builder":true,"private_or_authenticated_source":false}}
{"schema_version":"phase7g.historical_dataset.v1","row_id":"row_kalshi_demo_001_2026-05-06T16:00:00Z","dataset_id":"phase7g_kalshi_acceptance_candidate_demo","dataset_label":"kalshi_historical_local_v1","profile":"acceptance_candidate","timestamp":"2026-05-06T16:00:00Z","date":"2026-05-06","market_id":"KXDEMO-26MAY05-Y55","platform":"kalshi","title":"Will the demo metric exceed 55 by settlement?","market_type":"binary_prediction","outcome_side":"yes","bid":0.99,"ask":1.0,"last_price":1.0,"implied_probability":0.995,"liquidity":0.0,"volume":19000.0,"market_status_at_timestamp":"settled","paper_pnl_allowed":true,"acceptance_candidate":true,"evidence":[{"evidence_id":"ev_kalshi_demo_001_settle","source":"official_market_resolution","title":"Demo market resolves YES","url":"https://example.org/demo/resolution","published_at":"2026-05-06T15:00:00Z","retrieved_at":"2026-06-05T08:30:00Z","summary":"Official resolution source reported the YES outcome after the forecast period.","relevance_score":0.95,"credibility_score":0.95,"metadata":{"evidence_type":"official","timestamp_status":"known","supports_side":"settlement_only"}}],"settlement":{"outcome":"yes","status":"settled","resolved_at":"2026-05-06T15:00:00Z","label_available_at":"2026-05-06T15:00:00Z","source":"official_market_resolution","source_url":"https://example.org/demo/resolution","resolution_rule":"YES if the final demo metric is above 55.","verified_at":"2026-06-05T08:30:00Z","ambiguous":false,"method":"manual_verification","settlement_price":1.0},"settlement_outcome":"yes","source_provenance":{"source_name":"Kalshi public historical export","source_type":"official_api","source_url":"https://external-api.kalshi.com/trade-api/v2","source_record_id":"KXDEMO-26MAY05-Y55:settlement","retrieved_at":"2026-06-05T08:30:00Z","exported_at":"2026-06-05T08:31:00Z","raw_sha256":null,"transform_version":"manual_phase7g_v1","terms_review":"reviewed_public_research_local_only","network_used_by_builder":true,"private_or_authenticated_source":false}}
```

## Acceptance Boundary

A dataset may be used for Strategy v2 acceptance only when:

- `profile=acceptance_candidate`.
- `acceptance_candidate=true`.
- `paper_pnl_allowed=true`.
- All validation error counts are zero.
- Required data-level gates in
  `docs/reports/phase7g_dataset_acquisition_plan.md` pass.
- The offline evaluator still reports safety invariants intact.

Any dataset with missing or unproven historical bid/ask must remain
calibration-only, even if it has many markets, rows, settlement labels, and good
evidence timestamps.
