import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

Code = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,100}$")]
State = Literal[
    "SCHEDULED",
    "CHECK_IN",
    "BOARDING",
    "DEPARTED",
    "IN_AIR",
    "LANDED",
    "ARRIVED",
    "CANCELLED",
    "DIVERTED",
    "UNKNOWN",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Event(Strict):
    event_id: Identifier
    flight: Identifier
    revision: Annotated[int, Field(strict=True, ge=1, le=1_000_000)]
    status: State
    estimated_dep: AwareDatetime | None
    estimated_arr: AwareDatetime | None
    actual_dep: AwareDatetime | None
    actual_arr: AwareDatetime | None
    terminal_dep: Annotated[str, Field(min_length=1, max_length=12)]
    terminal_arr: Annotated[str, Field(min_length=1, max_length=12)]
    source_time: AwareDatetime

    @field_validator(
        "source_time",
        "estimated_dep",
        "estimated_arr",
        "actual_dep",
        "actual_arr",
        mode="before",
    )
    @classmethod
    def explicit_offset(cls, value):
        if value is None or isinstance(value, datetime):
            return value
        if not isinstance(value, str) or not re.search(
            r"T.+(?:Z|[+-]\d\d:\d\d)$", value
        ):
            raise ValueError("ISO 8601 with an explicit offset required")
        return value


class Flight(Strict):
    id: Identifier
    number: Identifier
    airline: Identifier
    origin: Code
    destination: Code
    scheduled_dep: AwareDatetime
    scheduled_arr: AwareDatetime
    terminal_dep: str
    terminal_arr: str


class Envelope(Strict):
    sequence: Annotated[int, Field(strict=True, gt=0)]
    event: dict


class Feed(Strict):
    events: Annotated[list[Envelope], Field(max_length=200)]


class Login(Strict):
    login: Identifier
    password: Annotated[str, Field(min_length=1, max_length=128)]


class NewUser(Login):
    name: Annotated[str, Field(min_length=2, max_length=100)]
    role: Literal["TRAVELER", "OPERATIONS_ANALYST", "ADMIN"]

    @field_validator("password")
    @classmethod
    def minimum_password(cls, value):
        if len(value) < 12:
            raise ValueError("Minimum 12 characters")
        return value


class Trip(Strict):
    title: Annotated[str, Field(min_length=2, max_length=120)]
    flights: Annotated[list[Identifier], Field(min_length=1, max_length=4)]


class Search(Strict):
    origin: Code
    destination: Code
    earliest: AwareDatetime
    max_legs: Annotated[int, Field(strict=True, ge=1, le=3)] = 3
    max_hours: Annotated[int, Field(strict=True, ge=1, le=72)] = 36


class Policy(Strict):
    domestic: Annotated[int, Field(strict=True, ge=15, le=240)]
    international: Annotated[int, Field(strict=True, ge=15, le=240)]
    terminal_extra: Annotated[int, Field(strict=True, ge=0, le=90)]
