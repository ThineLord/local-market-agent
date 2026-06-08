# Kalshi Normalized Collector Diagnostics Hardening

Scope: PR-CAL-13 diagnostics and taxonomy hardening only. This change does not
run a new collection, build a new historical dataset, import calibration rows,
collect or approve evidence, invent bid/ask, modify strategy logic, modify
acceptance gates, start Phase 8, add broker/live trading, add scheduler
behavior, or make paper-PnL, profitability, acceptance, Strategy v2 superiority,
or live-readiness claims.

## Summary

PR-CAL-13 hardens the temporary normalized-category Kalshi calibration collector
before any larger retry. The collector can now persist bounded diagnostics-only
examples of normalized candidates that were discovered but not selected, and the
shared `CollectorDiagnostics` schema records per-category candle attempts,
successes, failures, failure reasons, selected market counts, and selected row
counts while preserving the prior aggregate fields.

No new historical dataset was collected or imported for this PR.

## Collector Diagnostics

New diagnostics-only export files for future collector runs:

- `unselected_candidates.jsonl`
- `unselected_candidates_summary.md`

The default retained-example cap is 25 candidates per normalized category. Each
example includes ticker, title, event metadata when present, source category,
normalized category, semantic category, confidence, matched rules, warnings,
reason, and explicit `diagnostics_only` / `not_imported_as_historical_rows`
flags.

New additive `CollectorDiagnostics` fields:

- `selected_row_counts`
- `per_category_candle_attempt_counts`
- `per_category_candle_success_counts`
- `per_category_candle_failure_counts`
- `per_category_candle_failure_reasons`
- `per_category_selected_market_counts`
- `per_category_selected_row_counts`
- `per_category`

The existing aggregate fields remain unchanged for backward compatibility.

## Reader Compatibility

`lma normalize-category-export` now reads `unselected_candidates.jsonl` when it
exists and safely reports it as missing otherwise.

`lma normalized-availability-audit` now reads unselected candidate diagnostics
when present, uses them for weather examples and Fed/macro boundary review, and
continues to tolerate old diagnostics payloads that lack per-category fields.

## Taxonomy Boundary

The taxonomy rules changed narrowly:

- Added deterministic Fed/federal-funds matching.
- Expanded rate-policy matching to hyphenated and plural forms such as
  `interest-rate`, `rate cuts`, `rate hikes`, and `cut rates`.

Boundary retained:

- FOMC, Federal Reserve, Fed funds, interest-rate, rate cut, rate hike, CPI, and
  inflation map to `fed_policy_macro` when the market is actually about macro
  policy.
- Unemployment, jobs report, nonfarm payrolls, GDP, and Treasury yields remain
  `economics_other` unless an explicit Fed/rate/CPI/FOMC policy signal is
  present.
- Company earnings, stock, crypto, and sports examples do not map to
  `fed_policy_macro`.
- Mention-market format still overrides the final normalized category to
  `mention_market` while preserving the topical semantic category.

## Tests

Deterministic tests cover:

- capped unselected candidate examples by normalized category;
- unselected candidates not being imported as historical rows;
- per-category candle attempt/success/failure counts;
- per-category candle failure reason aggregation;
- backward compatibility with old diagnostics payloads;
- Fed/macro positive taxonomy cases;
- Fed/macro negative taxonomy cases and economics boundaries;
- mention-market override behavior;
- CLI/report readers tolerating missing or present unselected diagnostics;
- no broker/live/order API dependency.

## Recommended Next Step

Use PR-CAL-13 as the diagnostics baseline for PR-CAL-14 or the next bounded
calibration-only retry design. The next retry should remain calibration-only and
should use the new unselected-candidate files plus per-category candle
diagnostics before interpreting any weather or Fed/macro availability shortfall.
