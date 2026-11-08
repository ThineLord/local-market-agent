"""Bounded read-only discovery of liquid binary sports markets."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

from local_market_agent.adapters.base import safe_get_json
from local_market_agent.adapters.kalshi import KalshiAdapter, liquidity_details
from local_market_agent.config import Settings
from local_market_agent.risk.preflight import snapshot_checks
from local_market_agent.schemas.models import utc_now


def screen_public_markets(output, *, series="KXNBAGAME", max_pages=2, allow_network=False):
    if not allow_network:
        raise ValueError("Public discovery requires --allow-network")
    if series not in {"KXNBAGAME", "KXNFLGAME"} or not 1 <= max_pages <= 5:
        raise ValueError("Supported game series and 1–5 pages required")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cursor, seen_cursors, seen_markets, rows, receipts = "", set(), set(), [], []
    settings = Settings()
    for page in range(max_pages):
        query = {"series_ticker": series, "status": "open", "limit": 200}
        if cursor:
            query["cursor"] = cursor
        url = KalshiAdapter.BASE_URL + "/markets?" + urlencode(query)
        response = safe_get_json(url)
        observed = utc_now()
        if not isinstance(response, dict) or not isinstance(response.get("markets"), list):
            raise ValueError("Malformed public market list")
        if len(response["markets"]) > 200:
            raise ValueError("Public response exceeds requested bound")
        path = output / f"page-{page + 1}.json"
        path.write_text(json.dumps(response, sort_keys=True, indent=2))
        receipts.append({"url": url, "path": path.name, "retrieved_at": observed.isoformat(),
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for market in response["markets"]:
            ticker = market.get("ticker") if isinstance(market, dict) else None
            if not isinstance(ticker, str) or not ticker.startswith(series + "-"):
                raise ValueError("Returned market does not belong to requested series")
            if ticker in seen_markets:
                raise ValueError("Duplicate market across discovery pages; refresh the scan")
            seen_markets.add(ticker)
            try:
                snapshot = KalshiAdapter().normalize_market(market).model_copy(update={"as_of": observed})
                checks = snapshot_checks(snapshot, ticker, settings, observed)
                blockers = [f"{c.code}: {c.message}" for c in checks if not c.passed]
                if isinstance(market.get("notional_value_dollars"), bool) or float(market.get("notional_value_dollars", "nan")) != 1:
                    blockers.append("Only explicitly unit-dollar binary contracts are supported")
                rows.append({"market_id": ticker, "event_ticker": market.get("event_ticker"),
                    "observed_at": observed.isoformat(), "snapshot": snapshot.model_dump(mode="json"),
                    "liquidity": liquidity_details(market), "blockers": blockers,
                    "market_checks_passed": not blockers, "probability_ready": False,
                    "source_path": path.name})
            except (ValueError, TypeError, KeyError) as exc:
                rows.append({"market_id": ticker, "observed_at": observed.isoformat(),
                    "market_checks_passed": False, "probability_ready": False,
                    "blockers": ["Invalid public market: " + str(exc)], "source_path": path.name})
        cursor = response.get("cursor") or ""
        if not isinstance(cursor, str):
            raise ValueError("Invalid public pagination cursor")
        if not cursor:
            break
        if cursor in seen_cursors:
            raise ValueError("Repeated public pagination cursor")
        seen_cursors.add(cursor)
    eligible = sorted((r for r in rows if r["market_checks_passed"]),
                      key=lambda r: (-r["liquidity"]["value_usd"], r["market_id"]))
    report = {"series": series, "created_at": utc_now().isoformat(), "sources": receipts,
        "pages": len(receipts), "market_count": len(rows), "eligible_count": len(eligible),
        "truncated": bool(cursor), "ranked_market_ids": [r["market_id"] for r in eligible],
        "markets": rows, "risk_thresholds": settings.risk.as_dict(), "order_created": False,
        "scope": "Market quote/depth screen only. Match a pregame event and validate a probability before research/order approval."}
    (output / "screen.json").write_text(json.dumps(report, indent=2))
    return report
