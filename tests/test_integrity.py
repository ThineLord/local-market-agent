import json
from datetime import timedelta

import pytest
from test_ledger_atomicity import business_hash
from test_paper_authorization import NOW, approve
from test_phase7_replay import _run_phase7
from typer.testing import CliRunner

from local_market_agent.cli import app
from local_market_agent.integrity import seal_run, verify_execution
from local_market_agent.operations import Phase7ReplayService
from local_market_agent.paper import PaperLedger

pytest_plugins = ["test_paper_authorization"]


@pytest.mark.parametrize("artifact", ["snapshot", "brief", "signal", "risk", "record", "approval"])
def test_run_replay_detects_same_id_content_mutation(tmp_path, artifact):
    repo, record = _run_phase7(tmp_path)
    assert Phase7ReplayService(repo).replay(record.run_id).ok
    if artifact == "snapshot":
        x = repo.load_market_snapshot(record.snapshot_id)
        repo.save_market_snapshot(x.model_copy(update={"volume": x.volume+1}))
    elif artifact == "brief":
        x = repo.load_brief(record.brief_id)
        repo.save_brief(x.model_copy(update={"thesis": "changed"}))
    elif artifact == "signal":
        x = repo.load_signal(record.signal_id)
        repo.save_signal(x.model_copy(update={"rationale": "changed"}))
    elif artifact == "risk":
        x = repo.load_risk_decision(record.risk_decision_id)
        repo.save_risk_decision(x.model_copy(update={"max_position_usd": 1}))
    elif artifact == "record":
        repo.save_phase7_run_record(record.model_copy(update={"reasons": ["changed"]}))
    else:
        x = repo.list_paper_approvals()[0]
        repo.save_paper_approval(x.model_copy(update={"actor": "changed"}))
    before = business_hash(repo)
    result = Phase7ReplayService(repo).replay(record.run_id)
    assert not result.ok and any("checksum" in e for e in result.errors)
    assert business_hash(repo) == before


def test_run_relationship_validation_and_legitimate_close(tmp_path):
    repo, record = _run_phase7(tmp_path)
    position = repo.list_positions()[0]
    PaperLedger(repo).close_position(position.position_id, .65)
    assert Phase7ReplayService(repo).replay(record.run_id).ok
    signal = repo.load_signal(record.signal_id)
    repo.save_signal(signal.model_copy(update={"brief_id": "wrong"}))
    # Even regenerated hashes cannot make inconsistent links valid.
    manifest = repo.load_phase7_run_manifest(record.run_id)
    repo.save_phase7_run_manifest(seal_run(repo, record, manifest))
    result = Phase7ReplayService(repo).replay(record.run_id)
    assert not result.ok and any("relationship" in e for e in result.errors)


def test_legacy_run_warns_without_claiming_content_validation(tmp_path):
    repo, record = _run_phase7(tmp_path)
    manifest = repo.load_phase7_run_manifest(record.run_id)
    manifest.metadata.pop("integrity")
    repo.save_phase7_run_manifest(manifest)
    result = Phase7ReplayService(repo).replay(record.run_id)
    assert result.ok and "Legacy unsealed" in result.warnings[0]


def test_execution_receipt_replay_and_fill_mutation(repo, prepared):
    service, intent = prepared
    approve(service, intent)
    service.execute(intent.intent_id, now=NOW)
    assert verify_execution(repo, intent.intent_id)["ok"]
    result = CliRunner().invoke(app, ["paper-replay", "--intent-id", intent.intent_id, "--db", str(repo.db_path)])
    assert result.exit_code == 0 and json.loads(result.output)["ok"]
    fill = repo.list_paper_fills()[0]
    repo._save("paper_fills", "fill_id", fill.model_copy(update={"fees": fill.fees+1}))
    assert not verify_execution(repo, intent.intent_id)["ok"]


def test_execution_approval_expiry_link_even_if_resealed(repo, prepared):
    service, intent = prepared
    approve(service, intent)
    service.execute(intent.intent_id, now=NOW)
    a = repo.list_paper_approvals()[0]
    repo.save_paper_approval(a.model_copy(update={"expires_at": NOW-timedelta(seconds=1)}))
    assert not verify_execution(repo, intent.intent_id)["ok"]
