from __future__ import annotations

import json
from pathlib import Path

import pytest

from local_market_agent.operations import load_historical_dataset


def test_historical_dataset_sorts_records_and_reports_warning(tmp_path):
    path = tmp_path / "unsorted.jsonl"
    _write_jsonl(
        path,
        [
            _record("2026-05-02", bid=0.51, ask=0.53, last_price=0.52),
            _record("2026-05-01", bid=0.49, ask=0.51, last_price=0.50),
        ],
    )

    dataset = load_historical_dataset(path)

    assert [record.record_date.isoformat() for record in dataset.records] == [
        "2026-05-01",
        "2026-05-02",
    ]
    assert any("sorted" in warning.lower() for warning in dataset.warnings)


def test_historical_dataset_rejects_duplicate_market_date(tmp_path):
    path = tmp_path / "duplicate.jsonl"
    _write_jsonl(
        path,
        [
            _record("2026-05-01"),
            _record("2026-05-01", last_price=0.52),
        ],
    )

    with pytest.raises(ValueError, match="duplicate"):
        load_historical_dataset(path)


def test_historical_dataset_rejects_missing_bid_or_ask(tmp_path):
    path = tmp_path / "missing-ask.jsonl"
    payload = _record("2026-05-01")
    payload.pop("ask")
    _write_jsonl(path, [payload])

    with pytest.raises(ValueError, match="ask"):
        load_historical_dataset(path)


def test_historical_dataset_rejects_invalid_spread(tmp_path):
    path = tmp_path / "invalid-spread.jsonl"
    _write_jsonl(path, [_record("2026-05-01", bid=0.62, ask=0.58)])

    with pytest.raises(ValueError, match="invalid spread"):
        load_historical_dataset(path)


def test_historical_dataset_rejects_future_evidence(tmp_path):
    path = tmp_path / "future-evidence.jsonl"
    payload = _record("2026-05-01")
    payload["evidence"] = [
        {
            "title": "Future note",
            "summary": "Published after the historical market row.",
            "published_at": "2026-05-02T10:00:00Z",
            "relevance_score": 0.9,
            "credibility_score": 0.9,
        }
    ]
    _write_jsonl(path, [payload])

    with pytest.raises(ValueError, match="published after"):
        load_historical_dataset(path)


def _record(
    date: str,
    *,
    bid: float = 0.49,
    ask: float = 0.51,
    last_price: float = 0.50,
) -> dict[str, object]:
    return {
        "date": date,
        "market_id": "hist-test-market",
        "bid": bid,
        "ask": ask,
        "last_price": last_price,
        "implied_probability": round((bid + ask) / 2, 4),
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
