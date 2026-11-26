from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from typer.testing import CliRunner

from local_market_agent.cli import app
from local_market_agent.config import RiskGateConfig, Settings
from local_market_agent.operations import (
    Phase7SandboxRunner,
    load_historical_dataset,
    phase7_market_data_audit,
)
from local_market_agent.operations.phase7_historical_dataset import (
    credible_settlement_accepted,
)
from local_market_agent.storage import SQLiteRepository

FIXTURES = Path("data/fixtures/historical_validator")
CALIBRATION = FIXTURES / "valid_calibration_only.jsonl"
ACCEPTANCE = FIXTURES / "valid_acceptance_candidate.jsonl"
AMBIGUOUS = FIXTURES / "invalid_ambiguous_settlement.jsonl"
ORDINARY = Path("data/fixtures/phase7_historical_5d.jsonl")
PAPER_PNL_SENTENCE = "paper PnL can be interpreted"


def test_credible_settlement_rejects_builtin_ambiguous_fixture():
    record = load_historical_dataset(AMBIGUOUS).records[0]

    assert record.paper_pnl_allowed is True
    assert record.acceptance_candidate is True
    assert record.settlement_outcome == "yes"
    assert record.settlement_ambiguous is True
    assert record.settlement_status == "settled"
    assert credible_settlement_accepted(record) is False


def test_market_data_audit_rejects_calibration_only_as_paper_proof():
    payload = _audit(CALIBRATION)

    assert payload["historical_profile"] == "calibration_only_last_price"
    assert payload["paper_pnl_allowed"] is False
    assert payload["acceptance_candidate"] is False
    assert payload["read_only"] is True
    assert payload["can_create_orders"] is False
    assert payload["settlement_outcome"] == "no"
    assert payload["settlement_ambiguous"] is False
    assert payload["settlement_status"] == "settled"
    assert payload["settlement_label_present"] is True
    assert payload["credible_settlement"] is True
    assert payload["settlement_coverage"] == "full"
    assert payload["has_settlement"] is True
    assert payload["closed_position_evaluation_supported"] is False
    assert payload["profitability_claims_meaningful"] is False
    assert payload["paper_profit_block_reason"] == "calibration_only_last_price"
    assert PAPER_PNL_SENTENCE not in payload["paper_profit_note"]
    assert payload["historical_record_qualifications"][0]["bid_ask_present"] is False
    assert payload["historical_record_qualifications"][0]["credible_settlement"] is True
    assert payload["historical_record_qualifications"][0]["paper_evaluation_allowed"] is False


def test_market_data_audit_accepts_ordinary_and_acceptance_samples():
    ordinary = _audit(ORDINARY)
    acceptance = _audit(ACCEPTANCE)

    for payload in (ordinary, acceptance):
        assert payload["has_settlement"] is True
        assert payload["closed_position_evaluation_supported"] is True
        assert payload["profitability_claims_meaningful"] is True
        assert payload["credible_settlement"] is True
        assert payload["configuration_error"] is None
        assert PAPER_PNL_SENTENCE in payload["paper_profit_note"]
        assert payload["can_create_orders"] is False
    assert ordinary["settlement_coverage"] == "partial"
    assert ordinary["settlement_outcome"] == "yes"
    assert ordinary["eligible_historical_row_count"] == 5
    assert ordinary["ineligible_historical_row_count"] == 0
    assert acceptance["historical_profile"] == "acceptance_candidate"
    assert acceptance["paper_pnl_allowed"] is True
    assert acceptance["settlement_ambiguous"] is False
    assert acceptance["settlement_outcome"] == "yes"


def test_market_data_audit_keeps_ambiguous_settlement_visible_and_unproven():
    payload = _audit(AMBIGUOUS)

    assert payload["paper_pnl_allowed"] is True
    assert payload["acceptance_candidate"] is True
    assert payload["historical_profile"] == "acceptance_candidate"
    assert payload["settlement_outcome"] == "yes"
    assert payload["settlement_ambiguous"] is True
    assert payload["settlement_status"] == "settled"
    assert payload["settlement_label_present"] is True
    assert payload["credible_settlement"] is False
    assert payload["has_settlement"] is True
    assert payload["closed_position_evaluation_supported"] is False
    assert payload["profitability_claims_meaningful"] is False
    assert payload["paper_profit_block_reason"] == "ambiguous_settlement"
    assert "explicitly ambiguous" in payload["paper_profit_note"]
    assert PAPER_PNL_SENTENCE not in payload["paper_profit_note"]
    row = payload["historical_record_qualifications"][0]
    assert row["settlement_outcome"] == "yes"
    assert row["settlement_ambiguous"] is True
    assert row["credible_settlement"] is False
    assert row["paper_evaluation_allowed"] is False


def test_mixed_archive_does_not_unify_selected_markets(tmp_path):
    mixed = tmp_path / "mixed.jsonl"
    mixed.write_text(
        CALIBRATION.read_text(encoding="utf-8") + ACCEPTANCE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    calibration = _audit(mixed, market_id="KXCAL-26MAY05-Y55")
    acceptance = _audit(mixed, market_id="KXVALID-26MAY05-Y55")
    unspecified = _audit(mixed)
    wrong = _audit(mixed, market_id="missing-market")

    assert calibration["profitability_claims_meaningful"] is False
    assert calibration["has_settlement"] is True
    assert calibration["closed_position_evaluation_supported"] is False
    assert calibration["settlement_outcome"] == "no"
    assert acceptance["profitability_claims_meaningful"] is True
    assert acceptance["has_settlement"] is True
    assert acceptance["closed_position_evaluation_supported"] is True
    assert acceptance["settlement_outcome"] == "yes"
    for payload in (unspecified, wrong):
        assert payload["profitability_claims_meaningful"] is False
        assert payload["has_settlement"] is False
        assert payload["closed_position_evaluation_supported"] is False
        assert payload["credible_settlement"] is False
        assert payload["settlement_outcome"] is None
        assert payload["configuration_error"]
        assert PAPER_PNL_SENTENCE not in payload["paper_profit_note"]
    assert "multiple market ids" in unspecified["configuration_error"]
    assert unspecified["paper_profit_block_reason"] == "market_unspecified"
    assert wrong["paper_profit_block_reason"] == "market_not_in_dataset"


def test_same_market_ineligible_row_does_not_inherit_eligibility(tmp_path):
    rows = [
        json.loads(line)
        for line in ACCEPTANCE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows[1]["paper_pnl_allowed"] = False
    path = tmp_path / "same-market-ineligible.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    payload = _audit(path)
    qualifications = payload["historical_record_qualifications"]

    assert payload["market_id"] == "KXVALID-26MAY05-Y55"
    assert payload["historical_record_count"] == 2
    assert payload["settlement_outcome"] == "yes"
    assert payload["settlement_label_present"] is True
    assert payload["credible_settlement"] is True
    assert payload["paper_pnl_allowed"] is False
    assert payload["has_settlement"] is True
    assert payload["closed_position_evaluation_supported"] is False
    assert payload["profitability_claims_meaningful"] is False
    assert payload["eligible_historical_row_count"] == 1
    assert payload["ineligible_historical_row_count"] == 1
    assert qualifications[0]["paper_evaluation_allowed"] is True
    assert qualifications[0]["paper_pnl_allowed"] is True
    assert qualifications[1]["paper_evaluation_allowed"] is False
    assert qualifications[1]["paper_pnl_allowed"] is False
    assert qualifications[1]["block_reason"] == "paper_pnl_not_allowed"
    assert PAPER_PNL_SENTENCE not in payload["paper_profit_note"]
    assert "Eligible rows remain marked individually" in payload["paper_profit_note"]


def test_pending_settlement_is_not_paper_profit_proof(tmp_path):
    path = tmp_path / "pending.jsonl"
    path.write_text(
        json.dumps(
            {
                "date": "2026-05-01",
                "market_id": "pending-market",
                "bid": 0.42,
                "ask": 0.44,
                "last_price": 0.43,
                "profile": "acceptance_candidate",
                "paper_pnl_allowed": True,
                "acceptance_candidate": True,
                "settlement": {
                    "outcome": "yes",
                    "status": "pending",
                    "ambiguous": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = _audit(path)

    assert payload["settlement_outcome"] == "yes"
    assert payload["settlement_status"] == "pending"
    assert payload["settlement_ambiguous"] is False
    assert payload["settlement_label_present"] is True
    assert payload["credible_settlement"] is False
    assert payload["has_settlement"] is True
    assert payload["profitability_claims_meaningful"] is False
    assert payload["closed_position_evaluation_supported"] is False
    assert payload["paper_profit_block_reason"] == "pending_settlement"
    assert PAPER_PNL_SENTENCE not in payload["paper_profit_note"]


def test_conflicting_settlement_outcomes_are_not_unified(tmp_path):
    rows = [
        json.loads(line)
        for line in ACCEPTANCE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows[1]["settlement"]["outcome"] = "no"
    path = tmp_path / "conflict.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    payload = _audit(path)

    assert payload["settlement_outcome"] is None
    assert payload["settlement_label_present"] is True
    assert payload["has_settlement"] is True
    assert payload["credible_settlement"] is False
    assert payload["profitability_claims_meaningful"] is False
    assert [row["settlement_outcome"] for row in payload["historical_record_qualifications"]] == [
        "yes",
        "no",
    ]


def test_calibration_sandbox_and_daily_report_do_not_explain_paper_pnl(tmp_path):
    result, repo = _sandbox(tmp_path, CALIBRATION, days=1)
    summary = result.summary
    semantics = summary["sandbox_data_semantics"]
    report = Path(result.records[0].report_path).read_text(encoding="utf-8")
    nested = result.records[0].metadata["market_data"]

    assert summary["status_counts"]["rejected"] == 1
    assert summary["status_counts"]["completed"] == 0
    assert repo.list_paper_orders() == []
    assert summary["profitability_claims_meaningful"] is False
    assert summary["market_data"]["profitability_claims_meaningful"] is False
    assert summary["market_data"]["closed_position_evaluation_supported"] is False
    assert summary["market_data"]["has_settlement"] is True
    assert summary["market_data"]["settlement_outcome"] == "no"
    assert summary["live_trading_allowed"] is False
    assert summary["safety"]["real_money_enabled"] is False
    assert summary["safety"]["allow_live_orders"] is False
    assert summary["safety"]["human_approval_required_default"] is True
    assert semantics["profitability_claims_meaningful"] is False
    assert PAPER_PNL_SENTENCE not in semantics["note"]
    assert semantics["note"] == summary["market_data"]["paper_profit_note"]
    assert nested["profitability_claims_meaningful"] is False
    assert nested["closed_position_evaluation_supported"] is False
    assert nested["has_settlement"] is False
    assert nested["settlement_outcome"] is None
    assert nested["paper_profit_note"] == semantics["note"]
    assert "Profitability claims meaningful | False" in report
    assert "Has settlement | False" in report
    assert "Closed position evaluation supported | False" in report
    assert semantics["note"] in report
    assert PAPER_PNL_SENTENCE not in report
    assert '"settlement_outcome": "no"' not in _stored_receipts(repo)


def test_acceptance_sandbox_keeps_paper_profit_wording(tmp_path):
    result, repo = _sandbox(tmp_path, ACCEPTANCE, days=2)
    summary = result.summary
    report = Path(result.records[0].report_path).read_text(encoding="utf-8")
    nested = result.records[0].metadata["market_data"]

    assert summary["profitability_claims_meaningful"] is True
    assert summary["market_data"]["has_settlement"] is True
    assert summary["market_data"]["settlement_outcome"] == "yes"
    assert summary["market_data"]["closed_position_evaluation_supported"] is True
    assert summary["sandbox_data_semantics"]["label"] == (
        "historical local dataset with settlement"
    )
    assert PAPER_PNL_SENTENCE in summary["sandbox_data_semantics"]["note"]
    assert nested["profitability_claims_meaningful"] is False
    assert nested["has_settlement"] is False
    assert nested["settlement_outcome"] is None
    assert "Profitability claims meaningful | False" in report
    assert "Has settlement | False" in report
    assert "Closed position evaluation supported | False" in report
    assert PAPER_PNL_SENTENCE not in report
    assert '"settlement_outcome": "yes"' not in _stored_receipts(repo)


def test_may1_receipt_omits_later_rows_and_may5_keeps_visible_yes(tmp_path):
    may1, repo1 = _sandbox(
        tmp_path / "may1",
        ORDINARY,
        start_date=date(2026, 5, 1),
        days=1,
        require_manual_approval=True,
    )
    may5, repo5 = _sandbox(
        tmp_path / "may5",
        ORDINARY,
        start_date=date(2026, 5, 5),
        days=1,
        require_manual_approval=True,
    )
    early = _stored_receipts(repo1)
    late_record = may5.records[0]
    late_market = late_record.metadata["market_data"]
    late_manifest = repo5.load_phase7_run_manifest(late_record.run_id)

    assert may1.records[0].status.value == "pending_manual_approval"
    assert may1.summary["market_data"]["settlement_outcome"] == "yes"
    for day in ("2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05"):
        assert day not in early
    assert '"yes"' not in early
    assert may1.records[0].metadata["market_data"]["historical_record_qualifications"] == []
    report = Path(may1.records[0].report_path).read_text(encoding="utf-8")
    assert "2026-05-05" not in report
    assert "Has settlement | False" in report

    assert late_market["settlement_outcome"] == "yes"
    assert late_market["has_settlement"] is True
    assert late_market["profitability_claims_meaningful"] is True
    assert late_market["historical_record_qualifications"] == []
    assert late_manifest is not None
    assert late_manifest.configuration_snapshot["market_data"]["settlement_outcome"] == "yes"
    assert late_manifest.metadata["market_data"]["settlement_outcome"] == "yes"
    assert "2026-05-02" not in json.dumps(late_market)
    assert "2026-05-03" not in json.dumps(late_market)
    assert "2026-05-04" not in json.dumps(late_market)


def test_acceptance_label_stays_hidden_until_publication_time():
    published_at = datetime(2026, 5, 6, 15, tzinfo=UTC)
    before = datetime(2026, 5, 6, 14, 59, tzinfo=UTC)
    may1 = datetime(2026, 5, 1, 16, tzinfo=UTC)
    file_audit = phase7_market_data_audit(
        "historical-file",
        historical_file=ACCEPTANCE,
    )
    hidden = phase7_market_data_audit(
        "historical-file",
        historical_file=ACCEPTANCE,
        as_of=before,
    )
    visible = phase7_market_data_audit(
        "historical-file",
        historical_file=ACCEPTANCE,
        as_of=published_at,
    )
    same_day = phase7_market_data_audit(
        "historical-file",
        historical_file=ACCEPTANCE,
        as_of=may1,
    )

    assert file_audit.settlement_outcome == "yes"
    assert file_audit.has_settlement is True
    assert file_audit.credible_settlement is True
    assert file_audit.profitability_claims_meaningful is True
    assert file_audit.historical_record_qualifications
    assert file_audit.historical_record_qualifications[0]["settlement_outcome"] == "yes"
    assert hidden.settlement_outcome is None
    assert hidden.has_settlement is False
    assert hidden.profitability_claims_meaningful is False
    assert hidden.closed_position_evaluation_supported is False
    assert hidden.historical_record_qualifications == ()
    assert '"yes"' not in json.dumps(hidden.as_dict())
    assert same_day.settlement_outcome is None
    assert same_day.has_settlement is False
    assert same_day.historical_end_date == "2026-05-01"
    assert "2026-05-02" not in json.dumps(same_day.as_dict())
    assert visible.settlement_outcome == "yes"
    assert visible.has_settlement is True
    assert visible.credible_settlement is True
    assert visible.profitability_claims_meaningful is True
    assert visible.historical_record_qualifications == ()


def test_acceptance_may1_sandbox_receipt_hides_unpublished_yes(tmp_path):
    result, repo = _sandbox(
        tmp_path,
        ACCEPTANCE,
        start_date=date(2026, 5, 1),
        days=1,
        require_manual_approval=True,
    )
    stored = _stored_receipts(repo)
    market = result.records[0].metadata["market_data"]
    report = Path(result.records[0].report_path).read_text(encoding="utf-8")

    assert result.summary["market_data"]["settlement_outcome"] == "yes"
    assert result.summary["profitability_claims_meaningful"] is True
    assert market["settlement_outcome"] is None
    assert market["has_settlement"] is False
    assert market["profitability_claims_meaningful"] is False
    assert market["historical_record_qualifications"] == []
    assert '"settlement_outcome": "yes"' not in stored
    assert "2026-05-02" not in stored
    assert "2026-05-06" not in stored
    assert PAPER_PNL_SENTENCE not in report
    assert "Has settlement | False" in report


def _audit(path: Path, market_id: str | None = None) -> dict[str, object]:
    args = [
        "market-data-audit",
        "--market-source",
        "historical-file",
        "--historical-file",
        str(path),
    ]
    if market_id is not None:
        args.extend(["--market-id", market_id])
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _sandbox(
    tmp_path: Path,
    historical_file: Path,
    *,
    days: int | None = None,
    start_date: date | None = None,
    require_manual_approval: bool | None = False,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        db_path=tmp_path / "qualification.sqlite",
        research_brief_dir=tmp_path / "briefs",
        risk_gates=RiskGateConfig(require_manual_approval=False),
    )
    repo = SQLiteRepository(settings.db_path)
    runner = Phase7SandboxRunner(
        repository=repo,
        settings=settings,
        report_dir=tmp_path / "reports",
        market_source="historical-file",
        historical_file=historical_file,
    )
    return runner.run(
        start_date=start_date,
        days=days,
        require_manual_approval=require_manual_approval,
        replay_sample_size=0,
    ), repo


def _stored_receipts(repo: SQLiteRepository) -> str:
    payload = {
        "records": [record.model_dump(mode="json") for record in repo.list_phase7_run_records()],
        "manifests": [
            manifest.model_dump(mode="json") for manifest in repo.list_phase7_run_manifests()
        ],
    }
    return json.dumps(payload)
