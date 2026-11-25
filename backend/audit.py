"""Audit log: records every successful change made through the admin API.

A small ASGI middleware watches POST / PUT / PATCH / DELETE requests to /api/... (not sign-in or the public
booking pages). For each one that succeeds it stores the time, what changed, the record id, the data sent
(passwords, tokens and keys replaced by ***) and the device. Before a delete it keeps a copy of the record.
"""
import json
import re
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend import models
from backend.database import SessionLocal, get_db

SKIP = ("/api/auth/", "/api/public/", "/api/audit")
SECRET = re.compile(r"pass|token|secret|auth|sid|api_?key|private", re.I)
ENTITY_MODELS = {
    "clients": models.Client, "payments": models.Payment, "appointments": models.Appointment,
    "subscriptions": models.Subscription, "expenses": models.Expense, "services": models.Service,
    "staff": models.Staff, "discounts": models.DiscountCode, "gift-cards": models.GiftCard,
    "blocked-times": models.BlockedTime,
}
NAMES = {"clients": "client", "payments": "payment", "appointments": "session", "subscriptions": "package",
         "expenses": "expense", "services": "service", "staff": "trainer", "discounts": "discount code",
         "gift-cards": "gift card", "blocked-times": "blocked time", "settings": "settings", "notifications": "message",
         "backups": "backup", "push": "phone notifications", "dashboard": "dashboard"}
MAX_DETAILS = 4000


def redact(obj):
    if isinstance(obj, dict):
        return {k: ("***" if SECRET.search(str(k)) and v not in (None, "") else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def _row_dict(row) -> dict:
    out = {}
    for col in row.__table__.columns:
        v = getattr(row, col.name)
        out[col.name] = v.isoformat() if isinstance(v, datetime) else v
    return out


def _describe(data: dict) -> str:
    parts = []
    for k in ("name", "code", "client_name", "category", "status", "kind", "recipient_name"):
        if isinstance(data, dict) and data.get(k) not in (None, ""):
            parts.append(str(data[k]))
    for k in ("amount", "price", "price_paid", "value"):
        if isinstance(data, dict) and isinstance(data.get(k), (int, float)):
            parts.append(f"{k.replace('_', ' ')} {data[k]:g}")
    return ", ".join(parts[:3])


def _parse(path: str, method: str):
    segs = [s for s in path.split("/") if s][1:]  # drop "api"
    entity = segs[0] if segs else None
    ids = [int(s) for s in segs[1:] if s.isdigit()]
    tail = [s for s in segs[1:] if not s.isdigit()]
    if method == "DELETE":
        action = "deleted"
    elif method in ("PUT", "PATCH"):
        action = "updated"
    else:
        action = (tail[-1].replace("-", " ") if tail else "created")
    return entity, (ids[0] if ids else None), action


def _snapshot(entity: Optional[str], entity_id: Optional[int]) -> Optional[dict]:
    model = ENTITY_MODELS.get(entity or "")
    if not model or not entity_id:
        return None
    db = SessionLocal()
    try:
        row = db.query(model).filter(model.id == entity_id).first()
        return _row_dict(row) if row else None
    finally:
        db.close()


class AuditMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH", "DELETE"):
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if not path.startswith("/api/") or path.startswith(SKIP):
            return await self.app(scope, receive, send)
        method = scope["method"]
        entity, entity_id, action = _parse(path, method)
        before = _snapshot(entity, entity_id) if method == "DELETE" else None
        req_body, resp_body, status = bytearray(), bytearray(), {"code": 0}

        async def receive_wrapper():
            message = await receive()
            if message["type"] == "http.request" and len(req_body) < 65536:
                req_body.extend(message.get("body", b""))
            return message

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            elif message["type"] == "http.response.body" and len(resp_body) < 65536:
                resp_body.extend(message.get("body", b""))
            await send(message)

        await self.app(scope, receive_wrapper, send_wrapper)
        if status["code"] >= 400:
            return
        try:
            self._record(scope, method, path, entity, entity_id, action, before, bytes(req_body), bytes(resp_body), status["code"])
        except Exception as e:  # never break a request because of the log
            print(f"[audit] could not record {method} {path}: {e}")

    def _record(self, scope, method, path, entity, entity_id, action, before, req, resp, code):
        headers = {k.decode().lower(): v.decode(errors="ignore") for k, v in scope.get("headers", [])}
        ctype = headers.get("content-type", "")
        sent = None
        if req and "json" in ctype:
            try:
                sent = redact(json.loads(req))
            except ValueError:
                sent = None
        elif req:
            sent = "(file upload)" if "multipart" in ctype else None
        result = None
        try:
            result = json.loads(resp) if resp else None
        except ValueError:
            pass
        if entity_id is None and isinstance(result, dict) and isinstance(result.get("id"), int):
            entity_id = result["id"]
        described = _describe(before or (sent if isinstance(sent, dict) else {}) or (result if isinstance(result, dict) else {}))
        noun = NAMES.get(entity or "", entity or "item")
        summary = f"{action.capitalize()} {noun}" + (f" #{entity_id}" if entity_id else "") + (f": {described}" if described else "")
        details = {"sent": sent} if sent is not None else {}
        if before:
            details["before"] = redact(before)
        ip = (headers.get("x-forwarded-for") or "").split(",")[0].strip() or (scope.get("client") or [None])[0]
        actor = None
        auth_header = headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            from backend.auth import identity_for
            who = identity_for(auth_header[7:].strip())
            if who:
                actor = "Owner" if who["role"] == "owner" else f"{who['name']} ({who['role']})"
        db = SessionLocal()
        try:
            db.add(models.AuditLog(actor=actor, method=method, path=path, entity=entity, entity_id=entity_id, action=action,
                                   summary=summary[:250], details=json.dumps(details, default=str)[:MAX_DETAILS] if details else None,
                                   status=code, ip=ip, device=(headers.get("user-agent") or "")[:200]))
            db.commit()
        finally:
            db.close()


def prune_old(days: int = 365) -> int:
    """Keep one year of history."""
    from datetime import timedelta
    db = SessionLocal()
    try:
        n = db.query(models.AuditLog).filter(models.AuditLog.at < datetime.utcnow() - timedelta(days=days)).delete()
        db.commit()
        return n
    finally:
        db.close()


router = APIRouter(prefix="/api/audit", tags=["Audit"])


@router.get("/")
def list_audit(limit: int = Query(200, ge=1, le=2000), entity: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(models.AuditLog)
    if entity:
        q = q.filter(models.AuditLog.entity == entity)
    rows = q.order_by(models.AuditLog.at.desc(), models.AuditLog.id.desc()).limit(limit).all()
    return [{"id": r.id, "at": r.at, "method": r.method, "path": r.path, "entity": r.entity, "entity_id": r.entity_id,
             "action": r.action, "summary": r.summary, "details": r.details, "status": r.status, "ip": r.ip, "device": r.device,
             "actor": r.actor}
            for r in rows]
