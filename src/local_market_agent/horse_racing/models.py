"""Explicitly separate reported tickets, official entitlements and redeemed cash."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]
PositiveMoney = Annotated[
    Decimal, Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
]
HorseNumber = Annotated[int, Field(ge=1, le=30, strict=True)]
RaceNumber = Annotated[int, Field(ge=1, le=12, strict=True)]
Pool = Literal["WIN", "PLACE"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Ticket(StrictModel):
    ticket_id: str = Field(min_length=1)
    horse_no: HorseNumber
    pool: Pool
    stake: PositiveMoney
    record_kind: Literal["user_reported_actual", "synthetic_fixture"] = "user_reported_actual"
    placed_at: datetime | None = None
    reported_outcome: Literal["won", "lost", "UNKNOWN"] = "UNKNOWN"
    original_recommendation: Literal["UNKNOWN"] = "UNKNOWN"


class RaceRecord(StrictModel):
    race_no: RaceNumber
    participation: Literal["NOT_PLACED", "REPORTED_TICKETS", "UNKNOWN"]
    tickets: list[Ticket] = Field(default_factory=list)
    reported_top3: list[HorseNumber] | None = None
    provisional_gross_return: Money | None = None
    redeemed_cash: Money | None = None
    redemption_evidence: str | None = None

    @model_validator(mode="after")
    def consistency(self):
        if bool(self.tickets) != (self.participation == "REPORTED_TICKETS"):
            raise ValueError("Tickets and reported participation disagree")
        if self.participation == "NOT_PLACED" and any(
            v not in (None, 0) for v in (self.provisional_gross_return, self.redeemed_cash)
        ):
            raise ValueError("Unbet race cannot have a return")
        if self.reported_top3 is not None and (
            len(self.reported_top3) != 3 or len(set(self.reported_top3)) != 3
        ):
            raise ValueError("Reported top three must contain three distinct horses")
        if (self.redeemed_cash is not None) != bool(
            self.redemption_evidence and self.redemption_evidence.strip()
        ):
            raise ValueError(
                "Cash redemption and explicit documentary reference must be supplied together"
            )
        return self


class HistoricalRecord(StrictModel):
    schema_version: Literal[1] = 1
    meeting_date: date
    course: Literal["ST", "HV"]
    currency: Literal["HKD"] = "HKD"
    initial_bankroll: PositiveMoney
    unit_stake: PositiveMoney
    provenance: str = Field(min_length=1)
    recorded_at: datetime
    precommitted_meeting_budget: PositiveMoney | None = None
    budget_evidence: str | None = None
    races: list[RaceRecord] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def consistency(self):
        if self.recorded_at.tzinfo is None:
            raise ValueError("Record time requires timezone")
        ids = [t.ticket_id for r in self.races for t in r.tickets]
        numbers = [r.race_no for r in self.races]
        if len(ids) != len(set(ids)) or len(numbers) != len(set(numbers)):
            raise ValueError("Duplicate ticket or race identity")
        if numbers != list(range(1, max(numbers) + 1)):
            raise ValueError(
                "Explicit sequential coverage, including unbet/unknown races, is required"
            )
        if any(
            t.placed_at and (t.placed_at.tzinfo is None or t.placed_at > self.recorded_at)
            for r in self.races
            for t in r.tickets
        ):
            raise ValueError("Ticket timestamp must be aware and no later than record capture")
        if (self.precommitted_meeting_budget is not None) != bool(
            self.budget_evidence and self.budget_evidence.strip()
        ):
            raise ValueError(
                "Precommitted budget requires its own evidence; stake totals are not a budget"
            )
        return self


class ResultRunner(StrictModel):
    horse_no: HorseNumber
    name: str
    placing: str
    jockey: str
    trainer: str
    actual_weight: str
    horse_weight: str
    draw: str
    final_win_odds: str


class OfficialRace(StrictModel):
    race_no: RaceNumber
    source_id: str
    source_url: str
    retrieved_at: datetime
    title: str
    distance_m: int
    course_detail: str
    going: str
    runners: list[ResultRunner]
    dividends: dict[Pool, dict[str, Money]]
    unit_bet: PositiveMoney = Decimal("10.00")
    supported: bool
    blockers: list[str] = Field(default_factory=list)
    pre_race_eligible: Literal[False] = False

    @model_validator(mode="after")
    def identities(self):
        numbers = [r.horse_no for r in self.runners]
        if not numbers or len(numbers) != len(set(numbers)):
            raise ValueError("Complete distinct result runners required")
        if self.retrieved_at.tzinfo is None or set(self.dividends) != {"WIN", "PLACE"}:
            raise ValueError("Aware result receipt and separate WIN/PLACE dividends required")
        return self


class OfficialMeeting(StrictModel):
    schema_version: Literal[1] = 1
    meeting_date: date
    course: Literal["ST", "HV"]
    races: list[OfficialRace]
    declarations: dict[str, dict] = Field(default_factory=dict)
    source_manifest_sha256: str
    acquisition: Literal["retrospective_official_public_results"] = (
        "retrospective_official_public_results"
    )
