from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Annotated

import typer

from local_market_agent.adapters import FixtureAdapter
from local_market_agent.agents import Reporter, ResearchBriefGenerator
from local_market_agent.config import Settings, load_settings
from local_market_agent.data import (
    validate_historical_dataset,
    write_historical_validation_reports,
)
from local_market_agent.eval import (
    DEFAULT_QWEN_BASE_URL,
    DEFAULT_QWEN_MODEL,
    run_daily_provider_comparison,
    run_sandbox_provider_comparison,
)
from local_market_agent.eval.offline_strategy import run_strategy_offline_evaluation
from local_market_agent.llm import (
    build_llm_provider,
    llm_provider_audit,
)
from local_market_agent.operations import (
    Phase7DailyRunner,
    Phase7ReplayService,
    Phase7SandboxRunner,
)
from local_market_agent.operations.phase7_market_data import phase7_market_data_audit
from local_market_agent.paper import PaperLedger
from local_market_agent.reporting import DailyReportService
from local_market_agent.risk import RiskEngine
from local_market_agent.schemas import MarketSnapshot, ResearchBrief, Signal
from local_market_agent.storage import SQLiteRepository
from local_market_agent.strategy import PredictionMarketEdgeStrategy

app = typer.Typer(help="Local Market Agent: offline-first research and paper trading.")


def _settings(
    db: Path | None,
    *,
    market_source: str | None = None,
    market_id: str | None = None,
    historical_file: Path | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_base_url: str | None = None,
) -> Settings:
    settings = load_settings()
    normalized_market_id = _optional_cli_text(market_id)
    if (
        db is None
        and market_source is None
        and market_id is None
        and historical_file is None
        and llm_provider is None
        and llm_model is None
        and llm_base_url is None
    ):
        return settings
    return Settings(
        db_path=db or settings.db_path,
        raw_cache_dir=settings.raw_cache_dir,
        research_brief_dir=settings.research_brief_dir,
        real_money_enabled=settings.real_money_enabled,
        allow_live_orders=settings.allow_live_orders,
        human_approval_required=settings.human_approval_required,
        market_source=market_source or settings.market_source,
        market_id=normalized_market_id if market_id is not None else settings.market_id,
        historical_file=historical_file or settings.historical_file,
        llm_provider=llm_provider or settings.llm_provider,
        openai_compatible_base_url=llm_base_url or settings.openai_compatible_base_url,
        openai_compatible_model=llm_model or settings.openai_compatible_model,
        openai_compatible_api_key=settings.openai_compatible_api_key,
        openai_compatible_timeout_seconds=settings.openai_compatible_timeout_seconds,
        sec_user_agent=settings.sec_user_agent,
        run_network_tests=settings.run_network_tests,
        risk=settings.risk,
        risk_gates=settings.risk_gates,
    )


def _repository(settings: Settings) -> SQLiteRepository:
    return SQLiteRepository(settings.db_path)


def _optional_cli_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


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
        provider=build_llm_provider(settings),
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


@app.command("llm-provider-audit")
def llm_provider_audit_command(
    llm_provider: Annotated[
        str | None,
        typer.Option("--llm-provider", help="LLM provider: mock or openai-compatible."),
    ] = None,
    llm_model: Annotated[
        str | None,
        typer.Option("--llm-model", help="OpenAI-compatible research model name."),
    ] = None,
    llm_base_url: Annotated[
        str | None,
        typer.Option("--llm-base-url", help="OpenAI-compatible base URL."),
    ] = None,
) -> None:
    settings = _settings(
        None,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )
    audit = llm_provider_audit(settings).as_dict()
    typer.echo(json.dumps(audit, sort_keys=True))


@app.command("market-data-audit")
def market_data_audit_command(
    market_source: Annotated[
        str | None,
        typer.Option(
            "--market-source",
            help=(
                "Read-only market source: fixture, historical-file, polymarket, "
                "kalshi, or yfinance."
            ),
        ),
    ] = None,
    market_id: Annotated[
        str | None,
        typer.Option(
            "--market-id",
            help="Market identifier for non-fixture read-only sources.",
        ),
    ] = None,
    historical_file: Annotated[
        Path | None,
        typer.Option(
            "--historical-file",
            help="Local JSONL historical dataset for --market-source historical-file.",
        ),
    ] = None,
) -> None:
    settings = _settings(
        None,
        market_source=market_source,
        market_id=market_id,
        historical_file=historical_file,
    )
    try:
        audit = phase7_market_data_audit(
            settings.market_source,
            market_id=settings.market_id,
            historical_file=settings.historical_file,
        ).as_dict()
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(audit, sort_keys=True))


@app.command("validate-historical-dataset")
def validate_historical_dataset_command(
    historical_file: Annotated[
        Path,
        typer.Option("--historical-file", help="Local Phase 7G JSONL dataset to validate."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(help="Local Phase 7G validation report output directory."),
    ] = Path("data/reports/historical_dataset"),
) -> None:
    try:
        result = validate_historical_dataset(historical_file)
        artifacts = write_historical_validation_reports(result, output_dir)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        json.dumps(
            {
                "valid": result.valid,
                "profile": result.profile,
                "acceptance_candidate": result.acceptance_candidate,
                "paper_pnl_allowed": result.paper_pnl_allowed,
                "row_count": result.row_count,
                "market_count": result.market_count,
                "error_count": result.error_count,
                "warning_count": result.warning_count,
                "json_path": str(artifacts.json_path),
                "markdown_path": str(artifacts.markdown_path),
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
    market_source: Annotated[
        str | None,
        typer.Option(
            "--market-source",
            help=(
                "Read-only market source: fixture, historical-file, polymarket, "
                "kalshi, or yfinance."
            ),
        ),
    ] = None,
    market_id: Annotated[
        str | None,
        typer.Option(
            "--market-id",
            help="Market identifier for non-fixture read-only sources.",
        ),
    ] = None,
    historical_file: Annotated[
        Path | None,
        typer.Option(
            "--historical-file",
            help="Local JSONL historical dataset for --market-source historical-file.",
        ),
    ] = None,
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
            help="Refresh market data timestamp to the run time before risk gates.",
        ),
    ] = True,
    llm_provider: Annotated[
        str | None,
        typer.Option("--llm-provider", help="LLM provider: mock or openai-compatible."),
    ] = None,
    llm_model: Annotated[
        str | None,
        typer.Option("--llm-model", help="OpenAI-compatible research model name."),
    ] = None,
    llm_base_url: Annotated[
        str | None,
        typer.Option("--llm-base-url", help="OpenAI-compatible base URL."),
    ] = None,
) -> None:
    settings = _settings(
        db,
        market_source=market_source,
        market_id=market_id,
        historical_file=historical_file,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )
    repo = _repository(settings)
    record = Phase7DailyRunner(
        repository=repo,
        settings=settings,
        market_fixture=fixture,
        evidence_fixture=evidence,
        report_dir=report_dir,
        refresh_market_timestamp=refresh_market_timestamp,
        market_source=settings.market_source,
        market_id=settings.market_id,
        historical_file=settings.historical_file,
    ).run(
        dry_run=dry_run,
        require_manual_approval=require_manual_approval,
        cli_arguments={
            "source": "cli",
            "command": "phase7-run-daily",
            "fixture": str(fixture),
            "evidence": str(evidence),
            "market_source": settings.market_source,
            "market_id": settings.market_id,
            "historical_file": str(settings.historical_file)
            if settings.historical_file is not None
            else None,
            "db": str(settings.db_path),
            "report_dir": str(report_dir),
            "dry_run": dry_run,
            "require_manual_approval": require_manual_approval,
            "refresh_market_timestamp": refresh_market_timestamp,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.openai_compatible_model,
            "llm_base_url": settings.openai_compatible_base_url,
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
                "llm_provider": record.metadata.get("llm_provider"),
                "market_data": record.metadata.get("market_data"),
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


@app.command("phase7-sandbox-run")
def phase7_sandbox_run(
    fixture: Annotated[Path, typer.Option(help="Market fixture path.")] = Path(
        "data/fixtures/demo_market.json"
    ),
    evidence: Annotated[Path, typer.Option(help="Evidence fixture path.")] = Path(
        "data/fixtures/demo_evidence.json"
    ),
    market_source: Annotated[
        str | None,
        typer.Option(
            "--market-source",
            help=(
                "Read-only market source: fixture, historical-file, polymarket, "
                "kalshi, or yfinance."
            ),
        ),
    ] = None,
    market_id: Annotated[
        str | None,
        typer.Option(
            "--market-id",
            help="Market identifier for non-fixture read-only sources.",
        ),
    ] = None,
    historical_file: Annotated[
        Path | None,
        typer.Option(
            "--historical-file",
            help="Local JSONL historical dataset for --market-source historical-file.",
        ),
    ] = None,
    db: Annotated[Path | None, typer.Option(help="SQLite database path.")] = None,
    report_dir: Annotated[Path, typer.Option(help="Local report output directory.")] = Path(
        "data/reports"
    ),
    summary_dir: Annotated[
        Path | None,
        typer.Option(help="Local sandbox summary output directory. Defaults to report dir."),
    ] = None,
    days: Annotated[
        int | None,
        typer.Option(help="Number of sandbox days to simulate."),
    ] = None,
    start_date: Annotated[
        str | None,
        typer.Option(help="Inclusive sandbox start date in YYYY-MM-DD format."),
    ] = None,
    end_date: Annotated[
        str | None,
        typer.Option(help="Inclusive sandbox end date in YYYY-MM-DD format."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(help="Evaluate sandbox runs without creating paper positions."),
    ] = False,
    require_manual_approval: Annotated[
        bool | None,
        typer.Option(
            "--require-manual-approval/--no-require-manual-approval",
            help="Override Phase 7 paper risk gate manual approval mode for sandbox runs.",
        ),
    ] = None,
    refresh_market_timestamp: Annotated[
        bool,
        typer.Option(
            "--refresh-market-timestamp/--keep-fixture-timestamp",
            help="Refresh market data timestamp to each simulated run time.",
        ),
    ] = True,
    replay_sample_size: Annotated[
        int,
        typer.Option(help="Number of generated runs to replay-validate in the summary."),
    ] = 1,
    sandbox_id: Annotated[
        str | None,
        typer.Option(help="Optional deterministic sandbox id/seed."),
    ] = None,
    llm_provider: Annotated[
        str | None,
        typer.Option("--llm-provider", help="LLM provider: mock or openai-compatible."),
    ] = None,
    llm_model: Annotated[
        str | None,
        typer.Option("--llm-model", help="OpenAI-compatible research model name."),
    ] = None,
    llm_base_url: Annotated[
        str | None,
        typer.Option("--llm-base-url", help="OpenAI-compatible base URL."),
    ] = None,
) -> None:
    settings = _settings(
        db,
        market_source=market_source,
        market_id=market_id,
        historical_file=historical_file,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )
    repo = _repository(settings)
    try:
        parsed_start_date = _parse_cli_date(start_date, "--start-date")
        parsed_end_date = _parse_cli_date(end_date, "--end-date")
        result = Phase7SandboxRunner(
            repository=repo,
            settings=settings,
            market_fixture=fixture,
            evidence_fixture=evidence,
            report_dir=report_dir,
            summary_dir=summary_dir,
            refresh_market_timestamp=refresh_market_timestamp,
            market_source=settings.market_source,
            market_id=settings.market_id,
            historical_file=settings.historical_file,
        ).run(
            start_date=parsed_start_date,
            end_date=parsed_end_date,
            days=days,
            dry_run=dry_run,
            require_manual_approval=require_manual_approval,
            replay_sample_size=replay_sample_size,
            sandbox_id=sandbox_id,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result.summary, sort_keys=True))


@app.command("phase7-research-quality-daily-compare")
def phase7_research_quality_daily_compare(
    fixture: Annotated[Path, typer.Option(help="Market fixture path.")] = Path(
        "data/fixtures/demo_market.json"
    ),
    evidence: Annotated[Path, typer.Option(help="Evidence fixture path.")] = Path(
        "data/fixtures/demo_evidence.json"
    ),
    market_source: Annotated[
        str | None,
        typer.Option(
            "--market-source",
            help=(
                "Read-only market source for both provider runs: fixture, historical-file, "
                "polymarket, kalshi, or yfinance."
            ),
        ),
    ] = None,
    market_id: Annotated[
        str | None,
        typer.Option("--market-id", help="Market identifier for selected read-only source."),
    ] = None,
    historical_file: Annotated[
        Path | None,
        typer.Option("--historical-file", help="Local JSONL historical dataset path."),
    ] = None,
    artifact_dir: Annotated[
        Path,
        typer.Option(help="Local Phase 7D artifact output directory."),
    ] = Path("data/reports/research_quality"),
    comparison_id: Annotated[
        str | None,
        typer.Option("--comparison-id", help="Optional deterministic comparison id."),
    ] = None,
    evaluation_date: Annotated[
        str | None,
        typer.Option(
            "--evaluation-date",
            help="Optional daily comparison date in YYYY-MM-DD format, evaluated at 16:00 UTC.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(help="Evaluate without creating paper positions inside comparison DBs."),
    ] = False,
    require_manual_approval: Annotated[
        bool | None,
        typer.Option(
            "--require-manual-approval/--no-require-manual-approval",
            help="Override paper risk gate manual approval mode inside comparison DBs.",
        ),
    ] = False,
    refresh_market_timestamp: Annotated[
        bool,
        typer.Option(
            "--refresh-market-timestamp/--keep-fixture-timestamp",
            help="Refresh market data timestamps before risk gates.",
        ),
    ] = True,
    qwen_model: Annotated[
        str,
        typer.Option("--qwen-model", help="Ollama/OpenAI-compatible model name."),
    ] = DEFAULT_QWEN_MODEL,
    qwen_base_url: Annotated[
        str,
        typer.Option("--qwen-base-url", help="Ollama/OpenAI-compatible base URL."),
    ] = DEFAULT_QWEN_BASE_URL,
) -> None:
    settings = _settings(
        None,
        market_source=market_source,
        market_id=market_id,
        historical_file=historical_file,
    )
    now = _evaluation_datetime(evaluation_date)
    payload = run_daily_provider_comparison(
        settings,
        artifact_dir=artifact_dir,
        comparison_id=comparison_id,
        qwen_model=qwen_model,
        qwen_base_url=qwen_base_url,
        market_fixture=fixture,
        evidence_fixture=evidence,
        market_source=settings.market_source,
        market_id=settings.market_id,
        historical_file=settings.historical_file,
        dry_run=dry_run,
        require_manual_approval=require_manual_approval,
        refresh_market_timestamp=refresh_market_timestamp,
        now=now,
    )
    typer.echo(json.dumps(_comparison_cli_summary(payload), sort_keys=True))


@app.command("phase7-research-quality-sandbox-compare")
def phase7_research_quality_sandbox_compare(
    fixture: Annotated[Path, typer.Option(help="Market fixture path.")] = Path(
        "data/fixtures/demo_market.json"
    ),
    evidence: Annotated[Path, typer.Option(help="Evidence fixture path.")] = Path(
        "data/fixtures/demo_evidence.json"
    ),
    market_source: Annotated[
        str | None,
        typer.Option(
            "--market-source",
            help=(
                "Read-only market source for both provider sandboxes: fixture, "
                "historical-file, polymarket, kalshi, or yfinance."
            ),
        ),
    ] = None,
    market_id: Annotated[
        str | None,
        typer.Option("--market-id", help="Market identifier for selected read-only source."),
    ] = None,
    historical_file: Annotated[
        Path | None,
        typer.Option("--historical-file", help="Local JSONL historical dataset path."),
    ] = None,
    artifact_dir: Annotated[
        Path,
        typer.Option(help="Local Phase 7D artifact output directory."),
    ] = Path("data/reports/research_quality"),
    comparison_id: Annotated[
        str | None,
        typer.Option("--comparison-id", help="Optional deterministic comparison id."),
    ] = None,
    days: Annotated[
        int | None,
        typer.Option(help="Number of sandbox days to simulate."),
    ] = None,
    start_date: Annotated[
        str | None,
        typer.Option(help="Inclusive sandbox start date in YYYY-MM-DD format."),
    ] = None,
    end_date: Annotated[
        str | None,
        typer.Option(help="Inclusive sandbox end date in YYYY-MM-DD format."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(help="Evaluate without creating paper positions inside comparison DBs."),
    ] = False,
    require_manual_approval: Annotated[
        bool | None,
        typer.Option(
            "--require-manual-approval/--no-require-manual-approval",
            help="Override paper risk gate manual approval mode inside comparison DBs.",
        ),
    ] = False,
    refresh_market_timestamp: Annotated[
        bool,
        typer.Option(
            "--refresh-market-timestamp/--keep-fixture-timestamp",
            help="Refresh market data timestamps before risk gates.",
        ),
    ] = True,
    replay_sample_size: Annotated[
        int,
        typer.Option(help="Number of generated runs to replay-validate per provider."),
    ] = 1,
    qwen_model: Annotated[
        str,
        typer.Option("--qwen-model", help="Ollama/OpenAI-compatible model name."),
    ] = DEFAULT_QWEN_MODEL,
    qwen_base_url: Annotated[
        str,
        typer.Option("--qwen-base-url", help="Ollama/OpenAI-compatible base URL."),
    ] = DEFAULT_QWEN_BASE_URL,
) -> None:
    settings = _settings(
        None,
        market_source=market_source,
        market_id=market_id,
        historical_file=historical_file,
    )
    try:
        payload = run_sandbox_provider_comparison(
            settings,
            artifact_dir=artifact_dir,
            comparison_id=comparison_id,
            qwen_model=qwen_model,
            qwen_base_url=qwen_base_url,
            market_fixture=fixture,
            evidence_fixture=evidence,
            market_source=settings.market_source,
            market_id=settings.market_id,
            historical_file=settings.historical_file,
            days=days,
            start_date=_parse_cli_date(start_date, "--start-date"),
            end_date=_parse_cli_date(end_date, "--end-date"),
            dry_run=dry_run,
            require_manual_approval=require_manual_approval,
            refresh_market_timestamp=refresh_market_timestamp,
            replay_sample_size=replay_sample_size,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(_comparison_cli_summary(payload), sort_keys=True))


@app.command("strategy-eval-offline")
def strategy_eval_offline(
    historical_file: Annotated[
        Path,
        typer.Option(
            "--historical-file",
            help="Local JSONL historical dataset to evaluate.",
        ),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(help="Local strategy evaluation report output directory."),
    ] = Path("data/reports/strategy_eval"),
    market_id: Annotated[
        str | None,
        typer.Option("--market-id", help="Optional market id when the dataset has multiple markets."),
    ] = None,
    random_seed: Annotated[
        int,
        typer.Option("--random-seed", help="Fixed seed for the random/naive baseline."),
    ] = 20260605,
) -> None:
    try:
        result = run_strategy_offline_evaluation(
            historical_file=historical_file,
            output_dir=output_dir,
            market_id=_optional_cli_text(market_id),
            random_seed=random_seed,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    dataset = result.report["dataset"]
    acceptance_gate = result.report["acceptance_gate"]
    typer.echo(
        json.dumps(
            {
                "report_id": result.report["report_id"],
                "json_path": str(result.json_path),
                "markdown_path": str(result.markdown_path),
                "json_checksum": result.json_checksum,
                "markdown_checksum": result.markdown_checksum,
                "dataset_classification": dataset["classification"],
                "dataset_classification_detail": dataset["classification_detail"],
                "acceptance_evaluation_eligible": dataset[
                    "acceptance_evaluation_eligible"
                ],
                "gate_status": acceptance_gate["gate_status"],
                "superiority_claim_allowed": acceptance_gate[
                    "superiority_claim_allowed"
                ],
                "failed_gates": acceptance_gate["failed_gates"],
                "warning_gates": acceptance_gate["warning_gates"],
                "recommendation": acceptance_gate["recommendation"],
                "baselines": sorted(result.report["baselines"]),
            },
            sort_keys=True,
        )
    )


def _comparison_cli_summary(payload: dict[str, object]) -> dict[str, object]:
    comparison = payload["comparison"]
    if not isinstance(comparison, dict):
        comparison = {}
    summary = {
        "comparison_id": payload["comparison_id"],
        "comparison_kind": payload["comparison_kind"],
        "artifact_root": payload["artifact_root"],
        "json_path": payload["artifacts"]["json"],
        "markdown_path": payload["artifacts"]["markdown"],
        "materially_changed_outcomes": comparison.get("materially_changed_outcomes"),
        "materiality_basis": comparison.get("materiality_basis", []),
    }
    runs = payload.get("runs")
    if isinstance(runs, list) and payload["comparison_kind"] == "daily":
        summary["provider_statuses"] = {
            run["provider"]: run["run"]["status"]
            for run in runs
            if isinstance(run, dict) and isinstance(run.get("run"), dict)
        }
    return summary


def _evaluation_datetime(value: str | None) -> datetime | None:
    parsed = _parse_cli_date(value, "--evaluation-date")
    if parsed is None:
        return None
    return datetime.combine(parsed, time(hour=16), tzinfo=UTC)


def _parse_cli_date(value: str | None, option_name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        msg = f"{option_name} must use YYYY-MM-DD format"
        raise typer.BadParameter(msg) from exc


if __name__ == "__main__":
    app()
