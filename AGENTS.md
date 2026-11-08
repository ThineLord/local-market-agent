# Repository Rules for Agents

This repository is paper-trading only.

- Run `ruff check .` and `pytest` before opening a PR.
- Never commit secrets, API keys, cookies, private keys, `.env`, local databases, browser data, or credential files.
- Do not add live trading, private trading endpoints, withdrawals, leverage, derivatives, shorting, geoblock bypasses, or direct LLM-to-order paths.
- Keep `REAL_MONEY_ENABLED=false`, `ALLOW_LIVE_ORDERS=false`, and `HUMAN_APPROVAL_REQUIRED=true` as defaults.
- All paper orders must reference a signal and an approved risk decision. Ordinary opens must use `PaperExecutionService` with per-intent approval; low-level simulation is explicit and fixture-only.
- Network tests must be optional and marked `network`.
- Keep fixtures deterministic and suitable for offline demos.
- Prefer small, coherent changes and document validation results in `docs/IMPLEMENTATION_LOG.md`.

## Documentation and coordination

- Codex organizes and manages this repository; subagents independently review and perform merges. Do not delegate work to bots or external bot bridges.
- Start with [English Agent guide](docs/agents/README.md) or [中文 Agent 指南](docs/agents/README.zh-CN.md). User instructions belong in the separate [English](docs/users/README.md) and [中文](docs/users/README.zh-CN.md) user guides.
- Follow [version management](docs/maintainers/VERSIONING.md) for future changes and releases. Keep the changelog, package version, bilingual homepages, and release notes consistent.
- Run `python scripts/check_release.py` in addition to Ruff and pytest before opening a PR; release checks also use `--tag vX.Y.Z`.
- Require review and green CI for the exact PR head before a subagent merges. Publish tags only for reviewed, merged commits; do not force-move published tags.
