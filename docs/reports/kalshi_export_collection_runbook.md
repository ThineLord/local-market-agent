# Kalshi Export Collection Runbook

Date: 2026-06-05

Scope: DATA-OPS-1 documentation and operations planning only. This runbook
does not write downloader code, add adapters, call Kalshi APIs, make network
automation, start Phase 8, add broker integrations, add live trading, add
scheduler/daemon/autostart behavior, modify strategy logic, modify acceptance
gates, or make profitability claims.

## Objective

Collect a real, human-operated, local Kalshi public export that can be imported
by `lma import-kalshi-export` and audited as a Phase 7G historical dataset.

The first usable output should be a local export directory:

```text
data/source_exports/kalshi/{export_id}/
  source_manifest.json
  markets.jsonl
  candlesticks.jsonl
  evidence.jsonl
  trades.jsonl                  # optional
  market_rules.jsonl            # optional
  settlement_overrides.jsonl    # optional
```

The final acceptance goal is not merely "valid JSONL." The imported dataset
must eventually satisfy the Strategy v2 acceptance-gate preconditions:

| Requirement | Minimum |
| --- | ---: |
| Resolved binary markets | 25 |
| Point-in-time rows | 250 |
| Candidate forecast rows | 50 |
| Closed paper trades | 30 |
| Settlement coverage for scored markets | 100% |
| Evidence timestamp coverage | 95% |

## Operator Roles

Use at least two human roles when possible:

- Collector: gathers local public-export files and records the source manifest.
- Reviewer: verifies terms review, market inclusion, evidence timestamps,
  settlement labels, and validation reports.

The same person may fill both roles for an internal pilot, but acceptance
readiness should not rely on unchecked solo curation.

## Market Selection

### Include

Select Kalshi markets only when all of the following are true:

- Market is resolved or finalized.
- Market is binary YES/NO.
- Market has a stable `ticker`.
- Market has unambiguous final `result` or equivalent settlement field.
- Market has a settlement timestamp or best public label-availability
  timestamp.
- Market has enough pre-settlement candlesticks with populated
  `yes_bid.close_dollars` and `yes_ask.close_dollars`.
- Market title and rules can be represented in `markets.jsonl`.
- Public evidence can be found with timestamps before sampled forecast rows.

### Exclude

Exclude these market types from acceptance-candidate collection:

- Multi-outcome markets.
- Range, scalar, bracket, spread, or numeric payoff markets that cannot be
  reduced to one YES/NO outcome without changing semantics.
- Canceled, voided, disputed, or ambiguous markets.
- Markets whose resolution depends on private account state.
- Markets where the only available historical prices are last price, close, or
  OHLC without bid/ask.
- Markets with no reliable pre-resolution evidence timestamps.
- Markets that would require authenticated/private source data for collection.

### Target Categories

Use category diversity to reduce one-event overfitting. Prefer:

- Economic indicators.
- Elections and public policy.
- Weather or climate event contracts.
- Sports or entertainment only when rules and settlement are unambiguous.
- Public-company events only when evidence timestamps and settlement sources
  are clear.

Avoid a first dataset dominated by one narrow event family such as many
variants of the same election, same economic release, or same sports slate.

### Target Counts

| Target | Markets selected | Surviving markets | Purpose |
| --- | ---: | ---: | --- |
| Minimum target | 30 | 25+ | Barely clears market-count gate after expected exclusions. |
| Preferred target | 45 | 35+ | Gives buffer for evidence, bid/ask, and settlement exclusions. |
| Stretch target | 60 | 45+ | Better category diversity and holdout splitting. |

Do not stop at exactly 25 markets. A few exclusions are likely after duplicate,
terms, evidence, and settlement audit.

## Row Sampling

### Candle Interval

Preferred collection interval:

- 1-hour candlesticks for markets with sufficient activity.

Fallback interval:

- 1-day candlesticks when hourly history is sparse or unavailable.

Do not mix intervals within one market unless the reason is documented in
`source_manifest.json` notes or per-row metadata. Do not use high/low values as
point-in-time executable quotes.

### Sampling Cadence

For each market, collect at least 10 pre-settlement rows. Preferred relative
sampling:

- `T-14d`
- `T-10d`
- `T-7d`
- `T-5d`
- `T-3d`
- `T-2d`
- `T-1d`
- `T-12h`
- `T-6h`
- `T-1h`

If the market was not open that long, use evenly spaced pre-settlement candles
and document the shortened market window. Exclude the market from acceptance if
fewer than 6 useful pre-settlement rows remain and the dataset has enough
better alternatives.

### Timestamp Rules

For each candlestick row:

- `timestamp = end_period_ts`.
- `bid = yes_bid.close_dollars`.
- `ask = yes_ask.close_dollars`.
- `last_price = price.close_dollars`, unless a local trade at or before
  `end_period_ts` is explicitly selected and documented.
- `implied_probability = (bid + ask) / 2` when both bid and ask exist.
- Row timestamp must be before `settlement.label_available_at` for forecast
  scoring.

Do not use rows after the settlement label became knowable as forecast rows.
If a closing row is later needed for replay, keep it distinct and do not count
it toward candidate forecasts.

### Settlement Handling

For every selected market, record settlement metadata in `markets.jsonl` or
`settlement_overrides.jsonl`:

- final outcome as `yes` or `no`;
- final status;
- `settlement_ts` or resolved timestamp;
- label-availability timestamp;
- resolution rule;
- source URL or source descriptor;
- `settlement_value_dollars` when available;
- reviewer notes for any manual interpretation.

If settlement is ambiguous, disputed, or not public, exclude the market.

### Size Math

| Scenario | Markets | Rows per market | Total rows | Candidate forecast buffer |
| --- | ---: | ---: | ---: | --- |
| Bare minimum | 25 | 10 | 250 | Thin; one exclusion fails gate. |
| Minimum viable collection | 30 | 10 | 300 | Moderate buffer for row loss. |
| Preferred acceptance collection | 45 | 12 | 540 | Good buffer for abstentions and splits. |
| Stretch collection | 60 | 15 | 900 | Better holdout and category diversity. |

Expected exports:

- Pilot: 1 export with 5 markets and about 50 rows.
- Minimum viable dataset: 1 consolidated export with 30 markets and about 300
  rows.
- Preferred acceptance dataset: 1 consolidated export with 45 markets and 500+
  rows, possibly assembled from 3 to 5 human collection batches.

The current adapter imports one export directory at a time. If collection
happens in multiple human sessions, consolidate the accepted rows into one
final export directory before running acceptance validation.

## Evidence Collection

### Acceptable Evidence Types

Evidence may be attached when it is public and timestamped:

- Official statistics releases.
- Government or regulator pages.
- Official market rules and resolution sources.
- Public company filings or official press releases.
- Archived news articles with publication timestamps.
- Public event pages whose timestamp is visible and reliable.
- Neutral context sources available before the forecast row.

For each evidence item, record:

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
- `metadata`

### Unacceptable Evidence Types

Do not use:

- Outcome reports published after the sampled forecast timestamp.
- Private account pages.
- Authenticated or paywalled sources unless terms and redistribution are
  explicitly cleared; for the first acceptance dataset, avoid them entirely.
- Browser history, cookies, local session data, or cached private pages.
- Model-generated analysis as evidence.
- Evidence with unknown publication time for acceptance coverage.
- Settlement labels as forecast-time evidence.

### Timestamp Requirements

For every forecast row:

- At least one evidence item should have `published_at <= row.timestamp`.
- The preferred target is two independent evidence sources for rows likely to
  become candidate forecasts.
- `retrieved_at` may be after the row timestamp because it records collection
  time.
- Date-only evidence can be retained with warnings but should not be relied on
  for the 95% evidence timestamp coverage target.

If evidence was published after the candle timestamp, do not attach it to that
row. The PR-DATA-3 adapter filters future evidence, and missing coverage will
block acceptance.

### Provenance Requirements

For every evidence and market source, record:

- source URL or local public source descriptor;
- source name;
- retrieval timestamp;
- reviewer;
- raw file checksum where available;
- short note explaining why the source was public and non-private.

## Terms Review Checklist

Before setting `terms_review=reviewed_public_research_local_only`, a human
reviewer must check and record:

- Storage rights: local storage of the public export is allowed for the
  intended research use.
- Local research use: local analysis and validation are allowed without
  production trading use.
- Redistribution restrictions: whether raw exports, transformed JSONL, or
  reports can be shared outside the local machine or private repo.
- Dataset sharing restrictions: whether any future PR, issue, artifact, or
  report may include raw records, derived rows, screenshots, or source URLs.
- API/use constraints: no portfolio, order, fill, withdrawal, private account,
  or authenticated trading data is included.
- Attribution/documentation requirements: source name, source URL, retrieval
  time, terms reviewer, and terms review date are recorded.
- Retention limits: whether local retention duration or deletion obligations
  exist.
- Derived-data restrictions: whether transformed bid/ask rows or aggregate
  validation reports can be retained.

Manifest values:

- Use `terms_review=reviewed_public_research_local_only` only after review
  passes.
- Use `terms_review=pending_review` while unresolved.
- Use `terms_review=blocked` if terms disallow the planned local research
  export.
- Use `private_or_authenticated_source=false` only when every source file is
  public/non-private.
- Use `network_used_by_adapter=false` because the adapter itself must not use
  network.

## Local Folder Structure

Use this exact structure:

```text
data/source_exports/kalshi/{export_id}/
  source_manifest.json
  markets.jsonl
  candlesticks.jsonl
  evidence.jsonl
  trades.jsonl
  market_rules.jsonl
  settlement_overrides.jsonl
```

Required files:

- `source_manifest.json`
- `markets.jsonl`
- `candlesticks.jsonl`
- `evidence.jsonl`

Optional files:

- `trades.jsonl`
- `market_rules.jsonl`
- `settlement_overrides.jsonl`

Use an `export_id` with a date and scope, for example:

```text
kalshi_20260605_sprint1_10m_120r
kalshi_20260612_acceptance_candidate_45m_540r
```

Keep raw source exports local. Do not commit real collected exports unless a
human explicitly approves the exact files for repository storage after terms
review.

## Required File Schemas

### `source_manifest.json`

Required fields:

- `export_id`
- `dataset_id`
- `source_name`
- `source_type`
- `source_urls`
- `retrieved_at`
- `exported_at`
- `terms_review`
- `terms_reviewed_by`
- `terms_reviewed_at`
- `private_or_authenticated_source`
- `network_used_by_adapter`
- `raw_file_sha256`
- `notes`

### `markets.jsonl`

One JSON object per market. Include:

- `ticker`
- `series_ticker`
- `event_ticker`
- `title`
- `subtitle`
- `status`
- `result`
- `open_time`
- `close_time`
- `expected_expiration_time`
- `latest_expiration_time`
- `settlement_ts`
- `settlement_value_dollars`
- `rules_primary`
- `rules_secondary`
- `can_close_early`
- `volume_fp`
- `liquidity_dollars`

### `candlesticks.jsonl`

One JSON object per sampled candle. Include:

- `market_ticker`
- `period_interval`
- `end_period_ts`
- `yes_bid.open_dollars`
- `yes_bid.low_dollars`
- `yes_bid.high_dollars`
- `yes_bid.close_dollars`
- `yes_ask.open_dollars`
- `yes_ask.low_dollars`
- `yes_ask.high_dollars`
- `yes_ask.close_dollars`
- `price.open_dollars`
- `price.low_dollars`
- `price.high_dollars`
- `price.close_dollars`
- `price.mean_dollars`
- `price.previous_dollars`
- `volume_fp`
- `open_interest_fp`

Nested objects or dotted keys are acceptable if they match the adapter input
contract.

### `evidence.jsonl`

One JSON object per evidence item. Include:

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
- `metadata`

## Validation Workflow

### 1. Collect

Human operator collects local public export files and places them in:

```bash
export_id=kalshi_YYYYMMDD_sprintN
mkdir -p data/source_exports/kalshi/$export_id
```

Populate required files manually or from a human-controlled export process.
Do not add downloader code to the repository.

### 2. Build/Import

Run the local adapter:

```bash
PYTHONPATH=src .venv/bin/lma import-kalshi-export \
  --export-dir data/source_exports/kalshi/$export_id \
  --profile acceptance_candidate \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --source-audit-dir docs/reports \
  --validate
```

If bid/ask or evidence coverage is incomplete but terms and settlement are
otherwise safe, an operator may explicitly choose a calibration fallback:

```bash
PYTHONPATH=src .venv/bin/lma import-kalshi-export \
  --export-dir data/source_exports/kalshi/$export_id \
  --profile acceptance_candidate \
  --allow-downgrade \
  --output-dir data/historical \
  --report-dir data/reports/historical_dataset \
  --source-audit-dir docs/reports \
  --validate
```

Do not use downgrade output for paper PnL or Strategy v2 acceptance.

### 3. Validate

Run validator directly on the generated JSONL:

```bash
dataset_id=phase7g_kalshi_acceptance_candidate_YYYYMMDD_45m_540r
PYTHONPATH=src .venv/bin/lma validate-historical-dataset \
  --historical-file data/historical/$dataset_id.jsonl \
  --output-dir data/reports/historical_dataset
```

Review:

- `valid`
- `profile`
- `acceptance_candidate`
- `paper_pnl_allowed`
- `row_count`
- `market_count`
- `error_count`
- `warning_count`
- validation JSON path
- validation Markdown path

### 4. Audit

Review:

- `data/historical/{dataset_id}.manifest.json`
- `data/reports/historical_dataset/{dataset_id}.validation.json`
- `data/reports/historical_dataset/{dataset_id}_audit.md`
- `docs/reports/{dataset_id}_source_audit.md`

Stop if any of these are true:

- validation errors are nonzero;
- duplicate market/timestamp rows are nonzero;
- settlement coverage is below 100%;
- evidence timestamp coverage is below 95%;
- missing bid/ask rows are nonzero for acceptance;
- `terms_review` is not `reviewed_public_research_local_only`;
- `private_or_authenticated_source` is not `false`;
- secret-like material is detected.

### 5. Acceptance Evaluation

Only after data-level gates pass, run offline evaluation:

```bash
PYTHONPATH=src .venv/bin/lma strategy-eval-offline \
  --historical-file data/historical/$dataset_id.jsonl \
  --output-dir data/reports/strategy_eval
```

The acceptance gate may still return `fail` or `not_applicable`. A valid
dataset does not imply Strategy v2 superiority, profitability, or production
readiness.

## Go/No-Go Criteria

### Calibration-Only

The dataset is calibration-only when any of these are true:

- `profile=calibration_only_last_price`.
- bid/ask are missing or unproven for any scored acceptance row.
- source terms are pending but not blocked, and the operator chooses not to
  produce acceptance output.
- evidence timestamp coverage is useful for diagnostics but below acceptance
  target.

Calibration-only data may support forecast calibration diagnostics. It must not
support paper PnL claims, Strategy v2 acceptance, or superiority claims.

### Acceptance-Candidate

The dataset is acceptance-candidate when:

- `profile=acceptance_candidate`;
- validator reports `valid=true`;
- validator reports `acceptance_candidate=true`;
- validator reports `paper_pnl_allowed=true`;
- every row has source provenance;
- source terms and private-source flags pass.

Acceptance-candidate means the file is structurally eligible for acceptance
evaluation. It does not mean the acceptance gate will pass.

### Acceptance-Ready

The dataset is acceptance-ready when:

- acceptance-candidate requirements pass;
- at least 25 resolved binary markets survive audit;
- at least 250 point-in-time rows survive audit;
- at least 50 candidate forecast rows are present;
- expected activity is enough to evaluate 30 closed paper trades without
  forcing trades;
- settlement coverage is 100%;
- evidence timestamp coverage is at least 95%;
- category and event-family concentration are acceptable;
- train/validation/holdout split can be market-level or event-family aware.

### Stop Conditions

Stop collection or downgrade when:

- terms review is blocked;
- source files require credentials, cookies, private accounts, or authenticated
  trading/user endpoints;
- historical bid/ask fields are unavailable or too sparse;
- settlement labels cannot be verified;
- future evidence leakage cannot be eliminated;
- more than 20% of selected markets fail market-selection audit;
- the dataset becomes dominated by one event family;
- validation errors remain after one manual correction pass.

## First Collection Sprint

Sprint 1 should be a pilot, not an acceptance attempt.

| Field | Plan |
| --- | --- |
| Markets | 10 resolved binary markets |
| Categories | At least 3 |
| Rows | 8 to 12 per market, 80 to 120 total |
| Evidence | At least 2 public timestamped sources per market |
| Objective | Prove field availability, terms workflow, evidence cadence, and adapter import on real staged files |
| Expected outcome | Acceptance-shaped local export or documented calibration-only blocker |

Sprint 1 success criteria:

- `source_manifest.json` can honestly set `network_used_by_adapter=false`.
- terms review outcome is recorded.
- at least 8 of 10 markets survive binary/settlement audit.
- at least 80 rows import.
- validator has zero errors for the accepted profile or a clear downgrade
  reason.
- source audit identifies all missing fields and bottlenecks.

After Sprint 1, proceed to a preferred acceptance collection only if evidence,
settlement, and bid/ask coverage look realistic at scale.
