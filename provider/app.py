import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from time import sleep
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import AwareDatetime, BaseModel, Field

app = FastAPI(title="Wayline Synthetic Flight Provider")
FILE = os.getenv("PROVIDER_DB", "/tmp/wayline-provider.sqlite")
AIRPORTS = [
    ("OVB", "Новосибирск", "Asia/Novosibirsk", "RU"),
    ("IST", "Стамбул", "Europe/Istanbul", "TR"),
    ("FCO", "Рим", "Europe/Rome", "IT"),
    ("DXB", "Дубай", "Asia/Dubai", "AE"),
    ("LHR", "Лондон", "Europe/London", "GB"),
    ("JFK", "Нью-Йорк", "America/New_York", "US"),
    ("HND", "Токио", "Asia/Tokyo", "JP"),
    ("LAX", "Лос-Анджелес", "America/Los_Angeles", "US"),
]


def connect():
    db = sqlite3.connect(FILE, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def fixture(day):
    def at(hour, minute=0):
        return (day + timedelta(hours=hour, minutes=minute)).isoformat()

    legs = [
        ("WL101", "OVB", "IST", 6, 0, 11, 0, "A", "A"),
        ("WL103", "OVB", "IST", 6, 30, 11, 30, "A", "A"),
        ("WL202", "IST", "FCO", 12, 35, 15, 25, "A", "A"),
        ("WL214", "IST", "FCO", 15, 35, 18, 15, "A", "A"),
        ("WL220", "IST", "FCO", 19, 0, 21, 45, "B", "A"),
        ("WL115", "OVB", "DXB", 9, 0, 15, 0, "A", "B"),
        ("WL301", "DXB", "FCO", 17, 10, 23, 40, "B", "A"),
        ("WL140", "OVB", "IST", 14, 0, 19, 30, "A", "A"),
        ("WL226", "IST", "FCO", 21, 10, 24, 0, "A", "A"),
        ("WL400", "FCO", "LHR", 21, 45, 25, 50, "A", "A"),
        ("WL510", "HND", "LAX", 15, 10, 25, 0, "A", "A"),
        ("WL520", "JFK", "LHR", 23, 40, 31, 0, "A", "A"),
        ("WL900", "FCO", "OVB", 27, 0, 35, 20, "A", "B"),
    ]
    catalog = [
        {
            "id": n + "-" + day.date().isoformat(),
            "number": n,
            "airline": "WL",
            "origin": o,
            "destination": d,
            "scheduled_dep": at(h, m),
            "scheduled_arr": at(a, b),
            "terminal_dep": td,
            "terminal_arr": ta,
        }
        for n, o, d, h, m, a, b, td, ta in legs
    ]
    year = day.year
    november = datetime(year, 11, 1, tzinfo=UTC)
    transition_day = november + timedelta(days=(6 - november.weekday()) % 7)
    if transition_day < day:
        november = datetime(year + 1, 11, 1, tzinfo=UTC)
        transition_day = november + timedelta(days=(6 - november.weekday()) % 7)
    for number, origin, destination, start, stop in [
        ("WL601", "LHR", "JFK", 0, 5.5),
        ("WL602", "JFK", "LAX", 6.5, 12),
    ]:
        catalog.append(
            {
                "id": number + "-" + transition_day.date().isoformat(),
                "number": number,
                "airline": "WL",
                "origin": origin,
                "destination": destination,
                "scheduled_dep": (transition_day + timedelta(hours=start)).isoformat(),
                "scheduled_arr": (transition_day + timedelta(hours=stop)).isoformat(),
                "terminal_dep": "A",
                "terminal_arr": "A",
            }
        )
    return catalog


with closing(connect()) as conn, conn:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS configuration(id integer PRIMARY KEY CHECK(id=1), mode text NOT NULL, anchor text NOT NULL);
    CREATE TABLE IF NOT EXISTS updates(seq integer PRIMARY KEY AUTOINCREMENT, event text NOT NULL);
    """)
    day = (datetime.now(UTC) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    conn.execute(
        "INSERT OR IGNORE INTO configuration VALUES (1,'normal',?)", (day.isoformat(),)
    )


def schedule(conn):
    day = datetime.fromisoformat(
        conn.execute("SELECT anchor FROM configuration").fetchone()["anchor"]
    )
    return fixture(day)


class Change(BaseModel):
    flight: str
    event_id: str = Field(
        default_factory=lambda: uuid4().hex, min_length=1, max_length=100
    )
    revision: int | None = Field(default=None, gt=0, le=1_000_000)
    status: Literal[
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
    ] = "SCHEDULED"
    estimated_dep: AwareDatetime | None = None
    estimated_arr: AwareDatetime | None = None
    actual_dep: AwareDatetime | None = None
    actual_arr: AwareDatetime | None = None
    terminal_dep: str = Field(default="A", max_length=12)
    terminal_arr: str = Field(default="A", max_length=12)
    source_time: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


class Mode(BaseModel):
    mode: Literal["normal", "unavailable", "slow", "invalid"]


def controls():
    if os.getenv("LAB_MODE") != "1":
        raise HTTPException(404, "CONTROL_DISABLED")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/schedule")
def catalog():
    with closing(connect()) as conn:
        return {
            "airports": [
                dict(zip(("code", "city", "zone", "country"), row, strict=True))
                for row in AIRPORTS
            ],
            "airlines": [{"code": "WL", "name": "Wayline Air · учебный перевозчик"}],
            "flights": schedule(conn),
        }


@app.get("/flights/{flight}")
def status(flight: str):
    with closing(connect()) as conn:
        row = next((f for f in schedule(conn) if f["id"] == flight), None)
        if row is None:
            raise HTTPException(404, "UNKNOWN_FLIGHT")
        event = conn.execute(
            """SELECT event FROM updates WHERE json_extract(event,'$.flight')=?
          ORDER BY CAST(json_extract(event,'$.revision') AS INTEGER) DESC,seq DESC LIMIT 1""",
            (flight,),
        ).fetchone()
        return {
            "schedule": row,
            "last_snapshot": json.loads(event["event"]) if event else None,
        }


@app.get("/events")
def poll(after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)):
    with closing(connect()) as conn:
        mode = conn.execute("SELECT mode FROM configuration").fetchone()["mode"]
        if mode == "unavailable":
            raise HTTPException(503, "SIMULATED_OUTAGE")
        if mode == "slow":
            sleep(4)
        if mode == "invalid":
            return PlainTextResponse("invalid provider payload")
        return {
            "events": [
                {"sequence": r["seq"], "event": json.loads(r["event"])}
                for r in conn.execute(
                    "SELECT * FROM updates WHERE seq>? ORDER BY seq LIMIT ?",
                    (after, limit),
                )
            ]
        }


@app.post("/control/mode")
def mode(payload: Mode):
    controls()
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE configuration SET mode=?", (payload.mode,))
    return {"mode": payload.mode}


@app.post("/control/events", status_code=201)
def emit(payload: Change):
    controls()
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        if payload.flight not in {f["id"] for f in schedule(conn)}:
            raise HTTPException(404, "UNKNOWN_FLIGHT")
        row = conn.execute(
            "SELECT max(CAST(json_extract(event,'$.revision') AS integer)) AS revision FROM updates WHERE json_extract(event,'$.flight')=?",
            (payload.flight,),
        ).fetchone()
        body = payload.model_dump(mode="json")
        body["revision"] = payload.revision or (row["revision"] or 0) + 1
        sequence = conn.execute(
            "INSERT INTO updates(event) VALUES (?)", (json.dumps(body),)
        ).lastrowid
        return {"sequence": sequence, "event": body}


@app.post("/control/replay/{sequence}", status_code=201)
def replay(sequence: int):
    controls()
    with closing(connect()) as conn, conn:
        found = conn.execute(
            "SELECT event FROM updates WHERE seq=?", (sequence,)
        ).fetchone()
        if found is None:
            raise HTTPException(404, "UNKNOWN_SEQUENCE")
        new = conn.execute(
            "INSERT INTO updates(event) VALUES (?)", (found["event"],)
        ).lastrowid
    return {"sequence": new, "event": json.loads(found["event"])}
