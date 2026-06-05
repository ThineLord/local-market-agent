# Kalshi Sprint 1 Supervised Evidence Review Result

Date: 2026-06-05

Scope: DATA-EVIDENCE-3 supervised first-pass evidence review for
`data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/`.

This was a delegated evidence review pass, not a legal or terms review. The
review did not change `terms_review=pending_review`, did not approve evidence
automatically, did not perform source scraping, did not use private or
authenticated pages, and did not change strategy logic or acceptance gates.

## UI Operation

Launched the local Streamlit UI with overwrite enabled:

```bash
PYTHONPATH=src .venv/bin/streamlit run scripts/local_only/review_kalshi_evidence.py -- \
  --export-id kalshi_sprint1_20260605_public_probe \
  --export-root data/source_exports/kalshi \
  --overwrite
```

The UI loaded `evidence_template.jsonl` because `evidence_candidates.jsonl` was
not present. The UI displayed the expected warning that template rows are not
curated evidence. Each market section was inspected through the UI, including
title, rules, result, settlement timestamp, candle timestamp range, and
`required_evidence_before_ts`.

## Markets Reviewed

| Market | Title | Result | Required evidence before | Settlement | Candidates |
|---|---|---:|---:|---:|---:|
| `KXBTC15M-26JUN050015-15` | BTC price up in next 15 mins? | `yes` | `2026-06-05T04:01:00Z` | `2026-06-05T04:15:04Z` | 2 |
| `KXBTC15M-26JUN050030-30` | BTC price up in next 15 mins? | `yes` | `2026-06-05T04:16:00Z` | `2026-06-05T04:30:04Z` | 2 |
| `KXBTC15M-26JUN050215-15` | BTC price up in next 15 mins? | `no` | `2026-06-05T06:01:00Z` | `2026-06-05T06:15:04Z` | 2 |
| `KXITFMATCH-26JUN04KOYSIN-SIN` | Will Colin Sinclair win the Koyama vs Sinclair: M15 Harmon Quarterfinal match? | `no` | `2026-06-04T20:31:00Z` | `2026-06-05T04:23:44Z` | 2 |
| `KXITFMATCH-26JUN04ZENHUA-HUA` | Will Tsung-Hao Huang win the ZENG vs Huang: M15 Luan Quarterfinal match? | `no` | `2026-06-04T20:28:00Z` | `2026-06-05T04:33:54Z` | 2 |
| `KXITFMATCH-26JUN04ZENHUA-ZEN` | Will Yaojie ZENG win the ZENG vs Huang: M15 Luan Quarterfinal match? | `yes` | `2026-06-04T17:20:00Z` | `2026-06-05T04:33:54Z` | 2 |
| `KXITFWMATCH-26JUN04SAIZHI-SAI` | Will Rina Saigo win the Saigo vs Zhiyenbayeva: W50 Wuning Quarterfinal match? | `yes` | `2026-06-04T23:13:00Z` | `2026-06-05T06:44:04Z` | 2 |
| `KXITFWMATCH-26JUN04SAIZHI-ZHI` | Will Sonja Zhiyenbayeva win the Saigo vs Zhiyenbayeva: W50 Wuning Quarterfinal match? | `no` | `2026-06-04T18:49:00Z` | `2026-06-05T06:44:04Z` | 2 |
| `KXITFWMATCH-26JUN04YANREN-REN` | Will Yufei Ren win the Yang vs Ren: W50 Wuning Quarterfinal match? | `yes` | `2026-06-04T16:50:00Z` | `2026-06-05T05:28:24Z` | 2 |
| `KXITFWMATCH-26JUN04YANREN-YAN` | Will Yidi Yang win the Yang vs Ren: W50 Wuning Quarterfinal match? | `no` | `2026-06-04T21:11:00Z` | `2026-06-05T05:28:24Z` | 2 |

## Review Counts

- Markets reviewed: 10.
- Candidates reviewed: 20 template rows.
- Approved: 0.
- Rejected: 20.
- Needs more review: 0.
- Unreviewed: 0.

All 20 rows were rejected through the local review UI because they were
placeholder/template rows with TODO values, no public HTTP(S) source URL, no
real source/title/summary, and no timezone-aware `published_at` or
`retrieved_at` timestamp. The shared rejection reason was:

```text
Rejected by supervised evidence review agent: placeholder template row with TODO values; no real public timestamped evidence candidate exists.
```

No public web search was used in this pass. Since no real
`evidence_candidates.jsonl` file existed, this pass did not discover or curate
new evidence and did not infer publication timestamps.

## Output Files

Local export outputs:

- `data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/evidence_review_state.json` was written with 20 rejected rows.
- `data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/evidence_review_audit.md` was written with the review audit.
- `data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/evidence.jsonl` remains empty because there were 0 approved rows.

The UI did not enable `Export approved evidence` because approved count was 0.
This is the expected safety behavior for placeholder-only input. The empty
`evidence.jsonl` is therefore approved-only but contains no rows.

## Validation Result

Acceptance validation command:

```bash
PYTHONPATH=src .venv/bin/lma import-kalshi-export \
  --export-dir data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe \
  --profile acceptance_candidate \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --source-audit-dir docs/reports \
  --validate
```

Result: failed with exit code 2. Remaining blockers were
`terms_review=pending_review` and missing evidence timestamp coverage for all
100 candle rows.

Downgrade diagnostic command:

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

Result: completed with downgrade to `calibration_only_last_price`, but
validation remained invalid with `validation_valid=false`, `row_count=100`,
`market_count=10`, `error_count=100`, and `warning_count=400`.

## Remaining Blockers

- `terms_review` remains `pending_review`; this pass did not and must not clear
  it.
- No real curated public evidence exists yet.
- Evidence timestamp coverage remains 0%.
- `evidence_candidates.jsonl` is missing.
- `evidence.jsonl` contains no approved evidence rows.
- Acceptance-candidate import remains blocked until a human reviewer curates
  real public timestamped evidence and a separate human/legal terms review is
  completed.

## Files Changed

Committed documentation changes:

- `docs/reports/kalshi_sprint1_supervised_evidence_review_result.md`
- `docs/IMPLEMENTATION_LOG.md`

Local generated outputs not intended for commit:

- `data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/evidence_review_state.json`
- `data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/evidence_review_audit.md`
- `data/source_exports/kalshi/kalshi_sprint1_20260605_public_probe/evidence.jsonl`
- `data/historical/phase7g_kalshi_sprint1_kalshi_sprint1_20260605_public_probe.jsonl`
- `data/historical/phase7g_kalshi_sprint1_kalshi_sprint1_20260605_public_probe.manifest.json`
- `data/reports/historical_dataset/phase7g_kalshi_sprint1_kalshi_sprint1_20260605_public_probe.validation.json`
- `data/reports/historical_dataset/phase7g_kalshi_sprint1_kalshi_sprint1_20260605_public_probe_audit.md`
- `docs/reports/phase7g_kalshi_sprint1_kalshi_sprint1_20260605_public_probe_source_audit.md`

## Safety Notes

This review remained local-only and file-only. It added no scraping, source API
caller, browser automation for third-party sites, private/authenticated source
use, automatic approval, production integration, broker API, live trading,
account/order/portfolio/fill logic, Phase 8 work, strategy change, acceptance
gate change, or profitability claim.
