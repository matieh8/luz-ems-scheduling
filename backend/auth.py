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


def create_token() -> str:
    payload = f"{int(time.time()) + TOKEN_TTL_SECONDS}:{secrets.token_hex(4)}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()


def verify_token(token: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        payload, sig = raw.rsplit(".", 1)
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        expiry = int(payload.split(":")[0])
        return expiry > time.time()
    except Exception:
        return False


def require_auth(request: Request):
    if AUTH_DISABLED:
        return True
    token = None
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
    if not token:
        token = request.query_params.get("token")
    if not token or not verify_token(token):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return True


def ensure_admin_password(db: Session):
    settings = db.query(models.Setting).first()
    if settings and not settings.admin_password_hash:
        settings.admin_password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
        db.commit()
