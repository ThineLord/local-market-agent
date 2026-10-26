# Regression results — 2026-10-26

Environment: isolated non-synced worktree based on audit SHA `e04aaa05d9930264aed80b29d69cde95beb1bd95`; macOS arm64, Python 3.13.15, pytest 9.1.1, Ruff 0.17.2. Dependencies installed in a temporary virtual environment from the existing project dev specification. Repository CI independently uses Python 3.11.

Executed:

- `ruff check .`: PASS.
- `LMA_RUN_NETWORK_TESTS=false pytest -q`: **376 passed, 1 skipped**, 17.95 seconds. The skipped test is the opt-in public market network test.
- `git diff --check`: PASS.
- Focused tests during development: 34 passed, then 38 passed after dry-run/sandbox coverage; superseded by the full suite above.

Thirty new regression cases cover normal lifecycle compatibility, exceptions after every opening/closing write, KeyboardInterrupt, injected commit error, repeat requests after reconnect/close, concurrent opening and settlement, five forced-process-exit recovery points, SQLite integrity checks, read-only portfolio access, populated portfolio dry-run invariance and sandbox preview replay/equity.

Process exit cases reopen the file, compare the complete business-state hash, run `PRAGMA integrity_check` (ok) and `foreign_key_check` (empty), and retry successfully. The existing schema has no SQL foreign keys, so the latter is not proof of relational accounting consistency; tests separately verify row counts and transition links.

No production DB, credentials, live trading endpoints or external paid inference were used. No deployment or merge. Test pass is not a profitability claim or proof against arbitrary corruption. Exact reviewed commit and PR/CI receipts are delivered separately, avoiding a self-referential SHA inside the commit it identifies.

Baseline sensitivity check: ran the new opening-write-failure and fixture dry-run hash tests against the unmodified audited source. Both failed at the business-state equality assertion (**2 expected failures**), demonstrating that these regressions detect the previous behavior rather than only describing the fix.

Independent review identified that the populated historical test's approved/manual labels initially lacked sufficient synthetic evidence and could both reach REJECTED. The fixture now supplies deterministic evidence/liquidity and asserts the exact DRY_RUN, PENDING_MANUAL_APPROVAL, REJECTED and FAILED statuses. All 11 dry-run tests passed after this correction.

An additional isolated baseline/fix settlement probe confirmed the original ENG-02 directly: dry-run on two existing YES/NO positions changed open positions 2 -> 0, fills 2 -> 4, and paper cash 9799.8000 -> 9995.2990. The fixed implementation kept all three values unchanged (2 positions, 2 fills, 9799.8000 cash) and reported zero settlements. The example returned REJECTED in both versions, showing the old unconditional settlement could mutate holdings even after an evaluation rejection.
