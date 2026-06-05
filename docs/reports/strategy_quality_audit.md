# Phase 7E Strategy Quality Audit

Date: 2026-06-05

Scope: audit-only review of `PredictionMarketEdgeStrategy`. No strategy
implementation, Phase 8 work, broker integration, live trading, scheduler,
daemon, autostart, or real-money path was added.

## Executive Answer

The current `PredictionMarketEdgeStrategy` is not suitable for real
profitability testing. It is suitable for paper-only workflow smoke tests,
offline replay validation, and safety-gate validation.

The strategy has evidence-backed safety behavior: it refuses missing inputs,
thin liquidity, low confidence, low evidence quality, wide spreads, ambiguous
resolution, and non-paper-buy actions. It does not yet have evidence-backed
decision value. Its trading edge depends on fixture-style or LLM-provided
probability estimates that have not been calibrated, backtested on a meaningful
sample, benchmarked, or tied to demonstrable market inefficiency.

Weakest link: the agent probability estimate. The strategy treats
`brief.estimated_probability` as decision-grade, but current evidence shows it
is usually copied from `probability_hint` metadata or omitted by the real
provider. That makes the edge calculation deterministic arithmetic over an
untested estimate, not evidence of alpha.

## Artifacts Used

- Strategy code: `src/local_market_agent/strategy/prediction_market.py`.
- Research generation and probability hints:
  `src/local_market_agent/agents/research.py`.
- Risk approval path: `src/local_market_agent/risk/engine.py`.
- Risk gates and paper ledger: `src/local_market_agent/risk/gates.py`,
  `src/local_market_agent/paper/ledger.py`.
- Phase 7D reports:
  `docs/reports/research_quality_validation.md`,
  `docs/reports/research_quality_comparison.md`.
- Historical sandbox fixture:
  `data/fixtures/phase7_historical_5d.jsonl`.
- Existing tests:
  `tests/test_strategy_risk.py`, `tests/test_phase7_sandbox.py`,
  `tests/test_research_quality_eval.py`.

## Current Strategy Trace

### Inputs

The strategy consumes only a `ResearchBrief` and a `MarketSnapshot`.

Key strategy inputs:

| Field | Source | Use |
| --- | --- | --- |
| `brief.estimated_probability` | Research provider output | Agent probability for YES outcome |
| `snapshot.market_implied_probability` | Market snapshot | Market probability baseline |
| `snapshot.best_bid`, `snapshot.best_ask` | Market snapshot | Spread and side-specific EV checks |
| `snapshot.liquidity` | Market snapshot | Liquidity skip gate |
| `brief.confidence` | Research provider/calibrator | Confidence skip gate and risk input |
| `brief.evidence_quality` | Research provider | Evidence quality skip gate and risk input |
| `brief.recommended_action` | Research provider after skeptic/calibrator | Must align with selected side |
| `brief.resolution_ambiguity` | Research brief | Resolution skip gate |

The research path currently gives providers an `estimated_probability` hint
derived from evidence metadata and the same edge threshold used downstream. If
evidence items include `probability_hint`, `_weighted_probability_hint` averages
those hints using `relevance_score * credibility_score`. Without hints, it falls
back to the market probability.

### Thresholds

Defaults come from `RiskConfig`:

| Threshold | Default | Strategy behavior |
| --- | ---: | --- |
| Minimum confidence | `0.60` | Below this, `skip` |
| Minimum edge | `0.08` | Directional edge must clear this |
| Maximum spread | `0.08` | Wider spread causes `skip` |
| Minimum liquidity depth | `100.0` | Lower liquidity causes `skip` |
| Evidence quality floor | `0.65` | Below this, `skip` |
| Actionable threshold | `max(min_edge, 2 * spread)` | Used for edge and side EV |

These thresholds are coherent as guardrails, but they are not empirically
justified by current artifacts.

### Probability Handling

The strategy sets:

- `agent_probability = brief.estimated_probability`
- `market_probability = snapshot.market_implied_probability`

If either value is missing, the strategy returns `observe`, not `skip`, with:
`Missing market or agent probability prevents paper_buy_yes/no.`

This is safe. It also means decision quality depends almost entirely on the
upstream structured probability field.

### Edge Calculation

The strategy computes:

- `yes_edge = agent_probability - market_probability`
- `no_edge = market_probability - agent_probability`
- `directional_edge = max(yes_edge, no_edge)`
- `threshold = max(config.min_edge, 2 * spread)`

If `directional_edge < threshold`, the strategy returns `observe`.

The side-specific checks then compare executable-side EV:

- YES EV: `agent_probability - best_ask`
- NO EV: `(1 - agent_probability) - (1 - best_bid)`

This side-specific EV check is a useful arithmetic safety layer. It prevented a
final-day historical NO candidate from becoming a paper order even though its
market-midpoint directional edge cleared `0.08`.

### Action Selection

The strategy selects the stronger side by comparing `yes_edge` and `no_edge`.

YES path:

- Requires `brief.recommended_action` to be `paper_buy_yes` or legacy
  `paper_buy`.
- Requires YES EV to clear `threshold`.
- Emits `paper_buy_yes` only after both checks pass.

NO path:

- Requires `brief.recommended_action` to be `paper_buy_no`.
- Requires NO EV to clear `threshold`.
- Emits `paper_buy_no` only after both checks pass.

All other cases return `observe` or `skip`.

### Confidence Handling

Confidence is a gate, not a sizing or calibration input:

- Below `0.60`: strategy returns `skip`.
- At or above `0.60`: confidence is copied into the signal.
- Risk evaluation separately vetoes signals below the same threshold.

There is no calibration curve, provider reliability model, historical hit-rate
mapping, or uncertainty interval attached to confidence.

### Failure, Observe, And Skip Cases

`skip` cases:

- Liquidity below `100.0`.
- Resolution ambiguity.
- Evidence quality below `0.65`.
- Confidence below `0.60`.
- Spread above `0.08`.

`observe` cases:

- Missing market or agent probability.
- Missing bid/ask spread.
- Directional edge below actionable threshold.
- Research recommendation does not match selected side.
- Side-specific EV below the spread/fee/slippage buffer.

Risk then vetoes anything other than `paper_buy_yes` or `paper_buy_no`, any
missing or low edge, missing or wide spread, low confidence, low evidence
quality, live-mode attempts, leverage, derivatives, and sell/short attempts.

## Diagnostics

### Current Fixture Daily Run

Command:

`PYTHONPATH=src .venv/bin/lma phase7-run-daily --db "$tmpdir/daily.sqlite" --report-dir "$tmpdir/reports" --no-require-manual-approval --llm-provider mock`

Result:

- Status: `completed`.
- Provider: `mock`, research-only, no network calls, cannot create orders.
- Market source: fixture.
- Paper order created: yes.
- Direct strategy trace:
  - Market probability: `0.49`.
  - Agent probability: `0.6083`.
  - Bid/ask: `0.47` / `0.51`.
  - Spread: `0.04`.
  - Confidence: `0.7438`.
  - Evidence quality: `0.6564`.
  - Brief action: `paper_buy_yes`.
  - Signal action: `paper_buy_yes`.
  - Edge: `0.1183`.
  - Risk status: `approved`.

Assessment: fixture daily path proves the pipeline can generate and approve a
paper signal. It does not prove the signal is profitable.

### Historical 5-Day Sandbox

Command:

`PYTHONPATH=src .venv/bin/lma phase7-sandbox-run --market-source historical-file --historical-file data/fixtures/phase7_historical_5d.jsonl --days 5 --db "$tmpdir/historical.sqlite" --report-dir "$tmpdir/reports" --summary-dir "$tmpdir/summaries" --no-require-manual-approval --replay-sample-size 1 --llm-provider mock`

Result:

- Data mode: `historical_local_dataset`.
- Simulated days: `5`.
- Status counts: `4 completed`, `1 rejected`, `0 failed`.
- Replay sample: `ok=true`, `mutation_detected=false`.
- Paper orders: `4`.
- Settlement coverage: `partial`.
- Win rate: `1.0`.
- Total return: `0.03503622`.

Assessment: this is a useful sandbox integrity result, but it is too small and
too fixture-shaped to support profitability conclusions. The positive PnL comes
from four YES entries and a final YES settlement on a single local demo market.

Direct strategy trace:

| Date | Market p | Agent p | Spread | Threshold | Brief action | Signal | Edge | Risk | Rationale |
| --- | ---: | ---: | ---: | ---: | --- | --- | ---: | --- | --- |
| 2026-05-01 | 0.49 | 0.6849 | 0.02 | 0.08 | paper_buy_yes | paper_buy_yes | 0.1949 | approved | Positive YES edge clears thresholds |
| 2026-05-02 | 0.51 | 0.6852 | 0.02 | 0.08 | paper_buy_yes | paper_buy_yes | 0.1752 | approved | Positive YES edge clears thresholds |
| 2026-05-03 | 0.53 | 0.6951 | 0.02 | 0.08 | paper_buy_yes | paper_buy_yes | 0.1651 | approved | Positive YES edge clears thresholds |
| 2026-05-04 | 0.56 | 0.7151 | 0.02 | 0.08 | paper_buy_yes | paper_buy_yes | 0.1551 | approved | Positive YES edge clears thresholds |
| 2026-05-05 | 0.95 | 0.8626 | 0.02 | 0.08 | paper_buy_no | observe | 0.0874 | vetoed | NO EV below buffer |

The final day is a good safety example: midpoint NO edge cleared `0.08`, but
the executable NO side did not clear the side-specific EV threshold.

### Mock Provider Path

Command:

`PYTHONPATH=src .venv/bin/lma llm-provider-audit --llm-provider mock`

Result:

- `provider=mock`.
- `network_calls_enabled=false`.
- `research_only=true`.
- `can_create_orders=false`.
- `api_key_configured=false`.

Assessment: mock is deterministic and reliable for offline workflow testing,
but its probability estimates are generated from fixture metadata hints. It is
not an independent alpha model.

### Qwen Provider Path

Local Ollama model discovery returned `qwen3:14b`, so the qwen path is present.
An optional current qwen daily smoke was started and then stopped after roughly
2.5 minutes with no output because this audit does not need a fresh slow model
run. Existing Phase 7D artifacts were used instead.

Phase 7D evidence:

- Daily fixture comparison: qwen and mock produced the same action,
  probability, signal, risk, risk gate, and paper-order outcome. qwen raised
  confidence and evidence-quality scores only.
- Historical 5-day comparison: qwen changed three days materially, but the
  change was worse for decision reliability: it wrote probability discussion in
  prose while leaving structured `estimated_probability` as `null`, which
  caused observe/veto/reject outcomes.

Assessment: qwen does not currently add proven decision value. It should remain
optional research experimentation until structured-field completeness and
provider-quality scoring are added.

## Assumption Classification

| Assumption | Classification | Assessment |
| --- | --- | --- |
| Market implied probability is a fair baseline for edge comparison | Untested | The code accepts the market probability field, but no artifact validates whether the selected market is efficient, biased, stale, or midpoint-derived. |
| A positive difference between agent probability and market probability is tradable edge | Placeholder | This is the MVP core rule. It is mechanically tested, but no profitability evidence supports the estimate as alpha. |
| `brief.estimated_probability` is decision-grade | Unsafe | Current evidence shows it can be fixture-hint-derived or missing from qwen structured output. Orders depend on this field. |
| Evidence `probability_hint` metadata reflects real information | Placeholder | Historical and demo fixtures contain hints created for sandbox behavior. They are not independently validated forecasts. |
| Confidence above `0.60` means the estimate is reliable | Untested | Confidence is not calibrated to outcomes or provider accuracy. |
| Evidence quality above `0.65` means evidence is sufficient | Untested | Evidence-quality values are provider outputs or fixture-derived values, not audited empirical quality scores. |
| Minimum edge of `0.08` is enough to overcome errors and costs | Placeholder | The threshold is a safety constant, not an empirically optimized or validated hurdle. |
| `max(min_edge, 2 * spread)` is a sufficient spread buffer | Partially justified | It is directionally sensible and catches the final-day NO case, but it does not model depth, price impact, fees, queue position, or non-fill risk. |
| Spread at snapshot time represents executable cost | Untested | Current snapshot fields are single-point values; no order-book depth or time-in-force behavior is modeled. |
| Liquidity above `100.0` is enough for fills | Untested | Liquidity is checked, but not tied to requested order size, depth by level, or actual venue liquidity semantics. |
| YES can be priced from `best_ask` | Partially justified | Arithmetic is correct for simple binary contracts if the ask is executable. Executability is not proven. |
| NO can be priced as `1 - best_bid` | Partially justified | Arithmetic is correct for simple binary YES/NO complements if the book is coherent. Venue-specific fees and settlement rules are not modeled. |
| Immediate paper fill at limit plus 10 bps slippage is realistic | Unsafe | Useful for deterministic paper tests, but not safe for profitability claims without fill-rate and slippage evidence. |
| Flat `0.1%` paper fee is representative | Untested | It is configurable, but no venue-specific fee validation is included. |
| Final settlement outcome in the 5-day JSONL can validate PnL | Partially justified | The local fixture closes positions and tests settlement plumbing, but coverage is partial and sample size is one market. |
| Research recommended action should agree with selected edge side | Partially justified | This is a useful consistency gate, but the recommendation is partly guided by the same hints and thresholds. |
| Missing probability or spread should observe rather than trade | Evidence-backed | Tests and diagnostics confirm safe observe/veto behavior. |
| Low liquidity, low confidence, low evidence quality, ambiguity, and wide spread should skip | Evidence-backed | Existing tests cover these veto/skip paths. |
| Risk and paper ledger prevent live/direct orders | Evidence-backed | Existing tests and diagnostics confirm paper-only risk approval and ledger requirements. |

## Evidence Assessment

Evidence-backed:

- The implementation safely produces `skip`, `observe`, and paper-buy signals
  according to its thresholds.
- Risk evaluation vetoes non-actionable, live, low-quality, low-confidence,
  missing-edge, and wide-spread cases.
- Paper orders require an approved risk decision and remain paper-only.
- Sandbox and replay behavior is deterministic for local fixture/historical
  inputs.

Partially justified:

- Side-specific YES/NO EV arithmetic is a good MVP guardrail.
- Spread-buffer logic caught one false-looking final-day NO candidate.
- Historical local settlement proves paper PnL plumbing on the toy dataset.

Untested or placeholder:

- Probability estimation quality.
- Confidence calibration.
- Evidence-quality calibration.
- Threshold optimality.
- Liquidity and fill realism.
- Market-selection edge.
- Benchmark-relative performance.

Unsafe for profitability testing:

- Treating uncalibrated fixture or LLM probabilities as alpha.
- Treating immediate paper fills as executable fills.
- Inferring strategy quality from a five-day, single-market local fixture.

## Weaknesses

1. The strategy has no independent probability model. It consumes an estimate
   without checking calibration, uncertainty, source reliability, or historical
   hit rate.
2. Research guidance and strategy policy are coupled. The prompt includes the
   same weighted hint and threshold logic the strategy later enforces, so
   provider agreement can be circular.
3. Confidence is a gate only. It does not represent calibrated forecast
   uncertainty.
4. Edge is a point estimate. There is no confidence interval, error budget,
   drawdown-aware threshold, or expected-value distribution.
5. Fill assumptions are deterministic. The ledger is useful for paper controls,
   but not a market microstructure model.
6. Historical evidence is too small. The five-day sandbox exercises mechanics,
   not statistical significance.
7. No benchmark exists. There is no comparison to always-observe, market-price,
   random, naive threshold, or buy-and-hold equivalents.

## Suitability For Profitability Testing

Answer: no, not yet.

The current strategy can be included in paper-only pipeline diagnostics and
offline sandbox smoke tests. It should not be used as the subject of a
profitability claim or a serious profitability test until Strategy v2 has a
validated probability-estimation layer, larger historical data, explicit
benchmarking, and more realistic fill/settlement assumptions.

## What Should Not Be Changed Yet

- Do not tune the `0.08` edge threshold from the five-day fixture.
- Do not replace the default mock path with qwen for decisions.
- Do not weaken risk gates, manual approval defaults, or paper-only settings.
- Do not add broker APIs, live order code, real-money toggles, scheduler,
  daemon, autostart, Phase 8 code, leverage, derivatives, withdrawals, or
  direct LLM-to-order paths.
- Do not redesign the paper ledger fill model until Strategy v2 has a clear
  evaluation harness that can measure fill assumptions separately.
- Do not interpret qwen prose as a probability when the structured field is
  missing.

## Validation Results

Commands run:

- `PYTHONPATH=src .venv/bin/lma phase7-run-daily --db "$tmpdir/daily.sqlite" --report-dir "$tmpdir/reports" --no-require-manual-approval --llm-provider mock`
- `PYTHONPATH=src .venv/bin/lma phase7-sandbox-run --market-source historical-file --historical-file data/fixtures/phase7_historical_5d.jsonl --days 5 --db "$tmpdir/historical.sqlite" --report-dir "$tmpdir/reports" --summary-dir "$tmpdir/summaries" --no-require-manual-approval --replay-sample-size 1 --llm-provider mock`
- `PYTHONPATH=src .venv/bin/lma llm-provider-audit --llm-provider mock`
- `curl -sS --max-time 2 http://localhost:11434/v1/models`
- Direct fixture and historical strategy traces through
  `PredictionMarketEdgeStrategy`.
- `PYTHONPATH=src .venv/bin/ruff check .`
- `PYTHONPATH=src .venv/bin/pytest`

Results:

- Fixture daily mock run completed and created a paper order.
- Historical 5-day mock sandbox completed 4 runs, rejected 1 run, created 4
  paper orders, and replay sample validation returned `ok=true` with
  `mutation_detected=false`.
- Mock provider audit confirmed `research_only=true`,
  `network_calls_enabled=false`, and `can_create_orders=false`.
- Local Ollama listed `qwen3:14b`; optional current qwen daily smoke was stopped
  after roughly 2.5 minutes without output, and existing Phase 7D qwen artifacts
  were used for the qwen evidence assessment.
- Ruff passed.
- Pytest passed: 97 passed, 1 optional network test skipped.

## Final Finding

`PredictionMarketEdgeStrategy` is an MVP placeholder decision policy wrapped in
useful safety controls. The safety controls are evidence-backed by tests and
diagnostics. The alpha logic is not evidence-backed. The next strategy phase
should first improve estimation and evaluation, not order execution.
