# Phase 7F Strategy v2 Evaluation Specification

Date: 2026-06-05

Scope: specification only. This document defines the paper-only evaluation
contract that must exist before any Strategy v2 implementation. It does not
implement Strategy v2, start Phase 8, add broker integrations, add live trading,
add real-money execution, add a scheduler, add a daemon, add autostart, or tune
thresholds.

## Executive Summary

Strategy v2 must not be judged by whether it creates more paper orders. It must
be judged by whether it produces better calibrated forecasts, better or equal
risk-adjusted paper outcomes, and no safety regression versus the current
`PredictionMarketEdgeStrategy`.

The current Strategy v1 is safe as a paper-only workflow policy, but its
decision value is not evidence-backed. Its weakest link is the uncalibrated
`brief.estimated_probability` input. Therefore, Strategy v2 evaluation must
first measure forecast quality and provenance before measuring paper PnL.

The five-row historical fixture may be used only as a smoke fixture. It must not
be used to tune thresholds or to claim Strategy v2 quality.

## Required Reading Basis

This specification is based on:

- `docs/reports/strategy_quality_audit.md`
- `docs/reports/strategy_v2_recommendations.md`
- `docs/reports/research_quality_validation.md`
- `docs/reports/research_quality_comparison.md`
- `docs/PHASE_7C_PR_D2_HISTORICAL_DATASET.md`
- `docs/DATA_SOURCES.md`

## A. Forecast Inputs

### Required Forecast Fields

Every Strategy v2 evaluation row must produce or explicitly reject a structured
forecast record before a signal policy is evaluated.

Required fields:

| Field | Type | Rule |
| --- | --- | --- |
| `forecast_id` | string | Stable local identifier for replay and report joins |
| `market_id` | string | Must match the market snapshot and dataset row |
| `snapshot_id` | string | Must match the evaluated snapshot |
| `as_of` | timestamp | Point-in-time forecast timestamp |
| `estimated_probability_yes` | float or null | Required for any paper-buy candidate; must be in `[0, 1]` |
| `probability_source` | enum/string | Must identify where the probability came from |
| `probability_provenance` | object | Must explain source, transformation, and confidence limits |
| `input_completeness_score` | float | Must be in `[0, 1]` |
| `evidence_completeness_score` | float | Must be in `[0, 1]` |
| `structured_output_complete` | bool | False blocks paper-buy eligibility |
| `forecast_confidence` | float or null | Calibrated confidence only; raw provider confidence is not enough |
| `forecast_rationale` | string | Short structured rationale, not free-form hidden reasoning |
| `rejection_reasons` | list[string] | Required when no actionable forecast is available |

`estimated_probability_yes` may be null only when the forecast is explicitly
classified as non-actionable. A missing structured probability must never be
recovered from prose.

### Optional Forecast Fields

Optional fields should be recorded when available, but missing optional fields
must be visible in completeness scoring.

Optional fields:

| Field | Purpose |
| --- | --- |
| `uncertainty_band` | Estimated forecast error range, for example `[lower, upper]` |
| `calibration_bucket` | Historical reliability bucket assigned by the evaluator |
| `provider_label` | `mock`, `openai-compatible`, `qwen3:14b`, or other local provider label |
| `provider_confidence` | Raw provider confidence, diagnostic only |
| `provider_evidence_quality` | Raw provider evidence-quality score, diagnostic only |
| `model_version` | Local model or evaluator version |
| `market_probability_used` | Market-implied baseline used for comparison |
| `forecast_features` | Explicit non-secret feature summary |
| `counter_evidence_count` | Count of counter-evidence items |
| `resolution_risk_score` | Structured resolution ambiguity estimate |

Raw provider confidence and raw provider evidence quality must not be treated as
calibrated forecast confidence unless the evaluation harness has historical
evidence for that mapping.

### Provenance Fields

Each forecast must classify probability provenance:

| Provenance | Meaning | Paper-buy eligibility |
| --- | --- | --- |
| `market_implied_only` | Forecast equals market probability baseline | Baseline only, not Strategy v2 alpha |
| `fixture_hint` | Derived from fixture `probability_hint` metadata | Smoke only, not acceptance evidence |
| `historical_hint` | Derived from local historical evidence hints | Allowed for baseline comparison if labeled |
| `model_structured` | Provider supplied structured probability | Eligible only if complete and calibrated |
| `model_plus_rules` | Provider output adjusted by deterministic local evaluator | Eligible only if transformation is recorded |
| `human_labeled_dataset` | Dataset contains curated forecast labels | Eligible for offline evaluation if labels are point-in-time |
| `missing` | No structured probability | Always observe or reject |

The evaluator must preserve the distinction between model forecasts, fixture
hints, historical hints, and market-derived probabilities.

### Structured Probability Requirements

Structured probability rules:

- Probability must be stored as a numeric field, not inferred from text.
- Probability must be within `[0, 1]`.
- Probability must be for the YES outcome; NO probability is `1 - p_yes`.
- Probability must identify whether it was copied, averaged, adjusted, or
  model-generated.
- Probability must include enough provenance to reproduce the value from local
  artifacts.
- Probability must not be action-eligible when the provider discusses a value in
  prose but leaves the structured field null.
- Probability must be evaluated with Brier score and calibration buckets even
  when no trade is taken.

### Evidence Completeness Requirements

Minimum evidence completeness fields:

| Field | Requirement |
| --- | --- |
| `evidence_count` | Count evidence items available at or before forecast time |
| `counter_evidence_count` | Count counter-evidence items available at or before forecast time |
| `evidence_sources` | Distinct non-secret source labels |
| `latest_evidence_published_at` | Must be at or before forecast timestamp |
| `stale_evidence_flag` | True when evidence is older than the declared horizon |
| `future_leakage_flag` | Must be false for acceptance runs |
| `missing_evidence_reason` | Required when evidence is absent |

An actionable Strategy v2 candidate must have at least one time-valid evidence
item unless it is explicitly being evaluated as a market-only baseline. The
recommended target for acceptance evaluation is at least two independent
time-valid evidence items per actionable forecast.

### Settlement And Outcome Requirements

Forecast evaluation requires outcome metadata:

- Binary prediction markets must resolve to `yes` or `no`.
- Settlement outcome must be local historical metadata, not fetched through a
  broker or private endpoint.
- Settlement timestamp or date should be recorded when available.
- Ambiguous, disputed, or unavailable settlement must block realized PnL and
  calibration scoring for that market, but still count as missing-outcome
  coverage.
- Partial settlement coverage must be reported by market and by row.
- Final profitability claims require settlement/outcome coverage for all
  included closed-market evaluation rows.

## B. Dataset Requirements

### Minimum Dataset Fields

Each historical evaluation row must include:

| Field | Required | Notes |
| --- | --- | --- |
| `date` or `timestamp` | yes | Point-in-time row timestamp |
| `market_id` | yes | Stable market identifier |
| `title` | recommended | Useful for reports |
| `platform` | recommended | Source label |
| `bid` | yes | YES best bid, probability scale |
| `ask` | yes | YES best ask, probability scale |
| `last_price` | yes | Last observed YES price |
| `implied_probability` | yes or derived | May default to midpoint when omitted |
| `liquidity` | recommended | Required for liquidity-aware acceptance claims |
| `volume` | recommended | Required for market-quality analysis |
| `evidence` | recommended | Time-valid evidence array |
| `settlement_outcome` | required for acceptance | `yes` or `no` |

Rows must reject invalid probability fields, bid greater than ask, malformed
evidence, future evidence leakage, and duplicate `date + market_id` records.

### Time-Indexed Price Requirements

The dataset must be time-indexed:

- One evaluated row per market per simulated date or timestamp.
- Rows must be ordered or sortable by timestamp and market id.
- Historical mode must use the matching row for each simulated date, not reuse a
  current snapshot.
- Price fields must represent values available at or before the forecast time.
- Bid/ask spread must be computable for every Strategy v2 paper-buy candidate.
- If order-book depth is available, it should be point-in-time and side-specific.
- If depth is unavailable, the evaluator must record `depth_missing=true` and
  limit claims accordingly.

### Evidence Timestamp Rules

Evidence rules:

- `published_at` must be at or before the dataset row timestamp.
- `retrieved_at` may be later only when it is an archival retrieval timestamp;
  reports must distinguish retrieval time from evidence availability time.
- Evidence with no timestamp may be used only in smoke runs or must be marked
  `timestamp_unknown`.
- Evidence leakage after the row timestamp is a hard failure for acceptance
  evaluation.
- Evidence must remain associated with the row or market/date it supports.
- Historical evidence must not be blindly reused across dates unless the row
  explicitly carries it forward and marks it still valid.

### Settlement And Outcome Rules

Settlement rules:

- Accepted evaluation datasets must include `settlement_outcome` for every
  market whose forecasts are included in final calibration and paper PnL.
- Supported outcomes for the first Strategy v2 evaluation are `yes` and `no`.
- Missing settlement rows are allowed in smoke runs, but final profitability
  claims must exclude or separately report them.
- Ambiguous or disputed resolution must be classified and excluded from
  acceptance scoring unless a documented resolution policy exists.
- Settlement-driven position closing must remain local paper accounting.

### Duplicate And Missing Day Handling

Duplicate handling:

- Duplicate `date + market_id` rows are invalid.
- Duplicate evidence IDs within a row must be deduplicated or flagged.
- Duplicate markets with different titles/platforms must be reported.

Missing day handling:

- Missing rows inside a requested date range must fail strict acceptance runs.
- Smoke runs may allow missing rows only when the report records skipped dates.
- Calendar gaps caused by market closure must be explicitly labeled, not
  silently ignored.
- Metrics must include skipped/missing-day counts.

### Minimum Sample Size Target

The five-row historical fixture is explicitly below the acceptance threshold.

Minimum targets before Strategy v2 can be considered better than Strategy v1:

| Target | Minimum |
| --- | ---: |
| Historical markets | 25 resolved binary markets |
| Evaluation rows | 250 point-in-time rows |
| Actionable candidate forecasts | 50 candidate forecasts before policy abstention |
| Executed paper trades | 30 closed paper trades, unless abstention is the explicit finding |
| Settlement coverage | 100% for scored markets |
| Evidence timestamp coverage | 95% or higher for scored rows |

If these targets are not met, the evaluation may report diagnostics but must not
claim Strategy v2 superiority.

### Train, Validation, Holdout, And Walk-Forward Approach

The evaluation should use a walk-forward or fixed split:

1. Training/calibration segment:
   - Used only to estimate calibration buckets, uncertainty bands, and any
     non-strategy thresholds that are not already fixed by safety policy.
2. Validation segment:
   - Used to compare candidate policies and reject brittle variants.
3. Holdout segment:
   - Used once for the final Strategy v2 versus Strategy v1 acceptance gate.

Minimum split:

- 60% training/calibration.
- 20% validation.
- 20% holdout.

For small datasets that cannot satisfy the minimum targets, use walk-forward
diagnostics only and label the result as non-acceptance.

## C. Baselines

The evaluation harness must compare Strategy v2 against all required baselines
using identical market rows, evidence rows, fees, slippage, risk settings, and
paper-only ledger assumptions.

### Always Observe

Always emits `observe`.

Purpose:

- Confirms no-trade behavior.
- Establishes zero-trade baseline for abstention and safety.
- Prevents overvaluing strategies that lose money while merely being active.

### Market-Implied Probability Only

Uses `market_implied_probability` as the forecast and never claims independent
edge.

Purpose:

- Measures market baseline calibration.
- Provides Brier score and log loss baseline.
- Separates forecasting quality from trading policy.

### Current Strategy v1

Runs the existing `PredictionMarketEdgeStrategy` unchanged.

Purpose:

- Required incumbent comparator.
- Measures whether Strategy v2 improves over current threshold logic.
- Preserves current safety behavior as a baseline.

### Hint-Threshold Policy

Uses historical evidence `probability_hint` metadata with a declared threshold,
separate from any LLM provider.

Purpose:

- Quantifies how much of the result comes from fixture/historical hints.
- Prevents crediting Strategy v2 for simply copying hint metadata.
- Useful for detecting circular research guidance.

### Random Or Naive Policy

Use only as a diagnostic baseline, not as a serious trading comparator.

Recommended variants:

- Random action among `observe`, `paper_buy_yes`, and `paper_buy_no`, with a
  fixed local seed.
- Naive midpoint threshold policy with predeclared non-tuned thresholds.

Purpose:

- Detects tiny-sample artifacts.
- Demonstrates whether reported performance exceeds trivial behavior.

## D. Metrics

### Activity Metrics

Required:

- `evaluated_rows`
- `markets_evaluated`
- `trade_count`
- `closed_trade_count`
- `abstention_count`
- `abstention_rate`
- `skip_count`
- `rejection_count`
- `failure_count`
- `missing_probability_count`
- `missing_evidence_count`
- `missing_settlement_count`

Abstention rate:

`abstention_rate = observe_count / evaluated_rows`

### Forecast Metrics

Required for all rows with known settlement outcome:

- Brier score.
- Log loss when probabilities are bounded away from 0 and 1.
- Calibration by bucket.
- Forecast coverage.
- Structured probability completeness rate.

Brier score:

`mean((estimated_probability_yes - outcome_yes)^2)`

Log loss:

`mean(-outcome_yes * log(p) - (1 - outcome_yes) * log(1 - p))`

For log loss, clamp only for metric stability with a documented epsilon such as
`1e-6`; do not use clamping to hide overconfident poor forecasts.

Calibration by bucket:

| Bucket | Required report fields |
| --- | --- |
| `0.00-0.10` through `0.90-1.00` | row count, mean forecast, observed YES rate, absolute gap |
| Provider/calibration bucket | row count, mean forecast, observed YES rate, absolute gap |
| Action bucket | row count, trade count, observed YES rate |

### Paper Outcome Metrics

Required:

- Realized paper PnL.
- Total return.
- Benchmark-relative return.
- Max drawdown.
- Win rate.
- Profit factor.
- Average trade PnL.
- Median trade PnL.
- Gross profit.
- Gross loss.
- Fee total.
- Slippage total or assumed slippage summary.
- Open-position count at evaluation end.

Metrics must state whether paper fills are simulated as immediate fills at
declared prices and must not imply real executable fills.

### Risk And Reliability Metrics

Required:

- Risk veto count by reason.
- Risk gate rejection count by reason.
- Strategy observe/skip reasons.
- Provider structured-output failure count.
- Replay success rate.
- Replay mutation count.
- Report checksum availability.
- Run success rate.
- Data quality failure count.

Failure and rejection reasons must be grouped by category, including:

- missing structured probability,
- low evidence completeness,
- ambiguous resolution,
- stale or missing market data,
- spread too wide,
- liquidity too thin,
- side-specific EV below threshold,
- risk veto,
- risk gate rejection,
- malformed dataset row,
- future evidence leakage.

## E. Acceptance Thresholds

Strategy v2 may be considered better than Strategy v1 only if all acceptance
criteria pass on the holdout segment.

### Sample Size Gate

Must pass:

- At least 25 resolved binary markets.
- At least 250 point-in-time rows.
- At least 50 candidate forecasts before policy abstention.
- At least 30 closed paper trades, unless the documented policy intentionally
  abstains and wins on forecast quality rather than trading activity.
- 100% settlement coverage for scored markets.

### Forecast Quality Gate

Must pass:

- Brier score better than Strategy v1 and market-implied baseline by at least
  `0.01`, or statistically/operationally justified when sample size is larger.
- Calibration bucket absolute gap improves versus Strategy v1 in the majority
  of populated buckets.
- No populated bucket with 20 or more rows has an absolute calibration gap above
  `0.20` unless explicitly flagged as non-actionable.
- Structured probability completeness is at least `95%` for evaluated rows.
- Missing structured probability always results in observe/reject, never a
  paper-buy signal.

### Paper Performance Gate

Must pass:

- Max drawdown is no worse than Strategy v1.
- Profit factor is better than or equal to Strategy v1 and at least `1.0` on the
  holdout segment.
- Benchmark-relative return is non-negative versus Strategy v1 after fees and
  declared slippage.
- Realized paper PnL is not achieved through a materially larger drawdown or
  uncontrolled trade count.
- Win rate is reported but must not be the sole acceptance reason.

### Abstention Gate

Must pass:

- Abstention rate is controlled and explained.
- Target range for first acceptance run: `20%` to `90%`.
- Above `90%` requires a forecast-quality win and an explicit finding that
  Strategy v2 is primarily a filtering/abstention improvement.
- Below `20%` requires evidence that market quality, spreads, liquidity, and
  calibration support broad action.

### Safety And Replay Gate

Must pass:

- No live trading path.
- No broker API.
- No real-money execution.
- No direct LLM-to-order path.
- No weakened risk gates.
- No weakened manual approval defaults.
- No threshold tuning from the five-row fixture.
- Replay validation success rate is `100%` for sampled accepted runs.
- Replay mutation count is `0`.
- Reports and manifests remain checksum-verifiable.
- Network tests remain optional and marked `network`.

If any safety or replay gate fails, Strategy v2 fails acceptance regardless of
forecast or paper PnL metrics.

## F. Safety Constraints

Strategy v2 evaluation must preserve:

- Paper-only execution.
- `REAL_MONEY_ENABLED=false` default.
- `ALLOW_LIVE_ORDERS=false` default.
- `HUMAN_APPROVAL_REQUIRED=true` default.
- No broker APIs.
- No private trading endpoints.
- No live trading.
- No real-money execution.
- No direct LLM-to-order path.
- No scheduler.
- No daemon.
- No autostart.
- No leverage.
- No derivatives.
- No shorting.
- No withdrawals, wallets, private keys, cookies, browser data, or credentials.
- No weakened risk engine or risk gate checks.
- No threshold tuning from `data/fixtures/phase7_historical_5d.jsonl`.
- No profitability claims from fixture mode or current snapshot replay mode.

LLMs, including qwen or other OpenAI-compatible local providers, remain
research-only. Their output may create structured research fields, but
deterministic local strategy, risk, risk gate, and paper ledger systems must
remain the only path to paper-order mutation.

## G. Implementation Plan

These are future PRs only. Do not implement any of them in Phase 7F.

### PR-V2-1 Forecast Assessment Schema And Evaluator

Scope:

- Add local schema/model for forecast assessment.
- Add evaluator for structured probability completeness, provenance,
  evidence completeness, uncertainty metadata, and rejection reasons.
- Add tests for missing probability, prose-only probability, hint provenance,
  future evidence leakage, and calibration bucket assignment.

Non-scope:

- No Strategy v2 policy.
- No broker/live/scheduler work.
- No threshold tuning.

### PR-V2-2 Offline Evaluation Harness

Scope:

- Add offline-only comparison harness for datasets that meet this spec.
- Compute forecast, paper outcome, risk, replay, and failure metrics.
- Compare always-observe, market-implied, Strategy v1, hint-threshold, and
  random/naive baselines.
- Emit deterministic reports and JSON artifacts.

Non-scope:

- No Strategy v2 trading policy implementation.
- No live data downloader.
- No broker/live/scheduler work.

### PR-V2-3 Strategy v2 Candidate Policy

Scope:

- Add candidate policy only after PR-V2-1 and PR-V2-2 are reviewed.
- Use forecast assessment and executable-side EV as inputs.
- Emit paper-only signals with explicit abstention/rejection reasons.
- Preserve all existing risk and paper ledger boundaries.

Non-scope:

- No broker/live/scheduler work.
- No risk-gate weakening.
- No direct LLM-to-order path.

### PR-V2-4 Comparison Report And Acceptance Gate

Scope:

- Run Strategy v2 candidate against the evaluation harness.
- Produce comparison report against Strategy v1 and required baselines.
- Apply acceptance thresholds from this specification.
- Document pass/fail and residual risks.

Non-scope:

- No Phase 8.
- No broker/live/scheduler work.
- No production deployment claim.

## Required Report Outputs

The future evaluation harness should emit:

- Markdown comparison report.
- Machine-readable JSON comparison artifact.
- Dataset audit summary.
- Forecast metrics by strategy and baseline.
- Paper outcome metrics by strategy and baseline.
- Calibration bucket table.
- Failure/rejection reason table.
- Replay validation summary.
- Safety invariant summary.

Each report must clearly label whether the dataset is:

- fixture smoke,
- current snapshot replay,
- historical local dataset without settlement,
- historical local dataset with settlement but below sample-size target,
- historical local dataset eligible for acceptance evaluation.

## Phase 7F Decision

Strategy v2 implementation should not begin until this specification is reviewed
and accepted. The recommended next PR is PR-V2-1, limited to forecast assessment
schema and evaluator work.
