"""End-to-end API tests against a throwaway SQLite database."""
import os
import tempfile
from datetime import datetime, timedelta, timezone

os.environ["LUZ_DATA_DIR"] = tempfile.mkdtemp(prefix="luz-test-")
os.environ["LUZ_DISABLE_JOBS"] = "1"
os.environ["LUZ_DISABLE_WHATSAPP_BRIDGE"] = "1"
os.environ["LUZ_ADMIN_PASSWORD"] = "test-pass"

import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"password": "test-pass"})
        assert r.status_code == 200, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        yield c


def next_weekday_at(hour, days_ahead=1):
    """A UTC datetime for `hour` Dubai time, on a weekday at least days_ahead away."""
    d = datetime.now(timezone.utc) + timedelta(days=days_ahead)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    local = d.replace(hour=hour, minute=0, second=0, microsecond=0, tzinfo=timezone(timedelta(hours=4)))
    return local.astimezone(timezone.utc)


def test_requires_auth():
    with TestClient(app) as c:
        assert c.get("/api/clients/").status_code == 401
        assert c.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
        assert c.get("/api/public/info").status_code == 200


def test_seeded_defaults(client):
    assert len(client.get("/api/services/").json()) >= 3
    assert len(client.get("/api/settings/hours").json()) == 7
    assert len(client.get("/api/notifications/templates").json()) >= 8


def test_booking_flow_with_notifications_and_payment(client):
    r = client.post("/api/clients/", json={"name": "Test Client", "phone": "0501112222", "email": "t@example.com"})
    cid = r.json()["id"]
    svc = client.get("/api/services/").json()[0]
    start = next_weekday_at(10)
    r = client.post("/api/appointments/", json={"client_id": cid, "service_id": svc["id"], "start_time": start.isoformat()})
    assert r.status_code == 200, r.text
    appt = r.json()
    assert appt["status"] == "scheduled"
    assert appt["price"] == svc["price"]
    assert appt["public_token"]

    # Confirmation went out on whatsapp + email (demo mode)
    logs = client.get(f"/api/notifications/logs?client_id={cid}").json()
    channels = {l["channel"] for l in logs if l["type"] == "booking_confirmation"}
    assert channels == {"whatsapp", "email"}
    assert all(l["status"] == "sent" for l in logs)
    assert "Test" in logs[0]["content"]

    # Double booking is rejected (single machine)
    r = client.post("/api/appointments/", json={"client_name": "Other", "client_phone": "0509998888",
                                                "service_id": svc["id"], "start_time": start.isoformat()})
    assert r.status_code == 409
    # ...but allowed with force
    r = client.post("/api/appointments/", json={"client_name": "Other", "client_phone": "0509998888",
                                                "service_id": svc["id"], "start_time": start.isoformat(), "force": True})
    assert r.status_code == 200

    # Outside opening hours is rejected
    r = client.post("/api/appointments/", json={"client_id": cid, "service_id": svc["id"],
                                                "start_time": next_weekday_at(23, 2).isoformat()})
    assert r.status_code == 409

    # Availability hides the taken slot
    day = start.astimezone(timezone(timedelta(hours=4))).date().isoformat()
    av = client.get(f"/api/appointments/availability?service_id={svc['id']}&date={day}").json()
    assert av["open"]
    taken = [s for s in av["slots"] if s["start_time"].startswith(start.strftime("%Y-%m-%dT%H:%M"))]
    assert taken and not taken[0]["available"]

    # Reschedule sends a reschedule message
    new_start = start + timedelta(hours=3)
    r = client.put(f"/api/appointments/{appt['id']}", json={"start_time": new_start.isoformat()})
    assert r.status_code == 200, r.text
    types = {l["type"] for l in client.get(f"/api/notifications/logs?client_id={cid}").json()}
    assert "reschedule" in types

    # Complete with payment
    r = client.post(f"/api/appointments/{appt['id']}/status",
                    json={"status": "completed", "payment_amount": svc["price"], "payment_method": "card"})
    assert r.status_code == 200
    assert r.json()["paid_amount"] == svc["price"]
    assert r.json()["balance_due"] == 0

    # Revenue report sees the payment
    today = datetime.now().date().isoformat()
    rep = client.get(f"/api/reports/summary?from={today}&to={today}").json()
    assert rep["collected"] >= svc["price"]
    assert rep["by_method"][0]["method"] == "card"


def test_subscription_consumes_sessions_and_refunds_on_cancel(client):
    cid = client.post("/api/clients/", json={"name": "Pack Client", "phone": "0503334444"}).json()["id"]
    plan = client.get("/api/subscriptions/plans").json()[0]
    r = client.post("/api/subscriptions/", json={"client_id": cid, "plan_id": plan["id"], "payment_method": "cash"})
    assert r.status_code == 200, r.text
    sub = r.json()
    assert sub["sessions_remaining"] == plan["sessions_included"]
    assert sub["paid_amount"] == plan["price"]
    svc = [s for s in client.get("/api/services/").json() if s["price"]][0]
    r = client.post("/api/appointments/", json={"client_id": cid, "service_id": svc["id"],
                                                "start_time": next_weekday_at(16, 3).isoformat()})
    assert r.status_code == 200, r.text
    appt = r.json()
    assert appt["subscription_id"] == sub["id"] and appt["price"] == 0
    assert client.get(f"/api/subscriptions/?client_id={cid}").json()[0]["sessions_remaining"] == plan["sessions_included"] - 1
    client.post(f"/api/appointments/{appt['id']}/status", json={"status": "cancelled", "reason": "sick"})
    assert client.get(f"/api/subscriptions/?client_id={cid}").json()[0]["sessions_remaining"] == plan["sessions_included"]
    types = [l["type"] for l in client.get(f"/api/notifications/logs?client_id={cid}").json()]
    assert "cancellation" in types and "subscription_purchase" in types


def test_public_booking_and_manage_link(client):
    info = client.get("/api/public/info").json()
    svc = info["services"][0]
    day = next_weekday_at(9, 4)
    av = client.get(f"/api/public/availability?service_id={svc['id']}&date={day.astimezone(timezone(timedelta(hours=4))).date()}").json()
    assert av["slots"] and all(s["available"] for s in av["slots"])
    slot = av["slots"][0]["start_time"]
    with TestClient(app) as anon:
        r = anon.post("/api/public/book", json={"name": "Web Client", "phone": "0505556666", "email": "web@example.com",
                                                "service_id": svc["id"], "start_time": slot})
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        assert anon.get(f"/api/public/appointments/{token}").json()["can_cancel"]
        assert anon.post(f"/api/public/appointments/{token}/confirm").json()["status"] == "confirmed"
        assert anon.post(f"/api/public/appointments/{token}/cancel", json={"reason": "travel"}).json()["status"] == "cancelled"
        # Same slot is bookable again after the cancellation
        r = anon.post("/api/public/book", json={"name": "Web Client", "phone": "0505556666",
                                                "service_id": svc["id"], "start_time": slot})
        assert r.status_code == 200
    # Admin was alerted and the client was created from the booking
    logs = client.get("/api/notifications/logs?type=admin_new_booking").json()
    assert logs
    assert [c for c in client.get("/api/clients/?q=Web Client").json()][0]["source"] == "online"


def test_jobs_run(client):
    assert client.post("/api/notifications/run-jobs").status_code == 200
    assert client.get("/api/dashboard/").status_code == 200
    assert client.get("/api/reports/timeseries?granularity=week").status_code == 200
    assert client.get("/api/reports/export/payments.csv").status_code == 200


def test_delete_client_and_reset_data(client):
    c = client.post("/api/clients/", json={"name": "Temp Client", "phone": "0509998888"}).json()
    client.post("/api/notifications/custom", json={"client_id": c["id"], "channels": ["whatsapp"], "body": "hi"})
    r = client.delete(f"/api/clients/{c['id']}")
    assert r.status_code == 200
    assert client.get(f"/api/clients/{c['id']}").status_code == 404
    assert not any(l["client_id"] == c["id"] for l in client.get("/api/notifications/logs").json())

    assert client.post("/api/settings/reset-data", json={"confirm": "nope"}).status_code == 400
    r = client.post("/api/settings/reset-data", json={"confirm": "DELETE", "keep_clients": True})
    assert r.status_code == 200
    assert client.get("/api/appointments/").json() == []
    assert client.get("/api/payments/").json() == []
    assert client.get("/api/clients/").json() != []
    r = client.post("/api/settings/reset-data", json={"confirm": "DELETE"})
    assert r.status_code == 200 and client.get("/api/clients/").json() == []
    assert client.get("/api/services/").json()  # catalog kept
    st = client.get("/api/notifications/whatsapp-status").json()
    assert st["status"] == "bridge_offline" and st["reason"]


def test_temporary_whatsapp_failure_is_retried_automatically(client, monkeypatch):
    from backend.database import SessionLocal
    from backend import notifications, models
    from backend.tz import utcnow
    client.put("/api/settings/", json={"demo_mode": False, "whatsapp_provider": "whatsapp_web", "whatsapp_enabled": True})
    c = client.post("/api/clients/", json={"name": "Retry Client", "phone": "0501112222", "notify_whatsapp": True}).json()
    db = SessionLocal()
    try:
        logs = notifications.send(db, "reminder", db.get(models.Client, c["id"]), raw_body="hi", channels=["whatsapp"], sync=True)
        log = db.get(models.NotificationLog, logs[0].id); db.refresh(log)
        assert log.status == "failed" and log.attempts == 1 and log.next_retry_at is not None
        assert "not running" in log.external_response and "retry automatically" in log.external_response
        # Not due yet: nothing happens
        assert notifications.run_retry_job(db) == 0
        # Make it due, pretend the bridge is now connected
        log.next_retry_at = utcnow() - timedelta(minutes=1); db.commit()
        monkeypatch.setattr(notifications, "_send_whatsapp", lambda s, to, body: "whatsapp_web: ok")
        assert notifications.run_retry_job(db) == 1
        import time
        for _ in range(50):
            db.refresh(log)
            if log.status == "sent": break
            time.sleep(0.05)
        assert log.status == "sent" and log.next_retry_at is None
    finally:
        client.put("/api/settings/", json={"demo_mode": True})
        db.close()


def test_dismiss_failed_messages_alert(client):
    from backend.database import SessionLocal
    from backend import models
    db = SessionLocal()
    try:
        c = db.query(models.Client).first() or models.Client(name="Alert Client", phone="0503334444")
        db.add(c); db.commit()
        db.add(models.NotificationLog(client_id=c.id, type="reminder", channel="whatsapp", status="failed", content="x", recipient="971503334444")); db.commit()
    finally:
        db.close()
    keys = [a["key"] for a in client.get("/api/dashboard/").json()["alerts"]]
    assert "failed_messages" in keys
    assert client.post("/api/dashboard/alerts/failed_messages/dismiss").status_code == 200
    keys = [a["key"] for a in client.get("/api/dashboard/").json()["alerts"]]
    assert "failed_messages" not in keys
    # A new failure after the dismissal brings the alert back
    db = SessionLocal()
    try:
        c = db.query(models.Client).first()
        db.add(models.NotificationLog(client_id=c.id, type="reminder", channel="whatsapp", status="failed", content="y", recipient="971503334444")); db.commit()
    finally:
        db.close()
    assert "failed_messages" in [a["key"] for a in client.get("/api/dashboard/").json()["alerts"]]
