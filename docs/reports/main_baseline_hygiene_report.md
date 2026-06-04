# Main Baseline Hygiene Report

Date: 2026-06-05

## Scope

This report reviews the local and remote branch state for draft PR #1 without merging, force-pushing, rewriting history, or starting Phase 7 work.

PR: https://github.com/ThineLord/local-market-agent/pull/1

## Current Branch State

### Local Branches

`git branch -vv` shows only one local branch:

```text
* codex/phase0-6-local-market-agent 01072dc [origin/codex/phase0-6-local-market-agent] Update draft PR review CI notes
```

There is no local `main` branch.

### Remote Branches

`origin/main` points to:

```text
fe96ca2 chore: scaffold local market agent project
```

PR #1 head, `origin/codex/phase0-6-local-market-agent`, points to:

```text
01072dc Update draft PR review CI notes
```

The commit graph is linear:

```text
* 01072dc (HEAD -> codex/phase0-6-local-market-agent, origin/codex/phase0-6-local-market-agent, origin/HEAD) Update draft PR review CI notes
* a7d1955 Add draft PR review report
* 3c096d6 Add repo inspection and safety audit reports
* 2e8df51 Align implementation with original master plan
* 3e15f4d test: add offline workflow and safety coverage
* fe93c50 feat: add paper-only strategy risk ledger cli and dashboard
* 47e2bb2 feat: add schemas storage adapters and research pipeline
* fe96ca2 (origin/main) chore: scaffold local market agent project
```

GitHub currently reports the repository default branch as:

```text
codex/phase0-6-local-market-agent
```

That happened because the private repository was initially pushed from the feature branch. PR #1 still explicitly uses `main` as its base.

## PR #1 State

`gh pr view 1` reports:

- State: open
- Draft: true
- Base: `main`
- Head: `codex/phase0-6-local-market-agent`
- Merge state: `CLEAN`
- Latest PR and feature-branch CI checks: success

## Why `main` CI Failed Historically

The standalone `main` push workflow failed on commit `fe96ca2` because that scaffold commit contains `pyproject.toml` and CI configuration, but does not yet contain `src/`.

GitHub Actions failed during editable package install with:

```text
error: error in 'egg_base' option: 'src' does not exist or is not a directory
```

This is expected for the scaffold-only base branch and does not mean the Phase 0-6 PR branch is broken.

## Does This Affect PR #1 Correctness?

No P0/P1 correctness issue was found.

PR #1 is based on `main`, includes the implementation that adds `src/`, and its own CI checks pass. The failed `main` run is a historical base-branch run against an intentionally incomplete scaffold commit.

The main practical impact is review hygiene:

- Reviewers may notice a failed historical `main` run.
- The repository default branch is currently the feature branch, not `main`.
- `origin/main` will become healthy naturally after PR #1 is merged, because the merge result will include `src/` and the rest of the Phase 0-6 implementation.

## Recommended Handling

Do not rewrite `origin/main`.

Do not force-push.

Do not merge PR #1 yet.

Do not close or recreate PR #1.

The least disruptive path is:

1. Keep PR #1 open as a draft for manual review.
2. Accept that the standalone `main` CI failure is historical scaffold-only noise.
3. After manual review, merge PR #1 normally when ready.
4. After merge, confirm `main` CI passes on the merged implementation.
5. Set the repository default branch to `main` after merge if it still points to the feature branch.

No non-destructive correction to `origin/main` is needed before manual review. Updating `origin/main` early would either duplicate the PR result or reduce the usefulness of PR #1 as the review vehicle.

## Validation

Validation was run on the current PR branch after creating this report:

- `.venv/bin/ruff check .`: passed
- `.venv/bin/pytest`: 26 passed, 1 optional network test skipped
