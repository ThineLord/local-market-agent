# Changelog

Application releases use `vMAJOR.MINOR.PATCH`. See [version management](maintainers/VERSIONING.md) and [中文版本规则](maintainers/VERSIONING.zh-CN.md).

## Unreleased

- Keep an incomplete Hong Kong racing meeting unknown as a summary: pool hit rates are omitted until every ticket in that pool is settled, while settled outcomes and win counts remain.
- An entitlement curve with a later unknown race keeps the settled prefix, records `stopped_at_race`, and does not fill the gap with zero or draw that prefix as a finished meeting. Research decisions remain NO_BET.

## 0.5.1 — 2026-11-09

- Simplify the repository entry: move the Chinese homepage and changelog under docs, and group current technical and maintenance references.
- Replace superseded plans and one-time reports with fixed v0.5.0 archive links; preserve the historical report still read by the category-balance command and ignore new generated reports.
- Refresh bilingual READMEs with two real dashboard screenshots using only synthetic data; keep the secondary audit image collapsed.
- Preserve runtime paths, fixtures, safety defaults and local databases. Update release checks for the new documentation locations.

[English release notes](releases/0.5.1.md) · [中文发布说明](releases/0.5.1.zh-CN.md)

## 0.5.0 — 2026-11-09

- Add isolated Hong Kong historical replay with bounded public HKJC results/declarations, complete-field and source-chronology verification.
- Separate provisional returns, official entitlements, redeemed cash and historical recommendations; report WIN/PLACE metrics and race-close drawdown without inventing backtest evidence.
- Add source-bound T−10/T−3 transcription audits, descriptive full-field comparisons and explicit NO BET blockers. No validated racing probability model or order path is claimed.
- Add a parallel read-only HKD dashboard, bilingual guides and deterministic synthetic import; preserve existing markets, safety defaults and local databases.

[English release notes](releases/0.5.0.md) · [中文发布说明](releases/0.5.0.zh-CN.md)

## 0.4.0 — 2026-11-09

- Add bounded public NBA/NFL depth discovery using best-quote USD capacity and unchanged risk gates.
- Add a frozen NBA Elo probability model, checksummed 120-source history and chronological holdout validation with conservative residual stress checks.
- Bind current NBA research packets to exact pregame events, contract rules and reproducible source files; recheck game start, source age, model validation and net edge during preparation, approval and execution.
- Correct NO-position valuation by converting explicit YES market marks to the held NO outcome; preserve own-cost fallback and document historical derived-record replay.
- Keep public-source order approval explicit and all trading simulated. No database schema migration.

[English release notes](releases/0.4.0.md) · [中文发布说明](releases/0.4.0.zh-CN.md)

## 0.3.1 — 2026-11-09

- Fix current Kalshi depth normalization using conservative best-quote buy capacity in USD; distinguish missing versus genuinely insufficient liquidity and correct legacy cent units.
- Separate source integrity, exact research-review validation, strategy readiness, portfolio risk and order approval; show actual veto reasons and avoid equity-baseline writes on rejected preparation.
- Add a bounded opt-in public Kalshi/NWS collector with preserved receipts and an observation-only brief; no invented probability, review, order or settlement.

[English release notes](releases/0.3.1.md) · [中文发布说明](releases/0.3.1.zh-CN.md)

## 0.3.0 — 2026-11-09

- Add source-bound evidence packets, explicit research/settlement review, atomic settlement receipts, an isolated CLI demo and read-only next-step guidance.

- Seal run and execution artifact contents, verify semantic links on replay, and return distinct CLI failure/rejection/pending statuses.

- Require content-bound, expiring per-intent approvals across daily and legacy CLI execution, with atomic rechecks and fixture-only simulation receipts.

- Share fail-closed screening/execution preflight and persist UTC equity baselines and peak drawdown; preserve real observation times and research vetoes.

- Make paper ledger opens/closes atomic and idempotent; isolate daily and sandbox dry-runs from the source database.

[English release notes](releases/0.3.0.md) · [中文发布说明](releases/0.3.0.zh-CN.md)

## 0.2.0 — 2026-11-09

- Added concise English and Chinese project homepages and separate bilingual user/Agent guides.
- Moved historical phase documents to `docs/archive/phases/` and the root project review to `docs/archive/reviews/`; added a documentation index and path migration guide.
- Established versioned release notes, package/readme/tag consistency checks in CI, and a PR release checklist.
- Fixed the mocked public-watchlist test clock so the fixture closing date cannot make offline validation depend on the real calendar; runtime checks are unchanged.
- Documented Codex coordination with subagent review and merge, without bot delegation.
- Kept paper-only runtime behavior and data paths unchanged. The ledger atomicity/dry-run draft PR #4 is not included.

[English release notes](releases/0.2.0.md) · [中文发布说明](releases/0.2.0.zh-CN.md)

## 0.1.0 — pre-release history

The repository previously declared `0.1.0` without a published GitHub Release. Existing research, risk checks, paper workflows, watchlist screening, and local dashboards form the baseline. Dated work and validation are preserved in [IMPLEMENTATION_LOG](IMPLEMENTATION_LOG.md); this entry does not create a retrospective release or claim all historical findings are resolved.
