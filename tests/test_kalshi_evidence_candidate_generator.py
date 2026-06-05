from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path("scripts/local_only/generate_kalshi_evidence_candidates.py")


def load_generator_module():
    spec = importlib.util.spec_from_file_location(
        "generate_kalshi_evidence_candidates",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_candidate_generation_from_synthetic_local_search_fixtures(tmp_path: Path):
    generator = load_generator_module()
    export_dir = write_synthetic_export(tmp_path)
    fixture_query = 'official source "Will the demo metric rise"'
    search_client = generator.FixtureSearchClient(
        {
            fixture_query: [
                generator.SearchResult(
                    title="Official demo metric release",
                    url="https://official.example.org/releases/demo-metric",
                    snippet="Official public release for the demo metric before the forecast window.",
                    published_at="2026-06-05T11:00:00Z",
                    source="Official Example",
                )
            ]
        }
    )

    result = generator.generate_candidates(
        export_dir=export_dir,
        search_client=search_client,
        skip_network=True,
        use_seed_sources=False,
    )

    rows = read_jsonl(result.candidates_path)
    assert result.candidate_count == 1
    assert rows[0]["market_ticker"] == "KXDEMO-26JUN05-UP"
    assert rows[0]["url"] == "https://official.example.org/releases/demo-metric"
    assert rows[0]["published_at"] == "2026-06-05T11:00:00Z"
    assert rows[0]["retrieved_at"].endswith("Z")
    assert rows[0]["metadata"]["search_query_used"] == fixture_query
    assert result.report_path == export_dir / "evidence_candidate_generation_report.md"


def test_no_candidates_are_auto_approved(tmp_path: Path):
    generator = load_generator_module()
    export_dir = write_synthetic_export(tmp_path)
    rows = generate_fixture_rows(generator, export_dir)

    assert rows
    assert {row["reviewer_status"] for row in rows} == {"needs_more_review"}
    assert {
        row["metadata"]["reviewer_status"] for row in rows
    } == {"needs_human_review"}


def test_missing_timestamp_produces_warning(tmp_path: Path):
    generator = load_generator_module()
    export_dir = write_synthetic_export(tmp_path)
    search_client = generator.FixtureSearchClient(
        {
            'official source "Will the demo metric rise"': [
                generator.SearchResult(
                    title="Official undated demo note",
                    url="https://official.example.org/releases/undated-demo",
                    snippet="Official public page without a visible publication timestamp.",
                    source="Official Example",
                )
            ]
        }
    )

    generator.generate_candidates(
        export_dir=export_dir,
        search_client=search_client,
        skip_network=True,
        use_seed_sources=False,
    )
    row = read_jsonl(export_dir / "evidence_candidates.jsonl")[0]

    assert row["published_at"] is None
    assert row["metadata"]["timestamp_status"] == "missing"
    assert "missing_published_at" in row["metadata"]["candidate_warnings"]


def test_future_evidence_marked_when_included(tmp_path: Path):
    generator = load_generator_module()
    export_dir = write_synthetic_export(tmp_path)
    search_client = generator.FixtureSearchClient(
        {
            'official source "Will the demo metric rise"': [
                generator.SearchResult(
                    title="Official future demo release",
                    url="https://official.example.org/releases/future-demo",
                    snippet="Official public release after the forecast timestamp.",
                    published_at="2026-06-05T12:05:00Z",
                    source="Official Example",
                )
            ]
        }
    )

    generator.generate_candidates(
        export_dir=export_dir,
        search_client=search_client,
        skip_network=True,
        use_seed_sources=False,
        include_future_candidates=True,
    )
    row = read_jsonl(export_dir / "evidence_candidates.jsonl")[0]

    assert "future_evidence_candidate" in row["metadata"]["candidate_warnings"]
    assert (
        "published_after_required_evidence_before_ts"
        in row["metadata"]["candidate_warnings"]
    )


def test_future_evidence_skipped_when_not_useful(tmp_path: Path):
    generator = load_generator_module()
    export_dir = write_synthetic_export(tmp_path)
    search_client = generator.FixtureSearchClient(
        {
            'official source "Will the demo metric rise"': [
                generator.SearchResult(
                    title="Blog future demo result",
                    url="https://blog.example.net/demo-result",
                    snippet="Unofficial post-result note after the forecast timestamp.",
                    published_at="2026-06-05T12:05:00Z",
                    source="Example Blog",
                )
            ]
        }
    )

    result = generator.generate_candidates(
        export_dir=export_dir,
        search_client=search_client,
        skip_network=True,
        use_seed_sources=False,
        include_future_candidates=False,
    )

    assert result.candidate_count == 0
    assert read_jsonl(export_dir / "evidence_candidates.jsonl") == []


def test_private_or_authenticated_urls_are_blocked(tmp_path: Path):
    generator = load_generator_module()
    export_dir = write_synthetic_export(tmp_path)
    search_client = generator.FixtureSearchClient(
        {
            'official source "Will the demo metric rise"': [
                generator.SearchResult(
                    title="Private dashboard",
                    url="https://official.example.org/account/dashboard?token=secret",
                    snippet="This should not be used.",
                    published_at="2026-06-05T11:00:00Z",
                ),
                generator.SearchResult(
                    title="Localhost page",
                    url="http://localhost:8501/private",
                    snippet="This should not be used.",
                    published_at="2026-06-05T11:00:00Z",
                ),
            ]
        }
    )

    result = generator.generate_candidates(
        export_dir=export_dir,
        search_client=search_client,
        skip_network=True,
        use_seed_sources=False,
    )

    assert result.candidate_count == 0
    assert read_jsonl(export_dir / "evidence_candidates.jsonl") == []


def test_candidate_file_shape_matches_review_ui(tmp_path: Path):
    generator = load_generator_module()
    export_dir = write_synthetic_export(tmp_path)
    rows = generate_fixture_rows(generator, export_dir)
    required_top_level = {
        "market_ticker",
        "evidence_id",
        "source",
        "title",
        "url",
        "published_at",
        "retrieved_at",
        "summary",
        "relevance_score",
        "credibility_score",
        "metadata",
    }
    required_metadata = {
        "reviewer_status",
        "generated_by",
        "timestamp_status",
        "evidence_type",
        "supports_side",
        "source_public",
        "private_or_authenticated_source",
        "required_evidence_before_ts",
        "candidate_warnings",
        "search_query_used",
        "source_domain",
        "retrieval_method",
    }

    row = rows[0]
    assert required_top_level <= row.keys()
    assert required_metadata <= row["metadata"].keys()
    assert row["metadata"]["source_public"] is True
    assert row["metadata"]["private_or_authenticated_source"] is False


def test_generator_does_not_write_evidence_jsonl_or_mutate_terms_review(tmp_path: Path):
    generator = load_generator_module()
    export_dir = write_synthetic_export(tmp_path)
    manifest_path = export_dir / "source_manifest.json"
    before_manifest = manifest_path.read_text(encoding="utf-8")

    generate_fixture_rows(generator, export_dir)

    assert not (export_dir / "evidence.jsonl").exists()
    assert manifest_path.read_text(encoding="utf-8") == before_manifest
    assert json.loads(before_manifest)["terms_review"] == "pending_review"


def test_no_broker_live_order_api_terms_added():
    script_text = SCRIPT_PATH.read_text(encoding="utf-8").lower()

    forbidden = [
        "place_order",
        "submit_order",
        "live_order",
        "portfolio",
        "account_balance",
        "fills",
        "broker",
    ]
    for term in forbidden:
        assert term not in script_text


def generate_fixture_rows(generator, export_dir: Path) -> list[dict]:
    search_client = generator.FixtureSearchClient(
        {
            'official source "Will the demo metric rise"': [
                generator.SearchResult(
                    title="Official demo metric release",
                    url="https://official.example.org/releases/demo-metric",
                    snippet="Official public release for the demo metric before the forecast window.",
                    published_at="2026-06-05T11:00:00Z",
                    source="Official Example",
                )
            ]
        }
    )
    generator.generate_candidates(
        export_dir=export_dir,
        search_client=search_client,
        skip_network=True,
        use_seed_sources=False,
    )
    return read_jsonl(export_dir / "evidence_candidates.jsonl")


def write_synthetic_export(tmp_path: Path) -> Path:
    export_dir = tmp_path / "exports" / "synthetic"
    export_dir.mkdir(parents=True)
    write_json(export_dir / "source_manifest.json", manifest_row())
    write_jsonl(export_dir / "markets.jsonl", [market_row()])
    write_jsonl(
        export_dir / "candlesticks.jsonl",
        [
            candle_row("2026-06-05T12:00:00Z"),
            candle_row("2026-06-05T12:01:00Z"),
        ],
    )
    with (export_dir / "evidence_worksheet.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "market_ticker",
                "title",
                "subtitle",
                "rules_primary",
                "rules_secondary",
                "result",
                "settlement_ts",
                "earliest_candle_ts",
                "latest_candle_ts",
                "number_of_candles",
                "required_evidence_before_ts",
                "suggested_evidence_query_1",
                "suggested_evidence_query_2",
                "suggested_primary_source_type",
                "evidence_needed_count",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "market_ticker": "KXDEMO-26JUN05-UP",
                "title": "Will the demo metric rise?",
                "subtitle": "",
                "rules_primary": "YES if the metric is higher.",
                "rules_secondary": "Use the official demo metric release.",
                "result": "yes",
                "settlement_ts": "2026-06-05T12:02:00Z",
                "earliest_candle_ts": "2026-06-05T12:00:00Z",
                "latest_candle_ts": "2026-06-05T12:01:00Z",
                "number_of_candles": "2",
                "required_evidence_before_ts": "2026-06-05T12:00:00Z",
                "suggested_evidence_query_1": 'official source "Will the demo metric rise"',
                "suggested_evidence_query_2": "",
                "suggested_primary_source_type": "official statistics page",
                "evidence_needed_count": "1",
                "notes": "Synthetic worksheet.",
            }
        )
    return export_dir


def manifest_row() -> dict:
    return {
        "export_id": "synthetic",
        "terms_review": "pending_review",
        "network_used_by_adapter": False,
        "private_or_authenticated_source": False,
    }


def market_row() -> dict:
    return {
        "ticker": "KXDEMO-26JUN05-UP",
        "title": "Will the demo metric rise?",
        "subtitle": "",
        "rules_primary": "YES if the metric is higher.",
        "rules_secondary": "Use the official demo metric release.",
        "result": "yes",
        "settlement_ts": "2026-06-05T12:02:00Z",
    }


def candle_row(ts: str) -> dict:
    return {
        "market_ticker": "KXDEMO-26JUN05-UP",
        "end_period_ts": ts,
        "yes_bid": {"close_dollars": "0.40"},
        "yes_ask": {"close_dollars": "0.50"},
        "price": {"close_dollars": "0.45"},
    }


def write_json(path: Path, row: dict) -> None:
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
