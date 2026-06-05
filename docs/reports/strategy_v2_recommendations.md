# Strategy v2 Recommendations

Date: 2026-06-05

Scope: recommendations only. No Strategy v2 implementation was added. No Phase
8, broker integration, live trading, scheduler, daemon, autostart, or real-money
path was added.

## Goal

Strategy v2 should turn the current paper-only threshold policy into a
testable decision system. The minimum useful v2 is not a more aggressive
strategy; it is a better measurement and estimation layer that can prove whether
any edge exists before paper profitability testing is meaningful.

## Minimum Strategy v2 Should Do

### 1. Separate Estimation From Policy

Current behavior mixes research guidance, probability hints, recommendation, and
threshold policy. Strategy v2 should produce an explicit forecast object before
action selection.

Minimum forecast fields:

| Field | Purpose |
| --- | --- |
| `estimated_probability` | Forecasted YES probability |
| `probability_source` | Model, hint, human-entered fixture, provider output, or derived baseline |
| `uncertainty_band` | Estimate error range or confidence interval |
| `calibration_bucket` | Historical reliability bucket, if available |
| `input_completeness_score` | Whether required market/evidence fields are present |
| `forecast_rationale` | Short structured reason, separate from prose research |

No action should be selected from prose-only probability claims.

### 2. Validate Structured Research Before Strategy

Strategy v2 should reject or observe when provider output is incomplete,
internally inconsistent, or circular.

Minimum checks:

- `estimated_probability` must be present for paper-buy consideration.
- Recommended action must match the sign of executable-side EV.
- Prose may not override missing structured fields.
- Provider confidence must not be treated as calibrated confidence unless it has
  historical validation.
- Probability estimates copied from hints should be marked as hint-derived, not
  model-derived.

### 3. Use Executable-Side Expected Value

The current side-specific EV check is worth preserving. Strategy v2 should make
it the primary EV calculation rather than a secondary guard.

Minimum formula:

- YES EV uses the executable YES entry price, estimated YES probability, fees,
  slippage, and settlement assumptions.
- NO EV uses the executable NO entry price, estimated NO probability, fees,
  slippage, and settlement assumptions.
- EV must clear a margin that accounts for forecast uncertainty, not just spread.

The policy should record why a side failed: edge, uncertainty, spread, fee,
slippage, missing depth, stale data, or resolution risk.

### 4. Add Market Microstructure Gates

Do not add broker integrations. Do add richer read-only market checks when data
exists.

Minimum gates:

- Snapshot freshness.
- Bid/ask coherency.
- Spread as both absolute and relative hurdle.
- Liquidity tied to intended notional.
- Depth by side if the read-only data source supports it.
- Close/settlement timing.
- Market status and resolution ambiguity.

If these fields are unavailable, Strategy v2 should record the missingness and
observe.

### 5. Calibrate Confidence

Strategy v2 should avoid using raw LLM confidence as decision confidence.

Minimum replacement:

- Keep provider confidence as a diagnostic field.
- Add calibrated forecast confidence only after historical evaluation.
- Penalize estimates with sparse evidence, conflicting evidence, stale evidence,
  missing settlement source, or provider schema defects.
- Require confidence to map to empirical outcomes before it affects action.

### 6. Add A Real Offline Evaluation Harness

Do not start Phase 8. Do not add live trading. Strategy v2 should first be
evaluated offline.

Minimum evaluation requirements:

- A larger local historical dataset with time-indexed prices and settlement.
- Point-in-time evidence aligned to each simulated date.
- Walk-forward or holdout split.
- Baselines:
  - always observe,
  - market-implied probability only,
  - simple hint-threshold policy,
  - current Strategy v1.
- Metrics:
  - trade count,
  - abstention rate,
  - Brier score or log loss for probabilities,
  - realized paper PnL under declared fill assumptions,
  - max drawdown,
  - win rate,
  - profit factor,
  - benchmark-relative return.

Profitability claims should remain blocked until this harness exists and passes
with enough sample size to be meaningful.

### 7. Preserve Abstention As A First-Class Action

The current strategy safely observes many cases. Strategy v2 should keep that
behavior and make abstention measurable.

Minimum abstention reasons:

- Missing probability.
- Missing spread.
- Missing depth.
- Low evidence completeness.
- Uncalibrated probability.
- Edge within uncertainty band.
- Resolution source ambiguous.
- Provider structured output incomplete.
- Fill assumptions unsupported.

### 8. Keep Strategy Independent Of Order Execution

Strategy v2 should still emit paper-only signals. It should not create orders,
call brokers, approve risk, bypass manual approval, or run on a schedule.

The existing sequence should remain:

1. Research and forecast.
2. Strategy signal.
3. Risk decision.
4. Risk gate decision.
5. Paper ledger mutation only when approved.

## Recommended Strategy v2 Shape

The minimum design is three small layers:

| Layer | Responsibility | Output |
| --- | --- | --- |
| Forecast validator | Checks provider fields, hint provenance, probability completeness, and uncertainty | `ForecastAssessment` |
| Edge evaluator | Computes executable-side YES/NO EV after fees, slippage, spread, and uncertainty | `EdgeAssessment` |
| Policy selector | Converts assessments into `observe`, `skip`, `paper_buy_yes`, or `paper_buy_no` | `Signal` |

This keeps the current safety architecture intact while making the decision
logic auditable.

## Acceptance Criteria Before Implementation

Strategy v2 should not be implemented until the repository has:

- A written evaluation plan and minimum sample-size target.
- A local historical dataset beyond the current five-row fixture.
- A clear distinction between fixture hints, model forecasts, and market-derived
  probabilities.
- Tests for missing structured probability, contradictory recommendation, thin
  liquidity, stale data, side-specific EV, and uncertainty-driven abstention.
- A no-regression safety check proving no live trading, broker APIs, scheduler,
  daemon, autostart, leverage, derivatives, shorting, withdrawal, or direct
  LLM-to-order path was added.

## What Should Not Be Changed Yet

- Do not tune current thresholds from the five-day sandbox.
- Do not make qwen the default decision provider.
- Do not allow prose-only probabilities to drive orders.
- Do not add live trading, broker integration, scheduler, daemon, autostart, or
  Phase 8 code.
- Do not weaken `REAL_MONEY_ENABLED=false`, `ALLOW_LIVE_ORDERS=false`, or
  `HUMAN_APPROVAL_REQUIRED=true` defaults.
- Do not change paper ledger fill assumptions as part of strategy design unless
  the evaluation plan separately measures fill sensitivity.
- Do not remove current risk gates or manual approval requirements.

## Recommended Next Step

Before coding Strategy v2, write a paper-only Strategy v2 evaluation spec that
defines forecast inputs, required historical fields, baselines, metrics,
minimum sample size, and acceptance thresholds. Then implement the smallest
offline evaluator that can compare current Strategy v1 against candidate v2
logic without creating new order-execution capabilities.
