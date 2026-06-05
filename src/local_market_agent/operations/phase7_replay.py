from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from local_market_agent.operations.phase7_manifest import sha256_file
from local_market_agent.schemas import Phase7RunManifest, Phase7RunRecord, Phase7RunStatus
from local_market_agent.schemas.models import ExecutionMode
from local_market_agent.storage import SQLiteRepository


@dataclass(frozen=True)
class Phase7ReplayResult:
    run_id: str
    ok: bool
    status: str | None
    artifacts: dict[str, dict[str, object]]
    errors: list[str]
    warnings: list[str]
    manifest: Phase7RunManifest | None
    report_path: str | None
    report_checksum: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ok": self.ok,
            "status": self.status,
            "artifacts": self.artifacts,
            "errors": self.errors,
            "warnings": self.warnings,
            "manifest": self.manifest.model_dump(mode="json") if self.manifest else None,
            "report_path": self.report_path,
            "report_checksum": self.report_checksum,
        }


@dataclass
class Phase7ReplayService:
    repository: SQLiteRepository

    def replay(self, run_id: str) -> Phase7ReplayResult:
        errors: list[str] = []
        warnings: list[str] = []
        artifacts: dict[str, dict[str, object]] = {}

        record = self.repository.load_phase7_run_record(run_id)
        artifacts["run_record"] = _artifact(run_id, record is not None)
        if record is None:
            return Phase7ReplayResult(
                run_id=run_id,
                ok=False,
                status=None,
                artifacts=artifacts,
                errors=[f"Phase 7 run record not found: {run_id}"],
                warnings=[],
                manifest=None,
                report_path=None,
                report_checksum=None,
            )

        manifest_key = record.manifest_id or record.run_id
        manifest = self.repository.load_phase7_run_manifest(manifest_key)
        artifacts["run_manifest"] = _artifact(manifest_key, manifest is not None)
        if manifest is None:
            errors.append(f"Phase 7 run manifest not found: {manifest_key}")
        else:
            self._validate_manifest(record, manifest, errors, warnings)

        self._validate_references(record, artifacts, errors)
        report_path, report_checksum = self._validate_report(record, manifest, artifacts, errors)

        return Phase7ReplayResult(
            run_id=run_id,
            ok=not errors,
            status=str(record.status),
            artifacts=artifacts,
            errors=errors,
            warnings=warnings,
            manifest=manifest,
            report_path=report_path,
            report_checksum=report_checksum,
        )

    def _validate_manifest(
        self,
        record: Phase7RunRecord,
        manifest: Phase7RunManifest,
        errors: list[str],
        warnings: list[str],
    ) -> None:
        if manifest.run_id != record.run_id:
            errors.append("Manifest run_id does not match run record.")
        if manifest.execution_mode != ExecutionMode.PAPER:
            errors.append("Manifest execution mode is not paper.")
        if not manifest.configuration_snapshot:
            errors.append("Manifest configuration snapshot is missing.")
        if not manifest.cli_arguments:
            errors.append("Manifest CLI arguments are missing.")
        if not manifest.fixture_paths:
            errors.append("Manifest fixture paths are missing.")
        if manifest.code_version is None:
            warnings.append("Manifest code version is unavailable.")
        if record.report_path and manifest.report_path and record.report_path != manifest.report_path:
            errors.append("Manifest report path does not match run record report path.")

    def _validate_references(
        self,
        record: Phase7RunRecord,
        artifacts: dict[str, dict[str, object]],
        errors: list[str],
    ) -> None:
        references = {
            "market_snapshot": (record.snapshot_id, self.repository.load_market_snapshot),
            "research_brief": (record.brief_id, self.repository.load_brief),
            "signal": (record.signal_id, self.repository.load_signal),
            "risk_decision": (record.risk_decision_id, self.repository.load_risk_decision),
            "risk_gate_decision": (
                record.risk_gate_decision_id,
                self.repository.load_risk_gate_decision,
            ),
            "paper_order": (record.paper_order_id, self.repository.load_paper_order),
            "portfolio_snapshot": (
                record.portfolio_snapshot_id,
                self.repository.load_portfolio_snapshot,
            ),
        }
        for name, (identifier, loader) in references.items():
            if identifier is None:
                artifacts[name] = _artifact(None, False, required=_reference_required(name, record))
                if _reference_required(name, record):
                    errors.append(f"Required replay reference is missing: {name}")
                continue
            present = loader(identifier) is not None
            artifacts[name] = _artifact(identifier, present, required=_reference_required(name, record))
            if not present:
                errors.append(f"Stored replay reference not found: {name}={identifier}")

    def _validate_report(
        self,
        record: Phase7RunRecord,
        manifest: Phase7RunManifest | None,
        artifacts: dict[str, dict[str, object]],
        errors: list[str],
    ) -> tuple[str | None, str | None]:
        report_path = (
            manifest.report_path
            if manifest is not None and manifest.report_path is not None
            else record.report_path
        )
        report_required = record.status != Phase7RunStatus.FAILED
        if report_path is None:
            artifacts["report"] = _artifact(None, False, required=report_required)
            if report_required:
                errors.append("Report path is missing for replay.")
            return None, None

        path = Path(report_path)
        report_checksum = sha256_file(path)
        artifacts["report"] = _artifact(str(path), report_checksum is not None, required=report_required)
        if report_checksum is None:
            errors.append(f"Report artifact not found: {path}")
            return str(path), None

        expected_checksum = manifest.report_checksum if manifest is not None else None
        if expected_checksum is None and report_required:
            errors.append("Manifest report checksum is missing.")
        elif expected_checksum is not None and report_checksum != expected_checksum:
            errors.append("Report checksum does not match manifest.")
        return str(path), report_checksum


def _artifact(
    identifier: str | None,
    present: bool,
    *,
    required: bool = True,
) -> dict[str, object]:
    return {
        "id": identifier or "",
        "present": present,
        "required": required,
    }


def _reference_required(name: str, record: Phase7RunRecord) -> bool:
    if record.status == Phase7RunStatus.FAILED:
        return False
    if name == "paper_order":
        return record.status == Phase7RunStatus.COMPLETED
    return name in {
        "market_snapshot",
        "research_brief",
        "signal",
        "risk_decision",
        "risk_gate_decision",
        "portfolio_snapshot",
    }
