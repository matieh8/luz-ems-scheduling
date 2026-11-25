"""Automatic backups: once a day, a consistent copy of the SQLite database plus a zip of the progress photos.
The newest 14 of each are kept.

Copies live in <data dir>/backups on the same server. They protect against mistakes and a broken
database file; to survive losing the server itself, download them now and then (Settings -> Backups).
How to restore: docs/RESTORE.md.
"""
import os
import re
import sqlite3
import zipfile
from datetime import datetime
from typing import List, Optional
from backend.database import DATA_DIR, DB_PATH

BACKUP_DIR = os.path.join(DATA_DIR, "backups")
PHOTO_DIR = os.path.join(DATA_DIR, "photos")
KEEP = 14
NAME_RE = re.compile(r"^(app-\d{4}-\d{2}-\d{2}_\d{6}\.db|photos-\d{4}-\d{2}-\d{2}_\d{6}\.zip)$")


def _ensure_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def _kind(name: str) -> str:
    return "photos" if name.startswith("photos-") else "database"


def list_backups() -> List[dict]:
    """Newest first; for the same moment the database copy comes before its photos zip."""
    _ensure_dir()
    out = []
    for name in os.listdir(BACKUP_DIR):
        if NAME_RE.match(name):
            path = os.path.join(BACKUP_DIR, name)
            out.append({"name": name, "kind": _kind(name), "size": os.path.getsize(path),
                        "created_at": datetime.utcfromtimestamp(os.path.getmtime(path)).isoformat()})
    stamp = lambda b: b["name"].split("-", 1)[1].rsplit(".", 1)[0]
    return sorted(out, key=lambda b: (stamp(b), b["kind"] == "database"), reverse=True)


def _zip_photos(dest: str) -> bool:
    """Zip every progress photo. Returns False (and writes nothing) when there are none."""
    files = []
    for root, _, names in os.walk(PHOTO_DIR):
        files += [os.path.join(root, n) for n in names]
    if not files:
        return False
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as z:  # photos are already compressed
        for f in files:
            z.write(f, os.path.relpath(f, DATA_DIR))  # stored as photos/<client id>/<file>
    return True


def make_backup() -> dict:
    """Copy the live database with SQLite's online backup (safe while the app is running), and zip the photos."""
    _ensure_dir()
    stamp = f"{datetime.utcnow():%Y-%m-%d_%H%M%S}"
    name = f"app-{stamp}.db"
    dest = os.path.join(BACKUP_DIR, name)
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    result = {"name": name, "size": os.path.getsize(dest), "created_at": datetime.utcnow().isoformat(), "photos": None}
    photos = os.path.join(BACKUP_DIR, f"photos-{stamp}.zip")
    if _zip_photos(photos):
        result["photos"] = {"name": os.path.basename(photos), "size": os.path.getsize(photos)}
    prune()
    return result


def prune(keep: int = KEEP):
    backups = list_backups()
    for kind in ("database", "photos"):
        for b in [b for b in backups if b["kind"] == kind][keep:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, b["name"]))
            except FileNotFoundError:
                pass


def path_for(name: str) -> Optional[str]:
    if not NAME_RE.match(name or ""):
        return None
    path = os.path.join(BACKUP_DIR, name)
    return path if os.path.exists(path) else None


def run_daily_backup() -> Optional[dict]:
    """Called by the minute job: makes today's backup if there isn't one yet."""
    today = f"app-{datetime.utcnow():%Y-%m-%d}_"
    if any(b["name"].startswith(today) for b in list_backups()):
        return None
    return make_backup()
