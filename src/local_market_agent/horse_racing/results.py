"""Bounded public HKJC acquisition and offline parsing of retrospective evidence."""

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from local_market_agent.horse_racing.models import OfficialMeeting, OfficialRace, ResultRunner

BASE = "https://racing.hkjc.com"
COURSES = {"ST": "Sha Tin", "HV": "Happy Valley"}
LIMIT = 5_000_000


def result_url(day, course, race):
    return (
        BASE
        + "/en-us/local/information/localresults?"
        + urlencode({"RaceNo": race, "Racecourse": course, "racedate": day.strftime("%Y/%m/%d")})
    )


def starters_url(day, course):
    return (
        BASE
        + f"/Racing/Info/MCS/English/racing/prerace/dstr/{day:%Y%m%d}_{course}0000_S_DSTR.xml.zip"
    )


def text(node):
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def cells(row):
    return [text(c) for c in row.find_all(["td", "th"], recursive=False)]


def parse_result(raw, day, course, race, receipt):
    soup = BeautifulSoup(raw, "html.parser")
    heading = text(soup.select_one(".raceMeeting_select .f_fl"))
    expected = f"Race Meeting: {day:%d/%m/%Y} {COURSES[course]}"
    if heading != expected:
        raise ValueError("Result meeting identity mismatch")
    meta = soup.select_one(".race_tab")
    if meta is None or not re.fullmatch(rf"RACE {race} \(\d+\)", text(meta.select_one("thead td"))):
        raise ValueError("Result race identity mismatch")
    meta_rows = [cells(r) for r in meta.select("tbody > tr")]
    conditions = next((r for r in meta_rows if len(r) >= 3 and r[1] == "Going :"), None)
    track = next((r for r in meta_rows if len(r) >= 3 and r[1] == "Course :"), None)
    if not conditions or not track or not re.search(r"- (\d+)M -", conditions[0]):
        raise ValueError("Race distance/course/going metadata required")
    distance = int(re.search(r"- (\d+)M -", conditions[0])[1])
    result_tables = [
        t
        for t in soup.find_all("table")
        if text(t.find("thead"))
        == "Pla. Horse No. Horse Jockey Trainer Act. Wt. Declar. Horse Wt. Dr. LBW Running Position Finish Time Win Odds"
    ]
    dividend_tables = [
        t
        for t in soup.find_all("table")
        if text(t.find("thead")) == "Dividend Pool Winning Combination Dividend (HK$)"
    ]
    if len(result_tables) != 1 or len(dividend_tables) != 1:
        raise ValueError("Unambiguous complete result and dividend tables required")
    runners = []
    blockers = []
    for row in result_tables[0].select("tbody > tr"):
        c = cells(row)
        if len(c) != 12 or not c[1].isdigit():
            raise ValueError("Malformed full-field result row")
        runners.append(
            ResultRunner(
                horse_no=int(c[1]),
                name=c[2],
                placing=c[0],
                jockey=c[3],
                trainer=c[4],
                actual_weight=c[5],
                horse_weight=c[6],
                draw=c[7],
                final_win_odds=c[11],
            )
        )
        if not c[0].isdigit():
            blockers.append(
                "Non-numeric finish/withdrawal/dead heat requires manual settlement review"
            )
    placements = [int(r.placing) for r in runners if r.placing.isdigit()]
    if sorted(placements) != list(range(1, len(runners) + 1)):
        blockers.append("Non-contiguous/duplicate placings require manual settlement review")
    dividends = {"WIN": {}, "PLACE": {}}
    pool = None
    remaining = 0
    for row in dividend_tables[0].select("tbody > tr"):
        nodes = row.find_all(["td", "th"], recursive=False)
        c = [text(n) for n in nodes]
        if len(c) == 3:
            if remaining:
                raise ValueError("Dividend rowspan is truncated")
            pool = c.pop(0)
            remaining = int(nodes[0].get("rowspan", 1))
        elif len(c) != 2 or remaining <= 0:
            raise ValueError("Malformed dividend row/span")
        remaining -= 1
        if pool not in dividends:
            continue
        horse, value = c
        if not horse.isdigit():
            blockers.append("Unsupported WIN/PLACE refund/void/combined dividend")
            continue
        if horse in dividends[pool]:
            raise ValueError("Duplicate dividend horse")
        try:
            number = Decimal(value.replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError("Numeric official dividend required") from exc
        if not number.is_finite() or number < 10:
            raise ValueError("Official gross dividend must include the HK$10 unit stake")
        dividends[pool][horse] = number
    if remaining:
        raise ValueError("Incomplete dividend rowspan")
    numbers = {str(r.horse_no) for r in runners}
    if not set(dividends["WIN"]) <= numbers or not set(dividends["PLACE"]) <= numbers:
        raise ValueError("Dividend horse missing from full results")
    # Published pool winning combinations are authoritative; never infer place
    # qualification from the number of finishers after scratches.
    if len(dividends["WIN"]) != 1 or len(dividends["PLACE"]) not in {2, 3}:
        blockers.append("Unsupported or incomplete WIN/PLACE pools")
    winner = {str(r.horse_no) for r in runners if r.placing == "1"}
    if set(dividends["WIN"]) != winner:
        blockers.append("WIN dividend and official winner disagree")
    if not set(dividends["PLACE"]) <= {
        str(r.horse_no) for r in runners if r.placing in {"1", "2", "3"}
    }:
        blockers.append("PLACE dividend conflicts with official finishers")
    return OfficialRace(
        race_no=race,
        source_id=receipt["source_id"],
        source_url=receipt["url"],
        retrieved_at=receipt["retrieved_at"],
        title=track[0],
        distance_m=distance,
        course_detail=track[2],
        going=conditions[2],
        runners=runners,
        dividends=dividends,
        supported=not blockers,
        blockers=blockers,
    )


def parse_starters(raw, day, course, races):
    """The observed .xml.zip URL currently serves HTML; unsupported formats fail."""
    soup = BeautifulSoup(raw, "html.parser")
    header = text(soup.select_one("h2.meetingInfo"))
    prefix = f"FOR RACE MEETING ON {day:%d/%m/%Y} {COURSES[course].upper()} - "
    if not header.startswith(prefix):
        raise ValueError("Declared starters meeting identity mismatch")
    sections = [
        n
        for n in soup.select("[id]")
        if re.fullmatch(rf"{course}\d{{2}}", n.get("id", "")) and n.select_one("h3.raceInfo")
    ]
    if sorted(n["id"] for n in sections) != [f"{course}{n:02d}" for n in range(1, races + 1)]:
        raise ValueError("Requested race count differs from complete meeting declarations")
    output = {}
    for race in range(1, races + 1):
        sections = [
            n for n in soup.select(f"[id='{course}{race:02d}']") if n.select_one("h3.raceInfo")
        ]
        section = sections[0] if len(sections) == 1 else None
        if section is None:
            raise ValueError("Full meeting declarations required")
        info = text(section.select_one("h3.raceInfo"))
        if not info.startswith(f"RACE {race} - "):
            raise ValueError("Declaration race mismatch")
        start = re.match(rf"RACE {race} - (\d{{1,2}}:\d{{2}} [AP]M)\b", info)
        if not start:
            raise ValueError("Scheduled race time required for result chronology")
        scheduled = datetime.combine(
            day, datetime.strptime(start[1], "%I:%M %p").time(), ZoneInfo("Asia/Hong_Kong")
        )
        table = section.select_one("table.tbRace")
        if table is None:
            raise ValueError("Declaration table missing")
        rows = table.find_all("tr")
        expected = [
            "No",
            "Horse",
            "Brand No.",
            "Draw",
            "Gear",
            "Jockey",
            "Handicap Wt.",
            "Rtg",
            "Horse Wt.",
            "Last Winning Wt.",
            "Last Winning Date",
            "Trainer",
        ]
        if cells(rows[0]) != expected:
            raise ValueError("Unsupported declaration table headers")
        runners = []
        for row in rows[1:]:
            c = cells(row)
            if "Standby Declared Starters" in " ".join(c):
                break
            if len(c) != 12 or not re.match(r"^\d+", c[0]):
                raise ValueError("Malformed declaration row")
            number = int(re.match(r"^\d+", c[0])[0])
            runners.append(
                dict(
                    zip(
                        [
                            "horse_no_label",
                            "name",
                            "horse_id",
                            "draw",
                            "gear",
                            "jockey",
                            "handicap_weight",
                            "rating",
                            "horse_weight",
                            "last_winning_weight",
                            "last_winning_date",
                            "trainer",
                        ],
                        c,
                        strict=True,
                    )
                )
                | {"horse_no": number}
            )
        expected_count = re.findall(r"\b(\d+) Starters\b", text(section))
        if (
            len(expected_count) != 1
            or len(runners) != int(expected_count[0])
            or len({r["horse_no"] for r in runners}) != len(runners)
        ):
            raise ValueError("Declaration count/identity incomplete")
        output[str(race)] = {
            "race_no": race,
            "race_info": info,
            "scheduled_start": scheduled.isoformat(),
            "runners": runners,
            "declared_count": len(runners),
            "source_url": starters_url(day, course),
            "availability": "retrospective_archive_only",
            "pre_race_eligible": False,
            "recent_form": "UNKNOWN",
            "pre_race_odds": "UNKNOWN",
            "original_analysis": "UNKNOWN",
        }
    return output


def collect_results(output, day, *, course="ST", races=9, allow_network=False):
    if not allow_network:
        raise ValueError("Public racing collection requires --allow-network")
    day = date.fromisoformat(day) if isinstance(day, str) else day
    if course not in COURSES or not 1 <= races <= 12 or day >= datetime.now(UTC).date():
        raise ValueError("Historical meeting date, supported course and 1–12 races required")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    jobs = [(f"result-{n}", result_url(day, course, n)) for n in range(1, races + 1)] + [
        ("starters", starters_url(day, course))
    ]

    def fetch(job):
        sid, url = job
        with (
            httpx.Client(timeout=20, follow_redirects=False) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            chunks = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > LIMIT:
                    raise ValueError("Public racing source exceeds 5 MB")
                chunks.append(chunk)
            raw = b"".join(chunks)
        received = datetime.now(UTC)
        path = output / (sid + ".html")
        path.write_bytes(raw)
        return {
            "source_id": sid,
            "url": url,
            "path": path.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "retrieved_at": received.isoformat(),
            "published_at": None,
        }

    manifest = {
        "schema_version": 1,
        "meeting_date": day.isoformat(),
        "course": course,
        "race_count": races,
        "sources": [],
        "errors": [],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(fetch, j) for j in jobs]
        for job, future in zip(jobs, futures, strict=True):
            try:
                manifest["sources"].append(future.result())
            except (ValueError, OSError, httpx.HTTPError) as exc:
                manifest["errors"].append({"source_id": job[0], "error": str(exc)})
            (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if manifest["errors"]:
        raise ValueError(
            "Incomplete official source capture; retained diagnostics, no settlement allowed"
        )
    meeting = load_results(output)
    (output / "official.json").write_text(meeting.model_dump_json(indent=2))
    return meeting


def load_results(directory, *, now=None):
    directory = Path(directory).resolve()
    now = now or datetime.now(UTC)
    manifest_path = directory / "manifest.json"
    if manifest_path.stat().st_size > LIMIT:
        raise ValueError("Manifest too large")
    manifest = json.loads(manifest_path.read_text())
    day = date.fromisoformat(manifest["meeting_date"])
    course = manifest["course"]
    count = manifest["race_count"]
    if (
        manifest.get("schema_version") != 1
        or manifest.get("errors")
        or course not in COURSES
        or isinstance(count, bool)
        or not 1 <= count <= 12
    ):
        raise ValueError("Complete supported source manifest required")
    expected = {f"result-{n}": result_url(day, course, n) for n in range(1, count + 1)} | {
        "starters": starters_url(day, course)
    }
    sources = manifest["sources"]
    if len(sources) != len(expected) or {s["source_id"] for s in sources} != expected.keys():
        raise ValueError("Every race result and full declarations must have a source receipt")
    raw_by_id = {}
    receipts = {s["source_id"]: s for s in sources}
    for s in sources:
        path = (directory / s["path"]).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or path.stat().st_size > LIMIT:
            raise ValueError("Invalid official source path/size")
        raw = path.read_bytes()
        retrieved = datetime.fromisoformat(s["retrieved_at"])
        if (
            s["url"] != expected[s["source_id"]]
            or hashlib.sha256(raw).hexdigest() != s["sha256"]
            or retrieved.tzinfo is None
            or retrieved > now
        ):
            raise ValueError("Official source URL/hash/time mismatch")
        if retrieved.date() < day:
            raise ValueError("Result source cannot predate the meeting")
        raw_by_id[s["source_id"]] = raw
    parsed = [
        parse_result(raw_by_id[f"result-{n}"], day, course, n, receipts[f"result-{n}"])
        for n in range(1, count + 1)
    ]
    declarations = parse_starters(raw_by_id["starters"], day, course, count)
    for race in parsed:
        declaration = declarations[str(race.race_no)]
        if race.retrieved_at <= datetime.fromisoformat(declaration["scheduled_start"]):
            raise ValueError("Final result receipt cannot predate scheduled race start")
        declared = {r["horse_no"]: r for r in declaration["runners"]}
        actual = {r.horse_no: r for r in race.runners}
        if actual.keys() != declared.keys():
            race.blockers.append(
                "Declarations/result field changed; scratches/reserves need manual review"
            )
            race.supported = False
        places = 3 if len(declared) >= 7 else 2 if len(declared) >= 4 else 0
        expected_place = {
            str(r.horse_no)
            for r in race.runners
            if r.placing.isdigit() and 1 <= int(r.placing) <= places
        }
        if not places or set(race.dividends["PLACE"]) != expected_place:
            race.blockers.append(
                "PLACE pool incomplete or unsupported for unchanged declared field"
            )
            race.supported = False
        for number in actual.keys() & declared.keys():
            if actual[number].name != declared[number]["name"] + " " + declared[number]["horse_id"]:
                raise ValueError(
                    "Horse number/name identity differs between result and declarations"
                )
    return OfficialMeeting(
        meeting_date=day,
        course=course,
        races=parsed,
        declarations=declarations,
        source_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
