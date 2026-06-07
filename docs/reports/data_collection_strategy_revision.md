# Data Collection Strategy Revision

Date: 2026-06-07

Scope: DATA-COLLECT-3 audit and planning only. This document proposes next
steps; it does not implement a new collector, modify strategy logic, change
acceptance gates, approve evidence, clear terms review, start Phase 8, add
broker integrations, add live trading, or add scheduler/daemon/autostart
behavior.

## Strategic Conclusion

Do not run another broad acceptance-candidate sprint immediately.

The first two Kalshi sprints showed two different ways a broad crawl fails:

- Sprint 1 collected enough rows but selected evidence-hostile markets.
- Sprint 2 filtered out those traps but became too small and still had 0%
  timestamp-safe evidence coverage.

The next step should separate the two goals that have been tangled together:

1. Build a large calibration-only dataset to unblock Strategy v2 calibration
   diagnostics and market-history plumbing.
2. Run a smaller, manually targeted acceptance-evidence pilot only on market
   families whose evidence sources are known before collection.

Do not relax the evidence timestamp policy. Missing or unverifiable
`published_at` must remain a blocker for acceptance-candidate labeling.

## Option A: Loosen Sprint 2 Filters And Collect More Resolved Markets

Description: Reuse the Sprint 2 collector idea, but relax the evidence-friendly
score threshold, category requirements, candle attempt limit, and some hard
exclusions. Collect enough resolved markets/candles even if the selected
markets are less evidence friendly.

Pros:

- Fastest way to reach 10+ markets and 100+ candle rows.
- Builds on the existing local-only collector.
- May produce a broader row sample for importer and validator diagnostics.
- Useful for learning Kalshi candlestick availability across market families.

Cons:

- Likely repeats Sprint 1 evidence failures.
- More candidates will be timestamp-missing or final-result-only.
- Category diversity may improve numerically without improving acceptance
  quality.
- Human review burden rises quickly with little chance of approval.

Expected effort: low to medium.

Expected dataset profile: diagnostic or calibration-only, not
acceptance-candidate.

Acceptance-candidate possible: unlikely unless combined with manual
timestamp-safe evidence curation.

Can Strategy v2 gate eventually pass: not from this option alone. It may help
debug data plumbing, but acceptance gates require evidence and terms coverage.

## Option B: Build A Larger Calibration-Only Dataset First

Description: Explicitly target `calibration_only_last_price` or another
non-acceptance diagnostic profile using Kalshi prices and settlement labels,
without trying to satisfy evidence timestamp coverage.

Pros:

- Aligns with what the public Kalshi export path can currently produce.
- Avoids pretending missing evidence can support paper PnL acceptance.
- Can scale to 25+ markets and 250+ rows faster than acceptance collection.
- Useful for Brier score, calibration buckets, abstention behavior, and
  end-to-end historical import validation.
- Keeps safety and claims clean: no paper PnL or superiority claims.

Cons:

- Cannot pass Strategy v2 acceptance gates.
- Does not solve evidence timestamp coverage.
- Does not prove local research terms review.
- May require report language that keeps calibration diagnostics separate from
  acceptance evaluation.

Expected effort: medium.

Expected dataset profile: `calibration_only_last_price` or equivalent
calibration-only diagnostic dataset.

Acceptance-candidate possible: no, by design.

Can Strategy v2 gate eventually pass: no directly, but it can prepare the
pipeline and identify whether the strategy has calibration signal before
acceptance-size evidence curation work.

## Option C: Manually Target Specific Evidence-Rich Market Families

Description: Stop broad crawling as the primary acceptance path. Choose market
families first, then collect only when each family has known public
timestamp-safe evidence sources. Candidate families:

- Scheduled macro releases: CPI, PCE, payrolls, unemployment, GDP, retail
  sales, jobless claims.
- Fed/FOMC rate decisions and official meeting calendars.
- Weather markets with explicit NOAA/NWS forecast or observation sources.
- Major sports games with official schedules and timestamped pre-game pages,
  not player props or obscure events.
- Company events only when SEC filing/release timestamps are clean.

Pros:

- Best match for acceptance-candidate evidence requirements.
- Focuses human review on sources likely to have timestamps.
- Avoids transcript/mention, ultra-short, and obscure sports traps.
- Can design row timestamps around known evidence availability.

Cons:

- More manual planning before collection.
- May require longer date ranges or multiple collection passes.
- Public endpoints may not expose enough resolved examples in a short recent
  window.
- Terms review still blocks acceptance even if evidence improves.

Expected effort: medium to high.

Expected dataset profile: small acceptance-evidence pilot first; possible
acceptance-candidate dataset only after terms review and evidence approval.

Acceptance-candidate possible: yes, but only with pre-vetted sources and human
review.

Can Strategy v2 gate eventually pass: yes, if scaled to at least 25 resolved
markets, 250 rows, 50 candidate forecast rows, 100% settlement coverage, and
95%+ evidence timestamp coverage.

## Option D: Add Or Use An ImpliedData Calibration-Only Path

Description: Use a public or licensed historical market-data source such as
ImpliedData for calibration-only datasets if it provides easier bulk historical
probability/settlement coverage.

Pros:

- May be faster for broad calibration diagnostics.
- Reduces dependence on Kalshi public endpoint quirks.
- Could provide cleaner historical series for Brier/calibration work.

Cons:

- Likely requires new source terms review.
- May involve cost, licensing, API keys, or redistribution limits.
- Not necessarily acceptance-candidate because bid/ask provenance, evidence,
  and source terms may still be incomplete.
- Should not be mixed into the existing local Kalshi acceptance path without a
  separate source audit.

Expected effort: medium for feasibility audit; medium to high if implemented.

Expected dataset profile: calibration-only first.

Acceptance-candidate possible: not initially; only after terms, bid/ask,
settlement, and evidence provenance are proven.

Can Strategy v2 gate eventually pass: not from calibration-only use alone.

## Recommendation

Recommended next move:

1. Build a larger calibration-only Kalshi dataset first.
2. In parallel, design a manual Sprint 3 acceptance-evidence pilot for one or
   two market families with known timestamp-safe public sources.
3. Do not relax the evidence timestamp policy.
4. Do not try another broad acceptance-candidate crawl until source-family
   evidence is pre-vetted.

## Direct Answers

Should we try Sprint 3 acceptance-candidate collection?

Not as another broad crawl. A Sprint 3 acceptance pilot is worth trying only if
it is manually targeted to pre-vetted families such as CPI/FOMC/NWS/NOAA or
major sports schedules with timestamp-safe pages. The target should be small:
prove 2-3 markets with real approved evidence before scaling.

Should we first build a calibration-only large dataset?

Yes. The current tooling can already collect market/candle/settlement-shaped
data more readily than timestamp-safe evidence. A calibration-only dataset is
the pragmatic next artifact for Strategy v2 diagnostics, with clear labels that
paper PnL and acceptance claims are not allowed.

Should we relax evidence timestamp policy?

No. Relaxing timestamp policy would make the dataset look larger while
undermining the point-in-time guarantee. Missing, inferred, or final-result
evidence should remain non-acceptance unless a human reviewer records why it
was publicly available before every attached forecast timestamp.

Should we change market family selection?

Yes. Broad recent-market selection is the wrong shape for acceptance. Start
from source families and evidence availability, then collect markets. The
collector should eventually persist a reason histogram and allow date/family
targets, but that is a future implementation task, not part of DATA-COLLECT-3.

Should we stop investing in acceptance-candidate for now?

Pause broad acceptance-candidate collection. Do not abandon it. Keep a narrow
manual acceptance pilot alive while the larger calibration-only dataset proves
the historical evaluation pipeline.

## Proposed Next Work Items

1. DATA-CALIBRATION-1: Plan and build a larger calibration-only Kalshi dataset
   with explicit non-acceptance labeling.
2. DATA-EVIDENCE-5: Create a manual evidence-source matrix for CPI/FOMC/NWS and
   one major-sports family before any new collection.
3. DATA-COLLECT-4: Only after the source matrix, implement a targeted Sprint 3
   collector or manual collection worksheet for selected families and date
   ranges.

## Safety Notes

All recommended paths stay local and paper-only. None require broker
integrations, live trading, order/account/portfolio/fill endpoints,
scheduler/daemon/autostart, Phase 8, strategy changes, acceptance-gate changes,
automatic evidence approval, or terms review mutation.
