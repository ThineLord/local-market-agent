# Paper approval workflow

[中文](PAPER_WORKFLOW.zh-CN.md) · [User guide](README.md)

The default path is research → risk check → prepared intent → explicit approval → execution recheck → paper fill. `paper-log` now prepares an intent and returns `pending_manual_approval`; it does not directly fill an order. Inputs must be current and valid. The static 2026 demonstration data is historical, so ingesting it today correctly blocks execution.

Use `phase7-run-daily` with current valid inputs to create an intent, then inspect it with `paper-status --db PATH`. Review the exact market, side, quantity, limit, simulated fill price, fees, evidence and risk decision before approving:

```bash
lma paper-approve --intent-id INTENT_ID --actor YOUR_NAME --reason 'Reviewed evidence and paper risk' --expires-seconds 300 --db PATH
lma paper-execute --intent-id INTENT_ID --db PATH
```

To reject or revoke a still-unexecuted intent, run `paper-approve` with `--reject`. The latest recorded decision wins. Approval expires in 1–3600 seconds, with a 300-second default. Changes to the intent, snapshot, brief, signal, risk decision or risk configuration require a new intent. Expired/stale data must be refreshed and reviewed again. Approval never overrides hard market/evidence/risk checks. Successful execution is serialized with portfolio rechecks and ledger writes; retries return the existing order.

`--no-require-manual-approval` applies only to explicit local fixture/history simulations. They still create per-intent approval receipts labelled `local-simulation`; they are not human approvals or evidence of market profitability. Public-source runs always require explicit per-intent review. The low-level ledger opening API now refuses ordinary opens: use `PaperExecutionService`. Its explicit fixture-only `simulation_only=True` API is for deterministic ledger tests, not the user workflow.

Local actor names are audit labels, not authenticated identities. This is a trusted single-user local application, not a multi-user authorization server. Content hashes detect changes; a user with database write access can rewrite local records. No cryptographic nonrepudiation is claimed.

UTC risk sessions use the previous session's last observed equity as the next day's start. The first observation bootstraps from initial capital. Peak means the highest valid observed equity, not a continuously sampled market peak. All open holdings need fresh valid quotes for execution; rejected observations cannot update risk history. Backdated runs need a separate database.

CLI approval/execution returns JSON and exit codes: `0` approved/completed, `3` rejected, `4` awaiting approval, `5` risk halt. Invalid arguments use `2`; unexpected failures use nonzero. Pending and rejected runs are not completed orders.
