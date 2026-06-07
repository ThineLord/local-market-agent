# Calibration Dataset Plan

Date: 2026-06-07

Scope: DATA-CALIBRATION-1 planning and specification only. This plan does not
implement data collection, modify strategy logic, change acceptance gates, clear
terms review, approve evidence, start Phase 8, add broker integrations, add live
trading, or add scheduler/daemon/autostart behavior.

## Executive Recommendation

Build a calibration-first dataset path before attempting another broad
acceptance-candidate sprint.

The next implementation should be:

```text
PR-CAL-1 Calibration Dataset Audit
```

Use PR-CAL-1 to define and verify the audit semantics for calibration-only
datasets before adding or widening an import path. The repo already has manual
builder/importer and Kalshi export-adapter concepts, but the next risk is not
the lack of one more collection mechanism. The immediate risk is mixing
calibration diagnostics with acceptance claims. An audit-first PR should make
that boundary machine-visible in reports before any larger calibration import is
used for Strategy v2 comparison.

PR-CAL-1 should not collect data. It should specify or verify that a dataset is
clearly labeled as calibration-only, that settlement coverage is measured, that
missing timestamp-safe evidence blocks acceptance status, and that paper PnL or
Strategy v2 superiority claims stay disabled unless a later acceptance dataset
passes the existing gates.

## Context

DATA-COLLECT-3 established that broad acceptance-candidate collection is
bottlenecked by timestamp-safe evidence:

| Sprint | Markets | Candles | Evidence candidates | Timestamp coverage |
| --- | ---: | ---: | ---: | ---: |
| Sprint 1 | 10 | 100 | 20 | 0% |
| Sprint 2 | 4 | 20 | 8 | 0% |

Sprint 1 reached the rough row shape but selected evidence-hostile markets.
Sprint 2 avoided several traps but became too small and still produced no
timestamp-safe evidence. That means the next useful dataset should stop trying
to look acceptance-ready and instead evaluate forecasting quality from price and
settlement history while preserving all acceptance blockers.

## Dataset Tiers

### A. Minimum Calibration Dataset

Purpose:

- Prove calibration-only import, audit, and Strategy v1/v2 diagnostic reporting
  on a non-trivial sample.
- Establish whether the evaluator can compute forecast-quality metrics without
  acceptance evidence.
- Provide no acceptance, profitability, or superiority claim.

Targets:

| Requirement | Target |
| --- | --- |
| Market count | 25 resolved binary markets |
| Row count | 250 point-in-time rows |
| Rows per market | 8 to 12 |
| Categories | At least 3 categories |
| Category concentration | No category above 50% of rows |
| Settlement coverage | 100% for scored markets and rows |
| Evidence requirements | Evidence optional; allowed to be empty or timestamp-missing if labeled non-acceptance |
| Terms status | May remain pending for acceptance; source terms must still be documented for local calibration use |
| Expected effort | 8 to 16 hours if based on local public exports; 16 to 24 hours if manual cleanup is needed |

Recommended category mix:

| Category | Minimum markets |
| --- | ---: |
| Major sports or simple public events | 8 |
| Macro/Fed/government/weather-style markets | 8 |
| Company/public event or miscellaneous public markets | 7 |
| Buffer markets | 2 |

Success means the dataset can support Brier score, calibration buckets,
coverage, abstention, structured completeness, and baseline comparison
diagnostics. It still cannot pass the acceptance gate because evidence
timestamp coverage may be below 95%.

### B. Preferred Calibration Dataset

Purpose:

- Provide a useful first Strategy v2 diagnostic set with enough rows for
  populated calibration buckets and split-aware analysis.
- Identify whether Strategy v2 has forecast-signal value before spending
  human time on acceptance-size evidence curation.
- Keep the dataset clearly non-acceptance unless all existing acceptance
  preconditions independently pass.

Targets:

| Requirement | Target |
| --- | --- |
| Market count | 60 resolved binary markets |
| Row count | 720 point-in-time rows |
| Rows per market | 10 to 14 |
| Categories | At least 5 categories |
| Category concentration | No category above 35% of rows |
| Settlement coverage | 100% for scored rows; unresolved or ambiguous markets excluded from scored calibration |
| Evidence requirements | Source-family notes and optional candidate evidence allowed; timestamp-safe evidence not required for calibration label |
| Terms status | Local research/retention terms documented; pending acceptance terms must block acceptance labels |
| Expected effort | 24 to 40 hours if using existing local export patterns; 40 to 60 hours if market-family targeting and cleanup are manual |

Recommended category mix:

| Category | Target markets |
| --- | ---: |
| Macro/economic indicators | 12 |
| Fed/government/public-policy events | 10 |
| Weather/climate events | 10 |
| Major sports with simple binary settlement | 10 |
| Company/public event markets | 8 |
| Miscellaneous public events | 10 |

This is the recommended target for the next real calibration dataset. It is
large enough to make the forecast diagnostics informative while still small
enough to inspect manually for malformed markets, duplicate timestamps, and
settlement ambiguity.

### C. Stretch Calibration Dataset

Purpose:

- Support stronger walk-forward diagnostics and more stable calibration bucket
  estimates.
- Improve category and time-horizon diversity.
- Prepare for later acceptance-evidence pilots by revealing which market
  families have reliable price and settlement history.

Targets:

| Requirement | Target |
| --- | --- |
| Market count | 150 resolved binary markets |
| Row count | 2,000 to 2,500 point-in-time rows |
| Rows per market | 12 to 18 |
| Categories | At least 6 categories |
| Category concentration | No category above 25% of rows |
| Settlement coverage | 100% for scored rows; unresolved or disputed markets excluded or separately labeled |
| Evidence requirements | Evidence metadata optional; timestamp-safe acceptance evidence not required; source-family notes required |
| Terms status | Local calibration-use terms documented; no acceptance label if terms or evidence remain incomplete |
| Expected effort | 80 to 140 hours, mostly market screening, settlement verification, deduplication, and audit repair |

Recommended category mix:

| Category | Target markets |
| --- | ---: |
| Macro/economic indicators | 25 |
| Fed/government/public-policy events | 25 |
| Weather/climate events | 25 |
| Major sports with simple binary settlement | 25 |
| Company/public event markets | 20 |
| Miscellaneous public events | 30 |

Use the stretch target only after the preferred dataset proves that the audit
and evaluator outputs are stable. It is not a substitute for acceptance evidence.

## Metrics Allowed Without Acceptance Evidence

The following metrics can be evaluated on a calibration-only dataset when
settlement is known and every report labels the result as non-acceptance:

| Metric | Allowed? | Requirements | Claim boundary |
| --- | --- | --- | --- |
| Brier score | Yes | Structured forecast probability and known binary settlement | Forecast diagnostic only |
| Calibration buckets | Yes | Enough rows per bucket and known settlement | Reliability diagnostic only |
| Forecast coverage | Yes | Row count, forecast count, and rejection reasons | Measures forecast availability, not acceptance |
| Abstention rate | Yes | Strategy outputs or explicit observe/reject records | Activity diagnostic only |
| Structured completeness | Yes | Forecast assessment fields and rejection reasons | Provider/evaluator quality only |
| Strategy v1 vs v2 comparison | Yes | Same rows, same settlement labels, same paper-only assumptions | Diagnostic comparison only; no superiority claim |
| Paper simulation metrics | Limited yes | Bid/ask or declared last-price simulation profile plus settlement | Simulation diagnostics only; no paper PnL acceptance |

Paper simulation metrics are allowed only when the report states the fill model
plainly. If bid/ask is incomplete and last price is used, the output must remain
`calibration_only_last_price` and paper PnL must be treated as non-acceptance.

## Metrics Still Blocked

The following remain blocked until an acceptance-candidate dataset passes the
existing data-level gates:

| Metric or claim | Blocker |
| --- | --- |
| Acceptance gate pass | Requires existing gate preconditions, including sample size, settlement, evidence timestamp coverage, activity, safety, and replay checks |
| Evidence completeness | Requires reviewed evidence records, timestamp-safe `published_at`, and human/source review |
| Timestamp-safe acceptance evaluation | Requires evidence available at or before each forecast timestamp and no future leakage |
| Strategy v2 superiority claim | Requires `gate_status=pass` and `superiority_claim_allowed=true` |
| Acceptance paper PnL claim | Requires acceptance-candidate profile, complete bid/ask, settlement, evidence, terms, and gate pass |
| Production readiness | Remains out of scope; no Phase 8, broker, scheduler, or live-trading implication |

## Recommended Workflow

1. PR-CAL-1 Calibration Dataset Audit.
2. Use the audit to classify any local dataset as calibration-only,
   acceptance-candidate, or invalid without changing acceptance gates.
3. Only after audit semantics are stable, add or widen a calibration import path
   if existing builder/importer paths cannot express the preferred dataset.
4. Run Strategy v2 offline evaluation as a diagnostic only on the minimum or
   preferred calibration dataset.
5. Keep a separate manually targeted acceptance-evidence pilot for source
   families with known timestamp-safe evidence.

## Go/No-Go Criteria

Go to the minimum calibration dataset when:

- settlement coverage can be made 100% for at least 25 resolved binary markets;
- rows are point-in-time and duplicate-free;
- the dataset label prevents acceptance and superiority claims;
- source terms are documented for local calibration use.

Go to the preferred calibration dataset when:

- the minimum dataset audit has no schema errors;
- Strategy v1/v2 diagnostics run without acceptance claims;
- category concentration and duplicate-market-family risk are visible in the
  report.

Stop or downgrade when:

- settlement cannot be verified;
- row timestamps or market identifiers are unstable;
- source terms prohibit local retention;
- secret-like material appears in source files;
- report language implies acceptance despite missing timestamp-safe evidence.

## Expected Value

The expected value of calibration-first work is decision quality, not acceptance
readiness. A calibration dataset can answer whether Strategy v2 forecasts are
structured, available, calibrated, and meaningfully different from Strategy v1
and market-implied baselines. It can also reveal whether the system abstains for
the right reasons before the project spends 40+ hours curating acceptance-grade
evidence.

The expected non-value is equally important: it will not clear evidence
coverage, terms review, acceptance gates, Phase 8 readiness, or live-trading
readiness.

## Safety Notes

This plan is docs-only and paper-only. It does not add data collection, network
automation, source adapters, strategy changes, risk-gate changes,
acceptance-gate changes, broker integrations, live trading, account/order/fill
paths, scheduler/daemon/autostart behavior, Phase 8 work, or direct
LLM-to-order paths.
