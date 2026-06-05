from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from local_market_agent.adapters import FixtureAdapter
from local_market_agent.agents import Reporter, ResearchBriefGenerator
from local_market_agent.config import Settings, load_settings
from local_market_agent.llm import MockLLMProvider, OpenAICompatibleProvider
from local_market_agent.operations import Phase7DailyRunner, Phase7ReplayService
from local_market_agent.paper import PaperLedger
from local_market_agent.reporting import DailyReportService
from local_market_agent.risk import RiskEngine
from local_market_agent.schemas import MarketSnapshot, ResearchBrief, Signal
from local_market_agent.storage import SQLiteRepository
from local_market_agent.strategy import PredictionMarketEdgeStrategy

app = typer.Typer(help="Local Market Agent: offline-first research and paper trading.")


def _settings(db: Path | None) -> Settings:
    settings = load_settings()
    if db is None:
        return settings
    return Settings(
        db_path=db,
        raw_cache_dir=settings.raw_cache_dir,
        research_brief_dir=settings.research_brief_dir,
        real_money_enabled=settings.real_money_enabled,
        allow_live_orders=settings.allow_live_orders,
        human_approval_required=settings.human_approval_required,
        llm_provider=settings.llm_provider,
        openai_compatible_base_url=settings.openai_compatible_base_url,
        openai_compatible_model=settings.openai_compatible_model,
        openai_compatible_api_key=settings.openai_compatible_api_key,
        sec_user_agent=settings.sec_user_agent,
        run_network_tests=settings.run_network_tests,
        risk=settings.risk,
        risk_gates=settings.risk_gates,
    )


def _repository(settings: Settings) -> SQLiteRepository:
    return SQLiteRepository(settings.db_path)


def _provider(settings: Settings):
    if settings.llm_provider == "openai-compatible":
        return OpenAICompatibleProvider(
            base_url=settings.openai_compatible_base_url,
            api_key=settings.openai_compatible_api_key,
            model=settings.openai_compatible_model,
        )
    return MockLLMProvider()


def _latest_snapshot(repo: SQLiteRepository, market_id: str | None = None) -> MarketSnapshot:
    snapshots = repo.list_market_snapshots(market_id=market_id, limit=1)
    if not snapshots:
        raise typer.BadParameter("No market snapshots found. Run `lma ingest-demo` first.")
    return snapshots[0]


def _latest_brief(repo: SQLiteRepository) -> ResearchBrief:
    briefs = repo.list_briefs(limit=1)
    if not briefs:
        raise typer.BadParameter("No briefs found. Run `lma generate-brief` first.")
    return briefs[0]


def _latest_signal(repo: SQLiteRepository, signal_id: str) -> Signal:
    signal = repo.load_signal(signal_id)
    if signal is None:
        raise typer.BadParameter(f"Signal not found: {signal_id}")
    return signal


@app.command()
def ingest_demo(
    fixture: Annotated[Path, typer.Option(help="Market fixture path.")] = Path(
        "data/fixtures/demo_market.json"
    ),
    evidence: Annotated[Path, typer.Option(help="Evidence fixture path.")] = Path(
        "data/fixtures/demo_evidence.json"
    ),
    db: Annotated[Path | None, typer.Option(help="SQLite database path.")] = None,
) -> None:
    settings = _settings(db)
    repo = _repository(settings)
    adapter = FixtureAdapter(fixture, evidence)
    snapshot = adapter.fetch_snapshot()
    repo.save_market_snapshot(snapshot)
    evidence_items = adapter.fetch_evidence(snapshot.market.market_id)
    typer.echo(
        json.dumps(
            {
                "snapshot_id": snapshot.snapshot_id,
                "market_id": snapshot.market.market_id,
                "evidence_items": len(evidence_items),
                "db_path": str(settings.db_path),
            },
            sort_keys=True,
        )
    )


@app.command()
def generate_brief(
    fixture: Annotated[Path, typer.Option(help="Market fixture path.")] = Path(
        "data/fixtures/demo_market.json"
    ),
    evidence: Annotated[Path, typer.Option(help="Evidence fixture path.")] = Path(
        "data/fixtures/demo_evidence.json"
    ),
    db: Annotated[Path | None, typer.Option(help="SQLite database path.")] = None,
) -> None:
    settings = _settings(db)
    repo = _repository(settings)
    adapter = FixtureAdapter(fixture, evidence)
    snapshot = adapter.fetch_snapshot()
    repo.save_market_snapshot(snapshot)
    evidence_items = adapter.fetch_evidence(snapshot.market.market_id)
    generator = ResearchBriefGenerator(
        repository=repo,
        provider=_provider(settings),
        reporter=Reporter(settings.research_brief_dir),
    )
    brief = generator.generate(snapshot, evidence_items)
    typer.echo(
        json.dumps(
            {
                "brief_id": brief.brief_id,
                "market_id": brief.market_id,
                "recommended_action": brief.recommended_action,
                "confidence": brief.confidence,
                "evidence_quality": brief.evidence_quality,
            },
            sort_keys=True,
        )
    )


@app.command()
def risk_check(
    db: Annotated[Path | None, typer.Option(help="SQLite database path.")] = None,
) -> None:
    settings = _settings(db)
    repo = _repository(settings)
    brief = _latest_brief(repo)
    snapshot = _latest_snapshot(repo, brief.market_id)
    signal = PredictionMarketEdgeStrategy(settings.risk).generate_signal(brief, snapshot)
    repo.save_signal(signal)
    decision = RiskEngine(settings.risk).evaluate_signal(
        signal,
        open_positions=len([position for position in repo.list_positions() if position.is_open]),
    )
    repo.save_risk_decision(decision)
    typer.echo(
        json.dumps(
            {
                "signal_id": signal.signal_id,
                "risk_decision_id": decision.risk_decision_id,
                "signal_action": signal.action,
                "risk_status": decision.status,
                "reasons": decision.reasons,
            },
            sort_keys=True,
        )
    )


@app.command()
def paper_log(
    db: Annotated[Path | None, typer.Option(help="SQLite database path.")] = None,
) -> None:
    settings = _settings(db)
    repo = _repository(settings)
    decisions = repo.list_risk_decisions(limit=10)
    approved = next((decision for decision in decisions if decision.is_approved), None)
    if approved is None:
        typer.echo(json.dumps({"status": "no_approved_risk_decision"}, sort_keys=True))
        return
    existing = [
        order
        for order in repo.list_paper_orders(limit=50)
        if order.risk_decision_id == approved.risk_decision_id
    ]
    if existing:
        typer.echo(
            json.dumps(
                {"status": "existing_order", "order_id": existing[0].order_id},
                sort_keys=True,
            )
        )
        return
    signal = _latest_signal(repo, approved.signal_id)
    snapshot = _latest_snapshot(repo, signal.market_id)
    order = PaperLedger(repo, settings.risk).create_order(
        signal=signal,
        risk_decision=approved,
        snapshot=snapshot,
    )
    typer.echo(
        json.dumps(
            {
                "status": "paper_order_filled",
                "order_id": order.order_id,
                "quantity": order.quantity,
                "fill_price": order.fill_price,
            },
            sort_keys=True,
        )
    )


@app.command()
def report_daily(
    db: Annotated[Path | None, typer.Option(help="SQLite database path.")] = None,
) -> None:
    settings = _settings(db)
    repo = _repository(settings)
    report = DailyReportService(repo, settings.risk).build_report()
    export_dir = Path("data/reports")
    ledger = PaperLedger(repo, settings.risk)
    jsonl = ledger.export_jsonl(export_dir / "paper_orders.jsonl")
    csv = ledger.export_csv(export_dir / "paper_orders.csv")
    typer.echo(
        json.dumps(
            {
                "report_id": report.report_id,
                "orders": report.orders,
                "open_positions": report.open_positions,
                "realized_pnl": report.realized_pnl,
                "unrealized_pnl": report.unrealized_pnl,
                "jsonl": str(jsonl),
                "csv": str(csv),
            },
            sort_keys=True,
        )
    )


@app.command("phase7-run-daily")
def phase7_run_daily(
    fixture: Annotated[Path, typer.Option(help="Market fixture path.")] = Path(
        "data/fixtures/demo_market.json"
    ),
    evidence: Annotated[Path, typer.Option(help="Evidence fixture path.")] = Path(
        "data/fixtures/demo_evidence.json"
    ),
    db: Annotated[Path | None, typer.Option(help="SQLite database path.")] = None,
    report_dir: Annotated[Path, typer.Option(help="Local report output directory.")] = Path(
        "data/reports"
    ),
    dry_run: Annotated[
        bool,
        typer.Option(help="Evaluate the paper run without creating paper positions."),
    ] = False,
    require_manual_approval: Annotated[
        bool | None,
        typer.Option(
            "--require-manual-approval/--no-require-manual-approval",
            help="Override Phase 7 paper risk gate manual approval mode for this run.",
        ),
    ] = None,
    refresh_market_timestamp: Annotated[
        bool,
        typer.Option(
            "--refresh-market-timestamp/--keep-fixture-timestamp",
            help="Refresh fixture market data timestamp to the run time before risk gates.",
        ),
    ] = True,
) -> None:
    settings = _settings(db)
    repo = _repository(settings)
    record = Phase7DailyRunner(
        repository=repo,
        settings=settings,
        market_fixture=fixture,
        evidence_fixture=evidence,
        report_dir=report_dir,
        refresh_market_timestamp=refresh_market_timestamp,
    ).run(
        dry_run=dry_run,
        require_manual_approval=require_manual_approval,
        cli_arguments={
            "source": "cli",
            "command": "phase7-run-daily",
            "fixture": str(fixture),
            "evidence": str(evidence),
            "db": str(settings.db_path),
            "report_dir": str(report_dir),
            "dry_run": dry_run,
            "require_manual_approval": require_manual_approval,
            "refresh_market_timestamp": refresh_market_timestamp,
        },
    )
    typer.echo(
        json.dumps(
            {
                "run_id": record.run_id,
                "status": record.status,
                "dry_run": record.dry_run,
                "market_id": record.market_id,
                "paper_order_id": record.paper_order_id,
                "risk_gate_decision_id": record.risk_gate_decision_id,
                "report_path": record.report_path,
                "manifest_id": record.manifest_id,
                "report_checksum": record.metadata.get("report_checksum"),
                "db_path": str(settings.db_path),
            },
            sort_keys=True,
        )
    )


@app.command("phase7-replay")
def phase7_replay(
    run_id: Annotated[str, typer.Option("--run-id", help="Phase 7 run id to replay.")],
    db: Annotated[Path | None, typer.Option(help="SQLite database path.")] = None,
) -> None:
    settings = _settings(db)
    repo = _repository(settings)
    result = Phase7ReplayService(repo).replay(run_id)
    typer.echo(json.dumps(result.as_dict(), sort_keys=True))
    if not result.ok:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
