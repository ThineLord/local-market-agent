# Kalshi Sprint 1 Evidence Review UI

Date: 2026-06-05

Scope: DATA-EVIDENCE-2 local evidence review UI. This adds a human-operated
Streamlit interface for reviewing local evidence candidates and exporting only
approved rows into the PR-DATA-3 `evidence.jsonl` shape. It does not scrape
websites, automate a browser, call a source API, add a crawler, approve evidence
automatically, integrate production data flows, change strategy logic, change
acceptance gates, add broker/live trading, or make profitability claims.

## Launch

Run from the repository root:

```bash
PYTHONPATH=src .venv/bin/streamlit run scripts/local_only/review_kalshi_evidence.py -- \
  --export-id kalshi_sprint1_20260605_public_probe \
  --export-root data/source_exports/kalshi
```

Optional candidate/template paths are resolved relative to the export directory:

```bash
PYTHONPATH=src .venv/bin/streamlit run scripts/local_only/review_kalshi_evidence.py -- \
  --export-id kalshi_sprint1_20260605_public_probe \
  --export-root data/source_exports/kalshi \
  --candidates-file evidence_candidates.jsonl \
  --template-file evidence_template.jsonl
```

The current Sprint 1 export already has an empty `evidence.jsonl`. To export
approved rows, either pass `--overwrite` at launch or click the explicit
overwrite confirmation in the UI.

## Review Workflow

1. Open the current market section and compare the fixed market summary,
   especially `required_evidence_before_ts`, earliest candle, latest candle,
   settlement timestamp, rules, and result.
2. Review each evidence candidate one by one.
3. Edit source, title, URL, timestamps, summary, scores, evidence type,
   supported side, and curator notes before approving.
4. Use `Approve`, `Reject`, or `Needs more review`.
5. Add reviewer notes for accepted evidence and rejection reasons for rejected
   evidence.
6. Click `Export approved evidence` after all intended approvals are complete.

The UI writes intermediate review state on decisions, so the review can be
resumed from `evidence_review_state.json`.

Only the first market that still has unreviewed or needs-more-review candidates
is expanded by default. If `evidence_candidates.jsonl` is missing, the UI falls
back to `evidence_template.jsonl` and shows a red placeholder warning; those
template rows are not curated evidence. The in-browser session state is tied to
the active candidate/template file path, size, and modification time so a newly
added candidate file does not reuse stale template rows.

## Approval Criteria

Approval is blocked when any of these are true:

- URL is missing or is not an HTTP(S) public URL.
- Title, source, summary, `published_at`, or `retrieved_at` is missing.
- `published_at` or `retrieved_at` is not timezone-aware ISO 8601.
- `published_at` is after the market `required_evidence_before_ts`.
- The source appears private, authenticated, local-only, account-only, or
  session/cookie/token dependent.
- Placeholder/TODO values remain in candidate fields or metadata.
- `relevance_score` or `credibility_score` is missing or outside `0..1`.
- Evidence appears to be settlement/final-result evidence being used as
  forecast-time evidence.

Approval metadata records `reviewer_status=approved`, `reviewed_by`,
`reviewed_at`, `timestamp_status`, `evidence_type`, `supports_side`,
`curator_notes`, `source_public`, and
`private_or_authenticated_source=false`.

## Warnings

Warnings do not approve evidence automatically. The reviewer should resolve or
document them before export:

- Date-only timestamp.
- Weak source.
- Evidence only covers late candles.
- Summary too short.
- Source domain unknown.

## Rejection Criteria

Reject candidates that are private/authenticated, paywalled without explicit
clearance, post-settlement evidence for forecast-time rows, timestamp-ambiguous,
too weakly related to the market rule, or still contain TODO/template content.
Use `Needs more review` when a candidate may be usable but still needs timestamp,
terms, credibility, or relevance verification. A rejection reason is required
before a rejected row can be persisted for export/audit.

## Output Files

The UI writes these files under the export directory:

```text
data/source_exports/kalshi/{export_id}/evidence_review_state.json
data/source_exports/kalshi/{export_id}/evidence_review_audit.md
data/source_exports/kalshi/{export_id}/evidence.jsonl
```

`evidence.jsonl` contains approved rows only. Existing `evidence.jsonl` is not
replaced unless the reviewer passes `--overwrite` or clicks the UI overwrite
confirmation. Export is disabled and blocked when no rows are approved, even if
overwrite is enabled.

## Rerun Validation

After exporting evidence, rerun PR-DATA-3 import/validation:

```bash
PYTHONPATH=src .venv/bin/lma import-kalshi-export \
  --export-dir data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe \
  --profile acceptance_candidate \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --source-audit-dir docs/reports \
  --validate
```

Downgrade diagnostic:

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

The Sprint 1 export still has `terms_review=pending_review`; evidence export
does not clear that blocker.

## Limitations

- Local-only review tool; no source discovery or URL fetching.
- No automatic evidence approval or scoring.
- No terms-review mutation.
- No production integration.
- No browser automation.
- No scraper, crawler, or source API caller.
- No broker, live order, withdrawal, leverage, derivatives, shorting, or direct
  LLM-to-order path.
- No acceptance gate changes and no profitability claims.
