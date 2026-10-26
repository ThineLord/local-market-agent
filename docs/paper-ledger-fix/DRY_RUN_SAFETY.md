# Dry-run state boundary

Phase 7 daily and sandbox dry-runs evaluate a consistent SQLite backup in a temporary directory. The source is opened with `mode=ro` for backup. All research, signal, risk, portfolio, manifest and run-record writes occur only in the disposable copy. New orders and historical settlement are both skipped. The copy is removed when evaluation ends, including exceptions.

The invariant is equality of canonical SHA-256 hashes of **all 12 source business tables**, ordered by primary key and including all row columns. Tests also compare derived cash and existing YES/NO holdings. Logs, files and filesystem metadata are outside this business-state hash.

## Preview artifacts and compatibility

Daily reports plus run-record and manifest JSON are saved under `<report_dir>/dry_run/`. Report metadata explicitly labels the temporary preview. Preview IDs are not registered in the source ledger; they cannot be replayed later against that source. Daily JSON retains summary/manifest evidence, not the whole temporary database or every intermediate research row.

Sandbox dry-runs use one copy for the entire batch so equity curves and in-run replay checks keep their references. Reports and summary are under dry_run subdirectories (including a custom summary directory). The temporary database is discarded after summary generation. Normal paper runs keep persisted records, reports and replay behavior.

Dry-run is a no-business-state-change guarantee, not a universal no-I/O flag. It may read configured public market inputs or call the configured research provider under existing settings and may write preview reports/raw input caches. No exchange/broker execution path is added or invoked. All tests here use fixtures, mocks or synthetic historical JSON with isolated SQLite; no paid providers, trading credentials or real orders were used. Creating a repository for a new CLI database path can still initialize an empty schema before the runner; no business rows are added by dry-run.

## Acceptance coverage

Populated YES/NO holdings with YES and NO settlement outcomes; approved fixture preview; manual/rejected/failed evaluation branches; repeat previews; unchanged source rows and cash; no ledger create/close calls; socket connection guard in populated-portfolio cases; normal historical settlement retained; sandbox equity/replay preserved.
