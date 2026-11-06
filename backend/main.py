import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.auth import require_auth, ensure_admin_password
from backend.database import DATA_DIR, ROOT_DIR, SessionLocal
from backend.migrate import run_migrations
from backend.routers import (appointments, auth, clients, dashboard, expenses, notifications, payments, public,
                             reports, services, settings, staff, subscriptions)
from backend.seed import seed_data

FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")


BRIDGE_REASON = {"reason": None}
_bridge_lock = threading.Lock()
_bridge_stop_event = threading.Event()


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
    # The bridge runs in backend/whatsapp, so relative DATA_DIR would be resolved
    # from that directory. Pass absolute paths so the session/QR files land in the
    # same place as the SQLite database.
    session_dir = os.path.join(DATA_DIR, "whatsapp_session")
    env["SESSION_DIR"] = os.path.abspath(session_dir)
    env["DATA_DIR"] = os.path.abspath(DATA_DIR)
    try:
        return subprocess.Popen(["node", "server.js"], cwd=bridge_dir, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as e:
        BRIDGE_REASON["reason"] = f"bridge failed to start: {e}"
        print(f"[whatsapp-bridge] failed to start: {e}")
        return None


def _stop_bridge(proc):
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=15)  # give the bridge time to close the browser so the session is saved
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _bridge_log_thread(proc):
    for line in proc.stdout:
        print(f"[whatsapp-bridge] {line.decode('utf-8', errors='replace').rstrip()}")


def _bridge_watchdog(app):
    """Restart the WhatsApp bridge if its process dies or gets stuck."""
    stuck_since = None
    bridge_port = int(os.environ.get("WHATSAPP_BRIDGE_PORT", "8020"))
    status_url = f"http://127.0.0.1:{bridge_port}/status"
    reset_url = f"http://127.0.0.1:{bridge_port}/reset"
    while not _bridge_stop_event.is_set():
        with _bridge_lock:
            proc = getattr(app.state, "whatsapp_bridge", None)

        # Case 1: bridge process died
        if proc is not None and proc.poll() is not None:
            print(f"[whatsapp-bridge] process exited with code {proc.returncode}; restarting in 5s")
            stuck_since = None
            time.sleep(5)
            if _bridge_stop_event.is_set():
                break
            new_proc = _start_whatsapp_bridge()
            if new_proc:
                with _bridge_lock:
                    app.state.whatsapp_bridge = new_proc
                threading.Thread(target=_bridge_log_thread, args=(new_proc,), daemon=True).start()
                BRIDGE_REASON["reason"] = None
            else:
                BRIDGE_REASON["reason"] = "bridge restart failed (see earlier log)"
            time.sleep(25)
            continue

        # Case 2: bridge is alive but stuck in a bad state
        try:
            with urllib.request.urlopen(status_url, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                status = data.get("status", "unknown")
                if status in ("ready", "authenticated", "awaiting_qr"):
                    stuck_since = None
                elif status in ("initializing", "auth_failure", "disconnected"):
                    if stuck_since is None:
                        stuck_since = time.time()
                    elif time.time() - stuck_since > 180:
                        print(f"[whatsapp-bridge] bridge stuck in '{status}' for >3m; calling /reset")
                        try:
                            urllib.request.urlopen(reset_url, timeout=10).read()
                        except Exception as e:
                            print(f"[whatsapp-bridge] /reset failed: {e}; will restart process")
                            _stop_bridge(proc)
                        stuck_since = None
                else:
                    stuck_since = None
        except Exception as e:
            # HTTP endpoint not up yet; if it stays down too long, treat as stuck
            if stuck_since is None:
                stuck_since = time.time()
            elif time.time() - stuck_since > 300:
                print(f"[whatsapp-bridge] status endpoint unreachable for >5m; restarting process")
                _stop_bridge(proc)
                stuck_since = None
        time.sleep(30)


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
        threading.Thread(target=_bridge_log_thread, args=(bridge_proc,), daemon=True).start()
        threading.Thread(target=_bridge_watchdog, args=(app,), daemon=True).start()

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
    _bridge_stop_event.set()
    with _bridge_lock:
        _stop_bridge(getattr(app.state, "whatsapp_bridge", None))


app = FastAPI(title="LUZ EMS Scheduling", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Open endpoints
app.include_router(auth.router)
app.include_router(public.router)

# Admin endpoints (require login)
protected = [Depends(require_auth)]
app.include_router(expenses.router, dependencies=protected)
for r in (clients.router, staff.router, services.router, appointments.router, appointments.blocked_router,
          settings.router, dashboard.router, notifications.router, subscriptions.router, payments.router,
          reports.router):
    app.include_router(r, dependencies=protected)


@app.get("/api/health")
def health():
    return {"status": "ok", "env": os.environ.get("LUZ_ENV", "local")}


@app.get("/")
def landing_page():
    """Public marketing site. The admin app lives at /admin."""
    return FileResponse(os.path.join(FRONTEND_DIR, "home.html"))


@app.get("/admin")
def admin_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/book")
def book_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "book.html"))


@app.get("/a/{token}")
def manage_page(token: str):
    return FileResponse(os.path.join(FRONTEND_DIR, "manage.html"))


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
