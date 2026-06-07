# Kalshi Sprint 2 Failure Analysis

Date: 2026-06-07

Scope: DATA-COLLECT-3 audit and planning only. This report does not implement
a new collector, modify strategy logic, change acceptance gates, approve
evidence, clear terms review, start Phase 8, add broker integrations, add live
trading, or add scheduler/daemon/autostart behavior.

## Executive Diagnosis

Sprint 2 succeeded as a local public-data collection smoke test, but failed to
produce an acceptance-shaped dataset.

Final DATA-COLLECT-2 output:

- Export id: `kalshi_sprint2_evidence_friendly_20260606`
- Markets selected: 4
- Candles collected: 20
- Evidence candidates generated: 8
- Candidate timestamp status: `missing=8`
- `evidence.jsonl`: empty
- `terms_review`: `pending_review`

It missed every acceptance-shape target:

- 10-market pilot target was not met.
- 100-200 candle-row pilot target was not met.
- 3-category diversity target was not met.
- Evidence timestamp coverage stayed 0%.

The root cause is not one bug. It is a mismatch between a broad recent Kalshi
resolved-market crawl and the much narrower acceptance-candidate requirements:
timestamp-safe evidence, category diversity, usable pre-settlement bid/ask
candles, and reviewed terms.

## Why Only 4 Markets Were Selected

The Sprint 2 collector discovered 11,639 candidate markets and scored all of
them, but only 4 were selected after filtering and candle checks.

The final selected markets were all major-sports Champions League derivatives:

| Market | Category | Candles | Score |
|---|---:|---:|---:|
| `KXUCLTCORNERS-26APR07RMABMU-RMA5` | major_sports | 6 | 26 |
| `KXUCLTOTAL-26APR07RMABMU-5` | major_sports | 5 | 26 |
| `KXUCLTOTAL-26APR07RMABMU-6` | major_sports | 4 | 26 |
| `KXUCLTCORNERS-26APR07RMABMU-BMU6` | major_sports | 5 | 26 |

The collector was intentionally stricter than Sprint 1:

- It rejected BTC/ETH short-window micro price markets.
- It rejected small ITF/challenger-style tennis markets.
- It rejected low-info college baseball/softball markets.
- It rejected mention/transcript markets.
- It required a non-unknown category and score above the selectable threshold.
- It required at least 4 usable pre-settlement candles per market.

That prevented the Sprint 1 failure modes from repeating, but it also removed
most markets that the recent public endpoint crawl actually exposed.

## Which Filters Removed The Most Candidates

Persisted Sprint 2 artifacts include aggregate counts but not a per-reason
histogram. Known counts from `source_manifest.json`:

- Markets discovered: 11,639
- Markets hard-rejected by heuristic: 4,285
- Markets selected: 4

The largest known reducer was the hard-reject gate, which removed 4,285 markets
before candle selection.

The largest effective reducer was the combination of:

1. `category != unknown`
2. score threshold `>= 24`
3. at least 4 usable 60-minute pre-settlement candles

The final selected markets all had the same weakly acceptable score pattern:

- `category:major_sports`
- `resolved_or_finalized`
- `clear_binary_outcome`
- `rules_present`
- `intraday_market_window`

No selected market gained stronger evidence-friendly bonuses such as explicit
official data-source rules, named government/statistics source, or multi-day
review window.

The precise per-filter removal distribution should be added to a future
collector run report. DATA-COLLECT-2 did not persist reason counts by category,
so this audit should not pretend to know exact per-reason totals.

## Were Macro, Weather, Or Government-Style Markets Available?

Not in usable form in the final Sprint 2 export.

The scoring code would strongly prefer synthetic macro, Fed, weather, and major
event markets. The tests verify that:

- CPI/BLS-style markets score high.
- National Weather Service-style markets score high.
- NBA-style major-event markets score above the selectable threshold.

But the real selected export contains only `major_sports`. That means the final
public crawl did not expose enough resolved macro/weather/government-style
markets with both:

- recognizable title/rule keywords; and
- enough usable pre-settlement candles in the attempted endpoint/window.

Several apparent government or public-policy candidates in the real crawl were
mention/transcript markets, for example "What will X say during..." markets.
Those were intentionally excluded because their likely evidence source is the
post-event transcript or final result, which is unsafe as forecast-time
evidence.

## Were There Enough Resolved Markets With Usable Candles?

There were enough resolved markets in raw count, but not enough resolved markets
that also met the stricter evidence-friendly and candle-availability gates.

Sprint 2 found 11,639 resolved/scorable candidates, but selected only 4 after
market-family filtering and pre-settlement candle checks. The final export has
20 total candle rows, far below the 100-200 target.

This suggests the bottleneck was not just market availability. It was the
intersection of:

- resolved binary market;
- evidence-friendly family;
- not a transcript/mention/ultra-short/low-info event;
- enough pre-settlement bid/ask/price candles from Kalshi public endpoints;
- enough category diversity.

## Did Category Diversity Constraints Reduce Too Much?

Category diversity was not the final blocker.

The first selection pass caps a category at 40% of the target, so for a
10-market target it can select at most 4 markets from one category before
looking elsewhere. That explains why the primary pass stopped at 4
major-sports markets.

However, Sprint 2 also has a fallback path that fills without the category cap.
The final result was still 4 markets after that fallback. That means category
diversity constrained the first pass, but the final shortfall came from a lack
of additional selectable markets with usable candles.

## Did Candidate Generation Fail Because Of Timestamp Limitations?

Yes.

Sprint 2 generated 8 candidates, but every candidate had:

- `timestamp_status=missing`
- `missing_published_at`
- `needs_human_timestamp_review`

The generated candidates were source-discovery aids, not approvable evidence.
They pointed at public source families, but the pages did not expose a reliable
publication timestamp that can prove availability before each candle timestamp.

This repeats the Sprint 1 evidence failure in a smaller, cleaner dataset:
candidate discovery can find public pages, but public pages without reliable
publication time do not count toward acceptance evidence coverage.

## Root Cause Allocation

| Cause Area | Contribution | Notes |
|---|---:|---|
| Kalshi market availability | High | The recent resolved market pool was dominated by sports, short-window, mention, and low-info events rather than clean macro/weather/government releases. |
| Script heuristics | Medium | The stricter filters correctly removed Sprint 1 failure modes, but the scoring/crawl was still broad and did not target known evidence-rich families by series/date. |
| Kalshi candle API coverage | Medium | Many candidate markets did not yield at least 4 usable 60-minute pre-settlement candles with bid/ask/price under the attempted settings. |
| Evidence source design | High | Seed pages did not expose reliable `published_at`; official schedule/result pages are not automatically forecast-time evidence. |
| Terms review | Blocking | `terms_review=pending_review` independently blocks acceptance-candidate import. |

## Sprint 1 vs Sprint 2

| Metric | Sprint 1 | Sprint 2 |
|---|---:|---:|
| Markets selected | 10 | 4 |
| Candles collected | 100 | 20 |
| Evidence candidates | 20 after DATA-EVIDENCE-4 | 8 |
| Timestamp coverage | 0% | 0% |
| Categories | BTC 15-minute and ITF tennis | Major sports only |
| Acceptance viability | Not viable | Not viable |
| Main failure mode | Easy-to-collect markets were evidence-hostile; candidates had missing timestamps; terms pending | Evidence-friendly filters removed most candidates; remaining source seeds still lacked timestamps; terms pending |

## Acceptance Viability

Sprint 2 is not acceptance viable.

It fails the data-level requirements from the acceptance-candidate plan:

- fewer than 25 resolved binary markets;
- fewer than 250 point-in-time rows;
- fewer than 50 candidate forecast rows;
- evidence timestamp coverage below 95%;
- terms review not complete.

The export is useful as a failure diagnostic and as evidence that stricter
filters avoid obvious Sprint 1 traps, but it is not a Strategy v2 acceptance
dataset and does not support paper PnL, superiority, or profitability claims.

## Source Audit File Handling

The pre-existing untracked file
`docs/reports/phase7g_kalshi_sprint1_kalshi_sprint1_20260605_public_probe_source_audit.md`
was inspected. It was a generated source-audit artifact from the Sprint 1
downgrade diagnostic. It contained repeated missing-evidence diagnostics and
can be regenerated from the ignored local export.

Decision: delete it as generated/noisy local output and add
`docs/reports/*_source_audit.md` to `.gitignore` so future generated source
audits do not pollute the tracked docs tree by default.

## Safety Notes

This analysis did not collect new data, approve evidence, mutate terms review,
change strategy logic, change acceptance gates, add broker integrations, add
live trading, start Phase 8, or add scheduler/daemon/autostart behavior.
