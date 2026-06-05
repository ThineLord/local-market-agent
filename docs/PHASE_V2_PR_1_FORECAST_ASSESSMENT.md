# PR-V2-1 Forecast Assessment Schema And Evaluator

## Scope

PR-V2-1 adds the local forecast assessment layer required before Strategy v2
policy work. It is paper-only and evaluation-only.

This PR does not implement Strategy v2 policy, change trading decisions, change
the current `PredictionMarketEdgeStrategy`, redesign risk, redesign risk gates,
change the paper ledger, start Phase 8, add broker integrations, add live
trading, add real-money execution, add a scheduler, add a daemon, add autostart,
or tune thresholds.

## Architecture

New schema:

- `ForecastAssessment`
- `ProbabilitySource`

New evaluator:

- `ForecastAssessmentEvaluator`
- `assign_calibration_bucket`

The evaluator consumes:

- `ResearchBrief`
- `MarketSnapshot`
- optional local `evidence_metadata`

It returns a `ForecastAssessment`. It does not create signals, risk decisions,
risk gate decisions, paper intents, paper orders, fills, positions, or broker
requests.

## ForecastAssessment Fields

Core fields:

- `forecast_id`
- `market_id`
- `snapshot_id`
- `as_of`
- `estimated_probability_yes`
- `probability_source`
- `probability_provenance`
- `input_completeness_score`
- `evidence_completeness_score`
- `structured_output_complete`
- `forecast_confidence`
- `forecast_rationale`
- `rejection_reasons`

Additional evaluator fields:

- `calibration_bucket`
- `action_eligible`
- `evidence_count`
- `counter_evidence_count`
- `future_evidence_leakage`
- `stale_evidence`
- `missing_evidence`
- `metadata`

## Probability Sources

Supported provenance labels:

- `market_implied_only`
- `fixture_hint`
- `historical_hint`
- `model_structured`
- `model_plus_rules`
- `human_labeled_dataset`
- `missing`

The evaluator preserves the difference between fixture or historical
`probability_hint` values, market-derived probabilities, model structured
probabilities, and missing structured output. This prevents Strategy v2
evaluation from treating fixture hints or prose-only probabilities as proven
alpha.

Raw provider confidence and evidence-quality values are recorded in
`probability_provenance` as diagnostics. `forecast_confidence` is populated only
when an explicit calibrated confidence value is supplied in local evaluator
metadata.

## Evaluator Behavior

The evaluator detects and records:

- Missing structured probability.
- Prose-only probability claims when the structured field is missing.
- Probability values outside `[0, 1]`.
- Probability provenance.
- Missing market probability.
- Missing bid/ask fields.
- Market or snapshot mismatch.
- Evidence completeness.
- Missing evidence.
- Stale evidence.
- Future evidence leakage.
- Provider structured-output incompleteness.
- Calibration bucket assignment.

Missing structured probability is never recovered from prose. A rationale that
mentions a probability while `estimated_probability` is null produces a rejected
assessment with `prose_only_probability_not_accepted`.

Future evidence leakage blocks action eligibility. Missing or stale evidence is
recorded in rejection reasons and lowers evidence completeness.

## Calibration Buckets

`assign_calibration_bucket` returns simple probability buckets:

- `0.00-0.10`
- `0.10-0.20`
- `0.20-0.30`
- `0.30-0.40`
- `0.40-0.50`
- `0.50-0.60`
- `0.60-0.70`
- `0.70-0.80`
- `0.80-0.90`
- `0.90-1.00`

Out-of-range or missing probabilities receive no bucket.

## Tests

Added tests cover:

- Missing structured probability blocks action eligibility.
- Prose-only probability does not recover a missing structured field.
- Out-of-range probability is rejected.
- Hint-derived probability is labeled correctly.
- Market-implied-only probability is labeled correctly.
- Future evidence leakage is rejected.
- Missing evidence lowers completeness.
- Calibration bucket assignment.
- No live trading path added.
- No broker/order APIs added.

## Safety Notes

PR-V2-1 is local-only and paper-only. It does not add or call:

- Broker APIs.
- Private trading endpoints.
- Live orders.
- Real-money execution.
- Scheduler, daemon, or autostart.
- Risk engine changes.
- Risk gate changes.
- Paper ledger mutation.
- Direct LLM-to-order paths.

LLM outputs remain research-only inputs. This evaluator can classify structured
research output, but it cannot create orders or approve risk.

## Validation

Required validation:

- `PYTHONPATH=src .venv/bin/ruff check .`
- `PYTHONPATH=src .venv/bin/pytest`

## Next Step

After PR-V2-1 review, the next planned PR is PR-V2-2: an offline evaluation
harness that compares Strategy v1 and required baselines using the forecast
assessment layer. Strategy v2 policy implementation remains out of scope until
PR-V2-1 and PR-V2-2 are reviewed.
