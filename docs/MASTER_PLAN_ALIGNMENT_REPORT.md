# Master Plan Alignment Report

Date: 2026-06-05

Baseline reviewed:

- `docs/LOCAL_MARKET_AGENT_MASTER_PLAN_ORIGINAL.md`: full original source-of-truth plan, 1300 lines.
- `docs/LOCAL_MARKET_AGENT_MASTER_PLAN.md`: earlier reconstructed summary, 31 lines.
- Current implementation on branch `codex/phase0-6-local-market-agent`.

## Plan File Difference

`docs/LOCAL_MARKET_AGENT_MASTER_PLAN.md` differs materially from the original. It is a short reconstructed summary created before the original plan was present in the repo. The original plan includes detailed personal constraints, market/interface research, exact schema examples, risk defaults, milestone definitions, Codex Task 1-8 text, Phase 7/8 gates, and reference sources.

Both files are preserved. The generated summary should no longer be treated as a replacement for the original; use `docs/LOCAL_MARKET_AGENT_MASTER_PLAN_ORIGINAL.md` as the detailed baseline and this report as the Phase 0-6 alignment bridge.

## Implemented Correctly

- Project remains local-first, read-only by default, and paper-trading only.
- CLI commands exist and run offline with fixtures: `ingest-demo`, `generate-brief`, `risk-check`, `paper-log`, `report-daily`.
- Strict Pydantic schemas exist for market snapshots, evidence, briefs, signals, risk decisions, paper orders, positions, and performance reports.
- SQLite persistence stores and roundtrips snapshots, briefs, signals, risk decisions, paper orders, positions, and reports.
- Mock LLM provider is deterministic and tests do not call external APIs.
- OpenAI-compatible provider is configurable for local LM Studio/Ollama-style endpoints and remains optional.
- Implemented read-only adapters for fixtures, Polymarket, Kalshi placeholder, yfinance, SEC EDGAR, and GDELT.
- Strategy, risk, and paper ledger preserve the required chain: `ResearchBrief -> Signal -> RiskDecision -> PaperOrder`.
- Risk tests cover low confidence, wide spread, insufficient edge, live-trading attempts, missing risk decision, and LLM bypass attempts.
- Streamlit dashboard has the requested pages and no live trading buttons.
- CI runs Ruff and pytest.

## Missing Items

- Exact original schema field names are not fully mirrored. Examples: `timestamp_utc`, `asset_type`, `question`, `market_price`, `base_rate`, `reason_for_action`, `paper_order_id`, `paper_price`, `size`, `fee_assumption`, `slippage_assumption`, `exit_price`, and `pnl`.
- Evaluation metrics from the original plan are not implemented yet: Brier score, calibration curve, realized EV, drawdown metrics, random/buy-and-hold baselines, and resolution ambiguity error tracking.
- Backtest modules are placeholders only.
- A single dashboard view that deeply joins brief -> signal -> risk -> paper order is not yet specialized; the data is available across pages.
- Polymarket network behavior is covered only by optional tests and offline monkeypatched unit tests, not live API verification.

## Divergences Corrected In This Pass

- Prediction-market actions now include `paper_buy_yes` and `paper_buy_no`, matching the original plan. The old `paper_buy` value is retained only for backward parsing compatibility.
- Paper order sides now include `BUY_YES` and `BUY_NO`.
- `PredictionMarketEdgeStrategy` now supports YES and NO paper signals and uses simplified EV checks against YES/NO asks.
- Strategy now skips low-liquidity markets and ambiguous resolution sources.
- Risk defaults now match the original plan: `max_position_pct=1%`, `max_daily_loss_pct=2%`, `max_total_drawdown_pct=5%`.
- Risk decisions now expose audit fields for `requires_human_approval`, `live_trading_allowed`, `approved`, and `veto_reasons`.
- Polymarket adapter now has read-only public price and orderbook methods in addition to metadata search/snapshot.
- HTTP 429 responses now produce a rate-limit-specific error message.

## Remaining Divergences Kept Deliberately

- Storage uses SQLite only. The original allowed SQLite or DuckDB; no correction needed.
- Module layout is more consolidated than the illustrative original tree. For example, schemas are in one `models.py`, and LLM providers are in one `providers.py`. This is acceptable for Phase 0-6 and avoids churn.
- The generated master plan still says it is source of truth. It is preserved unchanged per instruction, and this report documents the difference.
- `PaperOrder` keeps internal fields such as `order_id`, `quantity`, `limit_price`, and `fill_price` rather than renaming to every original example field. The corrected action/side/risk semantics are the Phase 0-6 priority.

## Unsafe Or Over-Broad Choices

- No live trading endpoints, private exchange APIs, wallet handling, withdrawal logic, browser credential handling, or direct LLM-to-order path were found.
- The OpenAI-compatible provider can call a configured endpoint at runtime, but it is optional, tests stay offline, and no API key is required for local demo.
- Existing local generated SQLite databases, report exports, research markdowns, caches, virtualenv, and egg-info are ignored and not committed.

## Items That Should Remain Postponed

- Any real-money execution, private trading endpoints, API-key trading workflow, withdrawal permission, geoblock bypass, leverage, derivatives, or shorting.
- Phase 7 continuous paper run automation until Phase 0-6 is reviewed.
- Phase 8 small live-trading preparation until the original checklist is satisfied after at least 30 days of paper trading.
- Alpaca paper adapter, CCXT crypto adapter, NewsAPI, Alpha Vantage, IBKR/Futu/Moomoo, and any live-capable platform integrations.
- Advanced backtesting and calibration metrics beyond the current daily report.

## File-Level Correction Plan

Completed in this pass:

- `src/local_market_agent/schemas/models.py`: add original action/side vocabulary, risk audit fields, strategy name, and resolution ambiguity fields while retaining backward parsing compatibility.
- `src/local_market_agent/config/settings.py`: align default risk thresholds to the original plan and add `min_liquidity_depth`.
- `src/local_market_agent/llm/providers.py`: update deterministic mock output to recommend `paper_buy_yes`/`paper_buy_no`.
- `src/local_market_agent/agents/research.py`: apply sparse/missing-price calibration to YES/NO paper recommendations.
- `src/local_market_agent/strategy/prediction_market.py`: implement YES/NO paper signal generation, simplified EV checks, liquidity filter, and resolution ambiguity filter.
- `src/local_market_agent/risk/engine.py`: approve only `paper_buy_yes`/`paper_buy_no`, preserve live-trading vetoes, and emit human-approval/live-trading audit fields.
- `src/local_market_agent/paper/ledger.py`: create `BUY_YES`/`BUY_NO` paper orders only after approved risk decisions.
- `src/local_market_agent/adapters/base.py`: distinguish HTTP 429 rate-limit failures.
- `src/local_market_agent/adapters/polymarket.py`: add read-only public price/orderbook helpers.
- `tests/test_strategy_risk.py`: add YES/NO strategy, liquidity, resolution ambiguity, and risk-default coverage.
- `tests/test_paper_ledger.py`: add YES/NO order side coverage.
- `tests/test_adapters.py`: add offline Polymarket price/orderbook helper coverage.
- `tests/test_cli.py`, `tests/test_research.py`, `tests/test_schemas.py`: update assertions for original YES/NO vocabulary.

No further code corrections are required for Phase 0-6 alignment at this time.
