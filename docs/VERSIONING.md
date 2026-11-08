# Version management

[English](VERSIONING.md) · [简体中文](VERSIONING.zh-CN.md)

The first managed GitHub Release is **0.2.0**. Earlier repository history used package version `0.1.0` without a published release; no historical release is invented or backdated.

## Version boundaries

Use `MAJOR.MINOR.PATCH` for the application and `vMAJOR.MINOR.PATCH` for Git tags. Before 1.0, minor releases may change workflows and must describe migrations; patches contain compatible fixes and documentation corrections. After 1.0, incompatible public CLI/data-contract changes require a major version. Data schemas keep separate identifiers; never silently migrate local databases just to match an application version.

`pyproject.toml` and `src/local_market_agent/__init__.py` must agree. Root README files display that same version. Each release has English and Chinese notes in `docs/releases/X.Y.Z[.zh-CN].md`, and an entry in `CHANGELOG.md`. Use absolute GitHub `blob/vX.Y.Z/` URLs in release notes so the same body works on the GitHub Release page. Keep an Unreleased section for work awaiting a release. A development PR may update Unreleased first; the release PR finalizes the bump and notes before tagging.

## Release procedure

1. Start from current `main` on a `codex/` branch. Select only reviewed work intended for this release; list material exclusions and unresolved limits.
2. Update both version declarations, both homepages, changelog, bilingual release notes, and implementation log. Describe any file or data migrations.
3. Run `ruff check .`, `pytest`, `python scripts/check_release.py --tag vX.Y.Z`, and `git diff --check` before opening the draft PR. Inspect staged files for credentials and local data.
4. A subagent reviews the final diff and actual results. Resolve findings; require green CI for the final head. The subagent marks ready and merges with an expected-head SHA. Do not use bots or bypass branch policies.
5. Fetch `main`; confirm the reviewed PR is merged and identify its exact merge SHA. Validate that commit, including `python scripts/check_release.py --tag vX.Y.Z`. Wait for that merge commit's CI to succeed.
6. Codex creates an annotated `vX.Y.Z` tag at that exact merge SHA, pushes only that tag, then publishes a GitHub Release from `docs/releases/X.Y.Z.md`. Use `gh release create vX.Y.Z --verify-tag --title "Local Market Agent X.Y.Z" --notes-file docs/releases/X.Y.Z.md`. Do not upload local databases, raw exports, credentials, or environment folders.
7. Verify the release URL, tag target, version declarations, and tag CI. Report the released version and important limitations.

CI runs the version consistency check on branches, PRs, and `v*` tags; tag builds also check the tag against the package version. Publishing is an explicit coordinator action, not an automatic bot merge or release. Tags are immutable: correct an already published release with a new patch version, never force-move its tag. Roll back code through a reviewed PR and publish a new version.
