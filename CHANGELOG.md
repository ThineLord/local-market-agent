# Changelog

Application releases use `vMAJOR.MINOR.PATCH`. See [version management](docs/VERSIONING.md) and [中文版本规则](docs/VERSIONING.zh-CN.md).

## Unreleased

- Make paper ledger opens/closes atomic and idempotent; isolate daily and sandbox dry-runs from the source database.

## 0.2.0 — 2026-11-09

- Added concise English and Chinese project homepages and separate bilingual user/Agent guides.
- Moved historical phase documents to `docs/archive/phases/` and the root project review to `docs/archive/reviews/`; added a documentation index and path migration guide.
- Established versioned release notes, package/readme/tag consistency checks in CI, and a PR release checklist.
- Fixed the mocked public-watchlist test clock so the fixture closing date cannot make offline validation depend on the real calendar; runtime checks are unchanged.
- Documented Codex coordination with subagent review and merge, without bot delegation.
- Kept paper-only runtime behavior and data paths unchanged. The ledger atomicity/dry-run draft PR #4 is not included.

[English release notes](docs/releases/0.2.0.md) · [中文发布说明](docs/releases/0.2.0.zh-CN.md)

## 0.1.0 — pre-release history

The repository previously declared `0.1.0` without a published GitHub Release. Existing research, risk checks, paper workflows, watchlist screening, and local dashboards form the baseline. Dated work and validation are preserved in [IMPLEMENTATION_LOG](docs/IMPLEMENTATION_LOG.md); this entry does not create a retrospective release or claim all historical findings are resolved.
