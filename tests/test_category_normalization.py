from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from typer.testing import CliRunner

import local_market_agent.eval.category_normalization as normalization_module
import local_market_agent.eval.collector_diagnostics as diagnostics_module
from local_market_agent.cli import app
from local_market_agent.eval.category_normalization import (
    NORMALIZED_CRYPTO,
    NORMALIZED_ECONOMICS_OTHER,
    NORMALIZED_FED_POLICY_MACRO,
    NORMALIZED_MENTION_MARKET,
    NORMALIZED_SPORTS_MAJOR,
    NORMALIZED_SPORTS_TENNIS,
    NORMALIZED_UNKNOWN,
    NORMALIZED_WEATHER,
    WARNING_MENTION_MARKET_FORMAT,
    WARNING_PUBLIC_EVENT_SOURCE_OVERRIDDEN,
    WARNING_SOURCE_SEMANTIC_MISMATCH,
    normalize_market_category,
)
from local_market_agent.eval.collector_diagnostics import (
    FILTER_LOSS_NON_BINARY,
    FILTER_LOSS_NOT_FINALIZED,
    FILTER_LOSS_UNRESOLVED,
    build_collector_diagnostics,
)


def test_tennis_public_event_normalized_to_sports_tennis_with_mismatch_warning():
    result = normalize_market_category(
        _market(
            "KXWTAMATCH-26APR07VOLVEK-VEK",
            "public_event",
            "Will Donna Vekic win the Volynets vs Vekic professional tennis match?",
        )
    )

    assert result.source_category == "public_event"
    assert result.normalized_category == NORMALIZED_SPORTS_TENNIS
    assert result.semantic_category == NORMALIZED_SPORTS_TENNIS
    assert WARNING_SOURCE_SEMANTIC_MISMATCH in result.warnings
    assert WARNING_PUBLIC_EVENT_SOURCE_OVERRIDDEN in result.warnings


def test_major_sports_market_normalized_to_sports_major():
    result = normalize_market_category(
        _market(
            "KXMLB-26MAYNYYBOS-NYY",
            "major_sports",
            "Will the Yankees beat the Red Sox in the MLB baseball game?",
        )
    )

    assert result.normalized_category == NORMALIZED_SPORTS_MAJOR
    assert result.semantic_category == NORMALIZED_SPORTS_MAJOR
    assert WARNING_SOURCE_SEMANTIC_MISMATCH not in result.warnings


def test_fed_rate_cpi_market_normalized_to_fed_policy_macro():
    result = normalize_market_category(
        _market(
            "KXFOMCDECISION-26MAY-RATECUT",
            "public_event",
            "Will the Fed cut interest rates after the FOMC meeting?",
        )
    )

    assert result.normalized_category == NORMALIZED_FED_POLICY_MACRO
    assert result.semantic_category == NORMALIZED_FED_POLICY_MACRO
    assert WARNING_PUBLIC_EVENT_SOURCE_OVERRIDDEN in result.warnings


def test_fed_macro_positive_policy_boundaries():
    cases = [
        (
            "KXFOMC-26JUN",
            "Will the FOMC change monetary policy after the June meeting?",
        ),
        (
            "KXFEDFUNDS-26JUN",
            "Will the federal funds target range be above 5%?",
        ),
        (
            "KXRATECUT-26JUN",
            "Will the Federal Reserve announce an interest-rate cut?",
        ),
        (
            "KXRATEHIKE-26JUN",
            "Will the Fed announce rate hikes this year?",
        ),
        (
            "KXCPI-26JUN",
            "Will CPI inflation be above forecast?",
        ),
    ]

    for ticker, title in cases:
        result = normalize_market_category(_market(ticker, "public_event", title))
        assert result.normalized_category == NORMALIZED_FED_POLICY_MACRO
        assert result.semantic_category == NORMALIZED_FED_POLICY_MACRO


def test_macro_indicator_boundaries_stay_generic_economics_other():
    cases = [
        (
            "KXUNEMPLOY-26JUN",
            "Will unemployment be above 5% after the jobs report?",
        ),
        (
            "KXNONFARMPAYROLLS-26JUN",
            "Will nonfarm payrolls exceed economist expectations?",
        ),
        (
            "KXGDP-26JUN",
            "Will GDP growth be above 2%?",
        ),
        (
            "KXTREASURY-26JUN",
            "Will the 10-year treasury yield close above 5%?",
        ),
    ]

    for ticker, title in cases:
        result = normalize_market_category(_market(ticker, "public_event", title))
        assert result.normalized_category == NORMALIZED_ECONOMICS_OTHER
        assert result.semantic_category == NORMALIZED_ECONOMICS_OTHER


def test_fed_macro_negative_boundaries_do_not_overmatch():
    stock = normalize_market_category(
        _market(
            "KXTSLAEARNINGS-26JUN",
            "public_event",
            "Will Tesla stock rise after company earnings?",
        )
    )
    crypto = normalize_market_category(
        _market(
            "KXBTCPRICE-26JUN",
            "crypto",
            "Will Bitcoin close above $100,000?",
        )
    )
    sports = normalize_market_category(
        _market(
            "KXMLB-26JUNNYYBOS-NYY",
            "major_sports",
            "Will the Yankees beat the Red Sox in the MLB baseball game?",
        )
    )

    assert stock.normalized_category != NORMALIZED_FED_POLICY_MACRO
    assert crypto.normalized_category == NORMALIZED_CRYPTO
    assert crypto.normalized_category != NORMALIZED_FED_POLICY_MACRO
    assert sports.normalized_category == NORMALIZED_SPORTS_MAJOR
    assert sports.normalized_category != NORMALIZED_FED_POLICY_MACRO


def test_weather_market_normalized_to_weather():
    result = normalize_market_category(
        _market(
            "KXNYCRAIN-26MAY",
            "weather",
            "Will New York City receive rain tomorrow?",
        )
    )

    assert result.normalized_category == NORMALIZED_WEATHER
    assert result.semantic_category == NORMALIZED_WEATHER


def test_mention_market_detected_separately_from_topic():
    result = normalize_market_category(
        _market(
            "KXPERSONMENTION-26APR07-WEAT",
            "weather",
            "What will any NASA Participant say during Daily news conference?",
            rules_primary=(
                "If any NASA Participant says Weather as part of Daily news "
                "conference on Artemis II, then the market resolves to Yes."
            ),
        )
    )

    assert result.normalized_category == NORMALIZED_MENTION_MARKET
    assert result.semantic_category == NORMALIZED_WEATHER
    assert result.is_mention_market is True
    assert WARNING_MENTION_MARKET_FORMAT in result.warnings


def test_fed_mention_market_keeps_mention_override_and_semantic_topic():
    result = normalize_market_category(
        _market(
            "KXPERSONMENTION-26JUN-FED",
            "public_event",
            "What will Jerome Powell say during the Fed press conference?",
            rules_primary=(
                "If Jerome Powell says interest rates as part of the Federal Reserve "
                "press conference, then the market resolves to Yes."
            ),
        )
    )

    assert result.normalized_category == NORMALIZED_MENTION_MARKET
    assert result.semantic_category == NORMALIZED_FED_POLICY_MACRO
    assert result.is_mention_market is True
    assert WARNING_MENTION_MARKET_FORMAT in result.warnings


def test_public_event_is_not_final_category_when_semantic_signal_exists():
    result = normalize_market_category(
        _market(
            "KXBTCPRICE-26MAY",
            "public_event",
            "Will Bitcoin close above $100,000?",
        )
    )

    assert result.source_category == "public_event"
    assert result.normalized_category != "public_event"
    assert result.normalized_category != "public_event_generic"
    assert WARNING_PUBLIC_EVENT_SOURCE_OVERRIDDEN in result.warnings


def test_unknown_market_handled_safely():
    result = normalize_market_category(
        {
            "ticker": "KXUNKNOWN-26MAY",
            "title": "",
            "metadata": {},
        }
    )

    assert result.source_category == NORMALIZED_UNKNOWN
    assert result.normalized_category == NORMALIZED_UNKNOWN
    assert result.semantic_category == NORMALIZED_UNKNOWN
    assert result.confidence == "low"


def test_collector_diagnostics_aggregates_counts_and_failure_reasons():
    diagnostics = build_collector_diagnostics(
        pre_filter_categories=[
            NORMALIZED_SPORTS_TENNIS,
            NORMALIZED_SPORTS_TENNIS,
            NORMALIZED_WEATHER,
        ],
        post_filter_categories=[NORMALIZED_SPORTS_TENNIS, NORMALIZED_WEATHER],
        selected_categories=[NORMALIZED_SPORTS_TENNIS],
        filter_losses={
            FILTER_LOSS_UNRESOLVED: 1,
            FILTER_LOSS_NOT_FINALIZED: 2,
            FILTER_LOSS_NON_BINARY: 3,
        },
        candle_results=[
            (True, None),
            (False, "no_candles_returned"),
            (NORMALIZED_WEATHER, False, "insufficient_pre_settlement_candles"),
            (NORMALIZED_SPORTS_TENNIS, True, None),
        ],
        selected_row_counts={NORMALIZED_SPORTS_TENNIS: 8},
        quota_targets={NORMALIZED_SPORTS_TENNIS: 2, NORMALIZED_WEATHER: 2},
    )

    payload = diagnostics.as_dict()
    assert payload["discovered_count"] == 3
    assert payload["pre_filter_category_counts"][NORMALIZED_SPORTS_TENNIS] == 2
    assert payload["selected_category_counts"][NORMALIZED_SPORTS_TENNIS] == 1
    assert payload["filter_losses"]["unresolved_loss"] == 1
    assert payload["filter_losses"]["not_finalized_loss"] == 2
    assert payload["filter_losses"]["non_binary_loss"] == 3
    assert payload["candle_attempt_count"] == 4
    assert payload["candle_success_count"] == 2
    assert payload["candle_failure_count"] == 2
    assert payload["candle_failure_reasons"]["no_candles_returned"] == 1
    assert payload["per_category"]["sports_tennis"]["candle_attempt_count"] == 1
    assert payload["per_category"]["sports_tennis"]["candle_success_count"] == 1
    assert payload["per_category"]["sports_tennis"]["selected_row_count"] == 8
    assert payload["per_category"]["weather"]["candle_failure_count"] == 1
    assert payload["per_category"]["weather"]["candle_failure_reasons"] == {
        "insufficient_pre_settlement_candles": 1
    }
    assert payload["quota_shortfalls"] == {
        NORMALIZED_SPORTS_TENNIS: 1,
        NORMALIZED_WEATHER: 2,
    }
    assert payload["availability_limitations"]


def test_normalize_category_export_cli_writes_json_and_markdown(tmp_path: Path):
    export_dir = _write_export(
        tmp_path,
        [
            _market(
                "KXWTAMATCH-26APR07VOLVEK-VEK",
                "public_event",
                "Will Donna Vekic win the Volynets vs Vekic professional tennis match?",
            ),
            _market(
                "KXPERSONMENTION-26APR07-WEAT",
                "weather",
                "What will any NASA Participant say during Daily news conference?",
                rules_primary=(
                    "If any NASA Participant says Weather as part of Daily news "
                    "conference on Artemis II, then the market resolves to Yes."
                ),
            ),
        ],
        unselected_candidates=[
            {
                "ticker": "KXFEDRATE-26APR",
                "title": "Will the Federal Reserve announce a rate cut?",
                "source_category": "unknown",
                "normalized_category": NORMALIZED_FED_POLICY_MACRO,
                "semantic_category": NORMALIZED_FED_POLICY_MACRO,
                "warnings": [],
            }
        ],
    )

    result = CliRunner().invoke(
        app,
        [
            "normalize-category-export",
            "--source-export-dir",
            str(export_dir),
            "--output-dir",
            str(tmp_path / "reports"),
            "--docs-report-path",
            str(tmp_path / "docs" / "normalization.md"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["market_count"] == 2
    assert payload["normalized_category_counts"][NORMALIZED_SPORTS_TENNIS] == 1
    assert payload["normalized_category_counts"][NORMALIZED_MENTION_MARKET] == 1
    assert payload["public_event_mismatch_count"] == 1
    assert payload["mention_market_count"] == 1
    assert payload["guardrails"]["taxonomy_infrastructure_only"] is True
    assert Path(payload["json_path"]).exists()
    assert Path(payload["markdown_path"]).exists()
    assert Path(payload["docs_markdown_path"]).exists()
    markdown = Path(payload["markdown_path"]).read_text(encoding="utf-8")
    assert "Kalshi Category Normalization Result" in markdown
    assert "Collector Diagnostics Schema" in markdown
    report = json.loads(Path(payload["json_path"]).read_text(encoding="utf-8"))
    assert report["source_export"]["unselected_candidates_status"] == "loaded"
    assert report["summary"]["unselected_candidate_count"] == 1
    assert report["summary"]["unselected_candidate_category_counts"] == {
        NORMALIZED_FED_POLICY_MACRO: 1
    }


def test_category_normalization_adds_no_broker_live_or_order_api():
    combined_source = "\n".join(
        [
            inspect.getsource(normalization_module),
            inspect.getsource(diagnostics_module),
        ]
    )
    tree = ast.parse(combined_source)
    referenced_symbols = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    forbidden_symbols = {
        "PaperLedger",
        "PaperOrder",
        "PaperOrderIntent",
        "RiskEngine",
        "RiskGateEvaluator",
        "ExecutionMode.LIVE",
        "create_order",
        "open_position",
    }
    assert forbidden_symbols.isdisjoint(referenced_symbols)
    assert "local_market_agent.paper" not in combined_source
    assert "local_market_agent.risk" not in combined_source


def _write_export(
    tmp_path: Path,
    markets: list[dict[str, object]],
    *,
    unselected_candidates: list[dict[str, object]] | None = None,
) -> Path:
    export_dir = tmp_path / "source_exports" / "synthetic_normalization_export"
    export_dir.mkdir(parents=True)
    (export_dir / "markets.jsonl").write_text(
        "\n".join(json.dumps(market, sort_keys=True) for market in markets) + "\n",
        encoding="utf-8",
    )
    if unselected_candidates is not None:
        (export_dir / "unselected_candidates.jsonl").write_text(
            "\n".join(
                json.dumps(candidate, sort_keys=True)
                for candidate in unselected_candidates
            )
            + "\n",
            encoding="utf-8",
        )
    return export_dir


def _market(
    ticker: str,
    category: str,
    title: str,
    *,
    rules_primary: str | None = None,
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "event_ticker": ticker.rsplit("-", maxsplit=1)[0],
        "series_ticker": ticker.split("-", maxsplit=1)[0],
        "title": title,
        "rules_primary": rules_primary or title,
        "status": "finalized",
        "market_type": "binary",
        "metadata": {
            "calibration_category": category,
            "market_type": "binary",
            "source_family": "synthetic",
        },
    }
