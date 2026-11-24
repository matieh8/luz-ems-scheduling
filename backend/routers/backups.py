from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from backend import backups

router = APIRouter(prefix="/api/backups", tags=["Backups"])


@router.get("/")
def list_backups():
    return {"backups": backups.list_backups(), "keep": backups.KEEP}


@router.post("/")
def backup_now():
    return backups.make_backup()


@router.get("/{name}")
def download(name: str):
    if not backups.NAME_RE.match(name or ""):
        raise HTTPException(status_code=400, detail="Not a backup file name")
    path = backups.path_for(name)
    if not path:
        raise HTTPException(status_code=404, detail="Backup not found")
    return FileResponse(path, media_type="application/octet-stream", filename=name,
                        headers={"Cache-Control": "private, no-store"})
