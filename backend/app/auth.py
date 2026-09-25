"""Basic API security for the prototype: signed bearer tokens, role-based access, device keys, audit log."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import AUTH_SECRET, DEMO_USERS, DEVICE_API_KEY, TOKEN_TTL_HOURS
from .db import get_db
from .models import AuditLog

ROLES = ("admin", "warehouse_manager", "distributor", "retailer")
OPERATE = ("admin", "warehouse_manager", "distributor")  # may run optimisations / accept plans


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(username: str, role: str, name: str) -> str:
    payload = _b64(json.dumps({"sub": username, "role": role, "name": name,
                               "exp": int(time.time() + TOKEN_TTL_HOURS * 3600)}).encode())
    sig = _b64(hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_token(token: str) -> dict:
    try:
        payload, sig = token.split(".")
        expected = _b64(hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        data = json.loads(_unb64(payload))
        if data["exp"] < time.time():
            raise ValueError("expired")
        return data
    except Exception as exc:  # noqa: BLE001 - any failure is an auth failure
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc


def authenticate(username: str, password: str) -> dict | None:
    u = DEMO_USERS.get(username)
    if not u or not hmac.compare_digest(u[0], password):
        return None
    return {"username": username, "role": u[1], "name": u[2]}


def current_user(authorization: str = Header(default="")) -> dict:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return verify_token(authorization[7:])


def require_roles(*roles: str):
    def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role '{user['role']}' may not perform this action")
        return user
    return dep


def device_or_admin(x_device_key: str = Header(default=""), authorization: str = Header(default="")) -> dict:
    if x_device_key and hmac.compare_digest(x_device_key, DEVICE_API_KEY):
        return {"sub": "iot-gateway", "role": "device", "name": "IoT gateway"}
    if authorization.lower().startswith("bearer "):
        user = verify_token(authorization[7:])
        if user["role"] == "admin":
            return user
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Device key or admin token required")


def audit(db: Session, user: dict, action: str, resource: str, detail: str = "", request: Request | None = None) -> None:
    db.add(AuditLog(ts=datetime.utcnow(), username=user.get("sub", "?"), role=user.get("role", "?"), action=action,
                    resource=resource, detail=detail[:2000],
                    ip=(request.client.host if request and request.client else "")))
    db.commit()


__all__ = ["ROLES", "OPERATE", "issue_token", "authenticate", "current_user", "require_roles", "device_or_admin",
           "audit", "get_db"]
