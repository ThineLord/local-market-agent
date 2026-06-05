# PR-V2-3 Strategy v2 Candidate Policy

## Scope

PR-V2-3 adds the smallest Strategy v2 candidate policy for offline evaluation.
It remains paper-only, local-only, and offline-evaluation-first.

This PR does not start Phase 8, add broker integrations, add live trading, add
real-money execution, add a scheduler, add a daemon, add autostart, replace
Strategy v1 in production Phase 7 runs, redesign risk, redesign risk gates,
mutate the paper ledger, tune thresholds from the five-row fixture, or make a
superiority claim from the current fixture.

## Architecture

New module:

- `local_market_agent.strategy.prediction_market_v2`

New policy:

- `PredictionMarketV2CandidateStrategy`
- `StrategyV2Config`

The candidate consumes:

- `ForecastAssessment`
- `MarketSnapshot`
- existing `RiskConfig`

It outputs a normal `Signal` with `strategy_name="prediction_market_v2_candidate"`.
It does not save the signal, approve risk, create risk gate decisions, mutate
the paper ledger, or create paper positions.

## Policy Summary

The policy preserves abstention as the default safe outcome.

It observes on:

- Missing structured probability.
- Prose-only probability.
- `structured_output_complete=false`.
- `probability_source=missing`.
- `probability_source=market_implied_only`.
- Insufficient evidence completeness.
- Hint-derived probability outside an explicit local evaluation context.
- Missing bid/ask fields.
- Executable-side EV below the threshold.
- Edge that is erased by uncertainty band.
- Recommendation/side mismatch when recommendation provenance is present.

It skips on:

- Future evidence leakage.
- Spread above the existing `RiskConfig.max_spread`.
- Liquidity below the existing `RiskConfig.min_liquidity_depth`.

Hint-derived probabilities can trade only in local smoke/evaluation context and
are marked with `hint_source_evaluation_only=true` in signal metadata. This is
diagnostic and does not make fixture hints acceptance evidence.

## Executable-Side EV

Strategy v2 uses executable-side EV as the primary action hurdle.

YES side:

- Entry price is YES best ask.
- Raw YES EV is `p_yes - best_ask`.
- Adjusted YES EV subtracts fee buffer, slippage buffer, and YES-side
  uncertainty buffer.

NO side:

- Entry price is `1 - YES best_bid`.
- Raw NO EV is `(1 - p_yes) - (1 - best_bid)`.
- Adjusted NO EV subtracts fee buffer, slippage buffer, and NO-side uncertainty
  buffer.

The threshold remains the existing non-tuned hurdle:

`max(RiskConfig.min_edge, 2 * spread)`

No threshold was tuned from the five-row fixture.

## Offline Harness Integration

The offline harness now includes:

- `strategy_v2_candidate`

It still includes:

- `always_observe`
- `market_implied_probability_only`
- `strategy_v1`
- `hint_threshold_policy`
- `random_naive_policy`

Strategy v2 is not wired into `Phase7DailyRunner`, normal daily operations, risk
approval, risk gates, or the paper ledger. It is only a comparator inside
`lma strategy-eval-offline`.

## Tests

Added tests cover:

- Missing structured probability observes.
- Prose-only probability observes.
- Market-implied-only does not trade as alpha.
- Fixture hint can trade only in local evaluation context.
- Executable YES EV is required.
- Executable NO EV is required.
- Uncertainty band can force abstention.
- Future evidence leakage blocks action.
- Strategy v2 appears in offline evaluation reports.
- Strategy v2 is not used by Phase 7 daily runner.
- No broker/live/order APIs added by the v2 candidate.

## Safety Notes

PR-V2-3 does not add or call:

- Broker APIs.
- Private trading endpoints.
- Live orders.
- Real-money execution.
- Scheduler, daemon, or autostart.
- Risk approval mutation.
- Risk gate mutation.
- Paper ledger mutation.
- Direct LLM-to-order paths.

Strategy v1 remains the production/default Phase 7 strategy.

## Validation

Required validation:

- `PYTHONPATH=src .venv/bin/ruff check .`
- `PYTHONPATH=src .venv/bin/pytest`
- `PYTHONPATH=src .venv/bin/lma strategy-eval-offline --historical-file data/fixtures/phase7_historical_5d.jsonl --output-dir data/reports/strategy_eval`

The five-row fixture remains classified as `fixture_smoke` and
`superiority_claim_allowed=false`.

## Next Step

After PR-V2-3 review, PR-V2-4 can run and document the comparison report and
acceptance gate. Do not start Phase 8, broker integration, live trading,
scheduler, daemon, or production replacement work.
