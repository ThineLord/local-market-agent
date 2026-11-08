"""Fixed-budget public NBA schedule acquisition for the frozen Elo protocol."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from local_market_agent.adapters.base import safe_get_json
from local_market_agent.nba_probability import MODEL_SPEC, TEAM_IDS
from local_market_agent.schemas.models import utc_now


def collect_nba_history(output, *, allow_network=False):
    if not allow_network:
        raise ValueError("History collection requires --allow-network")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    protocol = {
        **MODEL_SPEC,
        "frozen_at": utc_now().isoformat(),
        "retrospective_not_point_in_time": True,
        "history_requests_max": 120,
        "retry_max_per_request": 1,
    }
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2))

    def fetch(job):
        season, team = job
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team}/schedule?season={season}&seasontype=2"
        errors = []
        for _ in range(2):
            try:
                payload = safe_get_json(url)
                retrieved = utc_now().isoformat()
                if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
                    raise ValueError("Malformed public schedule")
                raw = json.dumps(payload, sort_keys=True).encode()
                if len(raw) > 5_000_000:
                    raise ValueError("Schedule exceeds source size limit")
                name = f"{season}-team-{team}.json"
                (output / name).write_bytes(raw)
                return {
                    "season": season,
                    "team_id": team,
                    "url": url,
                    "path": name,
                    "retrieved_at": retrieved,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                    "event_count": len(payload["events"]),
                    "earlier_attempt_errors": errors,
                }
            except (ValueError, OSError, RuntimeError) as exc:
                errors.append(str(exc))
        return {"season": season, "team_id": team, "url": url, "errors": errors}

    jobs = [(s, t) for s in (2024, 2025, 2026, 2027) for t in sorted(TEAM_IDS, key=int)]
    receipts = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(fetch, jobs):
            receipts.append(result)
            (output / "receipts.json").write_text(json.dumps(receipts, indent=2))
    if any("errors" in r for r in receipts):
        raise ValueError(
            "Incomplete public history; inspect saved receipts; no validation is allowed"
        )
    return output
