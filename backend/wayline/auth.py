from hashlib import sha256
from secrets import token_urlsafe
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from wayline.db import audit, engine, one, run

passwords = PasswordHasher()
dummy = passwords.hash(token_urlsafe(24))
bearer = HTTPBearer(auto_error=False)


def digest(value):
    return sha256(value.encode()).hexdigest()


def signin(payload, request):
    with engine.begin() as conn:
        row = one(conn, "SELECT * FROM users WHERE login=:login", login=payload.login)
        try:
            valid = passwords.verify(
                row["password"] if row else dummy, payload.password
            )
        except VerifyMismatchError:
            valid = False
        if not valid or not row:
            raise HTTPException(401, "INVALID_CREDENTIALS")
        token = token_urlsafe(32)
        run(
            conn,
            "INSERT INTO sessions VALUES (:key,:login,now()+interval '8 hours')",
            key=digest(token),
            login=row["login"],
        )
        audit(conn, row["login"], request, "SIGN_IN", row["login"])
        return {
            "token": token,
            "login": row["login"],
            "name": row["name"],
            "role": row["role"],
        }


def auth(creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if creds:
        key = digest(creds.credentials)
        with engine.connect() as conn:
            row = one(
                conn,
                """SELECT u.login,u.name,u.role FROM users u JOIN sessions s ON s.login=u.login
                 WHERE s.digest=:key AND s.expires>now()""",
                key=key,
            )
        if row:
            return row | {"session": key}
    raise HTTPException(401, "AUTH_REQUIRED")


Actor = Annotated[dict, Depends(auth)]


def allow(actor, *roles):
    if actor["role"] not in roles:
        raise HTTPException(403, "ROLE_FORBIDDEN")
