import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend import backups, offsite
from backend.database import get_db
from backend.scheduling import get_settings

router = APIRouter(prefix="/api/backups", tags=["Backups"])


@router.get("/")
def list_backups(db: Session = Depends(get_db)):
    return {"backups": backups.list_backups(), "keep": backups.KEEP, "offsite": offsite.status(get_settings(db))}


@router.post("/")
def backup_now():
    return backups.make_backup()


class OffsiteBody(BaseModel):
    bucket: str = ""                          # empty = switch off-site copies off
    region: str = ""
    access_key_id: str = ""
    secret_access_key: Optional[str] = None   # empty = keep the one already saved


@router.put("/offsite")
def save_offsite(body: OffsiteBody, db: Session = Depends(get_db)):
    """Save the S3 details and prove they work by uploading the newest backup straight away."""
    s = get_settings(db)
    bucket, region, key_id = body.bucket.strip().lower(), body.region.strip().lower(), body.access_key_id.strip()
    if not bucket:
        s.s3_bucket = s.s3_region = s.s3_access_key_id = s.s3_secret_access_key = None
        s.s3_last_uploaded = s.s3_last_error = None
        db.commit()
        return offsite.status(s)
    if not offsite.BUCKET_RE.match(bucket):
        raise HTTPException(status_code=400, detail="Bucket name: 3-63 lower-case letters, digits and dashes (no dots)")
    if not offsite.REGION_RE.match(region):
        raise HTTPException(status_code=400, detail="Region looks wrong, e.g. me-central-1 or eu-central-1")
    if not re.match(r"^[A-Z0-9]{16,128}$", key_id):
        raise HTTPException(status_code=400, detail="Access key ID looks wrong (it starts with AKIA...)")
    secret = (body.secret_access_key or "").strip() or s.s3_secret_access_key
    if not secret:
        raise HTTPException(status_code=400, detail="Enter the secret access key")
    s.s3_bucket, s.s3_region, s.s3_access_key_id, s.s3_secret_access_key = bucket, region, key_id, secret
    s.s3_last_uploaded = None  # new place: send the newest backup again
    db.commit()
    try:
        offsite.upload_latest(db, s)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Saved, but the test upload failed: {e}")
    return offsite.status(s)


@router.get("/{name}")
def download(name: str):
    if not backups.NAME_RE.match(name or ""):
        raise HTTPException(status_code=400, detail="Not a backup file name")
    path = backups.path_for(name)
    if not path:
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(path, media_type="application/octet-stream", filename=name,
                        headers={"Cache-Control": "private, no-store"})
