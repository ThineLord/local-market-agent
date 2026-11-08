# Atomic paper transitions

`SQLiteRepository.transaction()` yields a copy bound to one SQLite connection. `BEGIN IMMEDIATE` acquires the write reservation before checking existing orders or position status. All validation reads and writes through the bound repository share that transaction. Successful exit commits once; exceptions (including BaseException and commit failures) roll back. Connections are explicitly closed. Unbound repository methods retain their existing single-operation behavior.

`PaperLedger` wraps order + position + opening fill in one unit, and closing fill + closed position in another. Portfolio snapshots also read a consistent database view; `persist=False` uses a deferred read transaction compatible with the read-only dashboard repository. Nested units are explicitly rejected, avoiding implicit outer commits.

## Retry contract

- One persisted `signal_id` identifies one opening, across `create_order` and `open_position`. Same signal/risk decision returns the stored order/fill/position even if already closed.
- A different risk decision for an already used signal is rejected. Ambiguous or incomplete existing opening links fail without creating another opening.
- Closing reloads position state under the write lock. An already closed position returns unchanged. The first successful close wins, including when a retry supplies another price.
- Independent repository instances serialize concurrent requests using SQLite, without a process-global transaction connection.
- A run retry that generates a new signal is not deduplicated against previous signals. Persist/reuse the original signal and approval when retrying a specific order.

## Compatibility and migration

No schema, table, index or serialized model migration. Existing IDs and repository public save/load APIs remain valid. There is no database-wide uniqueness constraint on JSON signal IDs; the ledger API enforces retry semantics under the write lock. Direct low-level repository writes are not a substitute for a ledger transition. Historical corruption requires a separately authorized, evidence-based repair; this patch does not silently rewrite it.

Failure tests cover each write, commit failure, KeyboardInterrupt, concurrent retries, reconnect retries and subprocess `os._exit` recovery. SQLite's journal restores interrupted uncommitted work. This is not a hardware power-loss/disk-corruption recovery claim.
