import json
import os
from hashlib import sha256

from sqlalchemy import create_engine, text

engine = create_engine(
    os.getenv(
        "DATABASE_URL", "postgresql+psycopg://wayline:wayline-local@localhost/wayline"
    ),
    pool_pre_ping=True,
)


def pack(value):
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)


def hash_data(value):
    return sha256(pack(value).encode()).hexdigest()


def run(conn, sql, **params):
    return conn.execute(text(sql), params)


def one(conn, sql, **params):
    row = run(conn, sql, **params).mappings().first()
    return dict(row) if row is not None else None


def many(conn, sql, **params):
    return [dict(row) for row in run(conn, sql, **params).mappings()]


def audit(conn, actor, request, action, subject, **data):
    run(
        conn,
        """INSERT INTO audit(actor,request,action,subject,detail)
                 VALUES (:a,:r,:kind,:s,CAST(:d AS jsonb))""",
        a=actor,
        r=request,
        kind=action,
        s=str(subject),
        d=pack(data),
    )
