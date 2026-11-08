# Local Market Agent Project Review

Date: 2026-06-17

Scope: senior engineering and research-readiness review. This document is
inspection-only. It does not implement new product behavior, live trading,
broker integration, scheduling, source scraping, acceptance-gate changes, or
Strategy v2 production enablement.

## 1. Project Overview

Local Market Agent is an offline-first Python research, risk-control, and
paper-trading system for public market data. The repository is deliberately
paper-only: live order execution, broker/private trading endpoints, withdrawals,
leverage, shorting, direct LLM-to-order paths, schedulers, daemons, and Phase 8
style automation are outside the current boundary.

The current project status is stronger than a prototype. The Phase 0-7 paper
workflow is implemented around deterministic fixtures, strict Pydantic models,
SQLite JSON persistence, a Typer CLI, a Streamlit read-only dashboard, immutable
Phase 7 manifests/reports, read-only replay, and a broad test suite. After Phase
7, the project moved into data and evaluation work: historical dataset
validation, Kalshi local export import, calibration-only public-data collectors,
bucket/category diagnostics, normalized-category diagnostics, and manual
acceptance-evidence planning.

The main research conclusion is also clear: the system is ready for supervised
paper-only operation and calibration diagnostics, but it is not ready for
Strategy v2 superiority claims, profitability claims, or acceptance/evaluation
claims from current data. The biggest missing component is not another trading
path. It is an acceptance-shaped historical dataset with timestamp-safe
evidence, point-in-time bid/ask, settlement provenance, and resolved source terms.

Live validation performed during this review:

- `git status --short`: clean before creating this file.
- `PYTHONPATH=src .venv/bin/ruff check .`: passed.
- `PYTHONPATH=src .venv/bin/pytest --collect-only -q`: interrupted after no
  output in roughly 90 seconds; traceback showed pytest still in plugin loading.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src .venv/bin/pytest --collect-only -q`:
  exited with code 143 without output after the review window.
- Full `pytest` was not run during this inspection.

Static test inventory found 297 `def test_...` functions across `tests/`, with
one network-marked test module gated by `LMA_RUN_NETWORK_TESTS`.

## 2. Current Architecture

The architecture is modular and intentionally local:

- `src/local_market_agent/schemas`: strict Pydantic contracts for markets,
  snapshots, evidence, briefs, forecasts, signals, risk decisions, paper orders,
  positions, Phase 7 runs, manifests, and reports.
- `src/local_market_agent/config`: environment-backed settings with paper-only
  defaults: `REAL_MONEY_ENABLED=false`, `ALLOW_LIVE_ORDERS=false`, and
  `HUMAN_APPROVAL_REQUIRED=true`.
- `src/local_market_agent/storage`: a small SQLite object repository that stores
  model payloads as JSON plus basic `market_id` and timestamp columns.
- `src/local_market_agent/adapters`: read-only fixture, Polymarket, Kalshi,
  yfinance, SEC EDGAR, and GDELT adapters. Network adapters are optional and do
  not expose private trading/account/order paths.
- `src/local_market_agent/llm`: deterministic mock provider plus
  OpenAI-compatible structured JSON provider. Provider audit reports whether
  network calls are enabled and confirms research-only behavior.
- `src/local_market_agent/agents`: research brief generation, skeptic review,
  confidence/evidence calibration, and Markdown research output.
- `src/local_market_agent/strategy`: production Strategy v1
  `PredictionMarketEdgeStrategy`; Strategy v2 candidate is evaluation-only.
- `src/local_market_agent/risk`: signal-level risk engine plus Phase 7 risk gate
  evaluator for freshness, position limits, exposure, drawdown, loss streaks,
  and manual approval.
- `src/local_market_agent/paper`: deterministic paper ledger, simulated fills,
  positions, cash/PnL snapshots, and exports.
- `src/local_market_agent/operations`: Phase 7 daily runner, sandbox runner,
  replay, manifests, historical-file input, and market data audit.
- `src/local_market_agent/data`: historical dataset builder/validator and Kalshi
  local export adapter.
- `src/local_market_agent/eval`: forecast assessment, offline strategy
  evaluation, calibration audit, bucket QA, category normalization, category
  balance planning, category calibration, normalized availability audit, and
  collector diagnostics.
- `scripts/local_only`: temporary/local Kalshi collectors, evidence worksheet,
  evidence candidate generation, and human review UI. These remain outside the
  package and write ignored local artifacts.
- `ui/app.py`: read-only Streamlit dashboard for local SQLite and Phase 7
  operations state.

The system's central production chain is:

```text
MarketSnapshot + Evidence -> ResearchBrief -> Signal -> RiskDecision
  -> PaperOrderIntent -> RiskGateDecision -> PaperOrder/PaperFill/Position
  -> PortfolioSnapshot -> Phase7DailyReport + Phase7RunManifest
```

The research/evaluation chain is:

```text
Local source export -> Historical JSONL -> Historical validation
  -> Calibration audit / bucket QA / category diagnostics
  -> Offline Strategy v1 vs Strategy v2 comparison
  -> Acceptance gate result
```

## 3. Key Workflows

Offline demo:

- `lma ingest-demo`
- `lma generate-brief --fixture data/fixtures/demo_market.json`
- `lma risk-check`
- `lma paper-log`
- `lma report-daily`

Phase 7 supervised daily paper run:

- Defaults to fixture market data and mock LLM.
- Explicitly supports read-only current snapshots from Polymarket, Kalshi, and
  yfinance.
- Supports local historical JSONL through `--market-source historical-file`.
- Writes immutable per-run reports and manifests.
- Persists failed runs best-effort.
- Replays stored runs read-only through `lma phase7-replay`.

Phase 7 sandbox:

- Runs repeated daily-paper workflow over fixture or historical-file date ranges.
- Uses deterministic model context for IDs and timestamps.
- Samples replay checks to confirm stored-run replay does not mutate state.

LLM provider workflow:

- Default `mock` provider is deterministic and offline.
- OpenAI-compatible provider must be explicitly selected.
- Provider output is schema-validated with bounded retries and parser hardening.
- LLM output can create research JSON only; downstream signals/risk/orders remain
  rule-based and paper-only.

Historical/calibration workflow:

- Validate historical JSONL with `lma validate-historical-dataset`.
- Import local Kalshi exports with `lma import-kalshi-export`.
- Audit calibration data with `lma audit-calibration-dataset`.
- Run bucket QA, category analysis, normalization, balance planning, and
  availability diagnostics.
- Run offline Strategy v1/v2 comparison with `lma strategy-eval-offline`.

Manual acceptance-evidence workflow:

- Pre-screen 8-12 candidate markets.
- Prepare evidence worksheet/template from a local export.
- Use local Streamlit review UI for human approval.
- Import only after evidence and terms review are complete.
- Validate and run strategy evaluation only if dataset-level gates pass.

## 4. Strengths

- Safety boundaries are unusually explicit and consistently reinforced in docs,
  schemas, risk logic, CLI behavior, tests, and local scripts.
- The repository is reproducible for offline demos without API keys.
- Pydantic schemas enforce paper-only execution modes on orders, fills,
  snapshots, risk gate decisions, run records, and manifests.
- The storage layer is simple and easy to inspect locally.
- Phase 7 has a coherent audit trail: manifests, immutable report paths,
  checksums, run records, failed-run metadata, and replay validation.
- Evaluation tooling is careful about claim guardrails: calibration-only datasets
  block acceptance, Strategy v2 superiority, paper-PnL, profitability, and live
  readiness claims.
- The data validation layer checks many research-grade failure modes: future
  evidence leakage, missing bid/ask, ambiguous settlement, source terms,
  private sources, duplicate rows, malformed probabilities, and secret-like
  fields.
- Local Kalshi work has evolved toward good diagnostics rather than opaque
  scraping: category normalization, per-category candle failures, unselected
  examples, and availability audits are all useful.
- Strategy v2 is correctly kept evaluation-only and more provenance-aware than
  Strategy v1.
- Tests are broad and aligned with safety boundaries; many tests explicitly check
  absence of broker/live/order API dependency.

## 5. Weaknesses

- No current acceptance-shaped dataset exists. The best data is still
  calibration-only, last-price-only, evidence-empty, and bid/ask-empty.
- Source terms remain a blocker for acceptance claims. The workflow documents
  `terms_review=pending_review` as a hard stop, but there is no completed terms
  closure artifact.
- Strategy v1 depends heavily on upstream `estimated_probability`, which often
  comes from fixture/historical hints or falls back to market-implied probability.
  It is safe for paper workflow validation but weak as an alpha model.
- Real-provider research has not shown reliable structured decision value. The
  qwen validation found richer prose but structured probability omissions that
  changed downstream outcomes in the wrong direction.
- The production paper runner is still single-input/single-market oriented.
  Multi-market universe persistence and completeness gates are thin.
- Storage is JSON-object based with no migrations or schema-version compatibility
  strategy for persisted SQLite records.
- Evaluation reports and local generated artifacts are numerous, ignored, and
  not managed by a first-class artifact registry. Reproducing exact historical
  local state depends on local files that may not travel with the repo.
- Pytest collection was unexpectedly slow or stalled during this review, which
  should be treated as a maintainability concern until reproduced or dismissed.
- The Streamlit dashboard has import/startup smoke tests but no full browser
  regression coverage.
- CI is simple and valuable, but it does not preserve generated reports, run
  acceptance smoke commands, or test slow/local-only collector behavior.

## 6. Technical Debt

- SQLite repository stores JSON blobs in generic tables. This is productive for
  rapid local research, but it makes migrations, compatibility checks, ad hoc
  queries, and partial indexes difficult.
- Schema evolution is risky: old payloads can become unreadable if strict
  Pydantic models change.
- CLI is large (`src/local_market_agent/cli.py`) and now owns many workflows.
  Command routing remains understandable, but review burden is increasing.
- The repository has several local-only scripts with duplicated export,
  timestamp, JSONL, and diagnostics patterns. Some duplication is intentional,
  but shared helpers may now be worth extracting for safety-critical parsing and
  artifact writing.
- yfinance normalization maps equity closes to probability-style fields only
  when close is between 0 and 1, making it mostly a snapshot smoke path rather
  than a useful market probability source.
- Risk metrics count all non-failed runs as successful; rejected, halted,
  pending manual approval, and dry-run statuses deserve clearer operational
  accounting.
- Skipped or missed calendar runs are not first-class records.
- Category metadata is often available in source manifests and diagnostics, but
  row-level historical datasets still lose too much category visibility.
- Generated local artifacts under `data/historical`, `data/source_exports`, and
  `data/reports` are intentionally ignored but numerous; checksum manifests and
  retention rules are not first-class.
- Some tests perform source-code string scans for safety invariants. These are
  useful guardrails but should not be the only safety proof for future larger
  changes.

## 7. Research Risks

- Calibration-only datasets collapse Strategy v1 and Strategy v2 to market
  implied or last-price diagnostics. They cannot support Strategy v2 superiority
  or paper-PnL claims.
- Current high-gap calibration buckets are useful QA targets but remain sensitive
  to source mix, category skew, missing bid/ask, missing evidence, thin liquidity,
  and public-event dominance.
- Evidence timestamp quality is the central blocker. Untimestamped, date-only,
  after-the-fact, settlement-only, or ambiguous-source evidence can create
  leakage.
- Settlement and label availability must be separated from forecast-time
  evidence. The docs do this well; future data entry must preserve that split.
- Real LLM providers can sound better while producing incomplete structured
  fields. Decision quality must be judged from downstream structured outputs,
  not prose.
- Benchmark comparisons are still thin. Market-implied probability is present as
  a baseline, but holdout splits, benchmark-relative return methodology, and
  robust significance claims remain future work.
- Manual data curation can introduce hidden selection bias unless rejected
  candidates, source failures, and reviewer decisions are preserved.
- Weather/Fed/macro availability findings depend on current Kalshi public-market
  availability and collector taxonomy. They should be treated as local
  diagnostics, not universal source-scarcity conclusions.
- Acceptance gate thresholds are sensible but unproven on a real acceptance
  dataset.

## 8. Reproducibility Concerns

- The tracked repository is reproducible for fixture/offline demos.
- Many important research artifacts are intentionally local and ignored:
  historical JSONL, source exports, calibration reports, strategy eval reports,
  research-quality SQLite databases, and evidence review artifacts.
- Docs reference generated local artifacts that may not exist on another clone.
  The current machine does contain many such artifacts under `data/`.
- There is no single artifact index that maps a docs report to exact source
  export, historical JSONL, validation JSON, strategy eval output, checksums,
  command, and git commit.
- Full pytest was not run during this review. Ruff passed, but test collection
  did not complete cleanly in this local environment.
- Optional network behavior is correctly gated, but current public endpoint
  availability is inherently unstable.
- The `.venv` currently uses Python 3.13, while CI uses Python 3.11. This is
  generally acceptable because the package declares `>=3.11`, but slow pytest
  collection should be checked on both versions before assuming it is local-only.

## 9. Missing Features

- Validated acceptance-candidate dataset with timestamp-safe evidence,
  point-in-time bid/ask, unambiguous settlement, and completed terms review.
- First-class source terms review artifact and status flow.
- Provider quality scoring for real LLMs, especially structured probability
  completeness and prose-only probability detection at run level.
- First-class skipped/missed-run accounting and long-running supervised operation
  evidence.
- Multi-market candidate universe persistence and completeness gates.
- Storage schema versioning, migrations, and compatibility tests for persisted
  SQLite payloads.
- Artifact registry for generated local datasets/reports/checksums.
- Row-level normalized category/provenance fields in historical JSONL imports.
- Holdout/benchmark methodology for Strategy v2 beyond calibration diagnostics.
- Full dashboard browser regression checks.
- CI job or local smoke command that verifies the key CLI commands still work
  after the test suite grows.
- Better pytest collection/runtime diagnostics if the current slow collection
  reproduces.

## 10. Top 10 Recommended Next Tasks

| Rank | Task | Impact | Implementation effort | Risk level | Rationale |
| ---: | --- | --- | --- | --- | --- |
| 1 | Execute a manual acceptance-evidence pilot for 5-10 markets | High | Medium | High | This is the highest-leverage research blocker. It tests whether the project can produce timestamp-safe evidence, bid/ask, settlement, and source provenance without relaxing guardrails. Risk is high because source availability and human curation quality may fail. |
| 2 | Create a source terms review artifact and gate it through import/audit reports | High | Small-Medium | Medium | Acceptance claims are blocked while terms are pending. A first-class artifact would make terms status auditable instead of only documented. |
| 3 | Add provider quality scoring to Phase 7 and offline evaluation | High | Medium | Medium | Real providers should be scored on structured probability completeness, prose-only probability mismatch, evidence copying, and downstream materiality before being trusted for paper decisions. |
| 4 | Add storage schema versioning and compatibility tests | High | Medium | Medium | The JSON-in-SQLite design is simple, but strict model changes can break old local records. Version tags and migration/compatibility tests reduce future fragility. |
| 5 | Build an artifact registry for local datasets and generated reports | High | Medium | Low-Medium | The repo has many ignored but important artifacts. A registry with command, source export, historical file, report paths, checksums, and commit hash would improve reproducibility without committing raw exports. |
| 6 | Persist row-level category/provenance metadata in historical imports | Medium-High | Medium | Low-Medium | Category diagnostics already exist, but historical rows lose too much category visibility. Carrying normalized category fields into rows would make bucket QA and acceptance reports clearer. |
| 7 | Add first-class skipped/missed-run accounting | Medium-High | Small-Medium | Low | Phase 7 run success rate currently treats non-failed statuses too coarsely. Missed calendar days and skipped runs need explicit records for 30-day/60-day supervised validation. |
| 8 | Design multi-market candidate universe persistence for paper-only runs | High | Medium-Large | Medium-High | The runner is coherent but single-input oriented. A persisted, read-only universe with completeness gates is needed before supervised operation can resemble a real research process. |
| 9 | Harden test collection/runtime and add a focused CLI smoke target | Medium | Small-Medium | Low | Ruff passes, but pytest collection did not complete during this review. A reliable smoke target should cover core CLI workflows quickly, separate from slow or optional tests. |
| 10 | Add holdout/benchmark evaluation plan for Strategy v2 after acceptance data exists | Medium-High | Medium-Large | Medium | Strategy v2 should remain evaluation-only until tested against an acceptance-shaped dataset with holdout discipline, benchmark comparisons, and claim guardrails. |

Recommended sequencing:

1. Finish acceptance evidence and terms readiness before strategy claims.
2. Improve reproducibility and artifact indexing before more dataset retries.
3. Tighten provider quality gates before leaning on real local LLMs.
4. Only then broaden multi-market paper operations or Strategy v2 evaluation.

Do not make broker/live trading, scheduler/daemon/autostart, Phase 8, or
Strategy v2 production-enablement tasks part of this next implementation queue.
