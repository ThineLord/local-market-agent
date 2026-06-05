# Kalshi Sprint 1 Evidence Curation Plan

Date: 2026-06-05

Scope: DATA-EVIDENCE-1 local evidence worksheet helper. This task produces
worksheet/template files for human curation only. It does not scrape websites,
automate browser access, call source APIs, add a crawler, add production
integration, modify acceptance gates, start Phase 8, add broker/live trading,
or make profitability claims.

## Generated Worksheet

Real Sprint 1 export:

```text
data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/
```

Command:

```bash
PYTHONPATH=src .venv/bin/python scripts/local_only/prepare_kalshi_evidence_worksheet.py \
  --export-id kalshi_sprint1_20260605_public_probe
```

Outputs:

```text
data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/evidence_worksheet.csv
data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/evidence_worksheet.md
data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/evidence_template.jsonl
```

The real worksheet outputs are ignored by Git with the rest of
`data/source_exports/kalshi/*` and should remain local unless explicitly
reviewed for safe sharing.

## Evidence Need

Sprint 1 currently has:

| Metric | Value |
| --- | ---: |
| Selected markets | 10 |
| Candlestick rows | 100 |
| Existing evidence rows | 0 |
| Markets requiring evidence | 10 |
| Template rows generated | 20 |

The worksheet uses two placeholder evidence rows per market by default. One
public timestamped item per market may be enough to remove the schema-level
missing-evidence issue if its `published_at` is early enough, but two
independent public sources are preferred for review quality.

## How To Use The Worksheet

1. Open `evidence_worksheet.csv` for sortable review, or
   `evidence_worksheet.md` for a readable per-market checklist.
2. For each market, inspect `required_evidence_before_ts`. Evidence intended
   to cover every sampled candle for that market must have
   `published_at <= required_evidence_before_ts`.
3. Use the suggested queries as starting prompts for manual research only.
   The script does not execute the searches.
4. Replace placeholder rows in `evidence_template.jsonl` with real public
   evidence details.
5. Copy reviewed rows into `evidence.jsonl` only after every `TODO` value is
   replaced.
6. Keep `terms_review=pending_review` until a human terms review explicitly
   clears local public research use.

## Timestamp Rules

- `published_at` is the evidence publication time, not the collection time.
- `retrieved_at` is when the curator accessed the public item.
- Forecast-time evidence must satisfy `published_at <= candle.end_period_ts`.
- To cover all sampled rows for a market with one item, use evidence published
  at or before the market worksheet's `required_evidence_before_ts`.
- Settlement labels, final results, or post-result reports are not
  forecast-time evidence for pre-settlement candles.
- Date-only evidence should be avoided for acceptance unless the reviewer can
  document why the timestamp is safe for every row it supports.

## Acceptable Evidence Examples

- Official event/result pages that were public before the candle timestamp.
- Government, regulator, or statistics releases with visible publication
  timestamps.
- Official weather, sports, exchange, or reference-price pages when directly
  tied to the market rule.
- Public company filings, official press releases, or primary-source event
  pages with clear timestamps.
- Archived news or public pages with reliable publication timestamps.

## Rejected Evidence Examples

- Private account pages, authenticated dashboards, browser history, cookies,
  local session data, or cached private pages.
- Paywalled or restricted sources unless terms and redistribution have been
  explicitly cleared.
- Settlement labels used as pre-result evidence.
- Outcome reports published after the candle timestamp being scored.
- Model-generated analysis or summaries pretending to be evidence.
- Evidence with unknown publication time for acceptance coverage.

## Filling `evidence.jsonl`

Each evidence row must be valid JSON with these PR-DATA-3 fields:

```json
{
  "market_ticker": "KXEXAMPLE-26JUN05-YES",
  "evidence_id": "ev_example_public_source_1",
  "source": "official_source_name",
  "title": "Public evidence title",
  "url": "https://example.invalid/public-evidence",
  "published_at": "2026-06-05T00:00:00Z",
  "retrieved_at": "2026-06-05T14:00:00Z",
  "summary": "Short factual summary of what the public item shows.",
  "relevance_score": 0.9,
  "credibility_score": 0.9,
  "metadata": {
    "timestamp_status": "explicit_utc_or_timezone_converted",
    "evidence_type": "official_public_source",
    "supports_side": "context_or_rule",
    "curator_notes": "Why this item was public before the forecast rows."
  }
}
```

Do not leave placeholder `TODO` values in `evidence.jsonl`. Do not fabricate
publication timestamps, sources, URLs, or summaries.

## Rerun Import And Validation

After reviewed evidence rows are added, rerun the existing PR-DATA-3 import:

```bash
PYTHONPATH=src .venv/bin/lma import-kalshi-export \
  --export-dir data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe \
  --profile acceptance_candidate \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --source-audit-dir docs/reports \
  --validate
```

This should still fail acceptance until `terms_review` is explicitly reviewed
and changed to `reviewed_public_research_local_only`.

For diagnostic downgrade only:

```bash
PYTHONPATH=src .venv/bin/lma import-kalshi-export \
  --export-dir data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe \
  --profile acceptance_candidate \
  --allow-downgrade \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --source-audit-dir docs/reports \
  --validate
```

## Current Blockers

- Human terms review is still pending.
- Evidence rows are not yet curated.
- Worksheet queries are only suggestions; a human must verify source relevance,
  public availability, and timestamps.
- The first Sprint 1 market mix is narrow and remains a field-availability
  diagnostic, not an acceptance-ready dataset.
