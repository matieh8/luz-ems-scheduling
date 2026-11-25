import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.database import DATA_DIR, get_db
from backend import models

TOKEN_TTL_SECONDS = 30 * 24 * 3600
AUTH_DISABLED = os.environ.get("LUZ_AUTH_DISABLED", "") == "1"
DEFAULT_ADMIN_PASSWORD = os.environ.get("LUZ_ADMIN_PASSWORD", "luz-admin")


def _secret() -> bytes:
    env = os.environ.get("LUZ_SECRET")
    if env:
        return env.encode()
    path = os.path.join(DATA_DIR, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip().encode()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return hmac.compare_digest(check, digest)


def _pw_stamp(password_hash: Optional[str]) -> str:
    """Short fingerprint of the current password: changing it signs out old sessions."""
    return hashlib.sha256((password_hash or "").encode()).hexdigest()[:10]


def create_token(role: str = "owner", staff_id: int = 0, stamp: str = "") -> str:
    """Every token carries role, staff id and a password stamp, so changing a password signs out old sessions."""
    base = f"{int(time.time()) + TOKEN_TTL_SECONDS}:{secrets.token_hex(4)}"
    payload = f"{base}:{role}:{int(staff_id)}:{stamp}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()


def parse_token(token: str) -> Optional[dict]:
    """{"role", "staff_id", "stamp"} for a valid, unexpired token, else None."""
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        payload, sig = raw.rsplit(".", 1)
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        parts = payload.split(":")
        if int(parts[0]) <= time.time():
            return None
        if len(parts) < 5:
            return None  # old-style owner token without a password stamp: sign in again
        return {"role": parts[2], "staff_id": int(parts[3]), "stamp": parts[4]}
    except Exception:
        return None


# ---------------------------------------------------------------- permissions
# What each staff role may do, checked on the server for every request (the owner can do everything).
_ANY, _READ = {"GET", "POST", "PUT", "PATCH", "DELETE"}, {"GET"}
_COMMON = [  # every signed-in account
    (_READ, r"/api/auth/me$"), (_READ, r"/api/services/"), (_READ, r"/api/staff/$"), (_READ, r"/api/settings/(hours)?$"),
    (_READ, r"/api/subscriptions/plans$"), (_ANY, r"/api/push/"), (_READ, r"/api/blocked-times/"),
]
_TRAINER = _COMMON + [
    (_ANY - {"DELETE"}, r"/api/appointments/"),
    (_READ, r"/api/clients/"), ({"PUT"}, r"/api/clients/\d+$"),
    (_ANY, r"/api/clients/(\d+/)?(notes|measurements|photos)(/|$)"), (_ANY, r"/api/clients/(notes|measurements|photos)/"),
    (_READ, r"/api/subscriptions/$"), (_READ, r"/api/notifications/logs"), ({"POST"}, r"/api/notifications/\d+/(reminder|confirmation)$"),
    (_READ, r"/api/devices/"), ({"POST"}, r"/api/devices/\d+/maintenance$"),
]
_RECEPTION = _TRAINER + [
    (_ANY, r"/api/appointments/"), (_ANY - {"DELETE"}, r"/api/clients/"), (_ANY, r"/api/blocked-times/"),
    (_ANY - {"DELETE"}, r"/api/subscriptions/"), (_ANY - {"DELETE"}, r"/api/payments/"),
    (_READ, r"/api/discounts/"), (_ANY, r"/api/gift-cards/"), (_ANY, r"/api/leads/"),
    # Reception can send and retry messages, but approving held automatic messages stays with owner/manager.
    (_READ, r"/api/notifications/(logs|pending)"), ({"POST"}, r"/api/notifications/logs/\d+/retry$"),
    ({"POST"}, r"/api/notifications/(custom$|\d+/)"),
]
_MANAGER_DENY = [r"/api/backups/", r"/api/audit/", r"/api/auth/password$", r"/api/staff/\d+/account$"]
PAGES = {
    "owner": ["dashboard", "calendar", "clients", "subscriptions", "leads", "payments", "expenses", "reports", "messages", "catalog", "settings"],
    "manager": ["dashboard", "calendar", "clients", "subscriptions", "leads", "payments", "expenses", "reports", "messages", "catalog"],
    "reception": ["calendar", "clients", "subscriptions", "leads", "payments", "messages"],
    "trainer": ["calendar", "clients"],
}


def allowed(role: str, method: str, path: str) -> bool:
    import re
    if role == "owner":
        return True
    if role == "manager":
        if any(re.match(p, path) for p in _MANAGER_DENY):
            return False
        if path.startswith("/api/settings/") and method != "GET":
            return False
        return True
    rules = {"trainer": _TRAINER, "reception": _RECEPTION}.get(role)
    return bool(rules) and any(method in m and re.match(p, path) for m, p in rules)


def identity_for(token: Optional[str], db=None) -> Optional[dict]:
    """Who a token belongs to, re-checked against the staff record so a switched-off account stops at once."""
    data = parse_token(token) if token else None
    if not data:
        return None
    from backend.database import SessionLocal
    own = db is None
    db = db or SessionLocal()
    try:
        if data["role"] == "owner":
            settings = db.query(models.Setting).first()
            if not settings or _pw_stamp(settings.admin_password_hash) != data["stamp"]:
                return None
            return {"role": "owner", "staff_id": 0, "name": "Owner"}
        s = db.query(models.Staff).filter(models.Staff.id == data["staff_id"]).first()
        if (not s or not s.active or s.access_role != data["role"] or not s.password_hash
                or _pw_stamp(s.password_hash) != data["stamp"]):
            return None
        return {"role": s.access_role, "staff_id": s.id, "name": s.name}
    finally:
        if own:
            db.close()


def token_from(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.query_params.get("token")


def require_auth(request: Request):
    if AUTH_DISABLED:
        request.state.identity = {"role": "owner", "staff_id": 0, "name": "Owner"}
        return True
    ident = identity_for(token_from(request))
    if not ident:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not allowed(ident["role"], request.method, request.url.path):
        raise HTTPException(status_code=403, detail="Your account doesn't have access to this. Ask the owner.")
    request.state.identity = ident
    return True


# ---------------------------------------------------------------- login throttling
_FAILS: dict = {}
MAX_FAILS, FAIL_WINDOW = 8, 15 * 60
MAX_FAILS_PER_ACCOUNT = 30  # across all addresses, so changing IP doesn't give unlimited guesses


def too_many_attempts(key: str) -> bool:
    now = time.time()
    recent = [t for t in _FAILS.get(key, []) if t > now - FAIL_WINDOW]
    _FAILS[key] = recent
    if len(_FAILS) > 10000:  # many different names or addresses: drop the ones with no recent failures
        for k in [k for k, v in _FAILS.items() if not v or v[-1] <= now - FAIL_WINDOW]:
            _FAILS.pop(k, None)
    limit = MAX_FAILS_PER_ACCOUNT if key.startswith("account|") else MAX_FAILS
    return len(recent) >= limit


def record_failure(key: str):
    _FAILS.setdefault(key, []).append(time.time())


def clear_failures(key: str):
    _FAILS.pop(key, None)


def ensure_admin_password(db: Session):
    settings = db.query(models.Setting).first()
    if settings and not settings.admin_password_hash:
        settings.admin_password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
        db.commit()
