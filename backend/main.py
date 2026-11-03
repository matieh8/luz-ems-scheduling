import os
import shutil
import subprocess
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.auth import require_auth, ensure_admin_password
from backend.database import DATA_DIR, ROOT_DIR, SessionLocal
from backend.migrate import run_migrations
from backend.routers import (appointments, auth, clients, dashboard, notifications, payments, public, reports,
                             services, settings, staff, subscriptions)
from backend.seed import seed_data

FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")


BRIDGE_REASON = {"reason": None}


def _start_whatsapp_bridge():
    bridge_dir = os.path.join(os.path.dirname(__file__), "whatsapp")
    if os.environ.get("LUZ_DISABLE_WHATSAPP_BRIDGE") == "1":
        BRIDGE_REASON["reason"] = "disabled: LUZ_DISABLE_WHATSAPP_BRIDGE=1 is set for this server"
        return None
    if shutil.which("node") is None:
        BRIDGE_REASON["reason"] = "Node.js is not installed on this server (install Node 18+ and restart)"
        print("[whatsapp-bridge] node not found; WhatsApp Web provider unavailable")
        return None
    if not os.path.exists(os.path.join(bridge_dir, "node_modules")):
        BRIDGE_REASON["reason"] = "bridge dependencies missing: run `npm install` inside backend/whatsapp and restart"
        print("[whatsapp-bridge] node_modules missing; run npm install in backend/whatsapp")
        return None
    env = os.environ.copy()
    env["PORT"] = os.environ.get("WHATSAPP_BRIDGE_PORT", "8020")
    env["SESSION_DIR"] = os.path.join(DATA_DIR, "whatsapp_session")
    try:
        return subprocess.Popen(["node", "server.js"], cwd=bridge_dir, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as e:
        BRIDGE_REASON["reason"] = f"bridge failed to start: {e}"
        print(f"[whatsapp-bridge] failed to start: {e}")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    seed_data()
    db = SessionLocal()
    try:
        ensure_admin_password(db)
    finally:
        db.close()

    bridge_proc = _start_whatsapp_bridge()
    app.state.whatsapp_bridge = bridge_proc
    if bridge_proc:
        def log_bridge():
            for line in bridge_proc.stdout:
                print(f"[whatsapp-bridge] {line.decode('utf-8', errors='replace').rstrip()}")
        threading.Thread(target=log_bridge, daemon=True).start()

    from apscheduler.schedulers.background import BackgroundScheduler
    from backend.notifications import run_all_jobs

    scheduler = BackgroundScheduler()

    def tick():
        db = SessionLocal()
        try:
            run_all_jobs(db)
        except Exception as e:
            print(f"[jobs] error: {e}")
        finally:
            db.close()

    if os.environ.get("LUZ_DISABLE_JOBS") != "1":
        scheduler.add_job(tick, "interval", minutes=1, id="jobs", replace_existing=True)
        scheduler.start()
    app.state.scheduler = scheduler
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)
    if bridge_proc:
        bridge_proc.terminate()
        try:
            bridge_proc.wait(timeout=5)
        except Exception:
            bridge_proc.kill()


app = FastAPI(title="LUZ EMS Scheduling", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Open endpoints
app.include_router(auth.router)
app.include_router(public.router)

# Admin endpoints (require login)
protected = [Depends(require_auth)]
for r in (clients.router, staff.router, services.router, appointments.router, appointments.blocked_router,
          settings.router, dashboard.router, notifications.router, subscriptions.router, payments.router,
          reports.router):
    app.include_router(r, dependencies=protected)


@app.get("/api/health")
def health():
    return {"status": "ok", "env": os.environ.get("LUZ_ENV", "local")}


@app.get("/book")
def book_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "book.html"))


@app.get("/a/{token}")
def manage_page(token: str):
    return FileResponse(os.path.join(FRONTEND_DIR, "manage.html"))


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
