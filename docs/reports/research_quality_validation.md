# Phase 7D Research Quality Validation

## Goal

Determine whether `qwen3:14b` through local Ollama materially improves research
quality and decision quality versus the deterministic mock provider in the
current Local Market Agent architecture.

This validation is not a profitability claim, broker integration test, live
trading exercise, scheduler test, or Phase 8 start.

## Methodology

- Added Phase 7D comparison tooling that runs paired provider experiments with
  isolated SQLite databases under `data/reports/research_quality/`.
- Compared `mock` against `openai-compatible` using model `qwen3:14b` and base
  URL `http://localhost:11434/v1`.
- Used identical inputs per pair, then compared research brief fields, confidence,
  recommendation, signal, risk decision, risk gate decision, and paper-order
  outcome.
- Treated research text, confidence, and evidence-quality differences as
  research differences, but treated only recommendation, signal action, risk
  status, risk gate status, run status, or paper-order changes as material
  downstream outcome changes.
- Kept all execution paper-only and local. The LLM remained research-only; signal,
  risk, gates, and paper orders remained deterministic downstream systems.

## Inputs

| Experiment | Market input | Evidence input | Provider A | Provider B |
| --- | --- | --- | --- | --- |
| Daily fixture comparison | `data/fixtures/demo_market.json` | `data/fixtures/demo_evidence.json` | `mock` | `qwen3:14b` via Ollama |
| Historical sandbox comparison | `data/fixtures/phase7_historical_5d.jsonl` | JSONL embedded evidence | `mock` | `qwen3:14b` via Ollama |

Provider audit results:

| Provider | Network calls | Research only | Can create orders | API key printed |
| --- | --- | --- | --- | --- |
| `mock` | `false` | `true` | `false` | no |
| `openai-compatible`, `qwen3:14b` | `true` | `true` | `false` | no |

Ollama model discovery confirmed `qwen3:14b` was available locally.

## Outputs

Generated comparison artifacts:

- `data/reports/research_quality/phase7d_daily_qwen3_14b_20260605/research_quality_comparison.json`
- `data/reports/research_quality/phase7d_daily_qwen3_14b_20260605/research_quality_comparison.md`
- `data/reports/research_quality/phase7d_sandbox_qwen3_14b_historical_5d_20260605/research_quality_comparison.json`
- `data/reports/research_quality/phase7d_sandbox_qwen3_14b_historical_5d_20260605/research_quality_comparison.md`

Required reports:

- `docs/reports/research_quality_validation.md`
- `docs/reports/research_quality_comparison.md`

## Observations

Daily fixture comparison:

- Both providers completed.
- Both recommended `paper_buy_yes`.
- Both produced the same estimated probability, `0.6083`.
- qwen increased confidence from `0.7438` to `0.82` and evidence quality from
  `0.6564` to `0.81`.
- Signal action, risk decision, risk gate status, paper order side, quantity,
  limit, fill, and status were unchanged.
- Corrected materiality result: no material downstream outcome change.

Historical 5-day sandbox comparison:

- Mock status counts: 4 completed, 1 rejected, 0 failed.
- qwen status counts: 1 completed, 4 rejected, 0 failed.
- Materially changed days: `2026-05-01`, `2026-05-02`, and `2026-05-03`.
- On the first three days, qwen prose referenced probability estimates above the
  market price, but the structured `estimated_probability` field was `null` and
  the recommendation became `observe`.
- Those `null` structured probabilities flowed into deterministic strategy and
  risk logic as `observe`, `vetoed`, rejected risk gates, and no paper order.
- On `2026-05-04` and `2026-05-05`, qwen matched the material downstream
  outcomes while raising confidence/evidence-quality scores.
- Replay sample validation for the qwen sandbox reported `ok=true` and
  `mutation_detected=false`.

## Bugs Found And Fixed

- The initial comparison materiality logic counted confidence/evidence-quality
  changes inside the signal as material downstream outcome changes, even when
  signal action, risk, gates, and paper order were unchanged.
- Fixed by separating research/signal field differences from material decision
  outcome changes.
- Added regression coverage proving confidence-only signal changes do not
  overstate materiality.

## Validation

Commands run:

- `PYTHONPATH=src .venv/bin/lma llm-provider-audit`
- `PYTHONPATH=src .venv/bin/lma llm-provider-audit --llm-provider openai-compatible --llm-model qwen3:14b --llm-base-url http://localhost:11434/v1`
- `curl -sS http://localhost:11434/v1/models`
- `PYTHONPATH=src .venv/bin/lma phase7-research-quality-daily-compare --artifact-dir data/reports/research_quality --comparison-id phase7d_daily_qwen3_14b_20260605 --evaluation-date 2026-06-05 --no-require-manual-approval --qwen-model qwen3:14b --qwen-base-url http://localhost:11434/v1`
- `PYTHONPATH=src .venv/bin/lma phase7-research-quality-sandbox-compare --artifact-dir data/reports/research_quality --comparison-id phase7d_sandbox_qwen3_14b_historical_5d_20260605 --market-source historical-file --historical-file data/fixtures/phase7_historical_5d.jsonl --days 5 --no-require-manual-approval --replay-sample-size 1 --qwen-model qwen3:14b --qwen-base-url http://localhost:11434/v1`
- `PYTHONPATH=src .venv/bin/ruff check .`
- `PYTHONPATH=src .venv/bin/pytest`

Results:

- Ruff passed.
- Pytest passed with 97 passed and 1 optional network test skipped.
- Provider audits preserved research-only and paper-only constraints.
- Daily and sandbox comparisons generated local artifacts without broker APIs,
  live orders, scheduler, daemon, autostart, or Phase 8 functionality.

## Conclusion

Using `qwen3:14b` provides some richer research prose and higher confidence or
evidence-quality scores, but it does not provide clear meaningful value over the
mock provider in the current architecture.

The daily fixture run showed no material downstream change. The historical
sandbox did show material downstream changes, but the main cause was qwen failing
to populate structured probability fields on three days despite discussing those
probabilities in prose. That reduced decision pipeline reliability rather than
improving it.

Answer: no, a real local LLM does not currently provide meaningful decision
value over the mock provider in this architecture. The next useful step is to
add stricter structured-field completeness checks and provider-quality scoring
before relying on real-provider research for paper decision evaluation.
