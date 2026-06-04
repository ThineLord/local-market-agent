# Phase 7 PR-3 - Daily Report Generator

## Scope

PR-3 adds a local Markdown report generator for Phase 7 paper operations. It
summarizes existing local SQLite data after paper portfolio and risk gate
records have already been produced.

Included:

- `Phase7DailyReportGenerator`
- `Phase7DailyReportArtifact`
- Markdown artifact generation
- Portfolio snapshot summary
- Open position table
- Paper order and fill tables
- Realized and unrealized PnL summary
- Exposure summary
- Risk gate decision summary and rejection/halt reasons
- Operational warnings

Out of scope:

- Broker APIs
- Live trading code
- Scheduler or continuous runner
- Dashboard changes
- Strategy changes
- New risk gates
- Paper ledger rewrite
- Risk gate evaluator rewrite
- Phase 8 broker integration

## Usage

```python
from local_market_agent.reporting import Phase7DailyReportGenerator
from local_market_agent.storage import SQLiteRepository

repo = SQLiteRepository("data/local_market_agent.sqlite")
artifact = Phase7DailyReportGenerator(repo).generate()
print(artifact.path)
```

By default, the report is written to:

```text
data/reports/phase7_daily_report_YYYY-MM-DD.md
```

Callers may pass an explicit `output_path` for tests or ad hoc local review.

## Report Sections

- Run metadata
- Portfolio snapshot summary
- Open positions
- Paper orders
- Paper fills
- PnL
- Exposure
- Risk gate decisions
- Risk gate rejection and halt reasons
- Operational warnings
- Safety notes

## Data Sources

The generator reads existing local repository records:

- `portfolio_snapshots`
- `positions`
- `paper_orders`
- `paper_fills`
- `risk_gate_decisions`

It does not create orders, fills, risk decisions, or portfolio snapshots.

## Safety Invariants

- Markdown is generated from local SQLite data only.
- No broker adapter, credential, private trading endpoint, withdrawal path,
  leverage path, scheduler, dashboard action, continuous runner, strategy
  change, new risk gate, or direct LLM-to-order path is introduced.
- The report includes explicit paper-only safety notes.
