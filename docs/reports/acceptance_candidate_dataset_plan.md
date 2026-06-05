# Acceptance-Candidate Dataset Plan

Date: 2026-06-05

Scope: DATA-OPS-1 documentation and operations planning only. This plan does
not implement downloader code, source adapters, network automation, Phase 8,
broker integrations, live trading, scheduler/daemon/autostart behavior,
strategy changes, acceptance-gate changes, or profitability claims.

## Recommended Collection Plan

Use Kalshi as the first acceptance-candidate source, but keep the process
human-operated and local-file based:

1. Complete terms review before labeling any export acceptance-candidate.
2. Run a 10-market pilot to prove real field availability and evidence
   workflow.
3. Build a minimum viable export with 30 markets and 300 rows.
4. Expand to a preferred export with 45 markets and 500+ rows.
5. Import with `lma import-kalshi-export`.
6. Validate with PR-DATA-1.
7. Review source audit artifacts.
8. Run Strategy v2 offline acceptance evaluation only after data-level gates
   pass.

The recommended first real collection sprint is not intended to pass Strategy
v2 acceptance. It is intended to discover whether real Kalshi exports can meet
bid/ask, settlement, evidence, and terms requirements before spending
acceptance-size effort.

## Dataset Size Targets

### Gate Minimums

| Metric | Acceptance gate minimum |
| --- | ---: |
| Resolved binary markets | 25 |
| Point-in-time rows | 250 |
| Candidate forecast rows | 50 |
| Closed paper trades | 30 |
| Settlement coverage | 100% |
| Evidence timestamp coverage | 95% |

### Operational Targets

| Dataset | Markets collected | Rows per market | Total rows | Exports | Intended use |
| --- | ---: | ---: | ---: | ---: | --- |
| Pilot sprint | 10 | 8 to 12 | 80 to 120 | 1 | Prove real export shape and bottlenecks. |
| Minimum viable dataset | 30 | 10 | 300 | 1 consolidated export | Clear size gates with little buffer. |
| Preferred acceptance dataset | 45 | 12 | 540 | 1 consolidated export from 3 to 5 human batches | Realistic first acceptance attempt. |
| Stretch dataset | 60 | 15 | 900 | 1 consolidated export from 5+ human batches | Better split quality and diversity. |

### Recommended First Acceptance Attempt

Use the preferred target:

- 45 selected resolved binary markets.
- At least 35 markets expected to survive full audit.
- 12 sampled pre-settlement rows per market.
- 540 initial rows.
- At least 450 rows expected after exclusions.
- At least 100 candidate forecast rows expected before policy abstention.
- Category cap: no category above 35% of rows.
- Event-family cap: no event family above 20% of rows.

This gives a cushion above the 25-market, 250-row, and 50-candidate minimums.
It also improves the chance that the evaluation can produce 30 closed paper
trades without forcing trades or tuning thresholds.

## Market Mix

Preferred category mix for a 45-market collection:

| Category | Target markets | Notes |
| --- | ---: | --- |
| Economic indicators | 10 | Strong timestamped primary sources. |
| Public policy/elections | 8 | Avoid many variants of the same race or bill. |
| Weather/climate events | 8 | Good if settlement source is explicit. |
| Company/public-event markets | 7 | Use only public filings or official releases. |
| Sports/entertainment | 6 | Include only simple binary markets with clean settlement. |
| Miscellaneous public events | 6 | Fill diversity gaps. |

Reject markets that are thinly traded, ambiguous, too correlated, or difficult
to evidence before forecast timestamps.

## Row Sampling Plan

Default per-market target:

- 12 rows per market.
- 1-hour candles when available and active.
- Daily candles only when hourly coverage is sparse or not useful.
- All sampled rows before `settlement.label_available_at`.

Preferred timestamps:

- `T-21d`
- `T-14d`
- `T-10d`
- `T-7d`
- `T-5d`
- `T-3d`
- `T-2d`
- `T-1d`
- `T-12h`
- `T-6h`
- `T-3h`
- `T-1h`

Rules:

- Use `end_period_ts` as row timestamp.
- Use `yes_bid.close_dollars` and `yes_ask.close_dollars` only.
- Do not use candle high/low values as quotes.
- Do not infer bid/ask from `price.close_dollars`.
- Do not synthesize missing bids or asks.
- Keep duplicate `market_ticker + end_period_ts` rows out of the final export.

## Evidence Requirements

### Coverage Target

Minimum:

- 95% of candidate forecast rows have at least one evidence item with
  `published_at <= row.timestamp`.

Preferred:

- 98%+ evidence timestamp coverage.
- Two independent public evidence items per market.
- At least one source that is primary, official, or archival.

### Evidence Quality Rules

Accept evidence that is:

- public;
- timestamped;
- retrievable or archived;
- relevant to the market resolution rule;
- available before the sampled forecast timestamp;
- summarized without adding model-generated claims.

Reject evidence that is:

- published after the row timestamp;
- private or authenticated;
- missing publication time;
- a final result report used as pre-result evidence;
- derived from model output;
- copied from settlement metadata into forecast-time evidence.

### Evidence Audit Fields

Each evidence row must include:

- `market_ticker`
- `evidence_id`
- `source`
- `title`
- `url`
- `published_at`
- `retrieved_at`
- `summary`
- `relevance_score`
- `credibility_score`
- `metadata.timestamp_status`
- `metadata.evidence_type`
- `metadata.supports_side`

If `published_at` is date-only or inferred, keep the row for diagnostics but
do not rely on it for acceptance coverage unless the reviewer records why the
timestamp is safe relative to every attached forecast row.

## Terms Review Checklist

Before acceptance import, confirm:

- Local storage of public export files is allowed.
- Local research validation is allowed.
- Redistribution limits are understood and documented.
- Raw files will not be committed or shared unless explicitly allowed.
- Transformed JSONL sharing rules are known.
- Validation reports and aggregate statistics can be retained locally.
- Source URLs and attribution requirements are recorded.
- Retention/deletion obligations are recorded.
- No authenticated/private/account/portfolio/order/fill/withdrawal data is in
  the export.
- No credentials, cookies, browser data, private keys, or secrets are present.
- `terms_reviewed_by` and `terms_reviewed_at` are set.

Manifest outcome:

| Review result | Manifest value | Acceptance behavior |
| --- | --- | --- |
| Approved for local research | `reviewed_public_research_local_only` | May proceed if other gates pass. |
| Not yet reviewed | `pending_review` | Block acceptance; may diagnose only. |
| Disallowed or unclear-risk unacceptable | `blocked` | Stop; do not produce acceptance output. |

## Local Export Plan

Use one final consolidated export directory:

```text
data/source_exports/kalshi/kalshi_YYYYMMDD_acceptance_candidate_45m_540r/
  source_manifest.json
  markets.jsonl
  candlesticks.jsonl
  evidence.jsonl
  trades.jsonl
  market_rules.jsonl
  settlement_overrides.jsonl
```

If collection happens in batches, keep batch working folders separate and copy
only reviewed rows into the final consolidated export. The adapter imports one
directory; do not rely on unimplemented multi-export merge behavior.

Recommended final `dataset_id`:

```text
phase7g_kalshi_acceptance_candidate_YYYYMMDD_45m_540r_{short_hash}
```

Recommended pilot `dataset_id`:

```text
phase7g_kalshi_acceptance_pilot_YYYYMMDD_10m_120r_{short_hash}
```

## Validation Workflow

### Import

```bash
export export_id=kalshi_YYYYMMDD_acceptance_candidate_45m_540r

PYTHONPATH=src .venv/bin/lma import-kalshi-export \
  --export-dir data/source_exports/kalshi/$export_id \
  --profile acceptance_candidate \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --source-audit-dir docs/reports \
  --validate
```

### Validate

```bash
export dataset_id=phase7g_kalshi_acceptance_candidate_YYYYMMDD_45m_540r_HASH

PYTHONPATH=src .venv/bin/lma validate-historical-dataset \
  --historical-file data/historical/$dataset_id.jsonl \
  --output-dir data/reports/historical_dataset
```

### Audit

Review:

```text
data/historical/{dataset_id}.manifest.json
data/reports/historical_dataset/{dataset_id}.validation.json
data/reports/historical_dataset/{dataset_id}_audit.md
docs/reports/{dataset_id}_source_audit.md
```

Required data-level audit results:

- `valid=true`
- `profile=acceptance_candidate`
- `acceptance_candidate=true`
- `paper_pnl_allowed=true`
- `row_count >= 250`
- `market_count >= 25`
- `resolved_binary_market_count >= 25`
- `candidate_forecast_row_count >= 50`
- `settlement_coverage_pct = 100`
- `evidence_timestamp_coverage_pct >= 95`
- `duplicate_row_count = 0`
- `duplicate_market_timestamp_count = 0`
- `missing_bid_ask_count = 0`
- `bid_exceeds_ask_count = 0`
- `future_evidence_leakage_count = 0`
- `missing_source_provenance_count = 0`
- no secret-like material;
- `source_terms_pending` warnings absent for acceptance;
- category and event-family concentration reviewed manually.

### Acceptance Evaluation

Run only after the data-level audit passes:

```bash
PYTHONPATH=src .venv/bin/lma strategy-eval-offline \
  --historical-file data/historical/$dataset_id.jsonl \
  --output-dir data/reports/strategy_eval
```

Review `acceptance_gate` in the generated JSON report. The dataset is only
accepted when `gate_status=pass` and `superiority_claim_allowed=true`. Any
other result blocks Strategy v2 superiority claims.

## Effort Estimates

### Minimum Viable Dataset

Target:

- 30 markets.
- 300 rows.
- 60 to 100 forecast candidates before policy abstention.
- 2 evidence items per market.

Estimated manual effort:

- Market screening: 4 to 6 hours.
- Source export staging: 3 to 6 hours.
- Evidence collection: 8 to 15 hours.
- Settlement verification: 3 to 5 hours.
- Manifest/checksum/audit pass: 2 to 4 hours.
- Total: 20 to 36 hours.

Likely bottleneck:

- Evidence timestamp coverage and terms review.

### Acceptance-Size Dataset

Target:

- 45 markets.
- 540 rows.
- 100+ forecast candidates before policy abstention.
- 90+ evidence records.

Estimated manual effort:

- Market screening: 8 to 12 hours.
- Source export staging: 6 to 10 hours.
- Evidence collection: 18 to 30 hours.
- Settlement verification: 5 to 8 hours.
- Validation/audit/correction: 6 to 12 hours.
- Total: 43 to 72 hours.

Likely bottlenecks:

- Human evidence curation.
- Terms review.
- Sparse bid/ask candles near target timestamps.
- Duplicate or correlated market families.

### Stretch Dataset

Target:

- 60 markets.
- 900 rows.
- 150+ forecast candidates before policy abstention.

Estimated manual effort:

- 80 to 120 hours.

Use this only if the preferred dataset fails because of sample diversity,
forecast activity, or split-quality issues.

## Go/No-Go Criteria

### Go To Minimum Viable Dataset

Proceed from pilot to 30 markets when:

- Terms review is resolved or has a clear path.
- Pilot import produces no unexpected schema blockers.
- At least 80% of pilot markets retain complete bid/ask and settlement.
- Evidence timestamp coverage can plausibly exceed 95%.
- No private/authenticated sources are needed.

### Go To Preferred Acceptance Dataset

Proceed from 30 to 45 markets when:

- Minimum viable dataset validates as `acceptance_candidate`.
- Market and row counts survive audit with buffer.
- Evidence curation process is repeatable.
- Category concentration can be controlled.
- No validator errors remain.

### Stop Or Downgrade

Stop or downgrade to calibration-only when:

- terms review is blocked;
- real exports do not contain reliable `yes_bid.close_dollars` and
  `yes_ask.close_dollars`;
- missing bid/ask cannot be corrected without inventing data;
- evidence timestamp coverage cannot reach 95%;
- settlement coverage is below 100%;
- the dataset relies on private/authenticated sources;
- validation detects secret-like material;
- duplicate/conflicting rows cannot be resolved.

## Dataset State Definitions

### Calibration-Only

A dataset is calibration-only when:

- bid/ask are missing or unproven;
- `profile=calibration_only_last_price`;
- `paper_pnl_allowed=false`;
- `acceptance_candidate=false`.

Allowed use:

- Forecast calibration diagnostics.
- Validator and harness smoke tests.

Disallowed use:

- Paper PnL claims.
- Strategy v2 acceptance.
- Profitability or superiority claims.

### Acceptance-Candidate

A dataset is acceptance-candidate when:

- PR-DATA-1 validation has zero errors;
- `profile=acceptance_candidate`;
- `acceptance_candidate=true`;
- `paper_pnl_allowed=true`;
- source terms, provenance, bid/ask, settlement, and evidence gates pass.

Allowed use:

- Strategy v2 offline acceptance evaluation.

Still disallowed:

- Claiming superiority before the acceptance gate passes.
- Production use or Phase 8 work.

### Acceptance-Ready

A dataset is acceptance-ready when it is acceptance-candidate and also clears
the data-level acceptance-size gates:

- 25+ resolved binary markets.
- 250+ rows.
- 50+ candidate forecast rows.
- enough activity to evaluate 30 closed paper trades without forcing trades.
- 100% settlement coverage.
- 95%+ evidence timestamp coverage.
- category and event-family concentration reviewed.

Acceptance-ready means "ready to run the gate," not "gate passed."

## Recommended First Collection Sprint

Sprint 1:

- 10 resolved binary Kalshi markets.
- 80 to 120 rows.
- At least 3 categories.
- At least 2 public timestamped evidence items per market.
- One local export directory.
- One import/validation/source-audit cycle.

Objective:

- Prove the real local export can populate `markets.jsonl`,
  `candlesticks.jsonl`, `evidence.jsonl`, and `source_manifest.json` exactly as
  PR-DATA-3 expects.

Expected outcome:

- Either a small `acceptance_candidate` pilot with no validator errors, or a
  documented `calibration_only_last_price` blocker explaining what prevents
  acceptance.

Sprint 1 should not be used for Strategy v2 superiority claims. It is a field
test for data quality, terms review, and human curation throughput.
