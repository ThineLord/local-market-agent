"""Prepare a source-bound, pregame NBA research packet; never approve an order."""

import hashlib
import json
import shutil
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from local_market_agent.adapters.base import safe_get_json
from local_market_agent.adapters.kalshi import KalshiAdapter, liquidity_details
from local_market_agent.config import Settings
from local_market_agent.evidence_packet import EvidencePacket, SourceReceipt, packet_status
from local_market_agent.nba_guard import MAX_HISTORY_AGE_SECONDS
from local_market_agent.nba_probability import (
    MODEL_SPEC,
    candidate_support,
    chronological_predictions,
    home_probability,
    load_history,
    parse_time,
    validate_predictions,
)
from local_market_agent.public_screen import screen_public_markets
from local_market_agent.schemas.models import EvidenceItem, ResearchBrief, utc_now

# Explicit provider/contract identities; never infer a team by fuzzy text matching.
TEAMS = {
    "1": ("ATL", "Atlanta"),
    "2": ("BOS", "Boston"),
    "3": ("NOP", "New Orleans"),
    "4": ("CHI", "Chicago"),
    "5": ("CLE", "Cleveland"),
    "6": ("DAL", "Dallas"),
    "7": ("DEN", "Denver"),
    "8": ("DET", "Detroit"),
    "9": ("GSW", "Golden State"),
    "10": ("HOU", "Houston"),
    "11": ("IND", "Indiana"),
    "12": ("LAC", "Los Angeles C"),
    "13": ("LAL", "Los Angeles L"),
    "14": ("MIA", "Miami"),
    "15": ("MIL", "Milwaukee"),
    "16": ("MIN", "Minnesota"),
    "17": ("BKN", "Brooklyn"),
    "18": ("NYK", "New York"),
    "19": ("ORL", "Orlando"),
    "20": ("PHI", "Philadelphia"),
    "21": ("PHX", "Phoenix"),
    "22": ("POR", "Portland"),
    "23": ("SAC", "Sacramento"),
    "24": ("SAS", "San Antonio"),
    "25": ("OKC", "Oklahoma City"),
    "26": ("UTA", "Utah"),
    "27": ("WAS", "Washington"),
    "28": ("TOR", "Toronto"),
    "29": ("MEM", "Memphis"),
    "30": ("CHA", "Charlotte"),
}
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


SECONDARY_RULE = (
    "If the game is postponed but begins within 48 hours of its originally scheduled start time, "
    "the market will remain open and resolve based on the official final result. If the game is "
    "cancelled or not started within 48 hours of its originally scheduled start, all markets will "
    "resolve to a fair price. Kalshi is not affiliated, associated, authorized, endorsed by, or in "
    "any way officially connected with the Governing League. All trademarks, logos, and brand "
    "names are the property of their respective owners."
)


def contract_requirements(market, series):
    depth = liquidity_details(market)
    notional = market.get("notional_value_dollars")
    if (
        depth["basis"] != "minimum_best_ask_buy_capacity_usd"
        or isinstance(notional, bool)
        or float(notional or "nan") != 1
    ):
        raise ValueError("Unit-dollar contract and exact best-quote depth required")
    if (
        series["series"]["ticker"] != "KXNBAGAME"
        or {"name": "the Governing League", "url": "https://www.nba.com"}
        not in series["series"]["settlement_sources"]
    ):
        raise ValueError("Expected NBA governing-league settlement source required")
    return depth


def input_requirements(audit, validation, support, observed):
    return {
        "source_hashes": True,
        "complete_history": audit["complete_historical_seasons"],
        "pregame_identity": True,
        "unit_dollar_rules": True,
        "current_history": 0
        <= (observed - parse_time(audit["current_history_oldest_retrieval"])).total_seconds()
        <= MAX_HISTORY_AGE_SECONDS,
        "holdout_validation": validation["passed"],
        "bin_support": support["enough_bin_data"],
        "conservative_edge": support["conservative_edge_passed"],
    }


def match_event(market, events, *, now):
    if " ".join(market.get("rules_secondary", "").split()) != SECONDARY_RULE:
        raise ValueError("Unsupported NBA postponement/cancellation rule version")
    matches = []
    for event, observed in events:
        if len(event.get("competitions", [])) != 1:
            continue
        c = event["competitions"][0]
        if len(c.get("competitors", [])) != 2:
            continue
        home = next((t for t in c["competitors"] if t.get("homeAway") == "home"), None)
        away = next((t for t in c["competitors"] if t.get("homeAway") == "away"), None)
        if not home or not away or home["id"] not in TEAMS or away["id"] not in TEAMS:
            continue
        start = parse_time(event["date"])
        date = start.astimezone(ZoneInfo("America/New_York"))
        key = f"KXNBAGAME-{date.year % 100:02d}{MONTHS[date.month - 1]}{date.day:02d}{TEAMS[away['id']][0]}{TEAMS[home['id']][0]}"
        if market.get("event_ticker") != key:
            continue
        codes = {TEAMS[home["id"]][0]: home["id"], TEAMS[away["id"]][0]: away["id"]}
        suffix = market["ticker"].removeprefix(key + "-")
        if suffix not in codes or market["ticker"] != key + "-" + suffix:
            raise ValueError("Exact YES team identity is required")
        yes = codes[suffix]
        name = TEAMS[yes][1]
        rule = f"If {name} wins the {TEAMS[away['id']][1]} vs {TEAMS[home['id']][1]} Pro Basketball game originally scheduled for {MONTHS[date.month - 1].title()} {date.day}, {date.year}, then the market resolves to Yes."
        if (
            market.get("yes_sub_title") != name
            or market.get("title") != name + " wins"
            or market.get("rules_primary") != rule
        ):
            raise ValueError("Contract wording does not match the exact NBA game/team rule")
        if (
            event.get("season", {}).get("year") != MODEL_SPEC["forward_season"]
            or event.get("season", {}).get("type") != 2
            or c.get("type", {}).get("id") != "1"
            or c.get("timeValid") is not True
            or not isinstance(c.get("neutralSite"), bool)
            or str(c.get("id")) != str(event["id"])
        ):
            raise ValueError(
                "Current regular-season standard game with verified schedule time required"
            )
        status = c["status"]["type"]
        if status.get("state") != "pre" or status.get("completed") is not False or now >= start:
            raise ValueError("NBA Elo is pregame only; game has started or is not scheduled")
        if (
            not 0
            <= (now - observed).total_seconds()
            <= Settings().risk_gates.max_market_data_age_seconds
        ):
            raise ValueError("Current event-status observation required")
        matches.append(
            {
                "event_id": str(event["id"]),
                "event_start": start.isoformat(),
                "event_observed_at": observed.isoformat(),
                "event_state": "pre",
                "home_id": home["id"],
                "away_id": away["id"],
                "yes_team_id": yes,
                "neutral": c["neutralSite"],
                "rule": rule,
                "event_ticker": key,
            }
        )
    if len(matches) != 1:
        raise ValueError("Exactly one matching current pregame event required")
    return matches[0]


def build_nba_packet(output, history, *, allow_network=False):
    if not allow_network:
        raise ValueError("Public NBA workflow requires --allow-network")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    packet_dir = output / "packet"
    packet_dir.mkdir()
    now = utc_now()
    history = Path(history).resolve()
    games, audit = load_history(history, now=now)
    predictions, ratings, state = chronological_predictions(games, cutoff=now)
    validation = validate_predictions(predictions, audit)
    oldest = parse_time(audit["current_history_oldest_retrieval"])
    if (
        not 0 <= (now - oldest).total_seconds() <= MAX_HISTORY_AGE_SECONDS
        or state["last_season"] != MODEL_SPEC["forward_season"]
    ):
        raise ValueError(
            "Refresh current-season history; current rating state and source age are required"
        )
    sources = []

    def capture(sid, url):
        payload = safe_get_json(url)
        received = utc_now()
        path = packet_dir / (sid + ".json")
        path.write_text(json.dumps(payload, sort_keys=True, indent=2))
        if path.stat().st_size > 5_000_000:
            raise ValueError("Public response exceeds source limit")
        sources.append(
            SourceReceipt(
                source_id=sid,
                url=url,
                path=path.name,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                retrieved_at=received,
            )
        )
        return payload, received

    def analysis(sid, payload):
        created = utc_now()
        path = packet_dir / (sid + ".json")
        path.write_text(json.dumps(payload, sort_keys=True, indent=2))
        receipt = SourceReceipt(
            source_id=sid,
            url="analysis://nba-elo/" + sid,
            path=path.name,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            retrieved_at=created,
            published_at=created,
        )
        sources.append(receipt)
        return receipt

    events = []
    today = now.astimezone(ZoneInfo("America/New_York")).date()
    for offset in range(3):
        date = today + timedelta(days=offset)
        url = (
            "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates="
            + date.strftime("%Y%m%d")
            + "&limit=100"
        )
        data, received = capture(f"scoreboard-{date.isoformat()}", url)
        if not isinstance(data.get("events"), list) or len(data["events"]) > 100:
            raise ValueError("Malformed/unbounded NBA scoreboard")
        events.extend((event, received) for event in data["events"])
    series, _ = capture("series", KalshiAdapter.BASE_URL + "/series/KXNBAGAME")
    if (
        series["series"]["ticker"] != "KXNBAGAME"
        or {"name": "the Governing League", "url": "https://www.nba.com"}
        not in series["series"]["settlement_sources"]
    ):
        raise ValueError("Expected NBA governing-league settlement source required")
    screen = screen_public_markets(output / "screen", series="KXNBAGAME", allow_network=True)
    public = {
        m["ticker"]: m
        for receipt in screen["sources"]
        for m in json.loads((output / "screen" / receipt["path"]).read_text())["markets"]
    }
    rows = []
    selected = None
    fallback = None
    settings = Settings()
    for ticker in screen["ranked_market_ids"]:
        market = public[ticker]
        try:
            match = match_event(market, events, now=utc_now())
            snapshot = KalshiAdapter().normalize_market(market)
            p_home = home_probability(ratings, match["home_id"], match["away_id"], match["neutral"])
            support = candidate_support(
                predictions,
                p_home,
                match["yes_team_id"] == match["home_id"],
                snapshot,
                settings.risk,
            )
            passed = (
                validation["passed"]
                and support["conservative_edge_passed"]
                and support["edge_support_fraction"] >= settings.risk.min_confidence
            )
            rows.append(
                {
                    "market_id": ticker,
                    "match": match,
                    "liquidity": liquidity_details(market),
                    "support": support,
                    "model_eligible": passed,
                }
            )
            if fallback is None:
                fallback = (market, match)
            if passed and selected is None:
                selected = (market, match)
        except (ValueError, KeyError, TypeError) as exc:
            rows.append({"market_id": ticker, "model_eligible": False, "blockers": [str(exc)]})
    (output / "candidates.json").write_text(
        json.dumps(
            {
                "screen_count": screen["market_count"],
                "depth_eligible": screen["eligible_count"],
                "selection_policy": "Highest screened conservative depth among supported pregame forecasts; one packet only; no tuning to market prices",
                "rows": rows,
            },
            indent=2,
        )
    )
    selected = selected or fallback
    if selected is None:
        raise ValueError(
            "No exact pregame candidate in bounded three-day coverage; see candidates.json"
        )
    market, match = selected
    # Every historical file remains available under this packet for independent replay.
    (packet_dir / "history").mkdir()
    for record in json.loads((history / "receipts.json").read_text()):
        source = history / record["path"]
        target = packet_dir / "history" / source.name
        shutil.copyfile(source, target)
        sources.append(
            SourceReceipt(
                source_id=f"history-{record['season']}-{record['team_id']}",
                url=record["url"],
                path=str(target.relative_to(packet_dir)),
                sha256=record["sha256"],
                retrieved_at=parse_time(record["retrieved_at"]),
            )
        )
    for name in ("protocol.json", "receipts.json"):
        target = packet_dir / "history" / name
        shutil.copyfile(history / name, target)
        sources.append(
            SourceReceipt(
                source_id="history-" + name.removesuffix(".json"),
                url="analysis://nba-elo/" + name,
                path=str(target.relative_to(packet_dir)),
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                retrieved_at=utc_now(),
            )
        )
    validation_receipt = analysis(
        "validation",
        {
            "analysis_as_of": now.isoformat(),
            "audit": audit,
            "validation": validation,
            "state": state,
            "ratings": ratings,
            "source_manifest": json.loads((history / "receipts.json").read_text()),
        },
    )
    event_receipt = analysis("event-match", match)
    capture("orderbook", KalshiAdapter.BASE_URL + "/markets/" + market["ticker"] + "/orderbook")
    final, observed = capture("market", KalshiAdapter.BASE_URL + "/markets/" + market["ticker"])
    final = final["market"]
    if final["ticker"] != market["ticker"]:
        raise ValueError("Final market does not match selected candidate")
    final_match = match_event(final, events, now=observed)
    if final_match != match:
        raise ValueError("Event mapping changed during preparation")
    snapshot = KalshiAdapter().normalize_market(final).model_copy(update={"as_of": observed})
    depth = contract_requirements(final, series)
    p_home = home_probability(ratings, match["home_id"], match["away_id"], match["neutral"])
    support = candidate_support(
        predictions, p_home, match["yes_team_id"] == match["home_id"], snapshot, settings.risk
    )
    input_checks = input_requirements(audit, validation, support, observed)
    guard = {
        "analysis_as_of": now.isoformat(),
        "model_spec": MODEL_SPEC,
        "market_id": snapshot.market.market_id,
        "snapshot_id": snapshot.snapshot_id,
        "last_season": state["last_season"],
        "event_start": match["event_start"],
        "event_observed_at": match["event_observed_at"],
        "event_state": match["event_state"],
        "current_history_oldest_retrieval": audit["current_history_oldest_retrieval"],
        "validation": validation,
        "match": match,
        "home_rating": ratings[match["home_id"]],
        "away_rating": ratings[match["away_id"]],
        "support": support,
        "input_checks": input_checks,
    }
    evidence = []
    for receipt, title, summary in [
        (
            validation_receipt,
            "Frozen NBA Elo validation",
            f"Retrospective independent holdout n={validation['holdout_n']}; raw Elo Brier={validation['brier']:.6f}, baseline={validation['baseline_brier']:.6f}, ECE={validation['ece']:.6f}. Full source receipts retained. Not a trading backtest.",
        ),
        (
            event_receipt,
            "Exact NBA pregame identity",
            f"ESPN event {match['event_id']}, home={match['home_id']}, away={match['away_id']}, YES={match['yes_team_id']}; start={match['event_start']}. State observed pregame, not final outcome evidence.",
        ),
    ]:
        evidence.append(
            EvidenceItem(
                source="Local analysis of public ESPN NBA data",
                title=title,
                url=receipt.url,
                published_at=receipt.published_at,
                retrieved_at=receipt.retrieved_at,
                summary=summary,
                relevance_score=1,
                credibility_score=1,
                metadata={
                    "source_id": receipt.source_id,
                    "source_type": "local_derived_analysis",
                    "independent_forecast_sources": False,
                },
            )
        )
    evidence[0].metadata.update(model=MODEL_SPEC["model"], nba_forecast=guard)
    vetoes = [
        "NBA model prerequisite failed: " + key for key, value in input_checks.items() if not value
    ]
    brief = ResearchBrief(
        market_id=snapshot.market.market_id,
        snapshot_id=snapshot.snapshot_id,
        thesis="Fixed historical NBA model probability with explicitly validated pregame scope.",
        rationale="Raw Elo uses only prior final scores and home/neutral status. Candidate direction is supported by a frozen holdout residual stress check; confidence is its edge-support fraction, not a probability of winning.",
        evidence=evidence,
        uncertainty_notes=validation["limitations"]
        + [
            "Historical and schedule evidence share ESPN; these are not two independent probability models.",
            "Current roster/injury changes are not modelled; residual-transfer assumptions can fail for this specific game.",
            "Postponement/cancellation can resolve to fair price under the contract; no automatic settlement is created.",
        ],
        confidence=support["edge_support_fraction"],
        evidence_quality=sum(input_checks.values()) / len(input_checks),
        estimated_probability=support["raw_probability_yes"],
        market_implied_probability=snapshot.market_implied_probability,
        recommended_action=("paper_buy_yes" if support["side"] == "BUY_YES" else "paper_buy_no")
        if not vetoes
        else "observe",
        must_not_trade_reasons=vetoes,
        resolution_source="https://www.nba.com",
    )
    packet = EvidencePacket(
        snapshot=snapshot,
        market_source_id="market",
        evidence=evidence,
        sources=sources,
        resolution_source=brief.resolution_source,
        brief=brief,
    )
    path = packet_dir / "packet.json"
    path.write_text(packet.model_dump_json(indent=2))
    status = packet_status(path)
    (output / "result.json").write_text(
        json.dumps(
            {
                "selected_market": snapshot.market.market_id,
                "liquidity": depth,
                "support": support,
                "validation": validation,
                "packet": str(path),
                "status": status,
                "order_created": False,
                "approval_created": False,
            },
            indent=2,
        )
    )
    return path


def verify_nba_packet(packet, directory):
    """Reproduce the labelled model from receipt-bound files, offline, on import.

    A local review is still required; checksums do not authenticate an external
    publisher. Execution subsequently seals these verified inputs.
    """
    directory = Path(directory)
    markers = [e for e in packet.evidence if e.metadata.get("model") == MODEL_SPEC["model"]]
    if len(markers) != 1 or packet.brief is None:
        raise ValueError("One NBA model proof and brief required")
    proof = markers[0].metadata["nba_forecast"]
    cutoff = parse_time(proof["analysis_as_of"])
    if cutoff > packet.snapshot.as_of:
        raise ValueError("Model analysis cannot follow the market observation")
    sources = {s.source_id: s for s in packet.sources}
    for name in ("protocol", "receipts"):
        receipt = sources["history-" + name]
        if (
            receipt.path != "history/" + name + ".json"
            or receipt.url != "analysis://nba-elo/" + name + ".json"
        ):
            raise ValueError("History protocol/manifest receipt mismatch")
    manifest = json.loads((directory / "history/receipts.json").read_text())
    for record in manifest:
        receipt = sources[f"history-{record['season']}-{record['team_id']}"]
        if (
            receipt.path != "history/" + record["path"]
            or receipt.url != record["url"]
            or receipt.sha256 != record["sha256"]
            or receipt.retrieved_at != parse_time(record["retrieved_at"])
        ):
            raise ValueError("History and packet source receipts disagree")
    games, audit = load_history(directory / "history", now=cutoff)
    predictions, ratings, state = chronological_predictions(games, cutoff=cutoff)
    validation = validate_predictions(predictions, audit)
    market_receipt = sources[packet.market_source_id]
    market = json.loads((directory / market_receipt.path).read_text())["market"]
    if (
        market_receipt.url
        != KalshiAdapter.BASE_URL + "/markets/" + packet.snapshot.market.market_id
    ):
        raise ValueError("Exact public market endpoint required")
    series_receipt = sources["series"]
    if (
        series_receipt.url != KalshiAdapter.BASE_URL + "/series/KXNBAGAME"
        or packet.resolution_source != "https://www.nba.com"
    ):
        raise ValueError("Exact NBA governing-league resolution provenance required")
    contract_requirements(market, json.loads((directory / series_receipt.path).read_text()))
    normalized = KalshiAdapter().normalize_market(market)
    excluded = {"as_of", "snapshot_id"}
    if (
        packet.snapshot.model_dump(exclude=excluded) != normalized.model_dump(exclude=excluded)
        or packet.snapshot.as_of != market_receipt.retrieved_at
    ):
        raise ValueError("Packet snapshot must reproduce the original public quote")
    events = []
    for sid, receipt in sources.items():
        if sid.startswith("scoreboard-"):
            date = sid.removeprefix("scoreboard-").replace("-", "")
            expected = (
                "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates="
                + date
                + "&limit=100"
            )
            if receipt.url != expected:
                raise ValueError("Exact public NBA scoreboard endpoint required")
            events.extend(
                (e, receipt.retrieved_at)
                for e in json.loads((directory / receipt.path).read_text())["events"]
            )
    match = match_event(market, events, now=packet.snapshot.as_of)
    p_home = home_probability(ratings, match["home_id"], match["away_id"], match["neutral"])
    support = candidate_support(
        predictions,
        p_home,
        match["yes_team_id"] == match["home_id"],
        packet.snapshot,
        Settings().risk,
    )
    expected = {
        "model_spec": MODEL_SPEC,
        "market_id": packet.snapshot.market.market_id,
        "snapshot_id": packet.snapshot.snapshot_id,
        "last_season": state["last_season"],
        "event_start": match["event_start"],
        "event_state": match["event_state"],
        "event_observed_at": match["event_observed_at"],
        "current_history_oldest_retrieval": audit["current_history_oldest_retrieval"],
        "validation": validation,
        "match": match,
        "home_rating": ratings[match["home_id"]],
        "away_rating": ratings[match["away_id"]],
        "support": support,
        "input_checks": input_requirements(audit, validation, support, packet.snapshot.as_of),
    }
    if any(proof[key] != value for key, value in expected.items()):
        raise ValueError("NBA forecast proof does not reproduce from its public source files")
    derived = json.loads((directory / sources["validation"].path).read_text())
    if derived != {
        "analysis_as_of": cutoff.isoformat(),
        "audit": audit,
        "validation": validation,
        "state": state,
        "ratings": ratings,
        "source_manifest": manifest,
    }:
        raise ValueError("Derived NBA validation report does not reproduce")
    if json.loads((directory / sources["event-match"].path).read_text()) != match:
        raise ValueError("Derived NBA event mapping does not reproduce")
    return True
