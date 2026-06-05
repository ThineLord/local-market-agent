# Phase 7D Research Quality Comparison

## Summary

`qwen3:14b` materially changed outcomes in the 5-day historical sandbox, but not
in the daily fixture run. The material sandbox changes were not clear quality
improvements: qwen often wrote useful probability analysis in prose but left the
structured `estimated_probability` field empty, which caused deterministic
downstream logic to observe, veto, reject risk gates, and skip paper orders.

## Daily Fixture Comparison

Artifact:
`data/reports/research_quality/phase7d_daily_qwen3_14b_20260605/research_quality_comparison.json`

| Field | Mock | qwen3:14b |
| --- | --- | --- |
| Run status | `completed` | `completed` |
| Recommendation | `paper_buy_yes` | `paper_buy_yes` |
| Confidence | `0.7438` | `0.82` |
| Evidence quality | `0.6564` | `0.81` |
| Estimated probability | `0.6083` | `0.6083` |
| Signal action | `paper_buy_yes` | `paper_buy_yes` |
| Signal edge | `0.1183` | `0.1183` |
| Risk decision | `approved` | `approved` |
| Risk gate | `approved` | `approved` |
| Paper order | `BUY_YES`, filled | `BUY_YES`, filled |
| Material outcome change | no | no |

Observation: qwen produced higher confidence and evidence-quality scores, but
those differences did not change recommendation, signal action, risk outcome,
risk gate outcome, or paper-order outcome.

## Historical Sandbox Comparison

Artifact:
`data/reports/research_quality/phase7d_sandbox_qwen3_14b_historical_5d_20260605/research_quality_comparison.json`

Aggregate results:

| Metric | Mock | qwen3:14b |
| --- | --- | --- |
| Completed runs | `4` | `1` |
| Rejected runs | `1` | `4` |
| Failed runs | `0` | `0` |
| Run success rate | `1.0` | `1.0` |
| Materially changed days | n/a | `2026-05-01`, `2026-05-02`, `2026-05-03` |
| Replay sample | `ok=true` | `ok=true`, `mutation_detected=false` |

Day-level comparison:

| Date | Mock recommendation | qwen recommendation | Mock signal | qwen signal | Material change | Main reason |
| --- | --- | --- | --- | --- | --- | --- |
| `2026-05-01` | `paper_buy_yes` | `observe` | `paper_buy_yes` | `observe` | yes | qwen omitted structured estimated probability |
| `2026-05-02` | `paper_buy_yes` | `observe` | `paper_buy_yes` | `observe` | yes | qwen omitted structured estimated probability |
| `2026-05-03` | `paper_buy_yes` | `observe` | `paper_buy_yes` | `observe` | yes | qwen omitted structured estimated probability |
| `2026-05-04` | `paper_buy_yes` | `paper_buy_yes` | `paper_buy_yes` | `paper_buy_yes` | no | qwen matched downstream outcome |
| `2026-05-05` | `paper_buy_no` | `paper_buy_no` | `observe` | `observe` | no | both blocked by deterministic strategy/risk |

## Structured Research Quality

Daily fixture:

- qwen matched the mock provider on action and estimated probability.
- qwen produced higher confidence and evidence-quality values.
- No downstream outcome changed.

Historical sandbox:

- qwen sometimes produced more expressive rationale.
- On the first three days, qwen's rationale mentioned probability estimates
  above the market, but the structured `estimated_probability` field was `null`.
- The architecture correctly refused to convert prose-only estimates into orders.
- The result was fewer paper orders and more rejected runs, not an evidenced
  quality improvement.

## Decision Quality Assessment

In the current architecture, decision quality depends on structured research
fields, not prose alone. qwen did not reliably improve those structured fields:

- It matched the mock provider when it copied probability hints into the schema.
- It changed outcomes when it failed to fill required decision-driving fields.
- It did not improve risk decisions, risk gate outcomes, or paper-order outcomes.
- It remained slower and less deterministic than the mock provider.

## Answer

No. `qwen3:14b` does not currently provide meaningful value over the mock
provider for Local Market Agent's paper-only research-to-decision pipeline.

It may be valuable later if the pipeline adds stricter structured-output
completeness validation, provider-quality scoring, and a larger evaluation set.
For now, the mock provider is more reliable for deterministic paper-only
validation, and qwen should remain an optional research experiment rather than a
decision-quality dependency.
