from datetime import datetime, timedelta
from uuid import uuid4

import httpx
from wayline.db import engine, run

client = httpx.Client(base_url="http://127.0.0.1:8000/api", timeout=20, trust_env=False)
tokens = {}


def api(who, method, path, data=None, expected=200):
    headers = {"Authorization": "Bearer " + tokens[who]} if who else {}
    response = client.request(method, path, json=data, headers=headers)
    assert response.status_code == expected, (
        method,
        path,
        response.status_code,
        response.text[:600],
    )
    assert response.headers["X-Request-ID"]
    return response.json() if response.content else None


for login in ("traveler", "other", "analyst", "admin"):
    import os

    tokens[login] = api(
        None,
        "POST",
        "/auth/login",
        {"login": login, "password": os.environ["DEMO_PASSWORD"]},
    )["token"]

api(None, "GET", "/trips", expected=401)
api("traveler", "POST", "/operations/sync", expected=403)
api(
    "traveler",
    "POST",
    "/policies/IST",
    {"domestic": 45, "international": 60, "terminal_extra": 20},
    403,
)
flights = {item["number"]: item for item in api("traveler", "GET", "/flights")}
a, b = flights["WL101"], flights["WL202"]
api(
    "traveler",
    "POST",
    "/trips",
    {"title": "Invalid", "flights": [b["id"], a["id"]]},
    422,
)
trip = api(
    "traveler",
    "POST",
    "/trips",
    {"title": "Проверка интеграции " + uuid4().hex[:5], "flights": [a["id"], b["id"]]},
    201,
)
path = f"/trips/{trip['id']}"
api("other", "GET", path, expected=404)
api("other", "POST", path + "/alternatives", expected=404)
assert api("traveler", "GET", path)["assessments"][0]["risk"] == "SAFE"
for name in (
    "normal",
    "small_delay",
    "risk",
    "alternatives",
    "no_route",
    "duplicate",
    "stale",
    "conflict",
    "outage",
    "recovery",
    "late",
    "midnight",
    "zones",
    "date_line",
    "dst",
    "mct",
    "recalculate",
    "concurrent",
    "snapshot",
    "timeout",
    "malformed",
):
    result = api("admin", "POST", "/lab/" + name)
    assert result["passed"], (name, result["checks"])
    print(name, result["checks"], flush=True)
with httpx.Client(
    base_url="http://provider:8100", timeout=4, trust_env=False
) as provider:
    event = provider.post(
        "/control/events",
        json={
            "flight": a["id"],
            "estimated_arr": (
                datetime.fromisoformat(a["scheduled_arr"]) + timedelta(minutes=60)
            ).isoformat(),
        },
    ).json()
    result = api("analyst", "POST", "/operations/sync")
    assert any(
        s["sequence"] == event["sequence"] and s["disposition"] == "APPLIED"
        for s in result["events"]
    )
    state = api("traveler", "GET", path)
    assert (
        state["flights"][0]["scheduled_arr"] == a["scheduled_arr"]
        and state["flights"][0]["actual_arr"] is None
    )
    active = next(i for i in state["incidents"] if i["resolved_at"] is None)
    assert (
        state["assessments"][0]["detail"]["connections"][0]["available_minutes"] == 35
    )
    assert (
        api("traveler", "POST", path + f"/incidents/{active['id']}/acknowledge")[
            "status"
        ]
        == "ACKNOWLEDGED"
    )
    notices = api("traveler", "GET", "/notifications")
    n = next(
        n
        for n in notices
        if n["trip"] == trip["id"] and n["kind"] == "CONNECTION_AT_RISK"
    )
    api("other", "POST", f"/notifications/{n['id']}/read", expected=404)
    assert api("traveler", "POST", f"/notifications/{n['id']}/read")["read_at"]
    route = api("traveler", "POST", path + "/alternatives")
    api("other", "GET", f"/searches/{route['id']}", expected=404)
    assert len(route["options"]) >= 2
    recovered = provider.post("/control/events", json={"flight": a["id"]})
    recovered.raise_for_status()
    api("analyst", "POST", "/operations/sync")
    assert api("traveler", "GET", path)["assessments"][0]["risk"] == "SAFE"

    # Force persistence to fail after fetching a real delivery. Verify the same feed row is recoverable.
    gap = provider.post(
        "/control/events", json={"flight": a["id"], "revision": result["cursor"] + 10}
    )
    gap.raise_for_status()
    pending = gap.json()["sequence"]
    with engine.begin() as conn:
        run(
            conn,
            "ALTER TABLE events ADD CONSTRAINT lab_reject CHECK(sequence<>"
            + str(int(pending))
            + ")",
        )
    try:
        api("analyst", "POST", "/operations/sync", expected=500)
        assert api("analyst", "GET", "/operations")["feed"]["cursor"] < pending
    finally:
        with engine.begin() as conn:
            run(conn, "ALTER TABLE events DROP CONSTRAINT lab_reject")
    assert any(
        x["sequence"] == pending and x["disposition"] == "APPLIED_GAP"
        for x in api("analyst", "POST", "/operations/sync")["events"]
    )

assert api("admin", "POST", "/lab/cancel")["passed"]
print(
    "22 lab scenarios and PostgreSQL integration, access scope, notification, rollback and replay verified."
)
