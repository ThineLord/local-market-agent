# Repository Inspection Report

Date: 2026-06-05

## Summary

- Branch: `codex/phase0-6-local-market-agent`
- Remote at inspection time: none configured (`git remote -v` returned no output).
- Latest commits:
  - `2e8df51 Align implementation with original master plan`
  - `3e15f4d test: add offline workflow and safety coverage`
  - `fe93c50 feat: add paper-only strategy risk ledger cli and dashboard`
  - `47e2bb2 feat: add schemas storage adapters and research pipeline`
  - `fe96ca2 chore: scaffold local market agent project`
- Main source modules:
  - `src/local_market_agent/schemas/models.py`
  - `src/local_market_agent/storage/repository.py`
  - `src/local_market_agent/llm/providers.py`
  - `src/local_market_agent/adapters/*.py`
  - `src/local_market_agent/agents/research.py`
  - `src/local_market_agent/strategy/prediction_market.py`
  - `src/local_market_agent/risk/engine.py`
  - `src/local_market_agent/paper/ledger.py`
  - `src/local_market_agent/reporting/daily.py`
  - `src/local_market_agent/cli.py`
  - `ui/app.py`
- Tests present:
  - Adapter, CLI, LLM, network-marker, paper ledger, research, schema, storage, and strategy/risk tests under `tests/`.
- Docs present:
  - Project docs, original master plan, reconstructed master plan, alignment report, implementation log, safety/risk docs, and this inspection report.
- Generated/local ignored artifacts observed:
  - `.DS_Store`, `.pytest_cache/`, `.ruff_cache/`, `.venv/`, local SQLite DBs under `data/`, generated research brief markdown under `data/research_briefs/`, generated report exports under `data/reports/`, `src/local_market_agent.egg-info/`, and Python `__pycache__/` directories.
- Python command note:
  - The requested `python - <<'PY' ... PY` failed because `python` is not on PATH in this shell.
  - The equivalent project-local command `.venv/bin/python - <<'PY' ... PY` succeeded and is recorded below.

## Raw Command Outputs

### `pwd`

```text
/Users/hanzhiyou/Documents/Local Market Agent
```

### `git status --short --branch`

```text
## codex/phase0-6-local-market-agent
```

### `git log --oneline --graph --decorate --all -n 20`

```text
* 2e8df51 (HEAD -> codex/phase0-6-local-market-agent) Align implementation with original master plan
* 3e15f4d test: add offline workflow and safety coverage
* fe93c50 feat: add paper-only strategy risk ledger cli and dashboard
* 47e2bb2 feat: add schemas storage adapters and research pipeline
* fe96ca2 chore: scaffold local market agent project
```

### `find . -maxdepth 3 -type f | sort`

```text
./.DS_Store
./.env.example
./.git/COMMIT_EDITMSG
./.git/HEAD
./.git/config
./.git/description
./.git/hooks/applypatch-msg.sample
./.git/hooks/commit-msg.sample
./.git/hooks/fsmonitor-watchman.sample
./.git/hooks/post-update.sample
./.git/hooks/pre-applypatch.sample
./.git/hooks/pre-commit.sample
./.git/hooks/pre-merge-commit.sample
./.git/hooks/pre-push.sample
./.git/hooks/pre-rebase.sample
./.git/hooks/pre-receive.sample
./.git/hooks/prepare-commit-msg.sample
./.git/hooks/push-to-checkout.sample
./.git/hooks/sendemail-validate.sample
./.git/hooks/update.sample
./.git/index
./.git/info/exclude
./.git/logs/HEAD
./.github/workflows/ci.yml
./.gitignore
./.pytest_cache/.gitignore
./.pytest_cache/CACHEDIR.TAG
./.pytest_cache/README.md
./.ruff_cache/.gitignore
./.ruff_cache/0.15.16/1432792828538236518
./.ruff_cache/0.15.16/1654583320260662237
./.ruff_cache/0.15.16/8658683689811766704
./.ruff_cache/CACHEDIR.TAG
./.venv/.gitignore
./.venv/bin/Activate.ps1
./.venv/bin/activate
./.venv/bin/activate.csh
./.venv/bin/activate.fish
./.venv/bin/curl-cffi
./.venv/bin/f2py
./.venv/bin/httpx
./.venv/bin/idna
./.venv/bin/jsonschema
./.venv/bin/lma
./.venv/bin/markdown-it
./.venv/bin/normalizer
./.venv/bin/numpy-config
./.venv/bin/pip
./.venv/bin/pip3
./.venv/bin/pip3.13
./.venv/bin/pwiz
./.venv/bin/py.test
./.venv/bin/pygmentize
./.venv/bin/pytest
./.venv/bin/ruff
./.venv/bin/sample
./.venv/bin/streamlit
./.venv/bin/typer
./.venv/bin/uvicorn
./.venv/bin/websockets
./.venv/pyvenv.cfg
./AGENTS.md
./README.md
./data/alignment_cli_1780600835.sqlite
./data/fixtures/demo_evidence.json
./data/fixtures/demo_market.json
./data/local_market_agent.sqlite
./data/raw_cache/.gitkeep
./data/reports/.gitkeep
./data/reports/paper_orders.csv
./data/reports/paper_orders.jsonl
./data/research_briefs/.gitkeep
./data/research_briefs/brief_08ff7cf985814028bd202c0cd685fa24.md
./data/research_briefs/brief_21b03d649bda4a3aa4c8e82710b3b172.md
./data/research_briefs/brief_40ed976c408c48a2909a61d80e2983e4.md
./data/research_briefs/brief_57aaf1e82e3749e2b4d3ef16ae2e9f8c.md
./data/research_briefs/brief_73cdd996ffac4292a6aecd0571a5e8b7.md
./data/research_briefs/brief_7facdcd4494549b49631a50876231b6a.md
./data/research_briefs/brief_9dc03381ef304d918737d8f83551f104.md
./data/research_briefs/brief_a6d8231b85a34d598490d6da28c405b1.md
./data/validation_cli_1780599789.sqlite
./docs/DATA_SOURCES.md
./docs/IMPLEMENTATION_LOG.md
./docs/LIVE_TRADING_CHECKLIST.md
./docs/LOCAL_MARKET_AGENT_MASTER_PLAN.md
./docs/LOCAL_MARKET_AGENT_MASTER_PLAN_ORIGINAL.md
./docs/MARKET_SELECTION.md
./docs/MASTER_PLAN_ALIGNMENT_REPORT.md
./docs/PROJECT_SPEC.md
./docs/SAFETY_AND_RISK.md
./pyproject.toml
./src/local_market_agent.egg-info/PKG-INFO
./src/local_market_agent.egg-info/SOURCES.txt
./src/local_market_agent.egg-info/dependency_links.txt
./src/local_market_agent.egg-info/entry_points.txt
./src/local_market_agent.egg-info/requires.txt
./src/local_market_agent.egg-info/top_level.txt
./src/local_market_agent/__init__.py
./src/local_market_agent/cli.py
./tests/__pycache__/conftest.cpython-313-pytest-9.0.3.pyc
./tests/__pycache__/test_adapters.cpython-313-pytest-9.0.3.pyc
./tests/__pycache__/test_cli.cpython-313-pytest-9.0.3.pyc
./tests/__pycache__/test_llm.cpython-313-pytest-9.0.3.pyc
./tests/__pycache__/test_network_adapters.cpython-313-pytest-9.0.3.pyc
./tests/__pycache__/test_paper_ledger.cpython-313-pytest-9.0.3.pyc
./tests/__pycache__/test_research.cpython-313-pytest-9.0.3.pyc
./tests/__pycache__/test_schemas.cpython-313-pytest-9.0.3.pyc
./tests/__pycache__/test_storage.cpython-313-pytest-9.0.3.pyc
./tests/__pycache__/test_strategy_risk.cpython-313-pytest-9.0.3.pyc
./tests/conftest.py
./tests/test_adapters.py
./tests/test_cli.py
./tests/test_llm.py
./tests/test_network_adapters.py
./tests/test_paper_ledger.py
./tests/test_research.py
./tests/test_schemas.py
./tests/test_storage.py
./tests/test_strategy_risk.py
./ui/app.py
```

### `find src tests ui docs -type f | sort`

```text
docs/DATA_SOURCES.md
docs/IMPLEMENTATION_LOG.md
docs/LIVE_TRADING_CHECKLIST.md
docs/LOCAL_MARKET_AGENT_MASTER_PLAN.md
docs/LOCAL_MARKET_AGENT_MASTER_PLAN_ORIGINAL.md
docs/MARKET_SELECTION.md
docs/MASTER_PLAN_ALIGNMENT_REPORT.md
docs/PROJECT_SPEC.md
docs/SAFETY_AND_RISK.md
src/local_market_agent.egg-info/PKG-INFO
src/local_market_agent.egg-info/SOURCES.txt
src/local_market_agent.egg-info/dependency_links.txt
src/local_market_agent.egg-info/entry_points.txt
src/local_market_agent.egg-info/requires.txt
src/local_market_agent.egg-info/top_level.txt
src/local_market_agent/__init__.py
src/local_market_agent/__pycache__/__init__.cpython-313.pyc
src/local_market_agent/__pycache__/cli.cpython-313.pyc
src/local_market_agent/adapters/__init__.py
src/local_market_agent/adapters/__pycache__/__init__.cpython-313.pyc
src/local_market_agent/adapters/__pycache__/base.cpython-313.pyc
src/local_market_agent/adapters/__pycache__/fixture.cpython-313.pyc
src/local_market_agent/adapters/__pycache__/gdelt.cpython-313.pyc
src/local_market_agent/adapters/__pycache__/kalshi.cpython-313.pyc
src/local_market_agent/adapters/__pycache__/polymarket.cpython-313.pyc
src/local_market_agent/adapters/__pycache__/sec_edgar.cpython-313.pyc
src/local_market_agent/adapters/__pycache__/yfinance_adapter.cpython-313.pyc
src/local_market_agent/adapters/base.py
src/local_market_agent/adapters/fixture.py
src/local_market_agent/adapters/gdelt.py
src/local_market_agent/adapters/kalshi.py
src/local_market_agent/adapters/polymarket.py
src/local_market_agent/adapters/sec_edgar.py
src/local_market_agent/adapters/yfinance_adapter.py
src/local_market_agent/agents/__init__.py
src/local_market_agent/agents/__pycache__/__init__.cpython-313.pyc
src/local_market_agent/agents/__pycache__/research.cpython-313.pyc
src/local_market_agent/agents/research.py
src/local_market_agent/backtest/__init__.py
src/local_market_agent/cli.py
src/local_market_agent/config/__init__.py
src/local_market_agent/config/__pycache__/__init__.cpython-313.pyc
src/local_market_agent/config/__pycache__/settings.cpython-313.pyc
src/local_market_agent/config/settings.py
src/local_market_agent/eval/__init__.py
src/local_market_agent/llm/__init__.py
src/local_market_agent/llm/__pycache__/__init__.cpython-313.pyc
src/local_market_agent/llm/__pycache__/providers.cpython-313.pyc
src/local_market_agent/llm/providers.py
src/local_market_agent/paper/__init__.py
src/local_market_agent/paper/__pycache__/__init__.cpython-313.pyc
src/local_market_agent/paper/__pycache__/ledger.cpython-313.pyc
src/local_market_agent/paper/ledger.py
src/local_market_agent/reporting/__init__.py
src/local_market_agent/reporting/__pycache__/__init__.cpython-313.pyc
src/local_market_agent/reporting/__pycache__/daily.cpython-313.pyc
src/local_market_agent/reporting/daily.py
src/local_market_agent/risk/__init__.py
src/local_market_agent/risk/__pycache__/__init__.cpython-313.pyc
src/local_market_agent/risk/__pycache__/engine.cpython-313.pyc
src/local_market_agent/risk/engine.py
src/local_market_agent/schemas/__init__.py
src/local_market_agent/schemas/__pycache__/__init__.cpython-313.pyc
src/local_market_agent/schemas/__pycache__/models.cpython-313.pyc
src/local_market_agent/schemas/models.py
src/local_market_agent/storage/__init__.py
src/local_market_agent/storage/__pycache__/__init__.cpython-313.pyc
src/local_market_agent/storage/__pycache__/repository.cpython-313.pyc
src/local_market_agent/storage/repository.py
src/local_market_agent/strategy/__init__.py
src/local_market_agent/strategy/__pycache__/__init__.cpython-313.pyc
src/local_market_agent/strategy/__pycache__/prediction_market.cpython-313.pyc
src/local_market_agent/strategy/prediction_market.py
tests/__pycache__/conftest.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_adapters.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_cli.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_llm.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_network_adapters.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_paper_ledger.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_research.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_schemas.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_storage.cpython-313-pytest-9.0.3.pyc
tests/__pycache__/test_strategy_risk.cpython-313.pyc
tests/conftest.py
tests/test_adapters.py
tests/test_cli.py
tests/test_llm.py
tests/test_network_adapters.py
tests/test_paper_ledger.py
tests/test_research.py
tests/test_schemas.py
tests/test_storage.py
tests/test_strategy_risk.py
ui/app.py
```

### Requested Python inventory command

Command:

```bash
python - <<'PY'
from pathlib import Path
for root in ["src", "tests", "ui"]:
    files = sorted(Path(root).rglob("*.py"))
    print(root, len(files))
    for p in files:
        print(" ", p)
PY
```

Output:

```text
zsh:1: command not found: python
```

### Project-local equivalent: `.venv/bin/python - <<'PY' ... PY`

```text
src 30
  src/local_market_agent/__init__.py
  src/local_market_agent/adapters/__init__.py
  src/local_market_agent/adapters/base.py
  src/local_market_agent/adapters/fixture.py
  src/local_market_agent/adapters/gdelt.py
  src/local_market_agent/adapters/kalshi.py
  src/local_market_agent/adapters/polymarket.py
  src/local_market_agent/adapters/sec_edgar.py
  src/local_market_agent/adapters/yfinance_adapter.py
  src/local_market_agent/agents/__init__.py
  src/local_market_agent/agents/research.py
  src/local_market_agent/backtest/__init__.py
  src/local_market_agent/cli.py
  src/local_market_agent/config/__init__.py
  src/local_market_agent/config/settings.py
  src/local_market_agent/eval/__init__.py
  src/local_market_agent/llm/__init__.py
  src/local_market_agent/llm/providers.py
  src/local_market_agent/paper/__init__.py
  src/local_market_agent/paper/ledger.py
  src/local_market_agent/reporting/__init__.py
  src/local_market_agent/reporting/daily.py
  src/local_market_agent/risk/__init__.py
  src/local_market_agent/risk/engine.py
  src/local_market_agent/schemas/__init__.py
  src/local_market_agent/schemas/models.py
  src/local_market_agent/storage/__init__.py
  src/local_market_agent/storage/repository.py
  src/local_market_agent/strategy/__init__.py
  src/local_market_agent/strategy/prediction_market.py
tests 10
  tests/conftest.py
  tests/test_adapters.py
  tests/test_cli.py
  tests/test_llm.py
  tests/test_network_adapters.py
  tests/test_paper_ledger.py
  tests/test_research.py
  tests/test_schemas.py
  tests/test_storage.py
  tests/test_strategy_risk.py
ui 1
  ui/app.py
```

### `git remote -v`

```text

```

### `git status --ignored --short`

```text
!! .DS_Store
!! .pytest_cache/
!! .ruff_cache/
!! .venv/
!! data/alignment_cli_1780600835.sqlite
!! data/local_market_agent.sqlite
!! data/reports/paper_orders.csv
!! data/reports/paper_orders.jsonl
!! data/research_briefs/brief_08ff7cf985814028bd202c0cd685fa24.md
!! data/research_briefs/brief_21b03d649bda4a3aa4c8e82710b3b172.md
!! data/research_briefs/brief_40ed976c408c48a2909a61d80e2983e4.md
!! data/research_briefs/brief_57aaf1e82e3749e2b4d3ef16ae2e9f8c.md
!! data/research_briefs/brief_73cdd996ffac4292a6aecd0571a5e8b7.md
!! data/research_briefs/brief_7facdcd4494549b49631a50876231b6a.md
!! data/research_briefs/brief_9dc03381ef304d918737d8f83551f104.md
!! data/validation_cli_1780599789.sqlite
!! src/local_market_agent.egg-info/
!! src/local_market_agent/__pycache__/
!! src/local_market_agent/adapters/__pycache__/
!! src/local_market_agent/agents/__pycache__/
!! src/local_market_agent/config/__pycache__/
!! src/local_market_agent/llm/__pycache__/
!! src/local_market_agent/paper/__pycache__/
!! src/local_market_agent/reporting/__pycache__/
!! src/local_market_agent/risk/__pycache__/
!! src/local_market_agent/schemas/__pycache__/
!! src/local_market_agent/storage/__pycache__/
!! src/local_market_agent/strategy/__pycache__/
!! tests/__pycache__/
```

## Validation Results

### `.venv/bin/ruff check .`

```text
All checks passed!
```

### `.venv/bin/pytest`

```text
collected 27 items
26 passed, 1 skipped in 0.08s
```

### Offline CLI chain

Command path used: `.venv/bin/lma`.

```text
{"db_path": "data/review_cli_1780601265.sqlite", "evidence_items": 3, "market_id": "demo-election-turnout-2026", "snapshot_id": "snapshot-demo-election-turnout-2026"}
{"brief_id": "brief_3ef921465b594ced9e89b0be97d962b9", "confidence": 0.7438, "evidence_quality": 0.6564, "market_id": "demo-election-turnout-2026", "recommended_action": "paper_buy_yes"}
{"reasons": ["Approved for paper trading only; live orders remain disabled."], "risk_decision_id": "risk_e4d457c883bb4b2f9d6381e407a12119", "risk_status": "approved", "signal_action": "paper_buy_yes", "signal_id": "signal_0fe447a18b0c4f8e946a0afc782a91b1"}
{"fill_price": 0.511, "order_id": "paper_order_01046cb57aed4a55b8ce52ed3dbf1352", "quantity": 195.69471624, "status": "paper_order_filled"}
{"csv": "data/reports/paper_orders.csv", "jsonl": "data/reports/paper_orders.jsonl", "open_positions": 1, "orders": 1, "realized_pnl": 0.0, "report_id": "performance_267a3df167274cb3aeadd571913752ec", "unrealized_pnl": -0.1}
```
