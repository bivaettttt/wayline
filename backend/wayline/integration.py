import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from pydantic import ValidationError

from wayline.contracts import Event, Feed, Flight
from wayline.db import audit, engine, hash_data, many, one, pack, run
from wayline.domain import FIELDS, transition
from wayline.trips import feed, recalc

PROVIDER = os.getenv("PROVIDER_URL", "http://127.0.0.1:8100")


def provider(method, path, **kwargs):
    with httpx.Client(base_url=PROVIDER, timeout=2.0, trust_env=False) as client:
        result = client.request(method, path, **kwargs)
        result.raise_for_status()
        return result.json()


def load_catalog(conn):
    payload = provider("GET", "/schedule")
    for row in payload["airports"]:
        run(
            conn,
            "INSERT INTO airports VALUES (:code,:city,:zone,:country) ON CONFLICT DO NOTHING",
            **row,
        )
    for row in payload["airlines"]:
        run(
            conn,
            "INSERT INTO airlines VALUES (:code,:name) ON CONFLICT DO NOTHING",
            **row,
        )
    for raw in payload["flights"]:
        row = Flight.model_validate(raw).model_dump()
        run(
            conn,
            """INSERT INTO flights(id,number,airline,origin,destination,scheduled_dep,scheduled_arr,terminal_dep,terminal_arr)
            VALUES (:id,:number,:airline,:origin,:destination,:scheduled_dep,:scheduled_arr,:terminal_dep,:terminal_arr)
            ON CONFLICT DO NOTHING""",
            **row,
        )


def apply(conn, envelope, request):
    raw = envelope.event
    sequence = envelope.sequence
    identifier = raw.get("event_id")
    id = identifier[:100] if isinstance(identifier, str) else f"invalid-{sequence}"
    result = "INVALID_PAYLOAD"
    flight = None
    event = None
    hashed = hash_data(raw)
    try:
        event = Event.model_validate(raw)
    except ValidationError:
        pass
    if event:
        e = event.model_dump()
        fields = {
            k: e[k].astimezone(UTC) if isinstance(e[k], datetime) else e[k]
            for k in FIELDS
        }
        normalized = e | fields | {"source_time": event.source_time.astimezone(UTC)}
        hashed = hash_data(normalized)
        saved = one(
            conn,
            "SELECT hash FROM events WHERE event_id=:id ORDER BY sequence LIMIT 1",
            id=id,
        )
        flight = one(
            conn, "SELECT * FROM flights WHERE id=:id FOR UPDATE", id=event.flight
        )
        snapshot = hash_data(fields)
        if saved:
            result = "DUPLICATE" if saved["hash"] == hashed else "EVENT_ID_CONFLICT"
        elif flight is None:
            result = "UNKNOWN_FLIGHT"
        elif e["revision"] < flight["revision"]:
            result = "STALE"
        elif e["revision"] == flight["revision"]:
            result = (
                "EQUIVALENT"
                if snapshot == flight["snapshot_hash"]
                else "REVISION_CONFLICT"
            )
        else:
            violation = transition(flight, fields)
            if violation:
                result = violation
            else:
                result = (
                    "APPLIED_GAP"
                    if e["revision"] > flight["revision"] + 1
                    else "APPLIED_LATE"
                    if datetime.now(UTC) - event.source_time > timedelta(hours=2)
                    else "APPLIED"
                )
                run(
                    conn,
                    """UPDATE flights SET status=:status,estimated_dep=:estimated_dep,estimated_arr=:estimated_arr,
                    actual_dep=:actual_dep,actual_arr=:actual_arr,terminal_dep=:terminal_dep,terminal_arr=:terminal_arr,
                    revision=:revision,source_time=:source_time,snapshot_hash=:snapshot WHERE id=:id""",
                    **fields,
                    revision=event.revision,
                    source_time=event.source_time,
                    snapshot=snapshot,
                    id=event.flight,
                )
    run(
        conn,
        """INSERT INTO events(sequence,event_id,flight,revision,source_time,disposition,hash,payload)
        VALUES (:sequence,:id,:f,:v,:t,:disposition,:hash,CAST(:p AS jsonb))""",
        sequence=sequence,
        id=id,
        f=event.flight if event else None,
        v=event.revision if event else None,
        t=event.source_time if event else None,
        disposition=result,
        hash=hashed,
        p=pack(raw),
    )
    if result.startswith("APPLIED"):
        run(conn, "UPDATE feed SET generation=generation+1")
        for trip in many(
            conn,
            "SELECT trip FROM segments WHERE flight=:id ORDER BY trip",
            id=event.flight,
        ):
            recalc(conn, trip["trip"], request, sequence)
    return {"sequence": sequence, "disposition": result}


def sync(actor=None, request=None):
    request = request or uuid4()
    with engine.connect() as conn:
        initial = feed(conn)["cursor"]
    try:
        batch = Feed.model_validate(
            provider("GET", "/events", params={"after": initial, "limit": 100})
        ).events
        if [e.sequence for e in batch] != list(
            range(initial + 1, initial + 1 + len(batch))
        ):
            raise ValueError("FEED_SEQUENCE_GAP")
        problem = None
    except httpx.TimeoutException:
        problem = "PROVIDER_TIMEOUT"
    except httpx.HTTPError:
        problem = "PROVIDER_UNAVAILABLE"
    except ValueError:
        problem = "PROVIDER_INVALID_RESPONSE"
    with engine.begin() as conn:
        previous = feed(conn, locking=True)
        if previous["cursor"] != initial:
            return {"status": "SUPERSEDED", "cursor": previous["cursor"], "events": []}
        if problem is None:
            run(
                conn,
                "UPDATE feed SET healthy=true,last_success=clock_timestamp(),last_error=NULL",
            )
            handled = [apply(conn, e, request) for e in batch]
            end = batch[-1].sequence if batch else initial
            run(conn, "UPDATE feed SET cursor=:end", end=end)
            status = "OK"
        else:
            run(
                conn,
                "UPDATE feed SET healthy=false,last_error=:problem",
                problem=problem,
            )
            end, handled, status = initial, [], problem
        if previous["fresh"] != (problem is None) or previous["healthy"] != (
            problem is None
        ):
            for trip in many(conn, "SELECT id FROM trips ORDER BY id"):
                recalc(conn, trip["id"], request)
            audit(conn, actor, request, "PROVIDER_HEALTH", "provider", status=status)
        if handled or status != "OK" or actor or not previous["healthy"]:
            run(
                conn,
                """INSERT INTO sync_runs(request,start_cursor,end_cursor,status,detail)
                VALUES (:r,:i,:e,:s,CAST(:d AS jsonb))""",
                r=request,
                i=initial,
                e=end,
                s=status,
                d=pack(handled),
            )
        return {"status": status, "cursor": end, "events": handled}
