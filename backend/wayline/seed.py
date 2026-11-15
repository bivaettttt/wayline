import os
from uuid import uuid4

from wayline.auth import passwords
from wayline.contracts import Trip
from wayline.db import engine, many, one, run
from wayline.integration import load_catalog
from wayline.trips import create

with engine.begin() as conn:
    run(conn, "SELECT pg_advisory_xact_lock(731200)")
    load_catalog(conn)
    if not one(conn, "SELECT login FROM users WHERE login='admin'"):
        password = os.environ["DEMO_PASSWORD"]
        if len(password) < 12:
            raise ValueError("At least 12 characters")
        for login, name, role in [
            ("traveler", "Анна Соколова", "TRAVELER"),
            ("other", "Илья Котов", "TRAVELER"),
            ("analyst", "Мария Волкова", "OPERATIONS_ANALYST"),
            ("admin", "Алексей Лебедев", "ADMIN"),
        ]:
            run(
                conn,
                "INSERT INTO users VALUES (:l,:n,:r,:p)",
                l=login,
                n=name,
                r=role,
                p=passwords.hash(password),
            )
        for airport, domestic, international, extra in [
            ("OVB", 35, 75, 10),
            ("IST", 45, 60, 20),
            ("FCO", 40, 70, 15),
            ("DXB", 55, 90, 25),
            ("LHR", 50, 85, 25),
            ("JFK", 45, 95, 20),
            ("HND", 40, 75, 15),
            ("LAX", 45, 80, 20),
        ]:
            run(
                conn,
                "INSERT INTO policies(airport,version,domestic,international,terminal_extra,author) VALUES (:a,1,:d,:i,:e,'admin')",
                a=airport,
                d=domestic,
                i=international,
                e=extra,
            )
        run(conn, "UPDATE feed SET healthy=true,last_success=now()")
        ids = {
            f["number"]: f["id"] for f in many(conn, "SELECT id,number FROM flights")
        }
        create(
            conn,
            Trip(title="Новосибирск — Рим", flights=[ids["WL101"], ids["WL202"]]),
            "traveler",
            uuid4(),
        )
        create(
            conn,
            Trip(title="Токио — Лос-Анджелес", flights=[ids["WL510"]]),
            "traveler",
            uuid4(),
        )
