from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path("scripts/local_only/collect_kalshi_sprint2_evidence_friendly.py")


def load_collector_module():
    script_dir = str(SCRIPT_PATH.parent.resolve())
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location(
        "collect_kalshi_sprint2_evidence_friendly",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_market_scoring_favors_macro_weather_and_major_events():
    collector = load_collector_module()
    cpi = collector.score_candidate_market(
        market_row(
            ticker="KXCPI-26JUN",
            title="Will CPI inflation be above 3.0%?",
            rules_primary="Resolved according to the official Bureau of Labor Statistics CPI release.",
            open_time="2026-05-01T00:00:00Z",
            close_time="2026-06-12T12:00:00Z",
        )
    )
    weather = collector.score_candidate_market(
        market_row(
            ticker="KXWEATHER-26JUN",
            title="Will the National Weather Service report high temperature above 90F?",
            rules_primary="Resolved using the official National Weather Service observation.",
            open_time="2026-05-30T00:00:00Z",
            close_time="2026-06-05T23:00:00Z",
        )
    )
    nba = collector.score_candidate_market(
        market_row(
            ticker="KXNBA-26FINALS",
            title="Will the NBA Finals game go over 210 points?",
            rules_primary="Resolved using the official NBA game result.",
            open_time="2026-05-25T00:00:00Z",
            close_time="2026-06-06T02:00:00Z",
        )
    )

    assert cpi.category == "economic_indicator"
    assert weather.category == "weather"
    assert nba.category == "major_sports"
    assert cpi.score > 70
    assert weather.score > 60
    assert nba.score > 45
    assert not cpi.hard_exclude
    assert not weather.hard_exclude
    assert not nba.hard_exclude


def test_market_scoring_rejects_btc_15m_micro_markets():
    collector = load_collector_module()

    score = collector.score_candidate_market(
        market_row(
            ticker="KXBTC15M-26JUN050015-15",
            title="BTC price up in next 15 mins?",
            rules_primary="If the BRTI average before 12:15 is above 12:00, resolves yes.",
            open_time="2026-06-05T04:00:00Z",
            close_time="2026-06-05T04:15:00Z",
        )
    )

    assert score.hard_exclude
    assert "excluded_micro_price_market" in score.reasons


def test_market_scoring_rejects_obscure_low_info_events():
    collector = load_collector_module()

    tennis_score = collector.score_candidate_market(
        market_row(
            ticker="KXITFMATCH-26JUN04KOYSIN-SIN",
            title="Will Colin Sinclair win the Koyama vs Sinclair: M15 Harmon Quarterfinal match?",
            rules_primary="If Colin Sinclair wins the professional tennis match, resolves yes.",
            open_time="2026-06-04T15:00:00Z",
            close_time="2026-06-05T04:00:00Z",
        )
    )
    college_baseball_score = collector.score_candidate_market(
        market_row(
            ticker="KXNCAABBGAME-26APR071500TOWCOP-COP",
            title="Towson vs Coppin State winner?",
            rules_primary=(
                "If Coppin State wins the Towson vs Coppin State College Baseball "
                "game, then the market resolves to Yes."
            ),
            open_time="2026-04-06T15:00:00Z",
            close_time="2026-04-07T19:00:00Z",
        )
    )

    assert tennis_score.hard_exclude
    assert "excluded_obscure_low_info_sports" in tennis_score.reasons
    assert college_baseball_score.category != "economic_indicator"
    assert college_baseball_score.hard_exclude
    assert "excluded_obscure_low_info_sports" in college_baseball_score.reasons


def test_market_scoring_rejects_mentions_and_avoids_house_false_positive():
    collector = load_collector_module()

    mention_score = collector.score_candidate_market(
        market_row(
            ticker="KXFEDGOVMENTION-26APR07-RATE",
            title=(
                "What will Austan Goolsbee say during Detroit Economic Club: "
                "A Conversation on The Economy and Monetary Policy?"
            ),
            rules_primary="Resolves according to whether the speaker mentions rates.",
            open_time="2026-04-07T10:00:00Z",
            close_time="2026-04-07T18:00:00Z",
        )
    )
    player_prop_score = collector.score_candidate_market(
        market_row(
            ticker="KXMLBHR-26APR061845STLWSH-WSHBHOUSE12-1",
            title="Brady House: 1+ home runs?",
            rules_primary="Resolved using the official MLB baseball game statistics.",
            open_time="2026-04-06T12:00:00Z",
            close_time="2026-04-06T23:00:00Z",
        )
    )

    assert mention_score.hard_exclude
    assert "excluded_mention_or_transcript_market" in mention_score.reasons
    assert player_prop_score.category != "election_public_policy"


def test_output_schema_compatible_with_pr_data_3(tmp_path: Path):
    collector = load_collector_module()
    export_dir = tmp_path / "kalshi_sprint2_evidence_friendly_test"
    export_dir.mkdir()
    selected = [selected_market(collector)]
    candidates = collector.build_evidence_candidates(
        selected,
        skip_metadata_fetch=True,
    )
    collector.sprint1.write_jsonl(
        export_dir / "markets.jsonl",
        [collector.to_export_market(selected[0])],
    )
    collector.sprint1.write_jsonl(
        export_dir / "candlesticks.jsonl",
        list(selected[0].candles),
    )
    collector.sprint1.write_jsonl(export_dir / "evidence.jsonl", [])
    collector.sprint1.write_jsonl(export_dir / "evidence_candidates.jsonl", candidates)
    manifest = collector.build_manifest(
        export_id="kalshi_sprint2_evidence_friendly_test",
        export_dir=export_dir,
        selected=selected,
        discovered_count=1,
        scored_count=1,
        rejected_count=0,
        candidate_count=len(candidates),
        terms_review="pending_review",
    )

    market = read_jsonl(export_dir / "markets.jsonl")[0]
    candle = read_jsonl(export_dir / "candlesticks.jsonl")[0]
    assert {"ticker", "title", "result", "settlement_ts", "rules_primary"} <= market.keys()
    assert {"market_ticker", "end_period_ts", "yes_bid", "yes_ask", "price"} <= candle.keys()
    assert manifest["terms_review"] == "pending_review"
    assert manifest["private_or_authenticated_source"] is False
    assert manifest["network_used_by_adapter"] is False
    assert manifest["raw_file_sha256"]["evidence.jsonl"]


def test_candidate_statuses_are_never_auto_approved():
    collector = load_collector_module()

    candidates = collector.build_evidence_candidates(
        [selected_market(collector)],
        skip_metadata_fetch=True,
    )

    assert candidates
    assert {row["reviewer_status"] for row in candidates} == {"needs_more_review"}
    assert {
        row["metadata"]["reviewer_status"] for row in candidates
    } == {"needs_human_review"}
    assert "approved" not in {row["reviewer_status"] for row in candidates}


def test_network_failure_diagnostic_is_explicit():
    collector = load_collector_module()
    client = collector.sprint1.KalshiPublicClient()
    client.requested_urls.extend(
        [
            "https://external-api.kalshi.com/trade-api/v2/markets?status=settled",
            (
                "https://external-api.kalshi.com/trade-api/v2/"
                "historical/markets/KXTEST/candlesticks?period_interval=60"
            ),
        ]
    )

    diagnostic = collector.build_network_failure_diagnostic(
        RuntimeError("Kalshi public GET failed for https://example.test: SSL EOF"),
        client=client,
        export_id="kalshi_sprint2_evidence_friendly_test",
        output_root=Path("data/source_exports/kalshi"),
    )

    assert diagnostic["network_status"] == "network_blocked_or_tls_failure"
    assert diagnostic["endpoint_families_attempted"] == [
        "historical_market_candlesticks",
        "live_settled_markets",
    ]
    assert diagnostic["safety"]["tls_verification_disabled"] is False
    assert diagnostic["safety"]["private_or_authenticated_source"] is False


def test_no_broker_live_order_account_api_added():
    script = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    forbidden = (
        "place_order",
        "submit_order",
        "live_order",
        "account_balance",
        "portfolio_position",
        "fills_endpoint",
        "broker_client",
        "api_key",
    )

    for term in forbidden:
        assert term not in script


def selected_market(collector):
    raw = market_row(
        ticker="KXCPI-26JUN",
        title="Will CPI inflation be above 3.0%?",
        rules_primary="Resolved according to the official Bureau of Labor Statistics CPI release.",
        open_time="2026-05-01T00:00:00Z",
        close_time="2026-06-12T12:00:00Z",
    )
    market = collector.sprint1.CandidateMarket(
        source_family="historical_markets",
        raw=raw,
        ticker=raw["ticker"],
        series_ticker="KXCPI",
        title=raw["title"],
        status=raw["status"],
        result=raw["result"],
        settlement_ts=raw["settlement_ts"],
        volume=1000.0,
    )
    score = collector.score_candidate_market(raw)
    return collector.SelectedMarket(
        market=market,
        score=score,
        period_interval=60,
        candles=(
            candle_row("2026-06-10T12:00:00Z"),
            candle_row("2026-06-11T12:00:00Z"),
        ),
    )


def market_row(
    *,
    ticker: str,
    title: str,
    rules_primary: str,
    open_time: str,
    close_time: str,
) -> dict:
    return {
        "ticker": ticker,
        "event_ticker": ticker.rsplit("-", maxsplit=1)[0],
        "series_ticker": ticker.split("-", maxsplit=1)[0],
        "title": title,
        "status": "finalized",
        "result": "yes",
        "market_type": "binary",
        "open_time": open_time,
        "close_time": close_time,
        "expected_expiration_time": close_time,
        "latest_expiration_time": close_time,
        "settlement_ts": close_time,
        "rules_primary": rules_primary,
        "rules_secondary": "Public official-source rule.",
        "volume_fp": "1000.0",
        "settlement_value_dollars": "1.0000",
    }


def candle_row(ts: str) -> dict:
    return {
        "market_ticker": "KXCPI-26JUN",
        "end_period_ts": ts,
        "period_interval": 60,
        "yes_bid": {"close_dollars": "0.40"},
        "yes_ask": {"close_dollars": "0.50"},
        "price": {"close_dollars": "0.45"},
        "metadata": {"quote_source": "kalshi_candlestick_close_bid_ask"},
    }


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
