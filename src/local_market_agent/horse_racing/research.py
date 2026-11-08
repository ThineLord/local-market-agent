"""Point-in-time input audit and descriptive comparison; no probability model or orders."""

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, model_validator

from local_market_agent.horse_racing.models import (
    HorseNumber,
    PositiveMoney,
    RaceNumber,
    StrictModel,
)

SHA = r"^[0-9a-f]{64}$"


class Source(StrictModel):
    source_id: str = Field(min_length=1)
    path: str
    sha256: str = Field(pattern=SHA)
    category: Literal["pre_race", "availability_evidence", "budget"]
    captured_at: AwareDatetime
    claimed_available_at: AwareDatetime
    description: str = Field(min_length=1)


class FormRun(StrictModel):
    race_date: date
    available_at: AwareDatetime
    course: str
    surface: str
    distance_m: int = Field(gt=0)
    finish: int | None = Field(default=None, ge=1)
    field_size: int = Field(ge=1)

    @model_validator(mode="after")
    def finish_in_field(self):
        if self.finish is not None and self.finish > self.field_size:
            raise ValueError("Finish exceeds field size")
        return self


class Quote(StrictModel):
    # Gross return per one dollar, inclusive of principal. No silent net/gross conversion.
    notation: Literal["gross_decimal_indicative"]
    observed_at: AwareDatetime
    low: float = Field(ge=1, allow_inf_nan=False)
    high: float = Field(ge=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def range_order(self):
        if self.high < self.low:
            raise ValueError("Odds interval is reversed")
        return self


class OriginalPrediction(StrictModel):
    probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    rationale: str = Field(min_length=1)
    method: str = Field(min_length=1)
    # This is a transcription, not a validated model estimate.
    source_id: str


class Runner(StrictModel):
    horse_no: HorseNumber
    horse_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    status: Literal["declared", "withdrawn"] = "declared"
    draw: int | None = Field(default=None, ge=1)
    weight_lb: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    jockey: str | None = None
    jockey_evidence: str | None = None
    recent_form: list[FormRun] | None = None
    win_quote: Quote | None = None
    place_quote: Quote | None = None
    original_win: OriginalPrediction | None = None
    original_place: OriginalPrediction | None = None
    source_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def pool_order(self):
        if (
            self.original_win
            and self.original_place
            and self.original_place.probability < self.original_win.probability
        ):
            raise ValueError("PLACE probability cannot be lower than WIN for the same runner")
        return self


class Checkpoint(StrictModel):
    meeting_date: date
    course: Literal["ST", "HV"]
    race_no: RaceNumber
    stage: Literal["T10", "T3"]
    decision_at: AwareDatetime
    scheduled_start: AwareDatetime
    scheduled_start_known_at: AwareDatetime
    surface: str | None = None
    distance_m: int | None = Field(default=None, gt=0)
    going: str | None = None
    declared_count: int = Field(ge=1, le=30)
    runners: list[Runner] = Field(min_length=1, max_length=30)
    source_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def full_field(self):
        if self.scheduled_start.astimezone(ZoneInfo("Asia/Hong_Kong")).date() != self.meeting_date:
            raise ValueError("Scheduled start must match the Hong Kong meeting date")
        numbers = [r.horse_no for r in self.runners]
        ids = [r.horse_id for r in self.runners]
        if (
            len(numbers) != self.declared_count
            or len(set(numbers)) != len(numbers)
            or len(set(ids)) != len(ids)
        ):
            raise ValueError("Complete distinct declared field required")
        if (
            all(r.original_win for r in self.runners)
            and abs(sum(r.original_win.probability for r in self.runners) - 1) > 0.001
        ):
            raise ValueError("Complete WIN probabilities must sum to one")
        return self


class Budget(StrictModel):
    initial_bankroll: PositiveMoney
    meeting_cap: PositiveMoney
    unit_stake: Literal[10] = 10
    frozen_at: AwareDatetime
    source_id: str

    @model_validator(mode="after")
    def cap(self):
        if self.meeting_cap > self.initial_bankroll:
            raise ValueError("Meeting cap cannot exceed bankroll")
        return self


class ResearchInput(StrictModel):
    schema_version: Literal[1] = 1
    meeting_date: date
    course: Literal["ST", "HV"]
    race_count: int = Field(ge=1, le=12, strict=True)
    data_kind: Literal["original_transcription", "synthetic_fixture"]
    sources: list[Source] = Field(default_factory=list)
    checkpoints: list[Checkpoint] = Field(default_factory=list)
    budget: Budget | None = None

    @model_validator(mode="after")
    def identity(self):
        ids = [s.source_id for s in self.sources]
        keys = [(c.race_no, c.stage) for c in self.checkpoints]
        if len(set(ids)) != len(ids) or len(set(keys)) != len(keys):
            raise ValueError("Duplicate source/checkpoint identity")
        for c in self.checkpoints:
            if (
                c.meeting_date != self.meeting_date
                or c.course != self.course
                or c.race_no > self.race_count
            ):
                raise ValueError("Cross-meeting checkpoint")
        return self


class AvailabilityReview(StrictModel):
    schema_version: Literal[1] = 1
    input_sha256: str = Field(pattern=SHA)
    source_hashes: dict[str, str]
    reviewer: str = Field(min_length=1)
    reviewed_at: AwareDatetime
    conclusion: Literal["supported_by_archived_evidence", "UNKNOWN"]
    availability_evidence_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)


def read_bounded(path):
    if not path.is_file() or path.stat().st_size > 5_000_000:
        raise ValueError("Research source missing or exceeds 5 MB")
    return path.read_bytes()


def load_research(directory, *, now=None):
    """Hashes bind manual transcription/review; they do not authenticate historical time."""
    directory = Path(directory).resolve()
    now = now or datetime.now(UTC)
    raw = read_bounded(directory / "research.json")
    packet = ResearchInput.model_validate_json(raw)
    digest = hashlib.sha256(raw).hexdigest()
    sources = {s.source_id: s for s in packet.sources}
    for source in packet.sources:
        path = (directory / source.path).resolve()
        if not path.is_relative_to(directory):
            raise ValueError("Research source escapes input directory")
        body = read_bounded(path)
        if hashlib.sha256(body).hexdigest() != source.sha256:
            raise ValueError("Research source hash mismatch")
        if source.captured_at > now or source.claimed_available_at > now:
            raise ValueError("Source time is in the future")
    review = None
    review_path = directory / "availability-review.json"
    if review_path.exists():
        review = AvailabilityReview.model_validate_json(read_bounded(review_path))
        if review.input_sha256 != digest or review.source_hashes != {
            s.source_id: s.sha256 for s in packet.sources
        }:
            raise ValueError("Availability review does not bind the current input and sources")
        if review.reviewed_at > now or any(
            s.captured_at > review.reviewed_at for s in packet.sources
        ):
            raise ValueError("Availability review chronology mismatch")
        if any(
            i not in sources or sources[i].category != "availability_evidence"
            for i in review.availability_evidence_ids
        ):
            raise ValueError("Availability review requires archived time evidence")
    return assess_research(packet, sources, review, digest, now)


def assess_research(packet, sources, review, digest, imported_at):
    reviewed = review is not None and review.conclusion == "supported_by_archived_evidence"
    rows = []
    for race in range(1, packet.race_count + 1):
        checkpoints = {c.stage: c for c in packet.checkpoints if c.race_no == race}
        blockers = ["PROBABILITY_MODEL_NOT_VALIDATED"]
        if not reviewed:
            blockers.append("POINT_IN_TIME_AVAILABILITY_UNREVIEWED")
        if packet.data_kind == "synthetic_fixture":
            blockers.append("SYNTHETIC_DATA_ONLY")
        if packet.budget is None:
            blockers.append("PRECOMMITTED_BUDGET_UNKNOWN")
        fields = {}
        for stage in ("T10", "T3"):
            c = checkpoints.get(stage)
            if not c:
                blockers.append(f"{stage}_SNAPSHOT_MISSING")
                fields[stage] = []
                continue
            offset = (c.scheduled_start - c.decision_at).total_seconds()
            target = 600 if stage == "T10" else 180
            if abs(offset - target) > 60 or c.scheduled_start_known_at > c.decision_at:
                blockers.append(f"{stage}_SCHEDULE_OR_CHECKPOINT_TIME_INVALID")
            if c.decision_at > imported_at:
                blockers.append(f"{stage}_DECISION_IN_FUTURE")
            if not all((c.surface, c.distance_m, c.going)):
                blockers.append(f"{stage}_RACE_CONDITIONS_UNKNOWN")
            refs = set(c.source_ids)
            for runner in c.runners:
                refs.update(runner.source_ids)
                for prediction in (runner.original_win, runner.original_place):
                    if prediction:
                        refs.add(prediction.source_id)
            if any(
                i not in sources
                or sources[i].category != "pre_race"
                or sources[i].captured_at > c.decision_at
                or sources[i].claimed_available_at > c.decision_at
                for i in refs
            ):
                blockers.append(f"{stage}_SOURCE_NOT_AVAILABLE_AT_DECISION")
            budget = packet.budget
            if budget:
                first_decision = min(x.decision_at for x in packet.checkpoints)
                bsource = sources.get(budget.source_id)
                if (
                    budget.frozen_at > first_decision
                    or not bsource
                    or bsource.category != "budget"
                    or max(bsource.captured_at, bsource.claimed_available_at) > budget.frozen_at
                ):
                    blockers.append("BUDGET_NOT_EVIDENCED_BEFORE_DECISION")
            comparisons = []
            for r in c.runners:
                missing = [
                    label
                    for label, value in [
                        ("draw", r.draw),
                        ("weight", r.weight_lb),
                        ("jockey", r.jockey),
                        ("jockey_evidence", r.jockey_evidence),
                        ("recent_form", r.recent_form),
                    ]
                    if value is None or value == ""
                ]
                if r.status != "declared":
                    blockers.append(f"{stage}_WITHDRAWAL_REQUIRES_REVIEW")
                if missing:
                    blockers.append(f"{stage}_HORSE_{r.horse_no}_FACTS_UNKNOWN")
                latest_capture = max(
                    (sources[i].captured_at for i in r.source_ids if i in sources), default=None
                )
                runs = r.recent_form or []
                temporal_ok = all(
                    x.race_date < c.meeting_date
                    and x.race_date <= x.available_at.date()
                    and x.available_at <= c.decision_at
                    and latest_capture is not None
                    and x.available_at <= latest_capture
                    for x in runs
                )
                if not temporal_ok:
                    blockers.append(f"{stage}_HORSE_{r.horse_no}_FORM_LOOKAHEAD")
                prior = runs if temporal_ok else []
                comparable = [
                    x
                    for x in prior
                    if x.course == c.course
                    and x.surface == c.surface
                    and x.distance_m == c.distance_m
                ]
                unknown_finishes = sum(x.finish is None for x in comparable)
                if unknown_finishes:
                    blockers.append(f"{stage}_HORSE_{r.horse_no}_FORM_FINISH_UNKNOWN")
                    missing.append(f"{unknown_finishes} comparable run finishes UNKNOWN")
                comparable = [x for x in comparable if x.finish is not None]
                strengths = (
                    [
                        f"{sum(x.finish is not None and x.finish <= 3 for x in comparable)}/{len(comparable)} recorded top-three finishes at this course/surface/distance"
                    ]
                    if comparable
                    else []
                )
                weaknesses = (
                    [
                        f"{sum(x.finish is not None and x.finish > 3 for x in comparable)}/{len(comparable)} recorded finishes outside top three at these conditions"
                    ]
                    if comparable
                    else []
                )
                values = {}
                for pool, quote, prediction in [
                    ("WIN", r.win_quote, r.original_win),
                    ("PLACE", r.place_quote, r.original_place),
                ]:
                    quote_ok = (
                        quote
                        and 0 <= (c.decision_at - quote.observed_at).total_seconds() <= 60
                        and latest_capture is not None
                        and quote.observed_at <= latest_capture
                    )
                    if not quote_ok:
                        blockers.append(f"{stage}_HORSE_{r.horse_no}_{pool}_QUOTE_MISSING_OR_STALE")
                    values[pool] = {
                        "original_probability": prediction.probability if prediction else None,
                        "original_source_id": prediction.source_id if prediction else None,
                        "original_rationale": prediction.rationale if prediction else "UNKNOWN",
                        "original_method": prediction.method if prediction else "UNKNOWN",
                        "validated_probability": None,
                        "quote": quote.model_dump(mode="json") if quote else None,
                        "illustrative_ev_lower": prediction.probability * quote.low - 1
                        if prediction and quote_ok
                        else None,
                        "status": "UNVALIDATED_INPUT_ONLY",
                    }
                comparisons.append(
                    {
                        "horse_no": r.horse_no,
                        "horse_id": r.horse_id,
                        "name": r.name,
                        "draw": r.draw,
                        "weight_lb": r.weight_lb,
                        "jockey": r.jockey,
                        "jockey_evidence": r.jockey_evidence or "UNKNOWN",
                        "strength_observations": strengths or ["UNKNOWN"],
                        "weakness_observations": weaknesses or ["UNKNOWN"],
                        "uncertainties": missing
                        + ["Descriptive form is not a causal ranking or a calibrated forecast"],
                        "source_ids": r.source_ids,
                        "pools": values,
                    }
                )
            fields[stage] = comparisons
        if len(checkpoints) == 2:
            a, b = checkpoints["T10"], checkpoints["T3"]
            if a.decision_at >= b.decision_at:
                blockers.append("CHECKPOINT_ORDER_INVALID")
            if a.scheduled_start != b.scheduled_start:
                blockers.append("SCHEDULE_CHANGE_REQUIRES_REVIEW")
            if {(r.horse_no, r.horse_id, r.status) for r in a.runners} != {
                (r.horse_no, r.horse_id, r.status) for r in b.runners
            }:
                blockers.append("FIELD_CHANGE_REQUIRES_REVIEW")
        rows.append(
            {
                "race_no": race,
                "decision": "NO_BET",
                "historical_recommendation": "UNKNOWN",
                "blockers": list(dict.fromkeys(blockers)),
                "checkpoints": fields,
                "checkpoint_metadata": {
                    stage: c.model_dump(mode="json", exclude={"runners"})
                    for stage, c in checkpoints.items()
                },
            }
        )
    return {
        "schema_version": 1,
        "kind": "horse_research_audit",
        "meeting_date": packet.meeting_date.isoformat(),
        "course": packet.course,
        "data_kind": packet.data_kind,
        "input_sha256": digest,
        "imported_at": imported_at.isoformat(),
        "availability_review": review.model_dump(mode="json") if review else None,
        "budget": packet.budget.model_dump(mode="json") if packet.budget else None,
        "races": rows,
        "orders_created": 0,
        "probability_model": "NOT_IMPLEMENTED_OR_VALIDATED",
        "limitations": [
            "Hashes and a human review bind records but do not cryptographically prove historical availability.",
            "All decisions are current replay decisions, never reconstructed original recommendations.",
            "WIN and PLACE original probabilities are unvalidated transcriptions; indicative gross odds are not locked execution prices.",
            "This version has no validated horse probability model, candidate approval or order path. NO BET is mandatory.",
        ],
    }


def empty_research(day, course, races):
    packet = ResearchInput(
        meeting_date=day, course=course, race_count=races, data_kind="original_transcription"
    )
    return assess_research(packet, {}, None, None, datetime.now(UTC))
