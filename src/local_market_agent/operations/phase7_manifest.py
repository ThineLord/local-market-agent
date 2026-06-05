from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from local_market_agent.config import Settings
from local_market_agent.llm import llm_provider_audit
from local_market_agent.schemas import Phase7RunManifest
from local_market_agent.schemas.models import ExecutionMode


def build_phase7_run_manifest(
    *,
    run_id: str,
    settings: Settings,
    created_at: datetime,
    market_fixture: Path,
    evidence_fixture: Path,
    report_path: Path | None,
    cli_arguments: dict[str, Any],
    market_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Phase7RunManifest:
    return Phase7RunManifest(
        run_id=run_id,
        created_at=created_at,
        code_version=_git_commit_hash(),
        configuration_snapshot=_configuration_snapshot(settings, market_data=market_data),
        cli_arguments=cli_arguments,
        fixture_paths={
            "market_fixture": str(market_fixture),
            "evidence_fixture": str(evidence_fixture),
        },
        report_path=str(report_path) if report_path is not None else None,
        report_checksum=sha256_file(report_path) if report_path is not None else None,
        execution_mode=ExecutionMode.PAPER,
        metadata=metadata or {},
    )


def _configuration_snapshot(
    settings: Settings,
    *,
    market_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = {
        "db_path": str(settings.db_path),
        "raw_cache_dir": str(settings.raw_cache_dir),
        "research_brief_dir": str(settings.research_brief_dir),
        "real_money_enabled": settings.real_money_enabled,
        "allow_live_orders": settings.allow_live_orders,
        "human_approval_required": settings.human_approval_required,
        "market_source": settings.market_source,
        "market_id": settings.market_id,
        "historical_file": str(settings.historical_file)
        if settings.historical_file is not None
        else None,
        "llm_provider": settings.llm_provider,
        "llm": llm_provider_audit(settings).as_dict(),
        "run_network_tests": settings.run_network_tests,
        "risk": settings.risk.as_dict(),
        "risk_gates": settings.risk_gates.as_dict(),
    }
    if market_data is not None:
        snapshot["market_data"] = market_data
    return snapshot


def sha256_file(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit_hash() -> str | None:
    root = Path(__file__).resolve().parents[3]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None
