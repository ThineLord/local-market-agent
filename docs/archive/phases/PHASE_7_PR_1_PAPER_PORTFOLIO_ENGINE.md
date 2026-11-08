# Phase 7 PR-1 - Paper Portfolio Engine

## Scope

PR-1 adds the paper-only portfolio subsystem for Phase 7 continuous operations.
It is intentionally limited to local simulated portfolio accounting.

Included:

- Portfolio domain models: `Position`, `PaperOrder`, `PaperFill`, and
  `PortfolioSnapshot`
- Opening paper positions from an approved existing signal/risk decision chain
- Closing paper positions with simulated sell fills
- Realized and unrealized PnL calculation
- Local persistence for paper orders, fills, positions, and portfolio snapshots
- JSONL/CSV export helpers for paper order and fill audit records

Out of scope:

- Broker APIs
- Live trading code
- Schedulers or continuous runners
- Dashboards
- Report generators
- New risk gates
- Phase 8 broker integration

## Data Flow

```text
Signal + approved RiskDecision + MarketSnapshot
    |
PaperLedger.open_position/create_order
    |
PaperOrder + PaperFill + Position
    |
PaperLedger.close_position
    |
Closing PaperFill + closed Position
    |
PortfolioSnapshot
```

## Persistence

Paper portfolio records are stored locally through `SQLiteRepository`:

- `paper_orders`
- `paper_fills`
- `positions`
- `portfolio_snapshots`

All records are JSON payloads in the local SQLite database. No external trading
endpoint, broker credential, or live order path is introduced.

## Accounting Semantics

- Opening a paper position creates a filled paper order, an opening fill, and an
  open position.
- Closing a paper position creates a closing fill and updates the position with
  `closed_at`, `close_price`, total fees, and realized PnL.
- Unrealized PnL uses caller-supplied marks by `market_id`; if no mark is
  supplied, the position average price is used.
- Portfolio snapshots derive paper cash from fills and portfolio value from cash
  plus the mark-to-market value of open positions.

## Safety Invariants

- `PaperOrder`, `PaperFill`, and `PortfolioSnapshot` reject live execution mode.
- `PaperLedger` only opens positions for `paper_buy_yes` and `paper_buy_no`
  signals.
- Paper orders still require a saved signal and approved saved risk decision.
- Closing fills must use `SELL` and can only close existing paper positions.
- The subsystem does not contain broker adapters, private endpoints, withdrawal
  logic, leverage, shorting, scheduling, or direct LLM-to-order paths.
