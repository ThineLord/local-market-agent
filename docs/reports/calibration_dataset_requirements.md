# Calibration Dataset Requirements

Date: 2026-06-07

Scope: DATA-CALIBRATION-1 requirements only. This document defines a
calibration-only dataset contract for evaluating forecast quality without
acceptance-candidate evidence completeness. It does not implement data
collection, modify strategy logic, change acceptance gates, approve evidence,
clear terms review, start Phase 8, add broker integrations, add live trading,
or add scheduler/daemon/autostart behavior.

## Dataset Classification

A calibration dataset is a local historical dataset used to evaluate forecast
quality from point-in-time market prices and settlement outcomes. It is not an
acceptance-candidate dataset unless every existing acceptance requirement also
passes.

Required classification fields:

| Field | Required value for calibration-only |
| --- | --- |
| `profile` | `calibration_only_last_price` or another explicit calibration-only profile |
| `acceptance_candidate` | `false` |
| `paper_pnl_allowed` | `false` |
| `superiority_claim_allowed` | `false` |
| `terms_review` | Recorded; pending or incomplete terms block acceptance labels |
| `evidence_timestamp_coverage_pct` | Reported, but not required to exceed 0% for calibration-only |
| `settlement_coverage_pct` | 100% for scored rows |

The audit must treat missing evidence as a calibration warning and an acceptance
blocker, not as a calibration error when the profile is explicitly
calibration-only.

## Required Row Fields

Each calibration row should include:

| Field | Required | Rule |
| --- | --- | --- |
| `dataset_id` | yes | Stable local dataset identifier |
| `row_id` | yes | Stable row identifier |
| `market_id` or `market_ticker` | yes | Stable market identifier |
| `timestamp` | yes | Point-in-time row timestamp |
| `platform` | yes | Source label such as `kalshi` |
| `title` | recommended | Human-readable market title |
| `category` | yes | Normalized category for concentration reporting |
| `last_price` | yes | YES probability or price on `[0, 1]` scale |
| `implied_probability` | yes | May equal `last_price` or a documented midpoint |
| `bid` | optional | Required only for bid/ask simulation or acceptance paths |
| `ask` | optional | Required only for bid/ask simulation or acceptance paths |
| `volume` | recommended | Missing volume must be reported |
| `liquidity` | recommended | Missing liquidity must be reported |
| `settlement_outcome` | yes for scored rows | `yes` or `no` |
| `settlement_timestamp` | recommended | Required when available from local metadata |
| `evidence` | optional | Missing or timestamp-unknown evidence blocks acceptance only |
| `source_provenance` | yes | Non-secret source/export notes |

Rows with malformed probabilities, duplicate `market_id + timestamp`, ambiguous
settlement, future-dated rows, or secret-like material should fail audit even in
calibration-only mode.

## Dataset Tiers

### Minimum Calibration Dataset

| Requirement | Minimum |
| --- | --- |
| Market count | 25 resolved binary markets |
| Row count | 250 point-in-time rows |
| Category count | At least 3 |
| Settlement coverage | 100% for scored rows |
| Evidence requirements | Evidence optional; if present, timestamp status must be reported |
| Expected effort | 8 to 16 hours for local-export cleanup; 16 to 24 hours if manual market repair is needed |

Minimum category requirement:

- at least 8 major-sports or simple public-event markets;
- at least 8 macro/Fed/government/weather-style markets;
- at least 7 company/public-event or miscellaneous markets;
- 2 buffer markets for replacement after audit exclusions.

### Preferred Calibration Dataset

| Requirement | Preferred |
| --- | --- |
| Market count | 60 resolved binary markets |
| Row count | 720 point-in-time rows |
| Category count | At least 5 |
| Settlement coverage | 100% for scored rows |
| Evidence requirements | Optional evidence/source-family notes; timestamp-safe evidence not required for calibration label |
| Expected effort | 24 to 40 hours with reusable local export flow; 40 to 60 hours with manual targeting and repair |

Preferred category requirement:

- 12 macro/economic indicator markets;
- 10 Fed/government/public-policy markets;
- 10 weather/climate markets;
- 10 major-sports simple binary markets;
- 8 company/public-event markets;
- 10 miscellaneous public-event markets.

### Stretch Calibration Dataset

| Requirement | Stretch |
| --- | --- |
| Market count | 150 resolved binary markets |
| Row count | 2,000 to 2,500 point-in-time rows |
| Category count | At least 6 |
| Settlement coverage | 100% for scored rows |
| Evidence requirements | Optional evidence metadata; source-family notes required; timestamp-safe acceptance evidence still not required |
| Expected effort | 80 to 140 hours |

Stretch category requirement:

- no category above 25% of rows;
- no event family above 15% of rows;
- at least 20 markets outside sports and crypto-like short-window families;
- enough date diversity to support walk-forward diagnostics.

## Settlement Requirements

Calibration metrics require known outcomes. Therefore:

- every scored market must be resolved binary;
- every scored row must join to `settlement_outcome=yes` or
  `settlement_outcome=no`;
- ambiguous, disputed, or unavailable settlements must be excluded from scored
  Brier/calibration metrics or reported separately as missing settlement;
- settlement labels must come from local historical metadata, not broker,
  account, order, or private trading endpoints;
- settlement coverage must be reported by row and by market.

The minimum, preferred, and stretch tiers all require 100% settlement coverage
for scored rows. A dataset may contain unscored diagnostic rows, but those rows
must not enter Brier score, calibration buckets, paper simulation metrics, or
Strategy v1/v2 comparison.

## Evidence Requirements

Calibration-only datasets do not require acceptance-candidate evidence
completeness.

Allowed calibration evidence states:

| Evidence state | Calibration use | Acceptance use |
| --- | --- | --- |
| Empty evidence array | Allowed with warning | Blocked |
| Candidate evidence with missing timestamp | Allowed with warning | Blocked |
| Timestamp-safe evidence below 95% coverage | Allowed with warning | Blocked |
| 95%+ timestamp-safe evidence but terms pending | Allowed for calibration | Blocked |
| Reviewed timestamp-safe evidence and terms complete | Eligible for acceptance audit if all other gates pass | Possible |

Evidence still must not contain private/authenticated sources, credentials,
cookies, browser data, or copied final-result material presented as
forecast-time evidence.

## Metrics Allowed Without Acceptance Evidence

These metrics are allowed when the dataset is labeled calibration-only and has
known settlement outcomes:

| Metric | Requirement | Notes |
| --- | --- | --- |
| Brier score | Structured probability and binary settlement | Compare Strategy v1, Strategy v2, and market-implied baselines |
| Calibration buckets | Enough rows per bucket and binary settlement | Report row count, mean forecast, observed YES rate, and absolute gap |
| Forecast coverage | Evaluated rows and forecast/rejection counts | Separates missing forecasts from abstentions |
| Abstention rate | Strategy action output | Report observe/reject reasons |
| Structured completeness | Forecast assessment fields | Report missing/prose-only/out-of-range probabilities |
| Strategy v1 vs v2 comparison | Same rows and same local assumptions | Diagnostic only; no superiority claim |
| Paper simulation metrics | Declared simulation model and settlement | Limited to non-acceptance simulation diagnostics |

Paper simulation metrics must disclose whether they use bid/ask, midpoint, or
last price. Last-price simulation is useful for debugging behavior, but it must
not be represented as acceptance paper PnL.

## Metrics And Claims Still Blocked

These remain blocked for calibration-only datasets:

| Blocked item | Reason |
| --- | --- |
| Acceptance gate pass | Existing gate requires acceptance-size data, evidence coverage, settlement, activity, safety, and replay checks |
| Evidence completeness | Requires reviewed timestamp-safe evidence, not candidate discovery |
| Timestamp-safe acceptance evaluation | Requires `published_at <= row.timestamp` for accepted evidence and no future leakage |
| Strategy v2 superiority claim | Requires `gate_status=pass` and `superiority_claim_allowed=true` |
| Acceptance paper PnL claim | Requires acceptance-candidate data and existing gate pass |
| Live or production readiness | Out of scope and prohibited |

## Audit Requirements For PR-CAL-1

PR-CAL-1 should be `Calibration Dataset Audit`.

Minimum audit outputs:

- dataset classification;
- market count;
- row count;
- category count and concentration;
- settlement coverage by market and row;
- evidence timestamp coverage by market and row;
- duplicate row count;
- malformed probability count;
- missing source provenance count;
- secret-like material count;
- forecast-metric eligibility;
- paper-simulation eligibility;
- acceptance-blocker list;
- explicit `superiority_claim_allowed=false` for calibration-only datasets.

The audit should make it hard for reports to blur calibration diagnostics into
acceptance. This is a prerequisite to any future `Calibration Dataset Import
Path` because importing a larger dataset without a clear audit boundary would
increase the chance of accidental claims from non-acceptance data.

## Import Path Requirements For A Later PR

A later import-path PR may be useful after the audit exists. That PR should:

- reuse existing local/manual import patterns where possible;
- accept local files only;
- avoid network collection and source automation unless explicitly scoped in a
  separate future task;
- preserve calibration-only labels;
- reject or warn on acceptance-only fields that are incomplete;
- never mutate acceptance gates to make calibration data pass.

## Safety Notes

These requirements are docs-only and paper-only. They add no data collection,
downloader implementation, source adapter, strategy logic change, acceptance
gate change, risk gate change, broker integration, live trading, account/order
path, scheduler/daemon/autostart behavior, Phase 8 work, or direct
LLM-to-order path.
