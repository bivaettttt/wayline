from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from wayline.domain import local_instant
from wayline.integration import provider

SCENARIOS = {
    "normal": "Поездка по расписанию",
    "small_delay": "Небольшая задержка",
    "risk": "Риск пересадки",
    "cancel": "Отмена рейса",
    "alternatives": "Есть альтернативы",
    "no_route": "Альтернатив нет",
    "duplicate": "Дубликат события",
    "stale": "Устаревшая версия",
    "conflict": "Конфликт версий",
    "outage": "Недоступность провайдера",
    "recovery": "Восстановление синхронизации",
    "late": "Запоздавшее событие",
    "midnight": "Перелёт через полночь",
    "zones": "Разные часовые пояса",
    "date_line": "Линия перемены дат",
    "dst": "Переход DST",
    "mct": "Новая версия MCT",
    "recalculate": "Повторный перерасчёт",
    "concurrent": "Конкурентная синхронизация",
    "snapshot": "Изменилось расписание",
    "timeout": "Тайм-аут провайдера",
    "malformed": "Некорректный ответ",
}


def experiment(name, token, traveler_token):
    trace = []
    checks = {}
    after = None
    with httpx.Client(
        base_url="http://127.0.0.1:8000/api", timeout=12, trust_env=False
    ) as client:

        def api(method, path, body=None, status=200, traveler=False):
            response = client.request(
                method,
                path,
                json=body,
                headers={
                    "Authorization": "Bearer " + (traveler_token if traveler else token)
                },
            )
            result = response.json()
            trace.append(
                {
                    "service": "Wayline",
                    "method": method,
                    "path": path,
                    "input": body,
                    "status": response.status_code,
                    "request_id": response.headers.get("X-Request-ID"),
                    "response": result,
                }
            )
            if response.status_code != status:
                raise RuntimeError(f"{path} returned HTTP {response.status_code}")
            return result

        def upstream(method, path, body=None):
            result = provider(method, path, json=body)
            trace.append(
                {
                    "service": "Provider",
                    "method": method,
                    "path": path,
                    "input": body,
                    "response": result,
                }
            )
            return result

        def poll():
            return api("POST", "/operations/sync")

        flights = {f["number"]: f for f in api("GET", "/flights")}
        a, b = flights["WL101"], flights["WL202"]
        trip = api(
            "POST",
            "/trips",
            {"title": "Lab · " + SCENARIOS[name], "flights": [a["id"], b["id"]]},
            status=201,
            traveler=True,
        )
        path = f"/trips/{trip['id']}"
        before = api("GET", path)
        baseline = {
            "status": a["status"],
            "estimated_dep": a["estimated_dep"],
            "estimated_arr": a["estimated_arr"],
            "actual_dep": a["actual_dep"],
            "actual_arr": a["actual_arr"],
            "terminal_dep": a["terminal_dep"],
            "terminal_arr": a["terminal_arr"],
        }
        if a["status"] == "CANCELLED" and name not in {
            "normal",
            "midnight",
            "date_line",
            "dst",
            "zones",
            "no_route",
            "outage",
            "recovery",
            "timeout",
            "malformed",
        }:
            raise RuntimeError(
                "Reset the isolated lab after cancellation before comparing the same flight"
            )
        planned = datetime.fromisoformat(a["scheduled_arr"])

        def event(delay=0, **overrides):
            return upstream(
                "POST",
                "/control/events",
                {
                    "flight": a["id"],
                    **baseline,
                    "estimated_arr": (planned + timedelta(minutes=delay)).isoformat(),
                    **overrides,
                },
            )

        def expect_outcome(response, sequence, strategy):
            return any(
                e["sequence"] == sequence and e["disposition"] == strategy
                for e in response["events"]
            )

        if name in {"small_delay", "risk", "alternatives", "cancel"}:
            item = event(
                15 if name == "small_delay" else 60,
                **({"status": "CANCELLED"} if name == "cancel" else {}),
            )
            checks["applied"] = any(
                e["sequence"] == item["sequence"]
                and e["disposition"].startswith("APPLIED")
                for e in poll()["events"]
            )
            after = api("GET", path)
            expected = (
                "SAFE"
                if name == "small_delay"
                else "MISSED"
                if name == "cancel"
                else "AT_RISK"
            )
            checks["risk"] = after["assessments"][0]["risk"] == expected
            if name in {"alternatives", "cancel", "risk"}:
                found = api("POST", path + "/alternatives")
                checks["feasible_options"] = len(found["options"]) >= 2
        elif name == "normal":
            checks["two_legs"] = len(before["flights"]) == 2
            checks["planned_gap"] = (
                before["assessments"][0]["detail"]["connections"][0]["planned_minutes"]
                == 95
            )
        elif name == "no_route":
            found = api(
                "POST",
                "/routes",
                {
                    "origin": "FCO",
                    "destination": "HND",
                    "earliest": a["scheduled_dep"],
                    "max_legs": 1,
                    "max_hours": 24,
                },
            )
            checks["empty_result"] = found["status"] == "NO_FEASIBLE_ALTERNATIVE"
        elif name in {
            "duplicate",
            "stale",
            "conflict",
            "late",
            "concurrent",
            "snapshot",
        }:
            initial = event(15)
            poll()
            if name == "duplicate":
                second = upstream("POST", f"/control/replay/{initial['sequence']}")
                checks["duplicate"] = expect_outcome(
                    poll(), second["sequence"], "DUPLICATE"
                )
            elif name == "stale":
                event(35)
                poll()
                second = event(5, revision=initial["event"]["revision"])
                checks["stale"] = expect_outcome(poll(), second["sequence"], "STALE")
            elif name == "conflict":
                second = event(50, revision=initial["event"]["revision"])
                checks["conflict"] = expect_outcome(
                    poll(), second["sequence"], "REVISION_CONFLICT"
                )
            elif name == "late":
                second = event(
                    30, source_time=(datetime.now(UTC) - timedelta(hours=5)).isoformat()
                )
                checks["late_applied"] = expect_outcome(
                    poll(), second["sequence"], "APPLIED_LATE"
                )
            elif name == "concurrent":
                event(31)
                second = event(32)
                with ThreadPoolExecutor(2) as pool:
                    outcomes = list(pool.map(lambda _: poll(), range(2)))
                after = api("GET", path)
                checks["latest_wins"] = (
                    after["flights"][0]["revision"] == second["event"]["revision"]
                )
                checks["one_processed"] = sum(len(r["events"]) for r in outcomes) == 2
            else:
                result = api("POST", path + "/alternatives")
                event(40)
                poll()
                checks["obsolete_snapshot"] = (
                    api("GET", f"/searches/{result['id']}")["current"] is False
                )
        elif name in {"outage", "recovery", "timeout", "malformed"}:
            mode = {"timeout": "slow", "malformed": "invalid"}.get(name, "unavailable")
            upstream("POST", "/control/mode", {"mode": mode})
            try:
                initial = poll()
                checks["failure_visible"] = initial["status"] in {
                    "PROVIDER_UNAVAILABLE",
                    "PROVIDER_TIMEOUT",
                    "PROVIDER_INVALID_RESPONSE",
                }
                after = api("GET", path)
                checks["stale_snapshot"] = after["feed"]["fresh"] is False
            finally:
                upstream("POST", "/control/mode", {"mode": "normal"})
            recovered = poll()
            checks["resumed"] = (
                recovered["status"] == "OK" and recovered["cursor"] == initial["cursor"]
            )
        elif name == "mct":
            versions = api("GET", "/policies")
            old = next(v for v in versions if v["airport"] == "IST")
            target = {
                k: old[k] for k in ("domestic", "international", "terminal_extra")
            }
            updated = api(
                "POST", "/policies/IST", target | {"international": 110}, status=201
            )
            after = api("GET", path)
            checks["new_policy"] = (
                after["assessments"][0]["detail"]["connections"][0]["policy_version"]
                == updated["version"]
            )
            checks["risk_recomputed"] = after["assessments"][0]["risk"] in {
                "AT_RISK",
                "MISSED",
            }
            api("POST", "/policies/IST", target, status=201)
        elif name == "recalculate":
            x = api("POST", path + "/recalculate")
            y = api("POST", path + "/recalculate")
            checks["same_assessment"] = x["id"] == y["id"]
        elif name in {"midnight", "zones", "date_line", "dst"}:
            flight = flights[
                {
                    "midnight": "WL400",
                    "zones": "WL101",
                    "date_line": "WL510",
                    "dst": "WL520",
                }[name]
            ]
            view = api("GET", f"/flights/{flight['id']}")
            dep = datetime.fromisoformat(view["scheduled_dep"]).astimezone(
                ZoneInfo(view["origin_zone"])
            )
            arr = datetime.fromisoformat(view["scheduled_arr"]).astimezone(
                ZoneInfo(view["destination_zone"])
            )
            checks["positive_elapsed"] = arr.astimezone(UTC) > dep.astimezone(UTC)
            if name == "midnight":
                checks["next_date"] = arr.date() > dep.date()
            elif name == "date_line":
                checks["arrival_local_previous_date"] = arr.date() < dep.date()
            elif name == "zones":
                checks["different_zone_offsets"] = arr.utcoffset() != dep.utcoffset()
            else:
                earlier = local_instant(
                    datetime(2026, 11, 1, 1, 30), "America/New_York", 0
                )
                later = local_instant(
                    datetime(2026, 11, 1, 1, 30), "America/New_York", 1
                )
                checks["repeated_local_hour_elapsed"] = (later - earlier) == timedelta(
                    hours=1
                )
            after = {
                "flight": view,
                "departure_local": dep.isoformat(),
                "arrival_local": arr.isoformat(),
            }
        if name in {
            "small_delay",
            "risk",
            "alternatives",
            "duplicate",
            "stale",
            "conflict",
            "late",
            "concurrent",
            "snapshot",
        }:
            upstream("POST", "/control/events", {"flight": a["id"], **baseline})
            poll()
        return {
            "passed": all(checks.values()) and bool(checks),
            "checks": checks,
            "before": before,
            "after": after or api("GET", path),
            "trace": trace,
        }
