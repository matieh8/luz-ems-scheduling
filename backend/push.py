"""Web Push for the admin app (iPhone / Android home-screen apps and desktop browsers).

Implements the two standards a push service expects, using only `cryptography` and `requests`:
  * RFC 8291 / RFC 8188 "aes128gcm" payload encryption
  * RFC 8292 VAPID authentication (an ES256-signed JWT)

The server key pair is created once and kept in the data directory (vapid.json). Each phone or
browser that enables notifications is stored as a PushSubscription row.
"""
import base64
import json
import os
import struct
import threading
import time
from typing import Iterable, Optional
from urllib.parse import urlparse

import requests
from sqlalchemy.orm import Session

from backend import models
from backend.database import DATA_DIR, SessionLocal

try:  # keep the app bootable even if the dependency is missing on a server
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    AVAILABLE = True
except Exception:  # pragma: no cover
    AVAILABLE = False

VAPID_PATH = os.path.join(DATA_DIR, "vapid.json")
_lock = threading.Lock()
_keys = None

# What each kind of alert is called in Settings (Setting.<column>) and its default deep link.
KINDS = {
    "booking": "push_bookings",          # new online booking, client confirmed / cancelled
    "reminder": "push_session_reminders",  # heads-up before each session
    "failed": "push_failed_messages",    # a client message could not be delivered
    "summary": "push_daily_summary",     # morning digest
    "test": None,
}


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(text: str) -> bytes:
    text = (text or "").strip().replace("+", "-").replace("/", "_")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ------------------------------------------------------------------ server keys
def _load_keys():
    """Returns (private_key, public_key_b64url). Created on first use."""
    global _keys
    with _lock:
        if _keys:
            return _keys
        if os.path.exists(VAPID_PATH):
            with open(VAPID_PATH) as f:
                raw = json.load(f)
            private = ec.derive_private_key(int.from_bytes(b64u_decode(raw["private"]), "big"), ec.SECP256R1())
        else:
            private = ec.generate_private_key(ec.SECP256R1())
            number = private.private_numbers().private_value.to_bytes(32, "big")
            fd = os.open(VAPID_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump({"private": b64u(number)}, f)
        public = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        _keys = (private, b64u(public))
        return _keys


def public_key() -> Optional[str]:
    return _load_keys()[1] if AVAILABLE else None


# ------------------------------------------------------------------ protocol
def vapid_header(endpoint: str, subject: str, ttl_seconds: int = 12 * 3600) -> str:
    private, public = _load_keys()
    u = urlparse(endpoint)
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = b64u(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + ttl_seconds, "sub": subject},
                             separators=(",", ":")).encode())
    der = private.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    sig = b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={head}.{claims}.{sig}, k={public}"


def encrypt(payload: bytes, p256dh: str, auth: str) -> bytes:
    """RFC 8291 message encryption, single aes128gcm record."""
    ua_public_raw = b64u_decode(p256dh)
    auth_secret = b64u_decode(auth)
    ua_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public_raw)
    as_private = ec.generate_private_key(ec.SECP256R1())
    as_public_raw = as_private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = as_private.exchange(ec.ECDH(), ua_public)

    def hkdf(salt, ikm, info, length):
        return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)

    ikm = hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_public_raw + as_public_raw, 32)
    salt = os.urandom(16)
    cek = hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    ciphertext = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)  # 0x02 marks the last record
    return salt + struct.pack(">I", 4096) + bytes([len(as_public_raw)]) + as_public_raw + ciphertext


def _subject(settings: models.Setting, sub: models.PushSubscription) -> str:
    # Apple rejects malformed or localhost subjects, so prefer the real site address.
    if sub.origin and sub.origin.startswith("https://") and "localhost" not in sub.origin:
        return sub.origin
    if settings.public_base_url and settings.public_base_url.startswith("https://"):
        return settings.public_base_url.rstrip("/")
    if settings.business_email and "@" in settings.business_email:
        return f"mailto:{settings.business_email.strip()}"
    return "mailto:noreply@example.com"


def _post(sub: models.PushSubscription, body: bytes, subject: str, tag: Optional[str]):
    headers = {"Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": str(24 * 3600),
               "Urgency": "high", "Authorization": vapid_header(sub.endpoint, subject)}
    if tag:
        headers["Topic"] = "".join(c if c.isalnum() or c in "-_" else "-" for c in tag)[:32]
    return requests.post(sub.endpoint, data=body, headers=headers, timeout=15)


def deliver(db: Session, subs: Iterable[models.PushSubscription], message: dict) -> dict:
    """Send to each device now. Devices whose subscription has expired are forgotten."""
    from backend.tz import utcnow
    settings = db.query(models.Setting).first()
    out = {"sent": 0, "failed": 0, "removed": 0, "errors": []}
    data = json.dumps(message, separators=(",", ":")).encode()
    for sub in list(subs):
        try:
            res = _post(sub, encrypt(data, sub.p256dh, sub.auth), _subject(settings, sub), message.get("tag"))
            code = res.status_code
        except Exception as e:
            out["failed"] += 1
            out["errors"].append(str(e)[:200])
            sub.last_error = str(e)[:300]
            continue
        if code in (200, 201, 202, 204):
            out["sent"] += 1
            sub.last_success_at = utcnow()
            sub.last_error = None
        elif code in (404, 410):  # the phone dropped the subscription (app removed, permission revoked)
            out["removed"] += 1
            db.delete(sub)
        else:
            out["failed"] += 1
            detail = f"{code} {(res.text or '')[:200]}"
            out["errors"].append(detail)
            sub.last_error = detail
    db.commit()
    return out


def _deliver_async(message: dict):
    db = SessionLocal()
    try:
        result = deliver(db, db.query(models.PushSubscription).all(), message)
        if result["failed"]:
            print(f"[push] {result}")
    except Exception as e:
        print(f"[push] delivery error: {e}")
    finally:
        db.close()


def notify(db: Session, kind: str, title: str, body: str, url: str = "/admin", tag: Optional[str] = None, sync: bool = False):
    """Push an admin alert to every device that enabled notifications. Never raises."""
    try:
        if not AVAILABLE:
            return None
        settings = db.query(models.Setting).first()
        column = KINDS.get(kind)
        if column and settings is not None and getattr(settings, column) is False:
            return None
        if db.query(models.PushSubscription).count() == 0:
            return None
        prefix = "[Staging] " if os.environ.get("LUZ_ENV") == "staging" else ""
        message = {"title": prefix + title, "body": body, "url": url, "tag": tag or kind}
        if sync:
            return deliver(db, db.query(models.PushSubscription).all(), message)
        threading.Thread(target=_deliver_async, args=(message,), daemon=True).start()
    except Exception as e:
        print(f"[push] notify failed: {e}")
    return None
