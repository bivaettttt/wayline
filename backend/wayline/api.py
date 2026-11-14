import os
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from wayline import contracts as c
from wayline import trips
from wayline.auth import Actor, allow, digest, passwords, signin
from wayline.db import audit, engine, many, one, run
from wayline.domain import effective
from wayline.integration import sync
from wayline.lab import SCENARIOS, experiment

app = FastAPI(
    title="Wayline",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
A = "/api"
OPS = ("OPERATIONS_ANALYST", "ADMIN")
Offset = Annotated[int, Query(ge=0)]


@app.middleware("http")
async def correlation(request: Request, call_next):
    request.state.id = uuid4()
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(request.state.id)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def error(request: Request, exc: HTTPException):
    return JSONResponse(
        {"detail": exc.detail, "request_id": str(request.state.id)},
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation(request: Request, exc: RequestValidationError):
    return JSONResponse(
        {
            "detail": "INVALID_INPUT",
            "fields": [
                {"path": list(e["loc"]), "code": e["type"]} for e in exc.errors()
            ],
            "request_id": str(request.state.id),
        },
        status_code=422,
    )


@app.exception_handler(SQLAlchemyError)
async def storage_error(request: Request, exc: SQLAlchemyError):
    return JSONResponse(
        {"detail": "STORAGE_FAILURE", "request_id": str(request.state.id)},
        status_code=500,
    )


@app.get("/health")
def health():
    with engine.connect() as conn:
        run(conn, "SELECT cursor FROM feed")
    return {"status": "ok"}


@app.post(A + "/auth/login")
def login(payload: c.Login, request: Request):
    return signin(payload, request.state.id)


@app.post(A + "/auth/logout", status_code=204)
def logout(actor: Actor):
    with engine.begin() as conn:
        run(conn, "DELETE FROM sessions WHERE digest=:key", key=actor["session"])


@app.get(A + "/users")
def users(actor: Actor):
    allow(actor, "ADMIN")
    with engine.connect() as conn:
        return many(conn, "SELECT login,name,role FROM users ORDER BY name")


@app.post(A + "/users", status_code=201)
def user(payload: c.NewUser, actor: Actor, request: Request):
    allow(actor, "ADMIN")
    with engine.begin() as conn:
        item = one(
            conn,
            """INSERT INTO users(login,name,role,password) VALUES (:login,:name,:role,:password)
            ON CONFLICT DO NOTHING RETURNING login,name,role""",
            **payload.model_dump() | {"password": passwords.hash(payload.password)},
        )
        if not item:
            raise HTTPException(409, "LOGIN_EXISTS")
        audit(
            conn,
            actor["login"],
            request.state.id,
            "USER_CREATED",
            item["login"],
            role=item["role"],
        )
        return item


@app.get(A + "/airports")
def airports(actor: Actor):
    with engine.connect() as conn:
        return many(conn, "SELECT * FROM airports ORDER BY code")


@app.get(A + "/airlines")
def airlines(actor: Actor):
    with engine.connect() as conn:
        return many(conn, "SELECT * FROM airlines ORDER BY code")


@app.get(A + "/flights")
def flights(
    actor: Actor, offset: Offset = 0, q: Annotated[str, Query(max_length=80)] = ""
):
    with engine.connect() as conn:
        return many(
            conn,
            trips.FLIGHTS
            + """ WHERE f.number ILIKE :q OR f.origin ILIKE :q OR f.destination ILIKE :q
               ORDER BY f.scheduled_dep,f.id LIMIT 50 OFFSET :offset""",
            q=f"%{q}%",
            offset=offset,
        )


@app.get(A + "/flights/{id}")
def flight(id: str, actor: Actor):
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        item = one(conn, trips.FLIGHTS + " WHERE f.id=:id", id=id)
        if not item:
            raise HTTPException(404, "FLIGHT_NOT_FOUND")
        events = many(
            conn,
            "SELECT * FROM events WHERE flight=:id ORDER BY sequence DESC LIMIT 100",
            id=id,
        )
        return item | {"events": events, "feed": trips.feed(conn)}


@app.get(A + "/trips")
def list_trips(actor: Actor, offset: Offset = 0):
    with engine.connect() as conn:
        return many(
            conn,
            """SELECT t.*,s.risk,s.detail, EXISTS(SELECT 1 FROM incidents i WHERE i.trip=t.id AND i.resolved_at IS NULL) AS disrupted FROM trips t LEFT JOIN LATERAL
          (SELECT risk,detail FROM assessments WHERE trip=t.id ORDER BY id DESC LIMIT 1) s ON true
          WHERE :staff OR t.owner=:owner ORDER BY t.created_at DESC,t.id LIMIT 50 OFFSET :offset""",
            staff=actor["role"] in OPS,
            owner=actor["login"],
            offset=offset,
        )


@app.post(A + "/trips", status_code=201)
def create_trip(payload: c.Trip, actor: Actor, request: Request):
    allow(actor, "TRAVELER")
    with engine.begin() as conn:
        return trips.create(conn, payload, actor["login"], request.state.id)


@app.get(A + "/trips/{id}")
def trip(id: UUID, actor: Actor):
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        return trips.detail(conn, id, actor)


@app.post(A + "/trips/{id}/recalculate")
def recalculate(id: UUID, actor: Actor, request: Request):
    with engine.begin() as conn:
        trips.feed(conn, locking=True)
        trips.visible(conn, id, actor)
        return trips.recalc(conn, id, request.state.id, actor=actor["login"])


@app.post(A + "/trips/{id}/incidents/{incident}/acknowledge")
def acknowledge(id: UUID, incident: UUID, actor: Actor, request: Request):
    allow(actor, "TRAVELER")
    with engine.begin() as conn:
        trips.feed(conn, locking=True)
        trips.visible(conn, id, actor)
        item = one(
            conn, "SELECT * FROM incidents WHERE id=:j AND trip=:id", id=id, j=incident
        )
        if not item:
            raise HTTPException(404, "INCIDENT_NOT_FOUND")
        if item["status"] == "RESOLVED":
            raise HTTPException(409, "INCIDENT_RESOLVED")
        if item["status"] == "ACKNOWLEDGED":
            return item
        result = one(
            conn,
            "UPDATE incidents SET status='ACKNOWLEDGED' WHERE id=:j RETURNING *",
            j=incident,
        )
        audit(conn, actor["login"], request.state.id, "ACKNOWLEDGED", incident, trip=id)
        return result


@app.post(A + "/routes")
def find_routes(payload: c.Search, actor: Actor, request: Request):
    if payload.origin == payload.destination:
        raise HTTPException(422, "SAME_AIRPORT")
    with (
        engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn,
        conn.begin(),
    ):
        matches = many(
            conn,
            "SELECT code FROM airports WHERE code=ANY(:codes)",
            codes=[payload.origin, payload.destination],
        )
        if len(matches) != 2:
            raise HTTPException(422, "AIRPORT_NOT_FOUND")
        return trips.search(
            conn, payload.model_dump(), actor["login"], request.state.id
        )


@app.post(A + "/trips/{id}/alternatives")
def alternatives(id: UUID, actor: Actor, request: Request):
    with (
        engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn,
        conn.begin(),
    ):
        trips.visible(conn, id, actor)
        legs = trips.trip_flights(conn, id)
        arrived = 0
        for leg in legs:
            if leg["status"] not in {"ARRIVED", "LANDED"}:
                break
            arrived += 1
        remaining = legs[arrived:]
        if not remaining:
            raise HTTPException(409, "TRIP_ALREADY_ARRIVED")
        first = remaining[0]
        if first["actual_dep"]:
            raise HTTPException(409, "ALTERNATIVES_REQUIRE_GROUND_POSITION")
        inbound = legs[arrived - 1] if arrived else None
        origin = first["origin"]
        earliest = max(
            effective(inbound, "arr") if inbound else first["scheduled_dep"],
            datetime.now(UTC),
        )
        params = dict(
            origin=origin,
            destination=legs[-1]["destination"],
            earliest=earliest,
            max_legs=3,
            max_hours=36,
        )
        return trips.search(
            conn,
            params,
            actor["login"],
            request.state.id,
            id,
            excluded=[f["id"] for f in remaining],
            inbound=inbound,
        )


@app.get(A + "/searches/{id}")
def show_search(id: UUID, actor: Actor):
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        s = one(
            conn,
            "SELECT * FROM searches WHERE id=:id AND actor=:a",
            id=id,
            a=actor["login"],
        )
        if not s:
            raise HTTPException(404, "SEARCH_NOT_FOUND")
        current = trips.feed(conn)
        return s | {
            "current": s["generation"] == current["generation"] and current["fresh"]
        }


@app.get(A + "/notifications")
def notifications(actor: Actor, offset: Offset = 0):
    with engine.connect() as conn:
        return many(
            conn,
            """SELECT n.*,t.title FROM notifications n JOIN trips t ON t.id=n.trip
            WHERE t.owner=:a ORDER BY n.id DESC LIMIT 50 OFFSET :offset""",
            a=actor["login"],
            offset=offset,
        )


@app.post(A + "/notifications/{id}/read")
def read_notice(id: int, actor: Actor, request: Request):
    with engine.begin() as conn:
        n = one(
            conn,
            """UPDATE notifications n SET read_at=COALESCE(n.read_at,now()) FROM trips t
            WHERE t.id=n.trip AND t.owner=:a AND n.id=:id RETURNING n.*""",
            id=id,
            a=actor["login"],
        )
        if not n:
            raise HTTPException(404, "NOTIFICATION_NOT_FOUND")
        audit(conn, actor["login"], request.state.id, "NOTIFICATION_READ", id)
        return n


@app.get(A + "/policies")
def policies(actor: Actor):
    with engine.connect() as conn:
        return many(conn, "SELECT * FROM policies ORDER BY airport,version DESC")


@app.post(A + "/policies/{airport}", status_code=201)
def publish_policy(airport: c.Code, payload: c.Policy, actor: Actor, request: Request):
    allow(actor, "ADMIN")
    with engine.begin() as conn:
        trips.feed(conn, locking=True)
        if not one(conn, "SELECT code FROM airports WHERE code=:a", a=airport):
            raise HTTPException(404, "AIRPORT_NOT_FOUND")
        result = one(
            conn,
            """INSERT INTO policies(airport,version,domestic,international,terminal_extra,author)
            SELECT :airport,COALESCE(max(version),0)+1,:domestic,:international,:terminal_extra,:actor
            FROM policies WHERE airport=:airport RETURNING *""",
            airport=airport,
            actor=actor["login"],
            **payload.model_dump(),
        )
        run(conn, "UPDATE feed SET generation=generation+1")
        for item in many(
            conn,
            """SELECT DISTINCT a.trip FROM segments a JOIN segments b ON b.trip=a.trip AND b.position=a.position+1
            JOIN flights f ON f.id=a.flight WHERE f.destination=:airport ORDER BY a.trip""",
            airport=airport,
        ):
            trips.recalc(conn, item["trip"], request.state.id, actor=actor["login"])
        audit(
            conn,
            actor["login"],
            request.state.id,
            "MCT_PUBLISHED",
            airport,
            version=result["version"],
        )
        return result


@app.get(A + "/operations")
def operations(actor: Actor, offset: Offset = 0):
    allow(actor, *OPS)
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        return {
            "feed": trips.feed(conn),
            "runs": many(
                conn,
                "SELECT * FROM sync_runs ORDER BY id DESC LIMIT 30 OFFSET :offset",
                offset=offset,
            ),
            "events": many(
                conn,
                "SELECT * FROM events ORDER BY sequence DESC LIMIT 50 OFFSET :offset",
                offset=offset,
            ),
            "counts": one(
                conn,
                """SELECT (SELECT count(*) FROM flights) AS flights,
                   (SELECT count(*) FROM trips) AS trips,(SELECT count(*) FROM incidents WHERE resolved_at IS NULL) AS incidents,
                   (SELECT count(*) FROM events WHERE disposition LIKE 'APPLIED%') AS applied""",
            ),
        }


@app.post(A + "/operations/sync")
def synchronize(actor: Actor, request: Request):
    allow(actor, *OPS)
    return sync(actor["login"], request.state.id)


@app.get(A + "/audit")
def log(actor: Actor, offset: Offset = 0):
    allow(actor, *OPS)
    with engine.connect() as conn:
        return many(
            conn,
            "SELECT * FROM audit ORDER BY id DESC LIMIT 50 OFFSET :offset",
            offset=offset,
        )


@app.get(A + "/lab")
def lab_config(actor: Actor):
    allow(actor, "ADMIN")
    return {
        "enabled": os.getenv("LAB_MODE") == "1",
        "scenarios": SCENARIOS if os.getenv("LAB_MODE") == "1" else {},
    }


@app.post(A + "/lab/{scenario}")
def lab_run(scenario: str, actor: Actor, request: Request):
    allow(actor, "ADMIN")
    if os.getenv("LAB_MODE") != "1" or scenario not in SCENARIOS:
        raise HTTPException(404, "SCENARIO_NOT_FOUND")
    admin, traveler = token_urlsafe(32), token_urlsafe(32)
    keys = [digest(admin), digest(traveler)]
    with engine.begin() as conn:
        if not run(conn, "SELECT pg_try_advisory_xact_lock(771212)").scalar_one():
            raise HTTPException(409, "LAB_BUSY")
        with engine.begin() as session:
            for login, key in zip((actor["login"], "traveler"), keys, strict=True):
                run(
                    session,
                    "INSERT INTO sessions VALUES (:k,:u,now()+interval '5 minutes')",
                    k=key,
                    u=login,
                )
        try:
            result = experiment(scenario, admin, traveler)
            audit(
                conn,
                actor["login"],
                request.state.id,
                "LAB_EXPERIMENT",
                scenario,
                passed=result["passed"],
            )
            return result
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        finally:
            with engine.begin() as session:
                run(session, "DELETE FROM sessions WHERE digest=ANY(:keys)", keys=keys)
