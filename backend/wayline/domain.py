from collections import defaultdict
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

ORDER = {
    k: i
    for i, k in enumerate(
        ("SCHEDULED", "CHECK_IN", "BOARDING", "DEPARTED", "IN_AIR", "LANDED", "ARRIVED")
    )
}
TERMINAL = {"ARRIVED", "CANCELLED", "DIVERTED"}
UNAVAILABLE = {"CANCELLED", "DIVERTED", "UNKNOWN"}
TIME_FIELDS = ("estimated_dep", "estimated_arr", "actual_dep", "actual_arr")
FIELDS = ("status", *TIME_FIELDS, "terminal_dep", "terminal_arr")


def local_instant(wall, zone, fold=None):
    if wall.tzinfo is not None:
        raise ValueError("Expected a local wall time")
    tz = ZoneInfo(zone)
    candidates = {}
    for f in (0, 1):
        utc = wall.replace(tzinfo=tz, fold=f).astimezone(UTC)
        if utc.astimezone(tz).replace(tzinfo=None) == wall:
            candidates[f] = utc
    if not candidates:
        raise ValueError("NONEXISTENT_LOCAL_TIME")
    if len(set(candidates.values())) > 1 and fold is None:
        raise ValueError("AMBIGUOUS_LOCAL_TIME")
    return candidates[fold or 0]


def effective(flight, side):
    return (
        flight["actual_" + side]
        or flight["estimated_" + side]
        or flight["scheduled_" + side]
    )


def transition(old, new):
    state, target = old["status"], new["status"]
    if state in TERMINAL and target != state:
        return "TERMINAL_STATE"
    if state in ORDER and target in ORDER and ORDER[target] < ORDER[state]:
        return "PHASE_REGRESSION"
    if target == "CANCELLED" and (
        old["actual_dep"] or ORDER.get(state, 0) >= ORDER["DEPARTED"]
    ):
        return "ALREADY_DEPARTED"
    if any(old[k] and old[k] != new[k] for k in ("actual_dep", "actual_arr")):
        return "ACTUAL_FACT_CHANGED"
    if target in {"LANDED", "ARRIVED"} and not new["actual_arr"]:
        return "MISSING_ACTUAL_ARRIVAL"
    if target in {"DEPARTED", "IN_AIR", "LANDED", "ARRIVED"} and not new["actual_dep"]:
        return "MISSING_ACTUAL_DEPARTURE"
    if new["actual_arr"] and (
        not new["actual_dep"] or new["actual_arr"] <= new["actual_dep"]
    ):
        return "INVALID_ACTUAL_TIMES"
    merged = old | new
    if effective(merged, "arr") <= effective(merged, "dep"):
        return "NEGATIVE_FLIGHT_DURATION"
    return None


def assess_connection(inbound, outbound, policies, fresh):
    airport = inbound["destination"]
    policy = policies.get(airport)
    gap = (effective(outbound, "dep") - effective(inbound, "arr")).total_seconds()
    planned = (outbound["scheduled_dep"] - inbound["scheduled_arr"]).total_seconds()
    international = (
        inbound["origin_country"] != inbound["destination_country"]
        or outbound["origin_country"] != outbound["destination_country"]
    )
    minimum = (
        None
        if policy is None
        else policy["international" if international else "domestic"]
    )
    change_terminal = inbound["terminal_arr"] != outbound["terminal_dep"]
    if minimum is not None and change_terminal:
        minimum += policy["terminal_extra"]
    if (
        not fresh
        or minimum is None
        or "UNKNOWN" in {inbound["status"], outbound["status"]}
    ):
        risk = "UNKNOWN"
    elif {inbound["status"], outbound["status"]} & {"CANCELLED", "DIVERTED"} or gap < 0:
        risk = "MISSED"
    elif gap < minimum * 60:
        risk = "AT_RISK"
    else:
        risk = "SAFE"
    return {
        "inbound": inbound["id"],
        "outbound": outbound["id"],
        "airport": airport,
        "available_minutes": round(gap / 60, 2),
        "planned_minutes": round(planned / 60, 2),
        "minimum_minutes": minimum,
        "policy_version": policy["version"] if policy else None,
        "international": international,
        "terminal_change": change_terminal,
        "risk": risk,
    }


def routes(
    flights, policies, origin, destination, earliest, max_legs, max_hours, excluded=()
):
    graph = defaultdict(list)
    for f in flights:
        if (
            f["status"] not in UNAVAILABLE | {"DEPARTED", "IN_AIR", "LANDED", "ARRIVED"}
            and f["id"] not in excluded
        ):
            graph[f["origin"]].append(f)
    latest = earliest + timedelta(hours=max_hours)
    results = []

    def visit(airport, path, visited, buffers):
        for leg in graph[airport]:
            departure, arrival = effective(leg, "dep"), effective(leg, "arr")
            if (
                leg["destination"] in visited
                or departure < earliest
                or arrival > latest
                or arrival <= departure
            ):
                continue
            connection = (
                assess_connection(path[-1], leg, policies, True) if path else None
            )
            if connection and connection["risk"] != "SAFE":
                continue
            next_path = [*path, leg]
            next_buffers = [*buffers, connection] if connection else buffers
            if leg["destination"] == destination:
                results.append(
                    (
                        arrival,
                        len(next_path),
                        arrival - effective(next_path[0], "dep"),
                        tuple(segment["id"] for segment in next_path),
                        next_path,
                        next_buffers,
                    )
                )
            elif len(next_path) < max_legs:
                visit(
                    leg["destination"],
                    next_path,
                    visited | {leg["destination"]},
                    next_buffers,
                )

    visit(origin, [], {origin}, [])
    return [
        {
            "segments": path,
            "connections": buffers,
            "arrival": arrival,
            "duration_minutes": int(duration.total_seconds() / 60),
            "stops": legs - 1,
            "explanation": "Earliest arrival, then fewer stops, then shorter elapsed duration",
        }
        for arrival, legs, duration, _, path, buffers in sorted(
            results, key=lambda row: row[:4]
        )[:5]
    ]
