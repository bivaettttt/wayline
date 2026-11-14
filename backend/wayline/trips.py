from datetime import UTC, datetime, timedelta
from itertools import pairwise

from fastapi import HTTPException

from wayline.db import audit, hash_data, many, one, pack, run
from wayline.domain import assess_connection, effective, routes

FLIGHTS = """SELECT f.*,a.zone AS origin_zone,b.zone AS destination_zone,a.country AS origin_country,
 b.country AS destination_country,a.city AS origin_city,b.city AS destination_city FROM flights f
 JOIN airports a ON a.code=f.origin JOIN airports b ON b.code=f.destination"""


def policy_map(conn):
    return {
        p["airport"]: p
        for p in many(
            conn,
            "SELECT DISTINCT ON (airport) * FROM policies ORDER BY airport,version DESC",
        )
    }


def trip_flights(conn, id):
    return many(
        conn,
        FLIGHTS
        + " JOIN segments s ON s.flight=f.id WHERE s.trip=:id ORDER BY s.position",
        id=id,
    )


def feed(conn, locking=False):
    row = one(conn, "SELECT * FROM feed" + (" FOR UPDATE" if locking else ""))
    row["fresh"] = (
        row["healthy"]
        and row["last_success"] is not None
        and row["last_success"] >= datetime.now(UTC) - timedelta(minutes=2)
    )
    return row


def visible(conn, id, actor):
    item = one(conn, "SELECT * FROM trips WHERE id=:id", id=id)
    if not item or (actor["role"] == "TRAVELER" and item["owner"] != actor["login"]):
        raise HTTPException(404, "TRIP_NOT_FOUND")
    return item


def recalc(conn, id, request, event=None, actor=None):
    flights = trip_flights(conn, id)
    fresh = feed(conn)["fresh"]
    policies = policy_map(conn)
    connection = [
        assess_connection(a, b, policies, fresh) for a, b in pairwise(flights)
    ]
    cancelled = any(f["status"] in {"CANCELLED", "DIVERTED"} for f in flights)
    delayed = any(
        effective(f, "arr") - f["scheduled_arr"] >= timedelta(minutes=20)
        for f in flights
    )
    risk = (
        "MISSED"
        if cancelled or any(c["risk"] == "MISSED" for c in connection)
        else "UNKNOWN"
        if not fresh
        or any(f["status"] == "UNKNOWN" for f in flights)
        or any(c["risk"] == "UNKNOWN" for c in connection)
        else "AT_RISK"
        if any(c["risk"] == "AT_RISK" for c in connection)
        else "SAFE"
    )
    reason = (
        "FLIGHT_DISRUPTED"
        if cancelled
        else "MISSED_CONNECTION"
        if risk == "MISSED"
        else "PROVIDER_UNAVAILABLE"
        if risk == "UNKNOWN"
        else "CONNECTION_AT_RISK"
        if risk == "AT_RISK"
        else "FLIGHT_DELAYED"
        if delayed
        else None
    )
    detail = {
        "connections": connection,
        "delayed": delayed,
        "reason": reason,
        "flight_versions": {f["id"]: f["revision"] for f in flights},
        "fresh": fresh,
    }
    fingerprint = hash_data(detail)
    previous = one(
        conn, "SELECT * FROM assessments WHERE trip=:id ORDER BY id DESC LIMIT 1", id=id
    )
    if previous and previous["fingerprint"] == fingerprint:
        return previous
    result = one(
        conn,
        """INSERT INTO assessments(trip,fingerprint,event_sequence,risk,detail)
       VALUES (:id,:f,:e,:risk,CAST(:d AS jsonb)) RETURNING *""",
        id=id,
        f=fingerprint,
        e=event,
        risk=risk,
        d=pack(detail),
    )
    incident = one(
        conn, "SELECT * FROM incidents WHERE trip=:id AND resolved_at IS NULL", id=id
    )
    if reason:
        if incident is None:
            run(
                conn,
                "INSERT INTO incidents(trip,status,reason,assessment) VALUES (:id,'OPEN',:reason,:a)",
                id=id,
                reason=reason,
                a=result["id"],
            )
        else:
            run(
                conn,
                "UPDATE incidents SET reason=:reason,assessment=:a,status=CASE WHEN reason<>:reason THEN 'OPEN' ELSE status END WHERE id=:id",
                id=incident["id"],
                reason=reason,
                a=result["id"],
            )
        if not incident or incident["reason"] != reason:
            run(
                conn,
                "INSERT INTO notifications(trip,assessment,kind) VALUES (:id,:a,:kind)",
                id=id,
                a=result["id"],
                kind=reason,
            )
    elif incident:
        run(
            conn,
            "UPDATE incidents SET status='RESOLVED',resolved_at=now(),assessment=:a WHERE id=:id",
            id=incident["id"],
            a=result["id"],
        )
        run(
            conn,
            "INSERT INTO notifications(trip,assessment,kind) VALUES (:id,:a,'RESOLVED')",
            id=id,
            a=result["id"],
        )
    audit(
        conn,
        actor,
        request,
        "TRIP_ASSESSED",
        id,
        risk=risk,
        assessment=result["id"],
        event=event,
    )
    return result


def create(conn, payload, actor, request):
    feed(conn, locking=True)
    catalog = {
        f["id"]: f
        for f in many(conn, FLIGHTS + " WHERE f.id=ANY(:ids)", ids=payload.flights)
    }
    if len(catalog) != len(payload.flights):
        raise HTTPException(422, "UNKNOWN_OR_DUPLICATE_FLIGHT")
    legs = [catalog[id] for id in payload.flights]
    rules = policy_map(conn)
    for a, b in pairwise(legs):
        planned = [
            f
            | {
                k: None
                for k in ("estimated_dep", "estimated_arr", "actual_dep", "actual_arr")
            }
            | {"status": "SCHEDULED"}
            for f in (a, b)
        ]
        if (
            a["destination"] != b["origin"]
            or assess_connection(*planned, rules, True)["risk"] != "SAFE"
        ):
            raise HTTPException(422, "INFEASIBLE_CONNECTION")
    item = one(
        conn,
        "INSERT INTO trips(owner,title) VALUES (:a,:title) RETURNING *",
        a=actor,
        title=payload.title.strip(),
    )
    for pos, id in enumerate(payload.flights, 1):
        run(
            conn,
            "INSERT INTO segments VALUES (:id,:position,:flight)",
            id=item["id"],
            position=pos,
            flight=id,
        )
    audit(conn, actor, request, "TRIP_CREATED", item["id"], flights=payload.flights)
    item["assessment"] = recalc(conn, item["id"], request, actor=actor)
    return item


def detail(conn, id, actor):
    trip = visible(conn, id, actor)
    return trip | {
        "flights": trip_flights(conn, id),
        "assessments": many(
            conn,
            "SELECT * FROM assessments WHERE trip=:id ORDER BY id DESC LIMIT 30",
            id=id,
        ),
        "incidents": many(
            conn,
            "SELECT * FROM incidents WHERE trip=:id ORDER BY opened_at DESC",
            id=id,
        ),
        "feed": feed(conn),
    }


def search(conn, params, actor, request, trip=None, excluded=()):
    state = feed(conn)
    catalog = many(
        conn,
        FLIGHTS
        + """ WHERE COALESCE(f.actual_dep,f.estimated_dep,f.scheduled_dep)>=:earliest
          AND COALESCE(f.actual_arr,f.estimated_arr,f.scheduled_arr)<=:end ORDER BY f.scheduled_dep,f.id LIMIT 1001""",
        earliest=params["earliest"],
        end=params["earliest"] + timedelta(hours=params["max_hours"]),
    )
    if len(catalog) > 1000:
        raise HTTPException(422, "SEARCH_CATALOG_LIMIT")
    options = (
        routes(catalog, policy_map(conn), excluded=excluded, **params)
        if state["fresh"]
        else []
    )
    item = one(
        conn,
        """INSERT INTO searches(trip,actor,generation,request,inputs,options)
       VALUES (:t,:a,:g,:r,CAST(:i AS jsonb),CAST(:o AS jsonb)) RETURNING *""",
        t=trip,
        a=actor,
        g=state["generation"],
        r=request,
        i=pack(params),
        o=pack(options),
    )
    item["status"] = (
        "DATA_UNAVAILABLE"
        if not state["fresh"]
        else "ALTERNATIVES_AVAILABLE"
        if options
        else "NO_FEASIBLE_ALTERNATIVE"
    )
    audit(
        conn,
        actor,
        request,
        "ROUTE_SEARCH",
        item["id"],
        count=len(options),
        status=item["status"],
        generation=state["generation"],
    )
    return item
