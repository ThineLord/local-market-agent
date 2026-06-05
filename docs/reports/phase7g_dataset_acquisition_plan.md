# Phase 7G Historical Dataset Acquisition Plan

Date: 2026-06-05

Scope: documentation and specification only. This plan designs the local data
acquisition and dataset-building workflow needed before Strategy v2 acceptance
evaluation. It does not implement downloader code, start Phase 8, add broker
integrations, add live trading, add private trading endpoints, add a scheduler,
add a daemon, add autostart, change strategy logic, tune thresholds, or make
profitability claims.

## Executive Recommendation

The first practical target should be a **Kalshi historical local export** that is
converted into the existing `historical-file` JSONL format plus the richer
Phase 7G provenance fields defined in
`docs/reports/historical_dataset_builder_spec.md`.

Reasoning:

- Kalshi has official public market-data documentation, unauthenticated public
  market-data examples, and explicit historical endpoints for settled markets,
  candlesticks, and trades.
- Kalshi binary orderbook semantics are documented well enough to derive YES
  bid/ask from YES and NO bids when point-in-time orderbook data is available.
- Settlement, market status, close time, and resolution rules are more likely
  to be structured consistently enough for a first acceptance-candidate export.
- The export must remain local-only after collection. Phase 7G does not add a
  downloader or network automation.

Important limitation: if the first Kalshi export cannot prove point-in-time
YES bid/ask for the sampled timestamps, the dataset must be labeled
`calibration_only_last_price`, paper PnL claims must be blocked, and the dataset
must not pass the Strategy v2 acceptance gate. Close, last-trade, OHLC, or
midpoint-only history is useful for forecast calibration diagnostics, but it is
not enough for Strategy v2 paper-PnL acceptance.

Target size should be deliberately above the gate minimum:

| Measure | Gate minimum | Phase 7G build target |
| --- | ---: | ---: |
| Resolved binary markets | 25 | 35 to 50 selected, with at least 25 surviving audit |
| Point-in-time rows | 250 | 400 to 750 rows before audit exclusions |
| Candidate forecasts | 50 | 100 or more forecastable rows before policy abstention |
| Closed paper trades | 30 | Enough rows and market diversity for 30 closed paper trades, without forcing trades |
| Settlement coverage | 100% for scored markets | 100% before acceptance run |
| Evidence timestamp coverage | 95% | 98% target before acceptance run |

## References Checked

These source capabilities were checked on 2026-06-05 for planning only:

- [Kalshi historical data](https://docs.kalshi.com/getting_started/historical_data):
  documents historical cutoffs and historical endpoints for markets,
  candlesticks, trades, fills, and orders.
- [Kalshi public market data quick start](https://docs.kalshi.com/getting_started/quick_start_market_data):
  documents unauthenticated public market-data examples.
- [Kalshi orderbook responses](https://docs.kalshi.com/getting_started/orderbook_responses):
  documents YES/NO bid arrays and how to derive YES ask and spreads.
- [Polymarket API introduction](https://docs.polymarket.com/api-reference/introduction):
  documents Gamma, Data, and CLOB APIs, including public market data and
  authenticated trading endpoints.
- [Polymarket orderbook and price history](https://docs.polymarket.com/trading/orderbook):
  documents orderbook, bid/ask, midpoint, spread, and price-history endpoints.
- [ImpliedData prediction-markets dataset](https://huggingface.co/datasets/ImpliedData/prediction-markets):
  an example public dataset with prediction-market OHLCV-style rows that may be
  useful for calibration-only experiments after license and provenance review.

## Candidate Sources

| Source | Resolved binary market availability | Historical price snapshots | Bid/ask availability | Settlement/outcome availability | Evidence availability | Timestamp quality | API stability | Terms/safety constraints | Ease of local-only export |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Polymarket public market data | Strong market breadth; filter to binary YES/NO and exclude multi-outcome or negative-risk markets unless explicitly supported. | Public price history exists for token prices with absolute time ranges. | Current orderbook, prices, midpoint, and spread are public; historical bid/ask needs proof from CLOB history, archived books, or a licensed export. | Market metadata may contain closed/resolved status and outcome fields, but this must be verified per market. | Must be curated separately from public sources; market comments are not sufficient evidence by themselves. | Price history timestamps are explicit; evidence timestamps require source-level audit. | Public docs are active, but endpoint fields and rate limits can change. | Use public read-only endpoints only. Do not use authenticated trading, bridge, wallet, private profile, or withdrawal paths. Respect rate limits and geographic/legal constraints. | Good for local export of market metadata and price history; acceptance export depends on bid/ask proof. |
| Kalshi public market data | Strong for binary event contracts; filter to settled/determined markets with clear YES/NO outcomes. | Historical markets, candlesticks, and trades are documented through historical endpoints. | Current orderbook is public and YES ask can be derived from NO bid; historical point-in-time bid/ask must be proven before acceptance. | Stronger structured settlement, close, status, and rule metadata expected from official market records. | Must be curated separately from official settlement sources, event pages, and public primary sources. | API timestamps and market close/settlement times are structured; evidence timestamps still need independent audit. | Official API with pagination and historical/live split; cutoff boundary must be captured in manifest. | Use public market-data endpoints only. Do not use portfolio, user fills, orders, authenticated APIs, or any trading path. Review data terms before storing/exporting. | Recommended first path because official historical partitioning and binary semantics are clearer. |
| yfinance | Not prediction-market data; cannot satisfy resolved binary market count. | Good OHLCV for equities, ETFs, indexes, and crypto proxies where supported. | OHLCV only, not prediction-market bid/ask. | No binary settlement outcome. | External evidence must be curated separately. | Market timestamps are generally clear, but exchange calendars and adjustments matter. | Package/API behavior can drift; optional only. | Use only for non-prediction-market baselines. No trading. | Easy local export, but not acceptance-eligible for Strategy v2 prediction-market gate. |
| Manually curated local JSONL | Strong if the curator selects enough resolved binary markets. | Only as strong as manually collected point-in-time records. | Strong if bid/ask is manually recorded with source timestamps; weak if inferred. | Strong if resolution source is manually verified. | Strongest path for timestamped evidence quality if every row is curated. | High if every item records published_at, retrieved_at, and source URL; otherwise weak. | Stable because the final artifact is local. | Must avoid secrets, private accounts, paywalled leakage, and post-resolution evidence leakage. | Easy to import once curated, but labor-intensive at acceptance scale. |
| Exported CSV/JSON public datasets | Depends on dataset; some public datasets have broad market coverage. | Often strong for OHLCV or trades. | Often missing bid/ask/depth; acceptance requires validation. | Often partial or separate metadata. | Usually absent and must be curated separately. | Varies widely; must inspect schema and sampling rules. | Dataset publication may be stale or regenerated. | Must review license, data terms, source provenance, and whether redistribution is allowed. | Good for calibration-only dry runs; acceptance use requires bid/ask, settlement, and evidence augmentation. |

## Source Selection Criteria

Hard requirements for an acceptance-candidate source:

- The market is a resolved binary YES/NO market with an unambiguous resolution
  rule and final outcome.
- Each scored row has a point-in-time timestamp before the outcome was known.
- Each scored row has YES `bid`, YES `ask`, `last_price`, and
  `implied_probability` on a probability scale from `0` to `1`.
- Bid/ask fields come from a real point-in-time quote, orderbook snapshot, or
  source export. They must not be invented from close price, last price, or a
  synthetic spread for acceptance use.
- Every scored market has settlement metadata, including outcome, resolution
  source, resolved timestamp or date, and label verification timestamp.
- At least 95% of scored rows have at least one evidence item with a known
  `published_at` at or before the row timestamp. The build target should be at
  least two independent evidence items per actionable forecast row.
- Source provenance is sufficient to reproduce the row from local raw exports or
  public source references.
- The source can be exported to local files without secrets, cookies, private
  keys, browser data, private account data, broker credentials, or trading
  endpoints.

Rejection criteria:

- Market is multi-outcome, ambiguous, disputed, canceled, or resolved by a rule
  that cannot be represented as `yes` or `no`.
- Historical data only contains current snapshots replayed across dates.
- Bid/ask is missing, inferred from a fixed spread, or sampled after the row
  timestamp.
- Evidence was published after the forecast timestamp.
- Settlement labels are guessed, copied from prose without source, or available
  only from private/user account records.
- Source terms do not allow the planned local research export.

## Recommended First Dataset Path

Choose: **Kalshi historical local export**.

Proposed dataset labels:

- `kalshi_historical_local_v1`: acceptance-candidate profile when point-in-time
  bid/ask, settlement, evidence timestamps, and provenance all pass audit.
- `kalshi_calibration_only_last_price_v1`: fallback profile when historical
  bid/ask cannot be proven, but last price or candles and settlement labels are
  good enough for forecast calibration diagnostics.

Initial market universe:

- Select 35 to 50 recently resolved binary markets across several categories.
- Prefer markets with regular activity over several days before close.
- Exclude markets with very late liquidity only, extremely wide spreads,
  ambiguous rules, manual adjudication uncertainty, or missing settlement
  metadata.
- Keep at least 25 markets after audit exclusions.

Why not Polymarket first:

- Polymarket remains a strong second target because it has broad market
  coverage, public market metadata, public orderbook endpoints, and public price
  history.
- The current planning risk is that public historical price history exposes
  price points, while Strategy v2 acceptance needs point-in-time bid/ask. If
  historical bid/ask can be proven from a public export or archive, Polymarket
  should be promoted to an acceptance-candidate source.

Why not synthetic first:

- A synthetic-but-realistic expansion is useful for harness stress testing only.
- It must be labeled `synthetic_stress_only`.
- It must not pass Strategy v2 acceptance and must not support paper PnL,
  calibration superiority, or profitability claims.

## Dataset Construction Workflow

### 1. Market Selection

Build a candidate list with:

- `market_id`, title, platform, category, market URL, source ticker/token ID,
  close time, settlement time, resolution source, and final YES/NO outcome.
- Binary-only flag.
- Exclusion reason when rejected.

Selection rules:

- Prefer markets that were open long enough to sample at least 10 pre-resolution
  timestamps.
- Avoid same-event near-duplicates that would leak shared outcomes across train,
  validation, and holdout.
- Keep category diversity so the evaluation does not become one narrow event
  type.
- Keep raw source IDs stable enough for future adapter implementation.

### 2. Date/Time Sampling Cadence

Minimum acceptance cadence:

- At least 10 point-in-time rows per surviving market.
- Rows must be before settlement and before any evidence item that reveals the
  final outcome.
- Suggested relative cadence when data exists:
  `T-14d`, `T-10d`, `T-7d`, `T-5d`, `T-3d`, `T-2d`, `T-1d`, `T-12h`, `T-6h`,
  `T-1h`.

Alternative cadence:

- Use hourly or 4-hour samples for active markets, then downsample to avoid one
  market dominating the dataset.
- If a market was open for fewer than 10 meaningful timestamps, either reject it
  or include it only if other markets cover the row-count target.

### 3. Price Field Capture

For acceptance-candidate rows:

- `bid`: best YES bid at or before row timestamp.
- `ask`: best YES ask at or before row timestamp.
- `last_price`: last YES trade price at or before row timestamp.
- `implied_probability`: bid/ask midpoint when both sides exist; otherwise a
  documented source probability only for calibration-only rows.
- `liquidity` and `volume`: include when available and record source semantics.

Kalshi-specific note:

- Kalshi orderbooks expose YES bids and NO bids. YES ask can be derived as
  `1 - best_no_bid` for binary markets, matching documented reciprocal
  semantics. This derivation is acceptable only when the YES and NO bids are
  from the same point-in-time orderbook record.

### 4. Evidence Collection

For every scored row:

- Attach evidence that was published at or before the row timestamp.
- Record `published_at` separately from `retrieved_at`.
- Prefer primary or official sources for resolution-relevant facts.
- Use `source`, `title`, `url`, `summary`, `relevance_score`,
  `credibility_score`, and `metadata`.
- Put uncertain or timestamp-missing evidence in the dataset only with a warning
  category and exclude it from the 95% timestamp-coverage numerator.

Evidence must not include:

- Final outcome reports published after the row timestamp, except on settlement
  rows used only to close paper positions.
- Private account data, cookies, browser data, API keys, paid/private feeds, or
  non-public source material.
- Model-generated rationale as evidence.

### 5. Settlement Labeling

For each market:

- Record final outcome as `yes` or `no`.
- Record resolution source, source URL, `resolved_at` or resolution date,
  `verified_at`, and resolution rule.
- Mark ambiguous or disputed outcomes and exclude them from acceptance scoring.
- Include top-level `settlement_outcome` only on the settlement/closing row when
  using the current `historical-file` importer. The richer nested settlement
  object may exist on all rows for audit and forecast scoring, but it must never
  be passed as forecast-time evidence.

### 6. Validation

Validation should run before Strategy v2 evaluation:

- Parse every JSONL line as one object.
- Validate probability ranges and nonnegative numeric fields.
- Sort by timestamp and market id, then fail duplicate `timestamp + market_id`
  rows.
- Reject bid greater than ask.
- Reject future evidence leakage.
- Reject missing source provenance for acceptance-candidate rows.
- Check that every scored market has one unambiguous settlement outcome.
- Confirm no secrets or private credential-like material appears in source
  provenance, raw cache paths, manifests, or examples.

### 7. Deduplication

Deduplicate by:

- `row_id`.
- `platform + market_id + timestamp`.
- Evidence `evidence_id` within each row.
- Source raw record checksums where available.

When duplicate rows have conflicting price fields, reject both until manually
resolved. Do not average conflicting point-in-time quotes for acceptance.

### 8. Leakage Prevention

Leakage checks:

- `evidence.published_at <= row.timestamp`.
- `settlement.resolved_at` and outcome fields are label-only and excluded from
  research inputs.
- No row timestamp after market settlement is used for forecast scoring, except
  an explicit paper-closing row.
- Train, validation, and holdout splits must be market-level or event-family
  aware so closely related markets do not leak outcomes across splits.
- Do not use final market price, settlement price, or post-resolution volume as
  forecast features for pre-resolution rows.

### 9. Train, Validation, Holdout Split

Default split:

- 60% training/calibration.
- 20% validation.
- 20% holdout.

Split rules:

- Split by market or event family first, not by row only.
- Preserve category diversity in all segments.
- Do not tune Strategy v2 thresholds on holdout.
- If the dataset is too small or too correlated for a clean split, label the run
  diagnostic-only and do not claim acceptance.

### 10. Export To JSONL

Export artifacts:

- Dataset JSONL sorted by `timestamp`, `platform`, `market_id`.
- Manifest JSON with dataset id, source list, build timestamp, raw export
  checksums, row count, market count, settlement coverage, evidence timestamp
  coverage, warning counts, and validation result.
- Markdown audit report under `data/reports/historical_dataset/`.

The final JSONL must remain local. Future PRs may add importers or source
adapters, but Phase 7G adds no downloader code.

## Data-Level Quality Gates

These gates must pass before running Strategy v2 acceptance evaluation:

| Gate | Acceptance threshold | Failure behavior |
| --- | ---: | --- |
| Resolved binary market count | At least 25 | `not_applicable`; no superiority claim |
| Point-in-time row count | At least 250 | `not_applicable`; no superiority claim |
| Candidate forecastable rows | At least 50 before policy abstention | `not_applicable`; no superiority claim |
| Settlement coverage | 100% for scored markets | Fail acceptance dataset validation |
| Evidence timestamp coverage | At least 95% for scored rows | Fail acceptance dataset validation |
| Duplicate `market_id + timestamp` | 0 | Fail validation |
| Missing bid/ask | 0 for acceptance profile | Fail validation or downgrade to calibration-only |
| Bid greater than ask | 0 | Fail validation |
| Spread sanity | No negative spread; wide-spread rows flagged; configurable max spread for acceptance audit | Reject or warn by profile |
| Missing last price | 0 for acceptance profile | Fail validation |
| Future evidence leakage | 0 | Fail validation |
| Missing source provenance | 0 for acceptance profile | Fail validation |
| Ambiguous settlement | 0 scored markets | Exclude market or fail if still needed for minimums |
| Source terms review | Completed and recorded | Block use as acceptance dataset |

Recommended warning gates:

- More than 20% of rows from one market.
- More than 50% of rows from one category.
- More than 10% of rows with single-source evidence only.
- More than 5% of rows with stale evidence under the configured horizon.
- Any row with derived or imputed bid/ask.
- Any row with a source timestamp rounded more coarsely than the sampling
  cadence.

## Manual Fallback Plan

If historical bid/ask data is not easily available:

- Use close, last price, or OHLCV only for forecast calibration diagnostics.
- Set `dataset_label=calibration_only_last_price`.
- Set `paper_pnl_allowed=false` in the manifest.
- Set `acceptance_candidate=false` in the manifest.
- Block paper PnL claims, fill-quality claims, profitability claims, and
  Strategy v2 superiority claims.
- Continue to require settlement labels for Brier score and calibration
  diagnostics.
- Continue to require evidence timestamp coverage for any forecast-quality
  diagnostics.
- Do not pass the Strategy v2 acceptance gate.

This fallback is still useful because it can answer whether Strategy v2
probabilities are better calibrated than market-implied or last-price baselines,
but it cannot validate executable-side EV or paper trading outcomes.

## Future PR Breakdown

Do not implement these in Phase 7G.

1. PR-DATA-1 dataset schema validator
   - Add a local validator for the Phase 7G JSONL schema, manifest, quality
     gates, error codes, and warning categories.
   - No network, downloader, broker, live trading, scheduler, or strategy
     changes.

2. PR-DATA-2 manual local dataset builder/importer
   - Add a local-only tool that converts manually curated CSV/JSONL into the
     validated JSONL schema.
   - Include deterministic fixtures and offline tests.

3. PR-DATA-3 source-specific public export adapter
   - Add one read-only public export adapter after source terms and fields are
     verified.
   - Recommended first adapter: Kalshi historical local export.
   - Keep network tests optional and marked `network`.

4. PR-DATA-4 dataset audit report
   - Generate Markdown and JSON audit reports with row counts, market counts,
     coverage metrics, duplicate checks, leakage checks, warning summaries,
     source provenance, and acceptance eligibility.

5. PR-DATA-5 acceptance-size dataset dry run
   - Build or import an acceptance-size local dataset.
   - Run the validator and offline evaluator.
   - Report whether the dataset is acceptance-candidate or calibration-only.
   - Do not claim Strategy v2 superiority unless all gate requirements pass.

## Safety Boundary

Phase 7G remains documentation/specification only. The future data path must
preserve:

- `REAL_MONEY_ENABLED=false`.
- `ALLOW_LIVE_ORDERS=false`.
- `HUMAN_APPROVAL_REQUIRED=true`.
- Paper-only local evaluation.
- No broker APIs.
- No private trading endpoints.
- No live orders.
- No scheduler, daemon, or autostart.
- No withdrawals, wallets, cookies, browser data, private keys, API keys, or
  credential files.
- No direct LLM-to-order path.
- No profitability claims from fixture, current snapshot, synthetic, or
  calibration-only datasets.
