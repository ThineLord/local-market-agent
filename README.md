# Local Market Agent

[English](README.md) · [简体中文](README.zh-CN.md)

**For users:** start with the [user guide](docs/users/README.md).

**For agents:** read [AGENTS.md](AGENTS.md), then the [Agent guide](docs/agents/README.md).

Local Market Agent connects **public market snapshots → research briefs → risk checks → simulated trades → local reports**. It is an offline-first Python workspace for inspecting evidence and testing paper workflows with deterministic fixtures and a local dashboard.

**Paper trading only.** This is an experimental research tool, not a live trading service. Demo results do not establish profitability or production readiness.

## Start locally

Use Python **3.11 or newer**. From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
lma watchlist-screen --as-of 2026-06-05T00:02:00Z
python ui/server.py
```

Open **http://127.0.0.1:8502/#watchlist/screening**. This synthetic example runs without an API key or market-data request. The fixed time matches the historical fixtures; current-time checks correctly mark old data stale. Use `python ui/server.py --port 8503` if the port is occupied.

## Three steps

1. **Inspect a watchlist.** Compare snapshots, evidence gaps, and blocking checks.
2. **Review research and risk.** Use the CLI workflows in the user guide; an LLM can draft research only.
3. **Read the audit trail.** Inspect saved reports and simulated records in the local, read-only dashboard.

## Project layout

```text
src/local_market_agent/   Python package and CLI
ui/                      local dashboard and Streamlit interface
data/fixtures/           committed deterministic examples
data/                    ignored local databases and generated outputs
tests/                   offline tests; optional network tests
scripts/                 release checks and local research utilities
docs/users/              English and Chinese user guides
docs/agents/             English and Chinese Agent guides
docs/releases/           notes for each published version
docs/archive/            historical phase plans and reviews
```

## Documentation and versions

- [User guide](docs/users/README.md) · [中文用户指南](docs/users/README.zh-CN.md)
- [Agent guide](docs/agents/README.md) · [中文 Agent 指南](docs/agents/README.zh-CN.md)
- [Documentation index](docs/README.md) · [Safety and risk](docs/SAFETY_AND_RISK.md)
- [Changelog](CHANGELOG.md) · [Version policy](docs/VERSIONING.md)
- [0.2.0 release notes](docs/releases/0.2.0.md) · [GitHub Releases](https://github.com/ThineLord/local-market-agent/releases)

The application version is **0.2.0**. Future releases use matching package versions, `vX.Y.Z` tags, release notes, and reviewed PRs. Codex coordinates the work; subagents review and merge. No bot delegation is used.

Defaults remain `REAL_MONEY_ENABLED=false`, `ALLOW_LIVE_ORDERS=false`, and `HUMAN_APPROVAL_REQUIRED=true`. Every paper order must reference a signal and an approved risk decision. See the release notes for known limitations and excluded work.
