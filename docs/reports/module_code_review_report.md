# Module-Level Code Review Report

Date: 2026-06-05

PR: https://github.com/ThineLord/local-market-agent/pull/1

Scope reviewed:

- `src/local_market_agent/schemas/models.py`
- `src/local_market_agent/storage/repository.py`
- `src/local_market_agent/llm/providers.py`
- `src/local_market_agent/agents/research.py`
- `src/local_market_agent/strategy/prediction_market.py`
- `src/local_market_agent/risk/engine.py`
- `src/local_market_agent/paper/ledger.py`
- `src/local_market_agent/reporting/daily.py`
- `src/local_market_agent/cli.py`
- `ui/app.py`
- `tests/test_strategy_risk.py`
- `tests/test_paper_ledger.py`
- `tests/test_cli.py`

## Executive Summary

One P1 issue was found and fixed during this review:

- `SQLiteRepository.append_paper_order` could persist a syntactically valid `PaperOrder` whose referenced `signal_id` or `risk_decision_id` was not present in storage. This could silently break the audit chain if code bypassed `PaperLedger`. The repository now rejects orphan, vetoed, mismatched-signal, or mismatched-market paper orders, and tests cover the orphan-order case.

No P0 issues were found.

The implementation is suitable to keep as a draft PR for manual review. It should not be merged until manual review is complete, but no remaining P0/P1 code blockers were identified after the storage relationship fix.

Follow-up reviewability pass:

- Addressed P2: daily report now has direct unit tests for order count, open positions, realized PnL, unrealized PnL, and notes that clarify paper-only mark-to-market/equity semantics rather than cash accounting.
- Addressed P2: Streamlit now includes an `Audit Chain` page joining brief -> signal -> risk decision -> paper order, with row selection and linked JSON inspection.

## Validation

After the P1 fix:

- `.venv/bin/ruff check .`: passed
- `.venv/bin/pytest`: 27 passed, 1 optional network test skipped
- Offline CLI chain with `.venv/bin/lma`: passed
  - `ingest-demo`
  - `generate-brief --fixture data/fixtures/demo_market.json`
  - `risk-check`
  - `paper-log`
  - `report-daily`

After the follow-up P2 reviewability pass:

- `.venv/bin/ruff check .`: passed
- `.venv/bin/pytest`: 30 passed, 1 optional network test skipped
- Offline CLI chain with `.venv/bin/lma` and fresh ignored `LMA_DB_PATH=data/reviewability_cli.sqlite`: passed
  - `ingest-demo`
  - `generate-brief --fixture data/fixtures/demo_market.json`
  - `risk-check`
  - `paper-log`
  - `report-daily`

## `schemas/models.py`

1. Purpose: strict Pydantic contracts for markets, snapshots, evidence, research briefs, signals, risk decisions, paper orders, positions, and performance reports.
2. Key public functions/classes: `Market`, `MarketSnapshot`, `EvidenceItem`, `ResearchBrief`, `Signal`, `RiskDecision`, `PaperOrder`, `Position`, `PerformanceReport`, action/status enums.
3. Data flow in/out: adapters and fixtures feed `MarketSnapshot`/`EvidenceItem`; LLM output validates into `ResearchBrief`; strategy emits `Signal`; risk emits `RiskDecision`; ledger emits `PaperOrder`/`Position`; reporting emits `PerformanceReport`.
4. Safety invariants: `extra="forbid"`, probability fields bounded 0-1, positive sizes, paper orders reject `ExecutionMode.LIVE`, skip briefs need reasons, paper orders require `signal_id` and `risk_decision_id`.
5. Test coverage: `tests/test_schemas.py`, plus broad use in CLI, research, storage, risk, and ledger tests.
6. Issues found:
   - P0: none.
   - P1: none.
   - P2: backward-compatible enum aliases such as `PAPER_BUY` and `OrderSide.BUY` can confuse review because the preferred Phase 0-6 vocabulary is `paper_buy_yes`/`paper_buy_no` and `BUY_YES`/`BUY_NO`.
   - P2: `Signal.edge` is not range-bounded, though current strategy emits sane values.
   - P2: object relationships are represented as string IDs, so cross-object existence is enforced in repository/ledger code rather than at schema level.
7. Code character: production-like for Phase 0-6 schema validation, with a few compatibility/scaffold compromises.

## `storage/repository.py`

1. Purpose: SQLite-backed JSON-object repository.
2. Key public functions/classes: `SQLiteRepository`, save/load/list methods, `append_paper_order`, `export_payloads`.
3. Data flow in/out: validated Pydantic models serialize to JSON payloads and hydrate back through schema validation.
4. Safety invariants: table names are fixed, payloads revalidate on load, paper orders now require existing stored signal and approved matching risk decision before persistence.
5. Test coverage: `tests/test_storage.py` roundtrips snapshots/briefs/signals/risk decisions and now rejects orphan paper orders.
6. Issues found:
   - P0: none.
   - P1: fixed. `append_paper_order` previously allowed orphan paper orders with unknown `signal_id`/`risk_decision_id`.
   - P2: SQLite does not use relational foreign keys because payloads are JSON objects; relationship checks are application-level.
   - P2: no schema migration/versioning path yet.
   - P2: list ordering uses `created_at` text from payload metadata, good enough for ISO timestamps but not a robust event-sourcing model.
7. Code character: production-like enough for local Phase 0-6, not yet production database infrastructure.

## `llm/providers.py`

1. Purpose: LLM provider abstraction with deterministic mock and optional OpenAI-compatible runtime provider.
2. Key public functions/classes: `BaseLLMProvider`, `MockLLMProvider`, `OpenAICompatibleProvider`, `structured_completion`.
3. Data flow in/out: research prompt JSON goes to provider; output JSON validates into a requested Pydantic schema.
4. Safety invariants: invalid JSON/schema output raises after bounded retries; tests use mock only; runtime provider does not create signals, risk decisions, or orders.
5. Test coverage: `tests/test_llm.py` verifies deterministic mock fields and invalid JSON handling.
6. Issues found:
   - P0: none.
   - P1: none.
   - P2: OpenAI-compatible provider is not integration-tested against LM Studio/Ollama in CI.
   - P2: runtime retry has no backoff or logging hook.
   - P2: system prompt asks for strict JSON but does not include an explicit schema summary.
7. Code character: production-like provider boundary for MVP; runtime integration remains thin.

## `agents/research.py`

1. Purpose: orchestrates researcher, skeptic, calibrator, and reporter roles.
2. Key public functions/classes: `Researcher`, `Skeptic`, `Calibrator`, `Reporter`, `ResearchBriefGenerator`.
3. Data flow in/out: `MarketSnapshot` plus `EvidenceItem` list becomes a `ResearchBrief`; optional repository save and markdown report output.
4. Safety invariants: no evidence leads to skip, missing market price prevents YES/NO paper buy, sparse evidence lowers confidence, paper sell is converted to observe.
5. Test coverage: `tests/test_research.py` verifies deterministic output, sparse-evidence confidence drop, missing price blocking, and no-evidence skip.
6. Issues found:
   - P0: none.
   - P1: none.
   - P2: safety is implemented as post-processing rather than as full schema-level invariants.
   - P2: reporter markdown is minimal and not a complete audit artifact.
   - P2: no separate uncertainty-auditor class beyond calibrator logic.
7. Code character: production-like MVP orchestration with intentionally simple role behavior.

## `strategy/prediction_market.py`

1. Purpose: converts validated research briefs and market snapshots into paper-only strategy signals.
2. Key public functions/classes: `PredictionMarketEdgeStrategy`, `CryptoTrendNewsVetoStrategy`, `EquityEventMonitorStrategy`.
3. Data flow in/out: `ResearchBrief` + `MarketSnapshot` -> `Signal`.
4. Safety invariants: low evidence quality skips, low confidence skips, low liquidity skips, resolution ambiguity skips, missing price/spread observes, wide spread skips, insufficient edge observes, only YES/NO paper signal actions are emitted for actionable cases.
5. Test coverage: `tests/test_strategy_risk.py` covers YES signal, NO signal, low confidence, wide spread, insufficient edge, low liquidity, resolution ambiguity, live-trading veto path downstream, and LLM bypass attempts downstream.
6. Issues found:
   - P0: none.
   - P1: none.
   - P2: YES/NO EV calculation is simplified and uses YES bid to infer NO ask; acceptable for fixtures but should be replaced with actual outcome orderbook data when available.
   - P2: fee/slippage buffers are represented by the same threshold rather than explicit configurable cost terms.
   - P2: crypto/equity strategies are placeholders returning observe.
7. Code character: production-like for prediction-market fixture MVP; placeholder-like for crypto/equity strategies.

## `risk/engine.py`

1. Purpose: hard risk gate for signals before paper orders.
2. Key public functions/classes: `RiskEngine.evaluate_signal`.
3. Data flow in/out: `Signal` plus caller-provided portfolio state -> `RiskDecision`.
4. Safety invariants: live execution veto, leverage veto, derivative veto, shorting/paper-sell veto, only `paper_buy_yes`/`paper_buy_no` can be approved, confidence/evidence/edge/spread/open-position/loss/drawdown thresholds enforced.
5. Test coverage: `tests/test_strategy_risk.py` covers required veto paths and default risk values.
6. Issues found:
   - P0: none.
   - P1: none.
   - P2: open positions, daily loss, and drawdown are supplied by caller rather than computed internally from repository state.
   - P2: manual approval is emitted as an audit field but does not block paper trading; acceptable because this is paper-only.
   - P2: no per-market exposure aggregation yet.
7. Code character: production-like hard gate for Phase 0-6 paper mode.

## `paper/ledger.py`

1. Purpose: creates simulated paper orders, positions, closes positions, computes PnL, exports ledger data.
2. Key public functions/classes: `PaperLedger.create_order`, `close_position`, `open_positions`, `unrealized_pnl`, `export_jsonl`, `export_csv`.
3. Data flow in/out: approved `RiskDecision` + `Signal` + `MarketSnapshot` -> `PaperOrder` + `Position`; positions -> PnL/export.
4. Safety invariants: missing/vetoed/mismatched risk decisions rejected, only YES/NO paper buys allowed, repository now also validates stored relationships.
5. Test coverage: `tests/test_paper_ledger.py` covers order lifecycle, veto rejection, YES side, and NO side.
6. Issues found:
   - P0: none.
   - P1: fixed via repository guard because storage previously allowed orphan paper orders if ledger was bypassed.
   - P2: `PaperOrder.status` remains `open` even though CLI reports `paper_order_filled`; status semantics should be clarified later.
   - P2: no cash ledger or reserved notional tracking.
   - P2: close PnL assumes long YES/NO-style payoff price marks and does not model final market resolution.
7. Code character: production-like for deterministic paper fixture ledger; not a complete trading ledger.

## `reporting/daily.py`

1. Purpose: aggregates paper positions/orders into a `PerformanceReport`.
2. Key public functions/classes: `DailyReportService.build_report`.
3. Data flow in/out: repository orders/positions -> saved `PerformanceReport`.
4. Safety invariants: report notes state paper-only behavior and clarify that `ending_cash` is a mark-to-market paper equity estimate, not cash-accounting or reserved-notional accounting.
5. Test coverage: `tests/test_daily_report.py` directly verifies order count, open positions, realized PnL, unrealized PnL, saved report output, and paper-only mark-to-market notes; CLI still covers the end-to-end daily command.
6. Issues found:
   - P0: none.
   - P1: none.
   - P2 addressed: direct daily report tests were added.
   - P2 addressed: note text now states mark-to-market paper equity semantics and warns against cash-accounting interpretation.
   - P2: drawdown, hit rate, Brier score, and calibration metrics are not implemented yet.
7. Code character: scaffold-like report aggregator suitable for MVP demo.

## `cli.py`

1. Purpose: Typer CLI for offline demo workflow.
2. Key public functions/classes: `app`, `ingest_demo`, `generate_brief`, `risk_check`, `paper_log`, `report_daily`.
3. Data flow in/out: fixtures -> repository -> brief -> signal/risk -> paper ledger -> report/export JSON.
4. Safety invariants: fixtures are defaults, no API key required for mock path, risk check precedes paper log, paper log uses `PaperLedger`.
5. Test coverage: `tests/test_cli.py` runs the full offline happy path.
6. Issues found:
   - P0: none.
   - P1: none.
   - P2: `paper-log` chooses the first approved decision in the latest 10, which is deterministic enough for demo but weak for multi-market runs.
   - P2: generated markdown reports use the configured/default output directory even when `--db` points to a test DB.
   - P2: CLI test is a happy-path integration test and does not cover command failure messages.
7. Code character: production-like for offline MVP CLI, not a batch-runner.

## `ui/app.py`

1. Purpose: Streamlit dashboard for local SQLite/fixture data.
2. Key public functions/classes: top-level Streamlit page handlers and helper `_repo`, `_frame`, `_audit_chain_rows`.
3. Data flow in/out: repository data -> tables/JSON in dashboard.
4. Safety invariants: no live trading buttons, no secret display, settings show only paths, booleans, provider name, and risk config.
5. Test coverage: `tests/test_ui.py` smoke-loads the Streamlit script and verifies the audit-chain helper returns linked brief, signal, risk decision, and paper order rows.
6. Issues found:
   - P0: none.
   - P1: none.
   - P2 addressed: added `Audit Chain` page with joined row display and linked JSON inspection.
   - P2: no full browser-level Streamlit regression test.
   - P2: table views are functional but sparse.
7. Code character: scaffold-like dashboard suitable for MVP inspection.

## `tests/test_strategy_risk.py`

1. Purpose: verifies strategy and risk safety paths.
2. Key public functions/classes: test functions for paper YES/NO, veto paths, live trading, LLM bypass, risk defaults.
3. Data flow in/out: fixture brief/snapshot -> strategy -> risk decisions.
4. Safety invariants: validates major risk gates required by the master plan.
5. Test coverage: strong for Phase 0-6 risk gates.
6. Issues found:
   - P0: none.
   - P1: none.
   - P2: boundary threshold tests at exact equality are not present.
   - P2: portfolio-state combinations are lightly tested.
7. Code character: production-like safety test suite for MVP.

## `tests/test_paper_ledger.py`

1. Purpose: verifies paper order creation, position lifecycle, veto rejection, and YES/NO order sides.
2. Key public functions/classes: paper ledger lifecycle tests.
3. Data flow in/out: strategy/risk decisions -> ledger -> repository positions/orders.
4. Safety invariants: confirms approved risk decisions are required and vetoed decisions are rejected.
5. Test coverage: good for core ledger paths.
6. Issues found:
   - P0: none.
   - P1: none after storage guard fix.
   - P2: CSV/JSONL export is indirectly covered by CLI, not directly asserted here.
   - P2: no explicit test for mismatched risk decision signal IDs.
7. Code character: production-like MVP ledger tests.

## `tests/test_cli.py`

1. Purpose: verifies the full offline CLI chain works from fixtures to daily report.
2. Key public functions/classes: `test_cli_offline_demo_chain`.
3. Data flow in/out: Typer runner -> temporary SQLite DB -> JSON CLI outputs.
4. Safety invariants: confirms offline defaults, paper-only signal, approved risk, paper order, report.
5. Test coverage: strong happy-path smoke/integration coverage.
6. Issues found:
   - P0: none.
   - P1: none.
   - P2: does not assert generated report export files exist.
   - P2: does not cover command sequencing errors beyond implicit behavior.
7. Code character: production-like happy-path integration test; failure-path coverage remains thin.

## Final Severity Summary

- P0: none.
- P1: one found and fixed in `SQLiteRepository.append_paper_order`.
- P2: remaining items are acceptable for Phase 0-6 draft PR but should guide the next review cycle.

Top P2 items:

1. Strategy EV logic is simplified, especially for NO prices and explicit fee/slippage handling.
2. Storage remains JSON-object oriented without relational foreign keys or migrations.
3. CLI and tests are mostly happy-path; failure-path and boundary tests should be expanded before Phase 7.
4. Dashboard now has an audit-chain helper test, but no full browser-level Streamlit regression test.
5. Daily reporting still omits drawdown, hit rate, Brier score, calibration metrics, and a true cash/reserved-notional ledger.

## Recommendation

Keep PR #1 as a draft and continue manual review. After the P1 storage relationship fix, the core Phase 0-6 MVP appears ready for manual maintainer review, but not yet ready to merge without human sign-off on the remaining P2 tradeoffs.
