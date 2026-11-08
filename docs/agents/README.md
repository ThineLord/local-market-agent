# Agent guide

[English](README.md) · [简体中文](README.zh-CN.md) · [Project home](../../README.md)

Read the root [AGENTS.md](../../AGENTS.md) first. Codex owns coordination, repository organization, implementation, and release preparation. Subagents independently review the final change and perform the merge after validation. Do not delegate to bots or external bot bridges. A subagent review is not automatically a GitHub APPROVED review; report the actual review mechanism.

## Start with the current state

1. Inspect the working tree, branch, remote default branch, open PRs, and latest release. Preserve unrelated work and local data; use an isolated checkout when necessary.
2. Read the [user guide](../users/README.md), [safety rules](../reference/SAFETY_AND_RISK.md), and [version policy](../maintainers/VERSIONING.md).
3. Use historical [phase documents](../archive/README.md) and [reports](../reports) as dated evidence. The [implementation log](../IMPLEMENTATION_LOG.md) preserves chronology, not a blanket acceptance claim.
4. Scope a coherent change on a `codex/` branch. Do not silently combine unrelated PRs or close them as housekeeping.

## Repository map

| Location | Purpose |
| --- | --- |
| `src/local_market_agent/` | Runtime package, adapters, research, risk, paper ledger, CLI |
| `ui/` | Loopback dashboard, static assets, Streamlit interface |
| `tests/` | Deterministic offline coverage; explicitly optional network tests |
| `data/fixtures/` | Committed synthetic examples and validation cases |
| `data/` | Local databases and generated data; most runtime outputs are ignored |
| `scripts/local_only/` | Research utilities; inspect their network and output behavior before running |
| `docs/users/`, `docs/agents/` | Separate English and Chinese entry guides |
| `docs/releases/` | Versioned release notes |
| `docs/reference/`, `docs/maintainers/` | Current technical protocols and version management |
| `docs/archive/`, `docs/reports/` | Fixed historical links and legacy report compatibility |

Keep runtime paths stable unless migration is explicitly part of the change. Do not commit `.env`, databases, cookies, keys, browser data, or raw private exports. `.env.example` contains placeholders only; never replace them with credentials.

## Safety requirements

This repository is paper-trading only. Never add live orders, private trading endpoints, withdrawals, leverage, derivatives, shorting, geoblock bypasses, or direct LLM-to-order paths. Preserve defaults:

```text
REAL_MONEY_ENABLED=false
ALLOW_LIVE_ORDERS=false
HUMAN_APPROVAL_REQUIRED=true
```

Every paper order must reference a signal and an approved risk decision. Model output is research, not order authorization. Keep fixtures deterministic. Network tests must be optional and marked `network`; do not enable network collection or paid providers merely to check documentation.

## Validate, review, merge

From an activated Python 3.11+ environment at repository root:

```bash
ruff check .
pytest
python scripts/check_release.py
git diff --check
```

Record actual results and limitations in `docs/IMPLEMENTATION_LOG.md` before opening a draft PR. Add focused checks only when the changed behavior warrants them. Review relative links and both language variants when moving docs. Keep release versions, notes, and the changelog consistent.

The reviewing subagent examines the final diff, validation evidence, and CI for the exact head commit. Resolve findings before it marks the PR ready and merges with an expected-head guard. If branch policy requires an independent GitHub approval that the available account cannot supply, report that blocker; do not bypass policy. Never claim an advisory review is a GitHub approval.

After merge, Codex verifies the merged commit, publishes the version tag and GitHub Release according to the [version policy](../maintainers/VERSIONING.md), and checks the resulting links. Merge authority does not authorize unrelated PRs, data collection, or real trades.

## Racing research boundary

Read [the racing protocol](../reference/HORSE_REPLAY.md) before importing horse records. Keep user tickets/snapshots in ignored local paths, preserve original source and import times, and never infer a historical recommendation from a result. The current module has no validated horse probability model and no order adapter: all research decisions are NO BET. An availability review is evidence-bound manual review, not proof supplied by a URL or self-filled timestamp.

## Repository presentation

Keep the root focused on code, tooling and `README.md`/`AGENTS.md`; the Chinese homepage is `docs/README.zh-CN.md` and changelog is `docs/CHANGELOG.md`. New current protocols belong in `docs/reference/`; superseded one-time reports should link to an immutable release snapshot. Do not remove runtime inputs just because they look like reports. Generated legacy reports remain ignored.

README images are actual 1440px dashboard captures in `docs/assets/`, with light appearance and motion paused. Reproduce them with `lma watchlist-screen --as-of 2026-06-05T00:02:00Z`, `python scripts/demo_workflow.py --output data/reports/readme-demo`, then `LMA_DB_PATH=data/reports/readme-demo/demo.sqlite python ui/server.py --port 8512`. Capture `#watchlist/screening` at 1440×1000 and `#audit` at 1440×850. Use a new demo output directory on reruns. Use synthetic fixtures only; never publish personal transactions, account paths, keys or browser data. Both language homepages share the same two images; keep the audit image collapsed.
