# Code Quality and Safety Audit

Date: 2026-06-05

## Scope

Audit performed on tracked repository files under `/Users/hanzhiyou/Documents/Local Market Agent`. Ignored local artifacts were observed but not inspected as source code. No browser profiles, Keychain entries, SSH private keys, wallets, `.env` files, or unrelated user files were inspected.

## Safety Findings

### Live Trading / Private Endpoints

No live-trading, order-execution, private trading endpoint, withdrawal, wallet, geoblock bypass, leverage, derivatives, or shorting implementation was found.

Relevant code behavior:

- `src/local_market_agent/risk/engine.py` vetoes live execution mode and live-order requests.
- `src/local_market_agent/paper/ledger.py` only creates simulated paper orders after an approved risk decision.
- `src/local_market_agent/adapters/polymarket.py` exposes read-only public metadata, price, and orderbook helpers only.
- `src/local_market_agent/adapters/kalshi.py` is documented as public/demo read-only and does not accept credentials.

### Secrets / Credentials

No tracked `.env`, SQLite DB, token file, private key, wallet, password file, or credential-like file path was found by `git ls-files`.

Tracked code contains only placeholder/configuration references:

- `.env.example` uses placeholder values.
- `OpenAICompatibleProvider` accepts an optional runtime `api_key`, but tests do not call external APIs and no key is committed.
- Docs mention API keys only as safety constraints or future-postponed topics.

### `.gitignore`

`.gitignore` excludes:

- `.env` and `.env.*` while allowing `.env.example`
- `.venv/`
- Python caches
- `.pytest_cache/`
- `.ruff_cache/`
- build/dist/egg-info
- local SQLite/database files
- `data/raw_cache/*`
- generated research briefs
- generated reports
- logs
- `.DS_Store`

This covers local DBs, caches, virtualenv, `.env`, raw caches, generated reports, and common local artifacts.

## Chain Enforcement

LLM output cannot directly create a paper order.

Current flow:

```text
Mock/OpenAI-compatible LLM output -> ResearchBrief schema
ResearchBrief + MarketSnapshot -> PredictionMarketEdgeStrategy -> Signal
Signal -> RiskEngine -> RiskDecision
Signal + approved RiskDecision + MarketSnapshot -> PaperLedger -> PaperOrder
```

`PaperLedger.create_order` rejects:

- missing risk decisions
- vetoed risk decisions
- risk decisions for another signal
- non-actionable signal actions

`PaperOrder` schema requires both `signal_id` and `risk_decision_id`.

## Risk Defaults

Risk defaults match the original master plan:

- `max_position_pct = 0.01`
- `max_daily_loss_pct = 0.02`
- `max_total_drawdown_pct = 0.05`
- `max_open_positions = 5`
- `min_confidence = 0.60`
- `min_edge = 0.08`
- `max_spread = 0.08`
- live trading disabled by default
- human approval required by default

Covered by `tests/test_strategy_risk.py::test_risk_defaults_match_original_master_plan`.

## Test Coverage Checklist

- Low confidence veto: covered by `tests/test_strategy_risk.py::test_low_confidence_veto`.
- Wide spread veto: covered by `tests/test_strategy_risk.py::test_wide_spread_veto`.
- Insufficient edge observe: covered by `tests/test_strategy_risk.py::test_insufficient_edge_observe`.
- Low liquidity skip: covered by `tests/test_strategy_risk.py::test_low_liquidity_skips`.
- Resolution ambiguity skip: covered by `tests/test_strategy_risk.py::test_resolution_ambiguity_skips`.
- Live trading attempt veto: covered by `tests/test_strategy_risk.py::test_live_trading_attempt_is_vetoed`.
- Missing risk decision prevents order: covered by `tests/test_strategy_risk.py::test_missing_risk_decision_blocks_paper_order`.
- YES/NO paper order sides: covered by `tests/test_paper_ledger.py::test_paper_order_position_lifecycle` and `tests/test_paper_ledger.py::test_paper_buy_no_order_uses_no_side`.

## Code Smells / Thin Placeholder Areas

- Backtest and evaluation modules are placeholders only: `src/local_market_agent/backtest/__init__.py`, `src/local_market_agent/eval/__init__.py`.
- Dashboard can inspect each table, but does not yet provide a single joined brief -> signal -> risk -> paper order chain view.
- Exact original schema example field names are not fully mirrored; this is documented in `docs/MASTER_PLAN_ALIGNMENT_REPORT.md`.
- Polymarket public network behavior is not validated live by default; network tests are optional and skipped unless explicitly enabled.
- Read-only adapters are intentionally minimal and should be reviewed before any Phase 7 automation.
- `OpenAICompatibleProvider` is runtime-capable but not integration-tested against LM Studio/Ollama in CI.
- Local generated artifacts exist in the worktree from validation runs, but they are ignored and untracked.

No P0/P1 safety defect was found. No code changes were made during this audit.

## Validation Results

### `.venv/bin/ruff check .`

```text
All checks passed!
```

### `.venv/bin/pytest`

```text
collected 27 items
26 passed, 1 skipped in 0.08s
```

The skipped test is the optional network-marked adapter test.

### Offline CLI Chain

Command path used: `.venv/bin/lma`.

```text
ingest-demo: passed
generate-brief: passed, recommended_action=paper_buy_yes
risk-check: passed, risk_status=approved, signal_action=paper_buy_yes
paper-log: passed, status=paper_order_filled
report-daily: passed, orders=1, open_positions=1
```

No live orders were placed or attempted.
