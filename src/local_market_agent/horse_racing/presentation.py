"""Recompute a local read-only racing view from source inputs, never trust cached totals."""

from pathlib import Path

from local_market_agent.horse_racing.models import HistoricalRecord
from local_market_agent.horse_racing.replay import replay_history
from local_market_agent.horse_racing.research import empty_research, load_research, read_bounded
from local_market_agent.horse_racing.results import load_results


def build_report(record, official=None, research=None):
    report = replay_history(record, official)
    research = research or empty_research(record.meeting_date, record.course, len(record.races))
    if (research["meeting_date"], research["course"], len(research["races"])) != (
        record.meeting_date.isoformat(),
        record.course,
        len(record.races),
    ):
        raise ValueError("Research audit and historical meeting differ")
    report["research"] = research
    report["full_fields"] = []
    for race in record.races:
        declaration = official.declarations.get(str(race.race_no)) if official else None
        result = (
            next((r for r in official.races if r.race_no == race.race_no), None)
            if official
            else None
        )
        report["full_fields"].append(
            {
                "race_no": race.race_no,
                "status": "retrospective_official_archive" if declaration else "UNKNOWN",
                "course_detail": result.course_detail if result else None,
                "going": result.going if result else None,
                "distance_m": result.distance_m if result else None,
                "source_url": declaration["source_url"] if declaration else None,
                "runners": declaration["runners"] if declaration else [],
                "pre_race_eligible": False,
                "strengths": "UNKNOWN: original pre-race form and reasoning not inferred from results",
                "weaknesses": "UNKNOWN: original pre-race form and reasoning not inferred from results",
            }
        )
    report["orders_created"] = 0
    return report


def workspace_payload(directory=None):
    if directory is None:
        return {"status": "missing", "report": None}
    directory = Path(directory)
    try:
        record = HistoricalRecord.model_validate_json(read_bounded(directory / "user-history.json"))
        official = (
            load_results(directory / "official") if (directory / "official").exists() else None
        )
        research = (
            load_research(directory / "research") if (directory / "research").exists() else None
        )
        return {"status": "available", "report": build_report(record, official, research)}
    except (ValueError, KeyError, TypeError, OSError, RuntimeError):
        return {"status": "invalid", "report": None}
