import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.database import engine, Base
from backend.routers import clients, services, appointments, settings, dashboard, notifications, subscriptions
from backend.seed import seed_data


def _start_whatsapp_bridge():
    import subprocess
    import os
    bridge_dir = os.path.join(os.path.dirname(__file__), "whatsapp")
    if not os.path.exists(os.path.join(bridge_dir, "node_modules")):
        return None
    env = os.environ.copy()
    env["PORT"] = "8020"
    env["SESSION_DIR"] = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "whatsapp_session")
    return subprocess.Popen(
        ["node", "server.js"],
        cwd=bridge_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_data()

    # Start WhatsApp Web bridge
    bridge_proc = _start_whatsapp_bridge()
    app.state.whatsapp_bridge = bridge_proc
    if bridge_proc:
        import threading
        def log_bridge():
            for line in bridge_proc.stdout:
                print(f"[whatsapp-bridge] {line.decode('utf-8', errors='replace').rstrip()}")
        threading.Thread(target=log_bridge, daemon=True).start()

    # Start background reminder scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    from backend.database import SessionLocal
    from backend.notifications import run_reminder_job

    scheduler = BackgroundScheduler()

    def tick():
        db = SessionLocal()
        try:
            run_reminder_job(db)
        finally:
            db.close()

    scheduler.add_job(tick, "interval", minutes=1, id="reminder_job", replace_existing=True)
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown(wait=False)
    if bridge_proc:
        bridge_proc.terminate()
        try:
            bridge_proc.wait(timeout=5)
        except Exception:
            bridge_proc.kill()


app = FastAPI(title="LUZ EMS Scheduling", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(clients.router)
app.include_router(services.router)
app.include_router(appointments.router)
app.include_router(settings.router)
app.include_router(dashboard.router)
app.include_router(notifications.router)
app.include_router(subscriptions.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
