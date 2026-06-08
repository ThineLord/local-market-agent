# Acceptance Candidate Shortlist Template

Scope: ACCEPT-2 documentation/template only. This template does not collect
data, approve evidence, build an acceptance dataset, implement a collector,
scrape sources, automate a browser, mutate source terms, change strategy logic,
change acceptance gates, start Phase 8, add broker/live/order/account,
portfolio/fill paths, add scheduler/daemon/autostart behavior, or make
profitability, paper-PnL, Strategy v2 superiority, acceptance-ready, or
live-readiness claims.

## Purpose

Use this artifact to manually pre-screen 8 to 12 candidate Kalshi markets and
select the strongest 5 to 10 for a future manual acceptance-evidence pilot.
This is a source-quality planning step only. Do not stage a local export, write
approved evidence, import acceptance rows, or run acceptance evaluation from
this template.

The future pilot target remains:

- 5 to 10 resolved binary markets.
- 5 to 12 pre-settlement rows per market.
- At least 2 public evidence items per market where possible.
- 100% settlement coverage.
- 100% evidence timestamp coverage for acceptance-candidate rows.
- Point-in-time bid/ask required; no bid/ask invention.
- `terms_review=pending_review` unless separately reviewed.

## Decision Values

Use these controlled values where possible:

| Field | Suggested values |
| --- | --- |
| `market_family` | `fed_fomc_rate`, `cpi_inflation`, `jobs_nfp`, `official_weather`, `major_sports`, `crypto_benchmark`, `reject_other` |
| `has_point_in_time_bid_ask_source` | `yes`, `no`, `unknown` |
| `timestamp_confidence` | `high`, `medium`, `low`, `reject` |
| `terms_status` | `pending_review`, `reviewed_public_research_local_only`, `blocked`, `unknown` |
| `shortlist_decision` | `select`, `alternate`, `reject`, `needs_more_review` |

`terms_status=pending_review` blocks acceptance claims. It does not block
manual pre-screening, but it must remain visible in every candidate row.

## Copyable CSV Header

```csv
candidate_id,market_ticker,market_title,market_family,market_close_time,expected_resolution_source,proposed_row_time_window,has_point_in_time_bid_ask_source,forecast_evidence_url_1,forecast_evidence_visible_timestamp_1,forecast_evidence_url_2,forecast_evidence_visible_timestamp_2,settlement_source_url,settlement_source_timestamp_or_label_available_at,timestamp_confidence,terms_status,rejection_reason_if_any,reviewer_notes,shortlist_decision
```

## Blank Shortlist Rows

Copy these rows into a local notes file or spreadsheet if useful. Keep raw
exports and filled worksheets local unless a separate publication review allows
sharing.

```csv
candidate_01,,,,,,,,,,,,,,,,,,
candidate_02,,,,,,,,,,,,,,,,,,
candidate_03,,,,,,,,,,,,,,,,,,
candidate_04,,,,,,,,,,,,,,,,,,
candidate_05,,,,,,,,,,,,,,,,,,
candidate_06,,,,,,,,,,,,,,,,,,
candidate_07,,,,,,,,,,,,,,,,,,
candidate_08,,,,,,,,,,,,,,,,,,
candidate_09,,,,,,,,,,,,,,,,,,
candidate_10,,,,,,,,,,,,,,,,,,
candidate_11,,,,,,,,,,,,,,,,,,
candidate_12,,,,,,,,,,,,,,,,,,
```

## Field Guide

| Column | How to fill it |
| --- | --- |
| `candidate_id` | Stable local id such as `candidate_01`. |
| `market_ticker` | Kalshi market ticker from the public market page or local note. |
| `market_title` | Human-readable market title. |
| `market_family` | One of the family values above. Prefer the most specific source family. |
| `market_close_time` | Market close timestamp if known, with timezone. Use `unknown` if not visible. |
| `expected_resolution_source` | Short source label, such as `Federal Reserve statement`, `BLS CPI release`, `NOAA/NWS observation`, or `official league box score`. |
| `proposed_row_time_window` | Planned row window, such as `T-7d to T-1h`, `pre-release daily`, or exact timestamps if already known. |
| `has_point_in_time_bid_ask_source` | `yes` only when bid and ask fields can be sourced as bid/ask at or before row timestamps. Last price alone is `no`. |
| `forecast_evidence_url_1` | Public URL for the strongest forecast-time evidence item. |
| `forecast_evidence_visible_timestamp_1` | Visible `published_at`, issued time, release time, or archive timestamp for evidence 1. Include timezone or timezone basis. |
| `forecast_evidence_url_2` | Public URL for the second independent forecast-time evidence item, if available. |
| `forecast_evidence_visible_timestamp_2` | Visible timestamp for evidence 2. Leave blank only if the reviewer records why one source is sufficient for pre-screening. |
| `settlement_source_url` | Public URL expected to verify the final outcome. |
| `settlement_source_timestamp_or_label_available_at` | Expected or observed time the settlement label became publicly knowable. |
| `timestamp_confidence` | `high` only when source timestamps and timezones are unambiguous. Use `reject` for ambiguous timestamps. |
| `terms_status` | Keep `pending_review` unless a separate terms review records another value. |
| `rejection_reason_if_any` | Required for rejected candidates. Use concise blocker text. |
| `reviewer_notes` | Short manual note explaining source fit, ambiguity, or follow-up needed. |
| `shortlist_decision` | `select`, `alternate`, `reject`, or `needs_more_review`. |

## Example Non-Approved Row

This is an illustrative template row, not approved evidence and not a market
recommendation:

```csv
candidate_01,KXEXAMPLE-26JUN,FOMC target range example,fed_fomc_rate,2026-06-17T18:00:00Z,Federal Reserve FOMC statement,T-7d to T-1h,unknown,https://example.org/fed-calendar,2026-05-01T12:00:00Z,https://example.org/public-preview,2026-06-10T14:30:00Z,https://example.org/fomc-statement,2026-06-17T18:00:00Z,medium,pending_review,,Template example only; not collected or approved,needs_more_review
```

## Manual Procedure

1. Manually inspect 8 to 12 candidate markets using public, non-authenticated
   pages only.
2. Fill every shortlist column for each candidate.
3. Reject anything with ambiguous evidence timestamps, unclear timezones,
   missing bid/ask source, private/authenticated source needs, or disputed
   settlement.
4. Pick 5 to 10 survivors with the strongest timestamp-safe forecast evidence
   and public settlement sources.
5. Only after the shortlist is reviewed, stage a future local export manually
   under the normal local-export workflow.

Do not use this shortlist to approve evidence, write `evidence.jsonl`, import
`acceptance_candidate` rows, or run `strategy-eval-offline`.

## Family-Specific Pre-Screen Notes

| Family | Prefer | Reject |
| --- | --- | --- |
| Fed/FOMC/rate decisions | Official Federal Reserve calendars, statement pages, target-rate tables, timestamped pre-meeting public previews. | Rows where the post-meeting statement is the only forecast evidence for pre-statement timestamps. |
| CPI/inflation | BLS release calendars, CPI release pages, official tables, timestamped pre-release context. | CPI report used as forecast evidence for rows before the report timestamp. |
| Unemployment/jobs/nonfarm payrolls | BLS Employment Situation calendars, official releases, timestamped public previews. | Generic economic commentary with unclear publication time or no rule mapping. |
| Official-only weather | NOAA/NWS/NHC issued-time products, official station observations, archived advisories. | Aggregator pages, missing issued time, unclear location/window mapping. |
| Major sports | Official league/team schedules, timestamped official previews, official final box scores for settlement. | Untimestamped schedule pages or final scores used as pre-game forecast evidence. |
| Crypto benchmark markets | Official benchmark administrator methodology and timestamped benchmark records. | Current price pages without archive/time proof, generic exchange prices when the rules name a benchmark. |

## Selection Preference

Rank candidates by:

1. Timestamp confidence.
2. Public and non-authenticated source quality.
3. Rule-compatible settlement clarity.
4. Proven point-in-time bid/ask availability.
5. Family diversity across the 5 to 10 selected survivors.

The best first shortlist should be weighted toward Fed/FOMC, CPI, jobs/NFP,
official-only weather, and timestamp-safe major sports. Crypto benchmark
markets should remain conditional until benchmark timestamp safety is proven.
