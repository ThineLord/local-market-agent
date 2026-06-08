# Manual Acceptance Evidence Pilot Plan

Scope: ACCEPT-1 documentation and planning only. This plan does not collect
data, approve evidence, build an acceptance dataset, implement a collector,
scrape sources, automate a browser, mutate source terms, change strategy logic,
change acceptance gates, start Phase 8, add broker/live/order/account,
portfolio/fill paths, add scheduler/daemon/autostart behavior, or make profitability,
paper-PnL, Strategy v2 superiority, acceptance-ready, or live-readiness claims.

## Objective

Design a small manually curated acceptance-evidence pilot for 5 to 10 resolved
binary markets where timestamp-safe public evidence is realistic. The pilot is
intended to test whether human curation can meet evidence, settlement,
point-in-time bid/ask, and terms-review requirements before any larger
acceptance attempt.

PR-CAL-14 showed that calibration diagnostics are now auditable, but those rows
remain `calibration_only_last_price`. Calibration data cannot be promoted to
acceptance data. The acceptance pilot must start from a separate manually
reviewed source workflow with bid/ask, settlement, evidence timestamps, and
source provenance.

## Pilot Target

| Target | Requirement |
| --- | --- |
| Markets | 5 to 10 resolved binary markets |
| Rows per market | 5 to 12 pre-settlement rows |
| Evidence per market | At least 2 public evidence items where possible |
| Settlement coverage | 100% |
| Evidence timestamp coverage | 100% for acceptance-candidate rows |
| Bid/ask | Required point-in-time bid and ask; no bid/ask invention |
| Terms review | Keep `terms_review=pending_review` unless separately reviewed |
| Evidence approval | Human-reviewed only; no automatic approval |
| Dataset build | Future-only; not part of ACCEPT-1 |

Acceptance-candidate rows should exist only if every row has point-in-time
bid/ask, unambiguous settlement, public provenance, and timestamp-safe evidence.
Rows that have only last price remain calibration-only and must not be counted
for acceptance or paper-PnL evaluation.

## Candidate Families

Use the detailed source-family rules in
`docs/reports/acceptance_source_matrix.md`. For this pilot, prioritize:

| Family | Pilot fit | Reason |
| --- | --- | --- |
| Fed/FOMC/rate decisions | Best if available | Official Federal Reserve releases and calendars are usually auditable. |
| CPI/inflation releases | Best if available | BLS calendars and release tables give strong settlement sources. |
| Unemployment/jobs/nonfarm payrolls | Strong | BLS Employment Situation releases are structured and timestampable. |
| Weather official-only | Selective | NOAA/NWS/NHC pages can be strong, but every source must have issued/update time and exact location/window fit. |
| Major sports | Selective | Official result pages are clean; forecast-time evidence is usable only when schedules/previews are timestamp-safe. |
| Crypto benchmark markets | Conditional | Use only if the benchmark source has timestamp-safe public pre-settlement and settlement records. |

Exclude from the first pilot:

- Markets whose evidence is mostly untimestamped news, social posts, or
  commentary.
- Markets needing private/authenticated pages, browser session state, paid
  terminals, or source scraping.
- Markets where the only usable evidence is a final settlement/result source.
- Markets whose bid/ask would need to be inferred from last price or candle
  close values.
- Markets with unresolved, ambiguous, canceled, or disputed settlement.

## Evidence Timestamp Rules

For every forecast row:

- At least one accepted evidence item must have `published_at <= row.timestamp`.
- The preferred target is two independent public evidence items per market.
- `retrieved_at` may be after the row timestamp because it records manual
  curation time.
- Date-only evidence does not count unless the reviewer records a conservative
  availability rule that is safely before every attached row timestamp.
- Settlement/result sources are allowed for settlement metadata, but they must
  not count as pre-settlement forecast-time evidence.
- Evidence with unknown timezone, missing publication time, or ambiguous update
  history is rejected for acceptance coverage.

Cutoff rule: if the evidence timestamp is equal to or earlier than the row
timestamp, it may be attached. If it is later than the row timestamp, it must
not be attached to that row. If availability is ambiguous, reject for
acceptance and keep only as a manual note.

## Settlement Rules

Every selected market needs:

- Public settlement source URL or public source descriptor.
- Final outcome as `yes` or `no`.
- `resolved_at` or best official resolution timestamp.
- `label_available_at`, meaning the earliest time the outcome became publicly
  knowable.
- Resolution rule mapping from the market text to the settlement source.
- `ambiguous=false`.

Rows after `settlement.label_available_at` must not be used as forecast rows.
Settlement evidence is label metadata, not forecast-time evidence.

## Go/No-Go Criteria

Go only when all of these are true:

- Source timestamp can be verified before each row timestamp.
- Settlement source is public, unambiguous, and rule-compatible.
- Point-in-time bid and ask are present without inference.
- Evidence is public, timestamped, manually reviewed, and relevant.
- No private/authenticated/account/order/portfolio/fill source appears in the
  workflow.
- Terms review is separately resolved before any acceptance claim.

No-go when any of these are true:

- Evidence is untimestamped, after-the-fact, private/authenticated, ambiguous,
  or only settlement-result evidence.
- Bid/ask is missing or would need to be invented from last price.
- Settlement is ambiguous, disputed, unavailable, or not rule-compatible.
- `terms_review` remains unresolved for acceptance claims.
- The proposed market family cannot support evidence before the row timestamps.

## Manual Workflow

These commands are future workflow commands only. They were not run for
ACCEPT-1.

Set the future export id:

```bash
export export_id=kalshi_manual_acceptance_pilot_YYYYMMDD_5to10m
```

Prepare the local evidence worksheet after a manually staged export exists:

```bash
PYTHONPATH=src .venv/bin/python scripts/local_only/prepare_kalshi_evidence_worksheet.py \
  --export-id "$export_id" \
  --evidence-needed-count 2
```

Open the local human-review UI after worksheet/template rows exist:

```bash
PYTHONPATH=src .venv/bin/streamlit run scripts/local_only/review_kalshi_evidence.py -- \
  --export-id "$export_id" \
  --export-root data/source_exports/kalshi \
  --overwrite
```

Import only after manual curation and separate terms review are complete:

```bash
PYTHONPATH=src .venv/bin/lma import-kalshi-export \
  --export-dir "data/source_exports/kalshi/$export_id" \
  --profile acceptance_candidate \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --source-audit-dir docs/reports \
  --validate
```

Validate the imported historical dataset:

```bash
export dataset_id=phase7g_kalshi_acceptance_pilot_YYYYMMDD_5to10m

PYTHONPATH=src .venv/bin/lma validate-historical-dataset \
  --historical-file "data/historical/$dataset_id.jsonl" \
  --output-dir data/reports/historical_dataset
```

Audit the source artifact written by `import-kalshi-export`:

```bash
sed -n '1,220p' "docs/reports/${dataset_id}_source_audit.md"
```

Run strategy evaluation only if validation passes and the dataset remains an
acceptance-candidate dataset:

```bash
PYTHONPATH=src .venv/bin/lma strategy-eval-offline \
  --historical-file "data/historical/$dataset_id.jsonl" \
  --output-dir data/reports/strategy_eval
```

Do not run `strategy-eval-offline` for an invalid dataset, a downgraded
calibration-only dataset, or any dataset with unresolved terms review.

## Guardrails

- Calibration data cannot be promoted to acceptance data.
- Accepted evidence must be human-reviewed; no automatic approval is allowed.
- `acceptance_candidate_possible` is a data-quality classification, not an
  acceptance-gate pass.
- Strategy v2 superiority remains blocked until the full acceptance gate passes.
- `terms_review=pending_review` blocks acceptance claims.
- Raw exports, evidence worksheets, and generated historical JSONL outputs
  should remain local unless a separate publication review explicitly allows
  sharing.
- This pilot plan does not authorize scraping, browser automation, new
  collection code, broker/live trading, account/order/portfolio/fill endpoints,
  scheduler/daemon/autostart behavior, or Phase 8 work.

## Recommended Human Action

Start with a manual pre-screen of 8 to 12 candidate markets, then pick 5 to 10
that survive the source matrix:

1. Prefer Fed/FOMC, CPI, and jobs releases with official timestamped source
   pages.
2. Add weather only when NOAA/NWS/NHC issued-time pages match the exact rule.
3. Add major sports only when official schedule/result pages and preview
   evidence are timestamp-safe.
4. Defer crypto unless benchmark archives prove pre-settlement availability.

The next useful human action is to fill a candidate shortlist with source URLs,
visible timestamps, settlement source URLs, and a short note explaining why
each source was public before the proposed row timestamps.
