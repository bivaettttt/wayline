from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from wayline.domain import (
    assess_connection,
    effective,
    local_instant,
    routes,
    transition,
)

NOON = datetime(2026, 5, 1, 12, tzinfo=UTC)
POLICY = {
    "IST": {"version": 2, "domestic": 40, "international": 60, "terminal_extra": 20}
}


def leg(id, origin, destination, dep, arr, status="SCHEDULED"):
    return dict(
        id=id,
        origin=origin,
        destination=destination,
        origin_country=origin,
        destination_country=destination,
        scheduled_dep=NOON + timedelta(minutes=dep),
        scheduled_arr=NOON + timedelta(minutes=arr),
        estimated_dep=None,
        estimated_arr=None,
        actual_dep=None,
        actual_arr=None,
        terminal_dep="A",
        terminal_arr="A",
        status=status,
    )


def test_risk_is_absolute_duration():
    a, b = leg("a", "OVB", "IST", 0, 200), leg("b", "IST", "FCO", 295, 420)
    assert assess_connection(a, b, POLICY, True)["available_minutes"] == 95
    a["estimated_arr"] = a["scheduled_arr"] + timedelta(minutes=60)
    result = assess_connection(a, b, POLICY, True)
    assert (
        result["available_minutes"],
        result["minimum_minutes"],
        result["risk"],
        result["policy_version"],
    ) == (35, 60, "AT_RISK", 2)
    assert assess_connection(a, b, POLICY, False)["risk"] == "UNKNOWN"


def test_terminal_margin():
    a, b = leg("a", "OVB", "IST", 0, 200), leg("b", "IST", "FCO", 270, 420)
    b["terminal_dep"] = "B"
    assert assess_connection(a, b, POLICY, True)["minimum_minutes"] == 80


def test_routes_exclude_infeasible_edges_and_cycles():
    flights = [
        leg("a", "OVB", "IST", 0, 200),
        leg("b", "IST", "FCO", 230, 390),
        leg("c", "IST", "FCO", 280, 450),
        leg("d", "OVB", "FCO", 10, 410, "CANCELLED"),
        leg("e", "IST", "OVB", 280, 360),
        leg("f", "OVB", "FCO", 10, 460),
    ]
    result = routes(flights, POLICY, "OVB", "FCO", NOON, 3, 24)
    assert [[f["id"] for f in x["segments"]] for x in result] == [["a", "c"], ["f"]]


def test_actual_and_schedule_are_distinct():
    a = leg("a", "OVB", "IST", 0, 90)
    assert (
        transition(
            a,
            {
                "status": "SCHEDULED",
                "estimated_arr": NOON - timedelta(minutes=1),
                "actual_dep": None,
                "actual_arr": None,
            },
        )
        == "NEGATIVE_FLIGHT_DURATION"
    )
    actual = NOON + timedelta(minutes=3)
    assert (
        effective(
            a | {"actual_dep": actual, "estimated_dep": NOON + timedelta(minutes=8)},
            "dep",
        )
        == actual
    )
    assert (
        transition(a | {"status": "CANCELLED"}, {"status": "SCHEDULED"})
        == "TERMINAL_STATE"
    )
    assert (
        transition(
            a | {"status": "DEPARTED", "actual_dep": actual},
            {"status": "IN_AIR", "actual_dep": None, "actual_arr": None},
        )
        == "ACTUAL_FACT_CHANGED"
    )


@pytest.mark.parametrize(
    ("wall", "message"),
    [
        (datetime(2026, 3, 8, 2, 30), "NONEXISTENT_LOCAL_TIME"),
        (datetime(2026, 11, 1, 1, 30), "AMBIGUOUS_LOCAL_TIME"),
    ],
)
def test_dst_invalid(wall, message):
    with pytest.raises(ValueError, match=message):
        local_instant(wall, "America/New_York")


def test_dst_fall_folds():
    wall = datetime(2026, 11, 1, 1, 30)
    assert local_instant(wall, "America/New_York", 1) - local_instant(
        wall, "America/New_York", 0
    ) == timedelta(hours=1)


def test_dst_spring_elapsed():
    before = local_instant(datetime(2026, 3, 8, 1, 30), "America/New_York")
    after = local_instant(datetime(2026, 3, 8, 3, 30), "America/New_York")
    assert after - before == timedelta(hours=1)


def test_date_line_and_delayed_midnight():
    departure = datetime(2026, 12, 2, 2, tzinfo=UTC)
    arrival = departure + timedelta(hours=9)
    assert (
        arrival.astimezone(ZoneInfo("America/Los_Angeles")).date()
        <= departure.astimezone(ZoneInfo("Asia/Tokyo")).date()
    )
    scheduled = datetime(2026, 12, 2, 22, 40, tzinfo=UTC)
    estimated = scheduled + timedelta(minutes=40)
    assert (
        estimated.astimezone(ZoneInfo("Europe/Rome")).date()
        > scheduled.astimezone(ZoneInfo("Europe/Rome")).date()
    )


def test_recommendation_checks_connection_from_completed_leg():
    inbound = leg("arrived", "OVB", "IST", 0, 200, "ARRIVED")
    inbound["terminal_arr"] = "B"
    early = leg("early", "IST", "FCO", 270, 420)
    later = leg("later", "IST", "FCO", 285, 450)
    options = routes([early, later], POLICY, "IST", "FCO", NOON, 2, 24, inbound=inbound)
    assert len(options) == 1
    assert options[0]["segments"][0]["id"] == "later"
    assert options[0]["connections"][0]["minimum_minutes"] == 80
