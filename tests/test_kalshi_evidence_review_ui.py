from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("scripts/local_only/review_kalshi_evidence.py")


def load_review_module():
    spec = importlib.util.spec_from_file_location(
        "review_kalshi_evidence",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_loads_synthetic_export_and_candidates(tmp_path: Path):
    review = load_review_module()
    export_root, export_id = write_synthetic_export(tmp_path)

    workspace = review.load_review_workspace(
        export_id=export_id,
        export_root=export_root,
    )

    assert workspace.export_id == export_id
    assert workspace.export_dir == export_root / export_id
    assert workspace.candidate_source_path == workspace.export_dir / "evidence_candidates.jsonl"
    assert len(workspace.markets) == 1
    assert workspace.markets[0]["market_ticker"] == "KXDEMO-26JUN05-UP"
    assert workspace.markets[0]["title"] == "Will the demo metric rise?"
    assert workspace.markets[0]["rules_primary"] == "YES if the metric is higher."
    assert workspace.markets[0]["earliest_candle_timestamp"] == "2026-06-05T12:00:00Z"
    assert workspace.markets[0]["latest_candle_timestamp"] == "2026-06-05T12:01:00Z"
    assert workspace.markets[0]["required_evidence_before_ts"] == "2026-06-05T12:00:00Z"
    assert workspace.markets[0]["candle_count"] == 2
    assert len(workspace.candidates) == 2


def test_blocks_approval_for_future_evidence(tmp_path: Path):
    review = load_review_module()
    export_root, export_id = write_synthetic_export(tmp_path)
    workspace = review.load_review_workspace(export_id=export_id, export_root=export_root)
    candidate = dict(workspace.candidates[0])
    candidate["published_at"] = "2026-06-05T12:01:00Z"

    validation = review.validate_candidate_for_approval(
        candidate,
        workspace.markets_by_ticker[candidate["market_ticker"]],
    )

    assert "published_at is after required_evidence_before_ts" in validation.blocking_errors
    assert "evidence only covers late candles" in validation.warnings
    assert not validation.can_approve


def test_blocks_todo_placeholders(tmp_path: Path):
    review = load_review_module()
    export_root, export_id = write_synthetic_export(tmp_path, with_candidates=False)
    workspace = review.load_review_workspace(export_id=export_id, export_root=export_root)

    validation = review.validate_candidate_for_approval(
        workspace.candidates[0],
        workspace.markets_by_ticker[workspace.candidates[0]["market_ticker"]],
    )

    assert "placeholder/TODO values remain" in validation.blocking_errors
    assert not validation.can_approve


def test_template_fallback_is_flagged(tmp_path: Path):
    review = load_review_module()
    export_root, export_id = write_synthetic_export(tmp_path, with_candidates=False)
    workspace = review.load_review_workspace(export_id=export_id, export_root=export_root)

    assert workspace.candidate_source_path == workspace.export_dir / "evidence_template.jsonl"
    assert review.using_template_fallback(workspace) is True


def test_first_market_to_expand_prefers_unreviewed_candidates(tmp_path: Path):
    review = load_review_module()
    export_root, export_id = write_synthetic_export(tmp_path)
    workspace = review.load_review_workspace(export_id=export_id, export_root=export_root)
    first_market = workspace.markets[0]
    second_market = {**first_market, "market_ticker": "KXSECOND-26JUN05-UP"}
    candidates_by_market = {
        first_market["market_ticker"]: [
            {**dict(workspace.candidates[0]), "reviewer_status": "approved"}
        ],
        second_market["market_ticker"]: [
            {**dict(workspace.candidates[1]), "reviewer_status": "needs_more_review"}
        ],
    }

    expanded = review.first_market_to_expand(
        (first_market, second_market),
        candidates_by_market,
    )

    assert expanded == "KXSECOND-26JUN05-UP"


def test_writes_review_state_json(tmp_path: Path):
    review = load_review_module()
    export_root, export_id = write_synthetic_export(tmp_path)
    workspace = review.load_review_workspace(export_id=export_id, export_root=export_root)
    rows = [dict(row) for row in workspace.candidates]
    rows[0]["reviewer_status"] = "approved"
    rows[1]["reviewer_status"] = "rejected"
    rows[1]["rejection_reason"] = "Not early enough for the worksheet window."

    result = review.write_review_outputs(
        workspace=workspace,
        review_rows=rows,
        reviewed_by="unit_reviewer",
        overwrite_evidence=True,
    )
    state = json.loads(result.state_path.read_text(encoding="utf-8"))

    assert result.state_path == workspace.export_dir / "evidence_review_state.json"
    assert state["schema_version"] == review.APP_VERSION
    assert state["reviewed_by"] == "unit_reviewer"
    assert state["counts"]["approved"] == 1
    assert state["counts"]["rejected"] == 1
    assert state["local_only"] is True
    assert state["network_used"] is False


def test_does_not_export_when_no_rows_are_approved(tmp_path: Path):
    review = load_review_module()
    export_root, export_id = write_synthetic_export(tmp_path)
    workspace = review.load_review_workspace(export_id=export_id, export_root=export_root)
    rows = [dict(row) for row in workspace.candidates]
    rows[0]["reviewer_status"] = "rejected"
    rows[1]["reviewer_status"] = "needs_more_review"

    with pytest.raises(ValueError, match="no approved evidence rows"):
        review.write_review_outputs(
            workspace=workspace,
            review_rows=rows,
            reviewed_by="unit_reviewer",
            overwrite_evidence=True,
        )

    assert not (workspace.export_dir / "evidence.jsonl").exists()


def test_rejected_rows_require_rejection_reason_before_export(tmp_path: Path):
    review = load_review_module()
    export_root, export_id = write_synthetic_export(tmp_path)
    workspace = review.load_review_workspace(export_id=export_id, export_root=export_root)
    rows = [dict(row) for row in workspace.candidates]
    rows[0]["reviewer_status"] = "approved"
    rows[1]["reviewer_status"] = "rejected"
    rows[1]["rejection_reason"] = ""

    with pytest.raises(ValueError, match="rejected evidence requires rejection_reason"):
        review.write_review_outputs(
            workspace=workspace,
            review_rows=rows,
            reviewed_by="unit_reviewer",
            overwrite_evidence=True,
        )

    assert not (workspace.export_dir / "evidence.jsonl").exists()


def test_writes_evidence_jsonl_with_approved_rows_only(tmp_path: Path):
    review = load_review_module()
    export_root, export_id = write_synthetic_export(tmp_path)
    workspace = review.load_review_workspace(export_id=export_id, export_root=export_root)
    rows = [dict(row) for row in workspace.candidates]
    rows[0]["reviewer_status"] = "approved"
    rows[0]["reviewer_note"] = "Reviewed against the local worksheet."
    rows[1]["reviewer_status"] = "needs_more_review"

    result = review.write_review_outputs(
        workspace=workspace,
        review_rows=rows,
        reviewed_by="unit_reviewer",
        overwrite_evidence=True,
    )
    evidence_rows = read_jsonl(result.evidence_path)

    assert result.approved_count == 1
    assert len(evidence_rows) == 1
    assert evidence_rows[0]["market_ticker"] == "KXDEMO-26JUN05-UP"
    assert evidence_rows[0]["evidence_id"] == "ev_demo_metric_release"
    assert evidence_rows[0]["published_at"] == "2026-06-05T11:00:00Z"
    assert evidence_rows[0]["retrieved_at"] == "2026-06-05T13:00:00Z"
    assert evidence_rows[0]["metadata"]["reviewer_status"] == "approved"
    assert evidence_rows[0]["metadata"]["reviewed_by"] == "unit_reviewer"
    assert evidence_rows[0]["metadata"]["source_public"] is True
    assert evidence_rows[0]["metadata"]["private_or_authenticated_source"] is False


def test_review_session_state_key_changes_when_candidate_file_changes(tmp_path: Path):
    review = load_review_module()
    export_root, export_id = write_synthetic_export(tmp_path)
    workspace = review.load_review_workspace(export_id=export_id, export_root=export_root)
    first_key = review.review_session_state_key(workspace)
    candidate_path = workspace.export_dir / "evidence_candidates.jsonl"
    existing = read_jsonl(candidate_path)
    existing.append(candidate_row("ev_demo_added_note", "Added public note"))
    write_jsonl(candidate_path, existing)

    second_key = review.review_session_state_key(workspace)

    assert first_key != second_key
    assert str(candidate_path) in second_key


def test_does_not_overwrite_existing_evidence_jsonl_without_explicit_flag(tmp_path: Path):
    review = load_review_module()
    export_root, export_id = write_synthetic_export(tmp_path)
    workspace = review.load_review_workspace(export_id=export_id, export_root=export_root)
    existing_path = workspace.export_dir / "evidence.jsonl"
    existing_payload = '{"market_ticker":"KEEP"}\n'
    existing_path.write_text(existing_payload, encoding="utf-8")
    rows = [dict(row) for row in workspace.candidates]
    rows[0]["reviewer_status"] = "approved"

    with pytest.raises(FileExistsError, match="already exists"):
        review.write_review_outputs(
            workspace=workspace,
            review_rows=rows,
            reviewed_by="unit_reviewer",
            overwrite_evidence=False,
        )

    assert existing_path.read_text(encoding="utf-8") == existing_payload


def test_review_script_has_no_network_browser_scraper_or_live_order_calls():
    source = SCRIPT_PATH.read_text(encoding="utf-8").lower()

    forbidden_terms = (
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
        "import socket",
        "from socket",
        "import webbrowser",
        "selenium",
        "playwright",
        "scrapy",
        "beautifulsoup",
        "broker.submit",
        "place_order",
        "submit_order",
        "live_order",
        "withdraw",
        "leverage",
    )
    assert all(term not in source for term in forbidden_terms)


def write_synthetic_export(
    tmp_path: Path,
    *,
    with_candidates: bool = True,
) -> tuple[Path, str]:
    export_root = tmp_path / "kalshi"
    export_id = "kalshi_sprint1_unit_review"
    export_dir = export_root / export_id
    export_dir.mkdir(parents=True)
    (export_dir / "source_manifest.json").write_text(
        json.dumps(
            {
                "export_id": export_id,
                "dataset_id": "phase7g_kalshi_sprint1_unit_review",
                "source_name": "kalshi_public_export_fixture",
                "source_type": "public_research_export",
                "source_urls": ["https://example.com/kalshi-public-export-demo"],
                "retrieved_at": "2026-06-05T13:00:00Z",
                "exported_at": "2026-06-05T13:05:00Z",
                "terms_review": "pending_review",
                "terms_reviewed_by": "pending_review",
                "terms_reviewed_at": "2026-06-05T13:05:00Z",
                "private_or_authenticated_source": False,
                "network_used_by_adapter": False,
                "raw_file_sha256": {
                    "markets.jsonl": "fixture_markets_sha256",
                    "candlesticks.jsonl": "fixture_candlesticks_sha256",
                    "evidence.jsonl": "fixture_evidence_sha256",
                },
                "notes": "Synthetic local review fixture.",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_jsonl(
        export_dir / "markets.jsonl",
        [
            {
                "ticker": "KXDEMO-26JUN05-UP",
                "title": "Will the demo metric rise?",
                "subtitle": "Synthetic market",
                "rules_primary": "YES if the metric is higher.",
                "rules_secondary": "Use the public demo reading.",
                "result": "yes",
                "settlement_ts": "2026-06-05T12:30:00Z",
            }
        ],
    )
    write_jsonl(
        export_dir / "candlesticks.jsonl",
        [
            candle("KXDEMO-26JUN05-UP", "2026-06-05T12:00:00Z"),
            candle("KXDEMO-26JUN05-UP", "2026-06-05T12:01:00Z"),
        ],
    )
    (export_dir / "evidence_worksheet.csv").write_text(
        "\n".join(
            [
                "market_ticker,title,subtitle,rules_primary,rules_secondary,result,settlement_ts,earliest_candle_ts,latest_candle_ts,number_of_candles,required_evidence_before_ts",
                "KXDEMO-26JUN05-UP,Will the demo metric rise?,Synthetic market,YES if the metric is higher.,Use the public demo reading.,yes,2026-06-05T12:30:00Z,2026-06-05T12:00:00Z,2026-06-05T12:01:00Z,2,2026-06-05T12:00:00Z",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    template_rows = [
        {
            "market_ticker": "KXDEMO-26JUN05-UP",
            "evidence_id": "TODO_KXDEMO_evidence_1",
            "source": "TODO_public_source_name",
            "title": "TODO_public_evidence_title",
            "url": "TODO_public_url",
            "published_at": "TODO_published_at",
            "retrieved_at": "TODO_retrieved_at",
            "summary": "TODO_public_summary",
            "relevance_score": 0.0,
            "credibility_score": 0.0,
            "metadata": {"placeholder": True, "replace_before_import": True},
        }
    ]
    write_jsonl(export_dir / "evidence_template.jsonl", template_rows)
    if with_candidates:
        write_jsonl(
            export_dir / "evidence_candidates.jsonl",
            [
                candidate_row("ev_demo_metric_release", "Public metric release"),
                candidate_row("ev_demo_context_note", "Public context note"),
            ],
        )
    return export_root, export_id


def candidate_row(evidence_id: str, title: str) -> dict[str, object]:
    return {
        "market_ticker": "KXDEMO-26JUN05-UP",
        "evidence_id": evidence_id,
        "source": "demo_public_source",
        "title": title,
        "url": f"https://public.example.org/{evidence_id}",
        "published_at": "2026-06-05T11:00:00Z",
        "retrieved_at": "2026-06-05T13:00:00Z",
        "summary": "The public demo release documented the relevant pre-market metric.",
        "relevance_score": 0.9,
        "credibility_score": 0.85,
        "timestamp_status": "explicit_utc",
        "evidence_type": "public_forecast_time_evidence",
        "supports_side": "context_or_rule",
        "curator_notes": "Published before the first sampled candle.",
        "metadata": {"source_public": True},
    }


def candle(ticker: str, timestamp: str) -> dict[str, object]:
    return {
        "market_ticker": ticker,
        "end_period_ts": timestamp,
        "yes_bid": {"close_dollars": "0.40"},
        "yes_ask": {"close_dollars": "0.42"},
        "price": {"close_dollars": "0.41"},
    }


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
