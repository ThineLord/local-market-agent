# PR-V2-2 Offline Evaluation Harness

## Scope

PR-V2-2 adds an offline-only strategy evaluation harness for local historical
JSONL datasets. It compares required baselines and produces machine-readable
JSON plus Markdown reports.

This PR does not implement Strategy v2 policy, start Phase 8, add broker
integrations, add live trading, add real-money execution, add a scheduler, add a
daemon, add autostart, tune thresholds, download historical data, or make
profitability superiority claims from the five-row fixture.

## Architecture

New module:

- `local_market_agent.eval.offline_strategy`

New CLI command:

```bash
lma strategy-eval-offline \
  --historical-file data/fixtures/phase7_historical_5d.jsonl \
  --output-dir data/reports/strategy_eval
```

The harness consumes:

- A local historical JSONL file loaded by the existing historical dataset
  importer.
- `ForecastAssessmentEvaluator` from PR-V2-1.
- The existing unchanged `PredictionMarketEdgeStrategy` for the Strategy v1
  baseline.

The harness writes:

- A JSON report.
- A Markdown report.

It simulates one-unit paper outcomes in memory only. It does not create signals
in repository storage, approve risk, create risk gate decisions, mutate the
paper ledger, create orders, or call any broker.

## Baselines

Implemented baselines:

- `always_observe`
- `market_implied_probability_only`
- `strategy_v1`
- `hint_threshold_policy`
- `random_naive_policy`

`strategy_v1` runs the current `PredictionMarketEdgeStrategy` unchanged. The
hint-threshold baseline exists only to measure how much apparent signal comes
from local `probability_hint` metadata. The random/naive baseline uses a fixed
seed and is diagnostic only.

## Metrics

Activity metrics:

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

Forecast metrics:

- Brier score.
- Log loss with `1e-6` metric-stability epsilon.
- Calibration by `0.10` buckets.
- Forecast coverage.
- Structured probability completeness rate.

Paper outcome metrics:

- Realized paper PnL.
- Total return.
- Benchmark-relative return versus the market-implied baseline.
- Max drawdown.
- Win rate.
- Profit factor.
- Average and median trade PnL.
- Gross profit.
- Gross loss.
- Fee total.
- Slippage summary.
- Open-position count.

Risk and reliability metrics:

- Rejection reasons by category.
- Observe/skip reasons.
- Provider structured-output failure count.
- Risk and risk-gate reason placeholders.
- Replay placeholders, because PR-V2-2 does not create replayable run records.
- Data quality failure count.

## Dataset Labels

The report classifies datasets as:

- `fixture_smoke`
- `historical_local_dataset_without_settlement`
- `historical_local_dataset_with_settlement_below_sample_size_target`
- `historical_local_dataset_eligible_for_acceptance_evaluation`

The five-row historical fixture is classified as `fixture_smoke` with detail:

`fixture smoke / historical local dataset with settlement but below sample-size target`

This blocks superiority claims even if in-memory paper outcome metrics are
positive.

## Acceptance Gating

The harness enforces the PR-V2 evaluation sample-size targets:

- At least 25 resolved binary markets.
- At least 250 evaluation rows.
- At least 50 candidate forecasts.
- At least 30 closed paper trades.
- 100% settlement coverage for scored markets.
- At least 95% evidence timestamp coverage.

If any gate fails, `superiority_claim_allowed=false`.

## Safety Notes

PR-V2-2 is paper-only, local-only, and evaluation-only.

It does not add or call:

- Broker APIs.
- Private trading endpoints.
- Live orders.
- Real-money execution.
- Scheduler, daemon, or autostart.
- Risk engine approval.
- Risk gate mutation.
- Paper ledger mutation.
- Direct LLM-to-order paths.
- Strategy v2 policy.

## Validation

Required validation:

- `PYTHONPATH=src .venv/bin/ruff check .`
- `PYTHONPATH=src .venv/bin/pytest`
- `PYTHONPATH=src .venv/bin/lma strategy-eval-offline --historical-file data/fixtures/phase7_historical_5d.jsonl --output-dir data/reports/strategy_eval`

## Next Step

After PR-V2-2 review, the next planned PR is PR-V2-3: a Strategy v2 candidate
policy. PR-V2-3 should not start until the forecast assessment layer and offline
evaluation harness are reviewed.
