"""Automatic database backups: a consistent copy of the SQLite file once a day, newest 14 kept.

Copies live in <data dir>/backups on the same server. They protect against mistakes and a broken
database file; to survive losing the server itself, download one now and then (Settings -> Backups).
"""
import os
import re
import sqlite3
from datetime import datetime
from typing import List, Optional
from backend.database import DATA_DIR, DB_PATH

BACKUP_DIR = os.path.join(DATA_DIR, "backups")
KEEP = 14
NAME_RE = re.compile(r"^app-\d{4}-\d{2}-\d{2}_\d{6}\.db$")


def _ensure_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def list_backups() -> List[dict]:
    _ensure_dir()
    out = []
    for name in os.listdir(BACKUP_DIR):
        if NAME_RE.match(name):
            path = os.path.join(BACKUP_DIR, name)
            out.append({"name": name, "size": os.path.getsize(path),
                        "created_at": datetime.utcfromtimestamp(os.path.getmtime(path)).isoformat()})
    return sorted(out, key=lambda b: b["name"], reverse=True)


def make_backup() -> dict:
    """Copy the live database with SQLite's online backup (safe while the app is running)."""
    _ensure_dir()
    name = f"app-{datetime.utcnow():%Y-%m-%d_%H%M%S}.db"
    dest = os.path.join(BACKUP_DIR, name)
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    prune()
    return {"name": name, "size": os.path.getsize(dest), "created_at": datetime.utcnow().isoformat()}


def prune(keep: int = KEEP):
    for b in list_backups()[keep:]:
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
