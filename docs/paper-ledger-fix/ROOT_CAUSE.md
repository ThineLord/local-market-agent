# ENG-01 / ENG-02 root cause

Baseline: `e04aaa05d9930264aed80b29d69cde95beb1bd95`, matching the 2026-10-26 GitHub audit. Reviewed the repository AUDIT.md, FINDINGS.json, and account RISK_REGISTER.md before implementation. Findings concern simulated accounting only.

## State machine and storage

| Entity | Representation and transition |
| --- | --- |
| Orders | `paper_orders`: immediately FILLED for an approved simulated buy; references persisted signal and approved risk decision |
| Executions / ledger entries | `paper_fills`: one opening fill; one closing SELL fill per position |
| Positions | `positions`: open after buy; `closed_at`, `close_price`, fees and realized PnL set at close |
| Balance | No mutable balance table. Cash is starting cash minus buy notional/fees plus closing proceeds minus fees |
| Portfolio | `portfolio_snapshots`: derived cash, holdings, fees and PnL; historical reports, not authoritative cash |
| Run lineage | Snapshots, briefs, signals, risk/gate decisions, manifests and records support evaluation and replay |

ENG-01: every repository `_save` previously opened and committed its own connection. Opening wrote order -> position -> fill; closing wrote fill -> closed position. A later failure could leave cash (fills) and holdings (positions) inconsistent. Random new IDs on retry could duplicate an opening. Close's open-state check outside a common transaction also allowed simultaneous callers to both settle.

ENG-02: `Phase7DailyRunner.run(dry_run=True)` skipped new orders but still unconditionally called historical settlement. Existing matching YES/NO positions could be closed and closing fills inserted. The original empty-database dry-run test did not exercise that precondition. Other evaluation and portfolio rows were also written to the source database.

## Scope decisions

Atomic unit is one position open or close, not an entire daily research/report workflow or a multi-position settlement batch. A failed later report does not undo an already committed valid paper trade. Reusing the same signal identifies a retry; a fresh daily run generates a new signal and is a new request. Existing partially committed legacy records are not automatically repaired. No production database was inspected, migrated or modified.
