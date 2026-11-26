"""Off-site copies: every new backup (database + photos zip) is uploaded to an Amazon S3 bucket.

The owner sets the bucket, region and an access key that may only upload (see docs/RESTORE.md) in
Settings -> Backups. Signed with AWS Signature V4 using the standard library and requests, so no SDK is needed.
"""
import hashlib
import hmac
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

from backend import backups, models
from backend.tz import now_utc

BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")  # no dots: they break the bucket's HTTPS name
REGION_RE = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d$")
RETRY_EVERY = timedelta(hours=1)


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def signature(method: str, host: str, uri: str, headers: dict, payload_hash: str, secret: str, region: str, amz_date: str) -> tuple:
    """AWS Signature V4 for S3. headers: lower-case names, must include host, x-amz-date, x-amz-content-sha256.
    Returns (signed_headers, signature)."""
    names = sorted(headers)
    canonical = "\n".join([method, uri, "", "".join(f"{k}:{str(headers[k]).strip()}\n" for k in names), ";".join(names), payload_hash])
    scope = f"{amz_date[:8]}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret).encode(), amz_date[:8]), region), "s3"), "aws4_request")
    return ";".join(names), hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()


# Self-check against AWS's published S3 example (GET /test.txt, "Signature Version 4 examples").
assert signature("GET", "examplebucket.s3.amazonaws.com", "/test.txt",
                 {"host": "examplebucket.s3.amazonaws.com", "range": "bytes=0-9",
                  "x-amz-content-sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "x-amz-date": "20130524T000000Z"},
                 "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                 "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1", "20130524T000000Z")[1] \
    == "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"


def configured(s: models.Setting) -> bool:
    return bool(s.s3_bucket and s.s3_region and s.s3_access_key_id and s.s3_secret_access_key)


def object_key(name: str) -> str:
    return f"luz-ems/{os.environ.get('LUZ_ENV', 'local')}/{name}"


def put_file(s: models.Setting, path: str, key: str):
    """Upload one file. Raises with a readable message when S3 refuses."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    payload = h.hexdigest()
    host = f"{s.s3_bucket}.s3.{s.s3_region}.amazonaws.com"
    uri = "/" + quote(key, safe="/-_.~")
    amz = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    headers = {"host": host, "x-amz-content-sha256": payload, "x-amz-date": amz}
    signed, sig = signature("PUT", host, uri, headers, payload, s.s3_secret_access_key, s.s3_region, amz)
    headers["authorization"] = (f"AWS4-HMAC-SHA256 Credential={s.s3_access_key_id}/{amz[:8]}/{s.s3_region}/s3/aws4_request, "
                                f"SignedHeaders={signed}, Signature={sig}")
    with open(path, "rb") as f:
        r = requests.put(f"https://{host}{uri}", data=f, headers=headers, timeout=600)
    if r.status_code != 200:
        code = re.search(r"<Code>(.*?)</Code>", r.text or "")
        raise RuntimeError(f"S3 refused the upload ({r.status_code}{' ' + code.group(1) if code else ''}). "
                           "Check the bucket name, region and access key.")


def upload_latest(db, s: models.Setting) -> str:
    """Upload the newest database backup and its photos zip. Returns the database backup's name."""
    found = backups.list_backups()
    db_b = next((b for b in found if b["kind"] == "database"), None)
    if not db_b:
        db_b = {"name": backups.make_backup()["name"]}
        found = backups.list_backups()
    stamp = db_b["name"].split("-", 1)[1].rsplit(".", 1)[0]
    s.s3_last_attempt_at = now_utc()
    try:
        for name in [db_b["name"]] + [b["name"] for b in found if b["kind"] == "photos" and stamp in b["name"]]:
            put_file(s, backups.path_for(name), object_key(name))
    except Exception as e:
        s.s3_last_error = str(e)[:500]
        db.commit()
        raise
    s.s3_last_uploaded, s.s3_last_uploaded_at, s.s3_last_error = db_b["name"], now_utc(), None
    db.commit()
    return db_b["name"]


def sync(db):
    """Called every minute: send the newest backup if it isn't off-site yet; after a failure, try again hourly."""
    s = db.query(models.Setting).first()
    if not s or not configured(s):
        return
    newest = next((b["name"] for b in backups.list_backups() if b["kind"] == "database"), None)
    if not newest or newest == s.s3_last_uploaded:
        return
    if s.s3_last_error and s.s3_last_attempt_at and s.s3_last_attempt_at > now_utc() - RETRY_EVERY:
        return
    had_error = bool(s.s3_last_error)
    try:
        upload_latest(db, s)
        print(f"[offsite] uploaded {newest}")
    except Exception as e:
        print(f"[offsite] failed: {e}")
        if not had_error:  # tell the owner once, not every hour
            from backend import push
            push.notify(db, "failed", "Off-site backup failed", f"{e} Open Settings, Backups.", url="/admin#settings", tag="offsite-backup")


def status(s: models.Setting) -> dict:
    return {"configured": configured(s), "bucket": s.s3_bucket, "region": s.s3_region, "access_key_id": s.s3_access_key_id,
            "secret_set": bool(s.s3_secret_access_key), "last_uploaded": s.s3_last_uploaded,
            "last_uploaded_at": s.s3_last_uploaded_at.isoformat() if s.s3_last_uploaded_at else None,
            "last_error": s.s3_last_error, "folder": f"s3://{s.s3_bucket}/{object_key('')}" if s.s3_bucket else None}
