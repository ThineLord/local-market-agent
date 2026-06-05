from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from local_market_agent.adapters import FixtureAdapter
from local_market_agent.config import Settings
from local_market_agent.llm import llm_provider_audit
from local_market_agent.operations.phase7_daily import Phase7DailyRunner
from local_market_agent.operations.phase7_market_data import (
    MARKET_SOURCE_FIXTURE,
    normalize_market_source,
    phase7_market_data_audit,
)
from local_market_agent.operations.phase7_replay import Phase7ReplayService
from local_market_agent.schemas import Phase7RunRecord, Phase7RunStatus
from local_market_agent.schemas.models import Position, deterministic_model_context
from local_market_agent.storage import SQLiteRepository


@dataclass(frozen=True)
class SandboxDateRange:
    start_date: date
    end_date: date

    @property
    def simulated_days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def dates(self) -> list[date]:
        return [
            self.start_date + timedelta(days=offset)
            for offset in range(self.simulated_days)
        ]


@dataclass(frozen=True)
class Phase7SandboxResult:
    summary_path: Path
    summary: dict[str, Any]
    records: list[Phase7RunRecord]


@dataclass
class Phase7SandboxRunner:
    repository: SQLiteRepository
    settings: Settings
    market_fixture: Path = Path("data/fixtures/demo_market.json")
    evidence_fixture: Path = Path("data/fixtures/demo_evidence.json")
    report_dir: Path = Path("data/reports")
    summary_dir: Path | None = None
    refresh_market_timestamp: bool = True
    market_source: str | None = None
    market_id: str | None = None

    def run(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        days: int | None = None,
        dry_run: bool = False,
        require_manual_approval: bool | None = None,
        replay_sample_size: int = 1,
        sandbox_id: str | None = None,
    ) -> Phase7SandboxResult:
        _assert_paper_only(self.settings)
        market_source = self.market_source or self.settings.market_source
        market_id = self.market_id if self.market_id is not None else self.settings.market_id
        market_data = phase7_market_data_audit(market_source, market_id=market_id)
        date_range = resolve_sandbox_date_range(
            market_fixture=self.market_fixture,
            evidence_fixture=self.evidence_fixture,
            start_date=start_date,
            end_date=end_date,
            days=days,
            market_source=market_source,
        )
        sandbox_id = sandbox_id or _sandbox_id(
            date_range=date_range,
            market_fixture=self.market_fixture,
            evidence_fixture=self.evidence_fixture,
            market_source=market_source,
            market_id=market_id,
            dry_run=dry_run,
            require_manual_approval=require_manual_approval,
            refresh_market_timestamp=self.refresh_market_timestamp,
            settings=self.settings,
        )
        records: list[Phase7RunRecord] = []
        daily_runner = Phase7DailyRunner(
            repository=self.repository,
            settings=self.settings,
            market_fixture=self.market_fixture,
            evidence_fixture=self.evidence_fixture,
            report_dir=self.report_dir,
            refresh_market_timestamp=self.refresh_market_timestamp,
            market_source=market_source,
            market_id=market_id,
        )

        for simulated_date in date_range.dates():
            simulated_at = datetime.combine(simulated_date, time(hour=16), tzinfo=UTC)
            seed = f"{sandbox_id}:{simulated_date.isoformat()}"
            with deterministic_model_context(seed=seed, now=simulated_at):
                record = daily_runner.run(
                    dry_run=dry_run,
                    require_manual_approval=require_manual_approval,
                    now=simulated_at,
                    cli_arguments={
                        "source": "cli",
                        "command": "phase7-sandbox-run",
                        "sandbox_id": sandbox_id,
                        "simulated_date": simulated_date.isoformat(),
                        "fixture": str(self.market_fixture),
                        "evidence": str(self.evidence_fixture),
                        "market_source": market_source,
                        "market_id": market_id,
                        "db": str(self.settings.db_path),
                        "report_dir": str(self.report_dir),
                        "dry_run": dry_run,
                        "require_manual_approval": require_manual_approval,
                        "refresh_market_timestamp": self.refresh_market_timestamp,
                        "llm_provider": self.settings.llm_provider,
                        "llm_model": self.settings.openai_compatible_model,
                        "llm_base_url": self.settings.openai_compatible_base_url,
                    },
                )
            records.append(record)

        replay_samples = _run_replay_samples(
            repository=self.repository,
            records=records,
            sample_size=replay_sample_size,
        )
        summary = _build_summary(
            repository=self.repository,
            settings=self.settings,
            sandbox_id=sandbox_id,
            date_range=date_range,
            records=records,
            replay_samples=replay_samples,
            market_fixture=self.market_fixture,
            evidence_fixture=self.evidence_fixture,
            report_dir=self.report_dir,
            dry_run=dry_run,
            require_manual_approval=require_manual_approval,
            refresh_market_timestamp=self.refresh_market_timestamp,
            market_data=market_data.as_dict(),
            market_source=market_source,
            market_id=market_id,
        )
        output = self._summary_path(sandbox_id, date_range)
        output.parent.mkdir(parents=True, exist_ok=True)
        summary["summary_path"] = str(output)
        output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return Phase7SandboxResult(summary_path=output, summary=summary, records=records)

    def _summary_path(self, sandbox_id: str, date_range: SandboxDateRange) -> Path:
        output_dir = self.summary_dir or self.report_dir
        return (
            output_dir
            / f"phase7_sandbox_summary_{sandbox_id}_{date_range.start_date.isoformat()}_"
            f"{date_range.end_date.isoformat()}.json"
        )


def resolve_sandbox_date_range(
    *,
    market_fixture: Path,
    evidence_fixture: Path,
    start_date: date | None = None,
    end_date: date | None = None,
    days: int | None = None,
    market_source: str | None = MARKET_SOURCE_FIXTURE,
) -> SandboxDateRange:
    if days is None and start_date is None and end_date is None:
        days = 30
    if days is not None and days <= 0:
        msg = "sandbox days must be greater than zero"
        raise ValueError(msg)
    if start_date is not None and end_date is not None:
        if days is not None and (end_date - start_date).days + 1 != days:
            msg = "sandbox days does not match the explicit start/end date range"
            raise ValueError(msg)
    elif days is not None and start_date is not None:
        end_date = start_date + timedelta(days=days - 1)
    elif days is not None and end_date is not None:
        start_date = end_date - timedelta(days=days - 1)
    elif days is not None:
        source = normalize_market_source(market_source)
        if source == MARKET_SOURCE_FIXTURE:
            end_date = FixtureAdapter(market_fixture, evidence_fixture).fetch_snapshot().as_of.date()
        else:
            end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=days - 1)
    else:
        msg = "provide --days, or provide both --start-date and --end-date"
        raise ValueError(msg)

    if start_date is None or end_date is None:
        msg = "sandbox date range could not be resolved"
        raise ValueError(msg)
    if start_date > end_date:
        msg = "sandbox start date must be on or before end date"
        raise ValueError(msg)
    return SandboxDateRange(start_date=start_date, end_date=end_date)


def _assert_paper_only(settings: Settings) -> None:
    if settings.real_money_enabled:
        msg = "phase7 sandbox is paper-only; REAL_MONEY_ENABLED must be false"
        raise ValueError(msg)
    if settings.allow_live_orders:
        msg = "phase7 sandbox is paper-only; ALLOW_LIVE_ORDERS must be false"
        raise ValueError(msg)
    if settings.risk.live_trading_allowed:
        msg = "phase7 sandbox is paper-only; risk.live_trading_allowed must be false"
        raise ValueError(msg)
    if not settings.risk.no_live_trading:
        msg = "phase7 sandbox is paper-only; risk.no_live_trading must be true"
        raise ValueError(msg)


def _sandbox_id(
    *,
    date_range: SandboxDateRange,
    market_fixture: Path,
    evidence_fixture: Path,
    market_source: str,
    market_id: str | None,
    dry_run: bool,
    require_manual_approval: bool | None,
    refresh_market_timestamp: bool,
    settings: Settings,
) -> str:
    payload = {
        "start_date": date_range.start_date.isoformat(),
        "end_date": date_range.end_date.isoformat(),
        "market_fixture": str(market_fixture),
        "evidence_fixture": str(evidence_fixture),
        "market_source": market_source,
        "market_id": market_id,
        "dry_run": dry_run,
        "require_manual_approval": require_manual_approval,
        "refresh_market_timestamp": refresh_market_timestamp,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.openai_compatible_model,
        "llm_base_url": settings.openai_compatible_base_url,
    }
    digest = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
    return f"phase7b_{digest}"


def _run_replay_samples(
    *,
    repository: SQLiteRepository,
    records: list[Phase7RunRecord],
    sample_size: int,
) -> list[dict[str, Any]]:
    if sample_size < 0:
        msg = "replay sample size cannot be negative"
        raise ValueError(msg)
    samples: list[dict[str, Any]] = []
    for record in records[:sample_size]:
        counts_before = _table_counts(repository)
        replay = Phase7ReplayService(repository).replay(record.run_id)
        counts_after = _table_counts(repository)
        samples.append(
            {
                "run_id": record.run_id,
                "status": record.status.value,
                "ok": replay.ok,
                "errors": replay.errors,
                "warnings": replay.warnings,
                "report_path": replay.report_path,
                "report_checksum": replay.report_checksum,
                "mutation_detected": counts_before != counts_after,
                "counts_before": counts_before,
                "counts_after": counts_after,
            }
        )
    return samples


def _table_counts(repository: SQLiteRepository) -> dict[str, int]:
    return {table: repository.count(table) for table in sorted(SQLiteRepository.TABLES)}


def _build_summary(
    *,
    repository: SQLiteRepository,
    settings: Settings,
    sandbox_id: str,
    date_range: SandboxDateRange,
    records: list[Phase7RunRecord],
    replay_samples: list[dict[str, Any]],
    market_fixture: Path,
    evidence_fixture: Path,
    report_dir: Path,
    dry_run: bool,
    require_manual_approval: bool | None,
    refresh_market_timestamp: bool,
    market_data: dict[str, Any],
    market_source: str,
    market_id: str | None,
) -> dict[str, Any]:
    equity_curve = _equity_curve(repository, records)
    status_counts = _status_counts(records)
    generated_order_ids = {
        record.paper_order_id for record in records if record.paper_order_id is not None
    }
    closed_positions = _closed_positions_for_orders(repository, generated_order_ids)
    win_rate, profit_factor = _win_rate_and_profit_factor(closed_positions)

    return {
        "sandbox_id": sandbox_id,
        "phase": "7B",
        "execution_mode": "paper",
        "local_only": not bool(market_data.get("network_calls_enabled")),
        "deterministic": bool(market_data.get("is_fixture")),
        "llm_provider": llm_provider_audit(settings).as_dict(),
        "market_source": market_data["market_source"],
        "data_mode": market_data["data_mode"],
        "profitability_claims_meaningful": market_data["profitability_claims_meaningful"],
        "market_data": market_data,
        "sandbox_data_semantics": _sandbox_data_semantics(market_data),
        "live_trading_allowed": False,
        "start_date": date_range.start_date.isoformat(),
        "end_date": date_range.end_date.isoformat(),
        "simulated_days": date_range.simulated_days,
        "status_counts": status_counts,
        "equity_curve": equity_curve,
        "total_return": _total_return(equity_curve, settings.risk.paper_starting_cash),
        "max_drawdown": _max_drawdown(equity_curve),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "run_success_rate": _run_success_rate(records),
        "report_paths": [record.report_path for record in records if record.report_path],
        "runs": [_run_summary(record) for record in records],
        "replay_validation_sample_results": replay_samples,
        "inputs": {
            "market_fixture": str(market_fixture),
            "evidence_fixture": str(evidence_fixture),
            "market_source": market_source,
            "market_id": market_id,
            "db_path": str(settings.db_path),
            "report_dir": str(report_dir),
            "dry_run": dry_run,
            "require_manual_approval": require_manual_approval,
            "refresh_market_timestamp": refresh_market_timestamp,
        },
        "safety": {
            "paper_only": True,
            "real_money_enabled": settings.real_money_enabled,
            "allow_live_orders": settings.allow_live_orders,
            "human_approval_required_default": settings.human_approval_required,
            "risk_live_trading_allowed": settings.risk.live_trading_allowed,
            "risk_no_live_trading": settings.risk.no_live_trading,
            "broker_integrations_added": False,
            "scheduler_added": False,
            "direct_llm_to_order_path": False,
        },
    }


def _run_summary(record: Phase7RunRecord) -> dict[str, Any]:
    return {
        "run_id": record.run_id,
        "simulated_date": record.report_date.date().isoformat(),
        "status": record.status.value,
        "market_id": record.market_id,
        "snapshot_id": record.snapshot_id,
        "signal_id": record.signal_id,
        "risk_decision_id": record.risk_decision_id,
        "risk_gate_decision_id": record.risk_gate_decision_id,
        "paper_order_id": record.paper_order_id,
        "portfolio_snapshot_id": record.portfolio_snapshot_id,
        "report_path": record.report_path,
        "manifest_id": record.manifest_id,
        "report_checksum": record.metadata.get("report_checksum"),
        "live_trading_allowed": record.metadata.get("live_trading_allowed"),
        "market_data": record.metadata.get("market_data"),
    }


def _sandbox_data_semantics(market_data: dict[str, Any]) -> dict[str, Any]:
    if market_data.get("is_fixture"):
        label = "fixture replay sandbox"
        note = (
            "Deterministic fixture data is replayed through the workflow; this validates "
            "system integrity and paper controls, not real historical profitability."
        )
    else:
        label = "snapshot repeated sandbox"
        note = (
            "A current read-only snapshot source is selected; repeated simulated days are "
            "not a historical backtest and profitability claims are not meaningful."
        )
    return {
        "label": label,
        "historical_market_data": bool(market_data.get("is_historical")),
        "snapshot_only": bool(market_data.get("is_snapshot_only")),
        "profitability_claims_meaningful": bool(
            market_data.get("profitability_claims_meaningful")
        ),
        "note": note,
    }


def _status_counts(records: list[Phase7RunRecord]) -> dict[str, int]:
    counts = {
        "completed": 0,
        "rejected": 0,
        "failed": 0,
        "pending": 0,
        "halted": 0,
        "dry_run": 0,
    }
    for record in records:
        if record.status == Phase7RunStatus.COMPLETED:
            counts["completed"] += 1
        elif record.status == Phase7RunStatus.REJECTED:
            counts["rejected"] += 1
        elif record.status == Phase7RunStatus.FAILED:
            counts["failed"] += 1
        elif record.status == Phase7RunStatus.PENDING_MANUAL_APPROVAL:
            counts["pending"] += 1
        elif record.status == Phase7RunStatus.HALTED:
            counts["halted"] += 1
        elif record.status == Phase7RunStatus.DRY_RUN:
            counts["dry_run"] += 1
    return counts


def _equity_curve(
    repository: SQLiteRepository,
    records: list[Phase7RunRecord],
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for record in records:
        if record.portfolio_snapshot_id is None:
            continue
        snapshot = repository.load_portfolio_snapshot(record.portfolio_snapshot_id)
        if snapshot is None:
            continue
        points.append(
            {
                "simulated_date": record.report_date.date().isoformat(),
                "run_id": record.run_id,
                "portfolio_snapshot_id": snapshot.snapshot_id,
                "portfolio_value": snapshot.portfolio_value,
                "realized_pnl": snapshot.realized_pnl,
                "unrealized_pnl": snapshot.unrealized_pnl,
                "cash_balance": snapshot.cash_balance,
                "open_positions": snapshot.open_positions,
                "closed_positions": snapshot.closed_positions,
            }
        )
    return points


def _total_return(equity_curve: list[dict[str, Any]], starting_cash: float) -> float | None:
    if not equity_curve or starting_cash <= 0:
        return None
    ending_value = float(equity_curve[-1]["portfolio_value"])
    return round((ending_value - starting_cash) / starting_cash, 8)


def _max_drawdown(equity_curve: list[dict[str, Any]]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for point in equity_curve:
        value = float(point["portfolio_value"])
        peak = max(peak, value)
        if peak <= 0:
            continue
        drawdown = (peak - value) / peak
        max_drawdown = max(max_drawdown, drawdown)
    return round(max_drawdown, 8)


def _closed_positions_for_orders(
    repository: SQLiteRepository,
    order_ids: set[str],
) -> list[Position]:
    if not order_ids:
        return []
    return [
        position
        for position in repository.list_positions()
        if position.order_id in order_ids and not position.is_open
    ]


def _win_rate_and_profit_factor(
    closed_positions: list[Position],
) -> tuple[float | None, float | None]:
    if not closed_positions:
        return None, None
    wins = [position for position in closed_positions if position.realized_pnl > 0]
    losses = [position for position in closed_positions if position.realized_pnl < 0]
    gross_profit = round(sum(position.realized_pnl for position in wins), 4)
    gross_loss = round(abs(sum(position.realized_pnl for position in losses)), 4)
    win_rate = round(len(wins) / len(closed_positions), 8)
    profit_factor = round(gross_profit / gross_loss, 8) if gross_loss > 0 else None
    return win_rate, profit_factor


def _run_success_rate(records: list[Phase7RunRecord]) -> float | None:
    if not records:
        return None
    failed = len([record for record in records if record.status == Phase7RunStatus.FAILED])
    return round((len(records) - failed) / len(records), 8)
