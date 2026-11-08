"""Bounded public NYC weather collection; never produces trade recommendations."""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from local_market_agent.adapters.base import safe_get_json
from local_market_agent.adapters.kalshi import KalshiAdapter, liquidity_details
from local_market_agent.evidence_packet import EvidencePacket, SourceReceipt, packet_status
from local_market_agent.schemas.models import EvidenceItem, ResearchBrief, utc_now

FORECAST_URL = "https://api.weather.gov/gridpoints/OKX/33,37/forecast"
OBSERVATION_URL = "https://api.weather.gov/stations/KNYC/observations/latest"


def collect_weather_packet(output, market_id, *, allow_network=False):
    """Collect six public GETs in a new directory; no credentials, LLM or ledger.

    Restricted to the NYC daily-high series: these fixed NWS sources are not
    relevant evidence for arbitrary markets. The draft always vetoes trading.
    """
    if not allow_network:
        raise ValueError("Public collection requires explicit --allow-network")
    if not re.fullmatch(r"KXHIGHNY-\d{2}[A-Z]{3}\d{2}-(?:T|B)\d+(?:\.\d+)?", market_id):
        raise ValueError("Only KXHIGHNY daily-high markets are supported by this weather collector")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = []

    def capture(sid, url, timestamp_field=None):
        payload = safe_get_json(url)
        retrieved = utc_now()
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object from {sid}")
        target = output / (sid + ".json")
        target.write_text(json.dumps(payload, indent=2, sort_keys=True))
        published = None
        if timestamp_field:
            published = datetime.fromisoformat(payload["properties"][timestamp_field].replace("Z", "+00:00"))
            if published.tzinfo is None:
                raise ValueError(f"Timezone required from {sid}")
        receipt = SourceReceipt(source_id=sid, url=url, path=target.name,
            sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            retrieved_at=retrieved, published_at=published)
        sources.append(receipt)
        return payload, receipt

    base = KalshiAdapter.BASE_URL
    series, _ = capture("series", base + "/series/KXHIGHNY")
    if series["series"]["ticker"] != "KXHIGHNY":
        raise ValueError("Returned series does not match KXHIGHNY")
    resolution_sources = series["series"]["settlement_sources"]
    if len(resolution_sources) != 1 or not resolution_sources[0].get("url"):
        raise ValueError("Review ambiguous or missing settlement sources manually")
    forecast, forecast_receipt = capture("forecast", FORECAST_URL, "generatedAt")
    observation, observation_receipt = capture("observation", OBSERVATION_URL, "timestamp")
    event_id = market_id.rsplit("-", 1)[0]
    scan, _ = capture("event-markets", base + "/markets?event_ticker=" + quote(event_id) + "&limit=20")
    book, _ = capture("orderbook", base + "/markets/" + quote(market_id) + "/orderbook")
    market_response, market_receipt = capture("market", base + "/markets/" + quote(market_id))
    market = market_response["market"]
    if market.get("ticker") != market_id or market.get("event_ticker") != event_id:
        raise ValueError("Returned market identity does not match the request")
    snapshot = KalshiAdapter().normalize_market(market).model_copy(update={"as_of": market_receipt.retrieved_at})
    forecast_values = [{key: p[key] for key in ("name", "startTime", "endTime", "temperature", "temperatureUnit")}
                       for p in forecast["properties"]["periods"][:4]]
    if not forecast_values:
        raise ValueError("Forecast has no periods")
    observed = observation["properties"]
    evidence = []
    for receipt, title, summary, time_basis in [
        (forecast_receipt, "NWS NYC grid forecast", json.dumps(forecast_values) + "; point forecasts, not an outcome probability distribution.", "forecast generatedAt"),
        (observation_receipt, "NWS Central Park observation", json.dumps({"timestamp": observed["timestamp"], "temperature": observed["temperature"]}) + "; one observation, not a daily final maximum or future forecast.", "observation timestamp"),
    ]:
        evidence.append(EvidenceItem(source="National Weather Service", title=title, url=receipt.url,
            published_at=receipt.published_at, retrieved_at=receipt.retrieved_at, summary=summary,
            relevance_score=0.7, credibility_score=0.9,
            metadata={"source_id": receipt.source_id, "time_basis": time_basis,
                      "first_publication_verified": False, "independent_publisher": False,
                      "provenance_only": True}))
    packet = EvidencePacket(snapshot=snapshot, market_source_id="market", evidence=evidence,
        sources=sources, resolution_source=resolution_sources[0]["url"])
    source_path = output / "sources-only-packet.json"
    source_path.write_text(packet.model_dump_json(indent=2))
    initial = packet_status(source_path)
    brief = ResearchBrief(market_id=market_id, snapshot_id=snapshot.snapshot_id,
        thesis="Public NYC weather observation; no justified actionable probability estimate.",
        rationale="The captured NWS point forecast and observation support contextual research only. "
                  "Market rules: " + market["rules_primary"], evidence=evidence,
        uncertainty_notes=["Both weather items share one publisher; they are not independent confirmations.",
            "Source timestamps are generation/observation times, not verified first publication.",
            "NWS is supporting research, not the market's declared final settlement source.",
            "No calibrated distribution converts these point values into a contract probability."],
        confidence=0, evidence_quality=0, estimated_probability=None,
        market_implied_probability=snapshot.market_implied_probability,
        recommended_action="observe", must_not_trade_reasons=[
            "No defensible calibrated probability estimate from the captured point weather data.",
            "Automated observation draft requires source/brief review; no trade recommendation."],
        resolution_source=packet.resolution_source)
    packet.brief = brief
    path = output / "packet.json"
    path.write_text(packet.model_dump_json(indent=2))
    report = {"market_id": market_id, "observed_at": snapshot.as_of.isoformat(),
        "public_read_only": True, "paper_only": True, "order_created": False,
        "review_created": False, "settlement_source": packet.resolution_source,
        "liquidity": liquidity_details(market), "legacy_liquidity": market.get("liquidity_dollars", market.get("liquidity")),
        "event_scan": [{"market_id": m["ticker"], **liquidity_details(m)} for m in scan["markets"]
                       if m.get("event_ticker") == event_id],
        "scan_scope": "One response, at most 20 same-event markets; no pagination or market selection for trading",
        "orderbook_captured": isinstance(book.get("orderbook_fp"), dict),
        "before_brief": initial, "after_brief": packet_status(path),
        "limitations": brief.uncertainty_notes,
        "next_step": "Independently review source files and the exact observation brief; a review does not remove economic/risk vetoes."}
    (output / "collection.json").write_text(json.dumps(report, indent=2))
    return path
