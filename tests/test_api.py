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


def test_public_pages_and_landing_data():
    with TestClient(app) as c:
        home = c.get("/")
        assert home.status_code == 200 and "Stronger in" in home.text
        assert "Sign in to manage your studio" in c.get("/admin").text
        assert "Book a session" in c.get("/book").text
        info = c.get("/api/public/info").json()
        assert info["plans"] and {"name", "sessions_included", "price"} <= set(info["plans"][0])
        assert "email" in info


def test_repeat_booking_series_and_cancel(client):
    svc = client.get("/api/services/").json()[0]
    c = client.post("/api/clients/", json={"name": "Weekly Client", "phone": "0507770001"}).json()
    start = next_weekday_at(15, days_ahead=20)
    # Occupy week 3 with other clients on every machine so the series has to skip it
    settings = client.get("/api/settings/").json()
    for i in range(settings["max_concurrent_sessions"]):
        o = client.post("/api/clients/", json={"name": f"Blocker {i}", "phone": f"05088800{i:02d}"}).json()
        r = client.post("/api/appointments/", json={"client_id": o["id"], "service_id": svc["id"], "send_notification": False,
                                                     "start_time": (start + timedelta(weeks=2)).isoformat()})
        assert r.status_code == 200, r.text
    r = client.post("/api/appointments/", json={"client_id": c["id"], "service_id": svc["id"], "start_time": start.isoformat(),
                                                 "repeat_interval_weeks": 1, "repeat_count": 8})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["series_id"] and a["series_created"] == 7 and len(a["series_skipped"]) == 1
    assert a["notify_result"] and a["notify_result"][0]["status"] == "sent"   # demo mode logs it as sent
    mine = [x for x in client.get(f"/api/appointments/?client_id={c['id']}").json()]
    assert len(mine) == 7 and len({x["series_id"] for x in mine}) == 1
    # Same local time each week
    assert len({x["start_time"][11:16] for x in mine}) == 1
    log = [l for l in client.get(f"/api/notifications/logs?client_id={c['id']}").json() if l["type"] == "booking_confirmation"]
    assert len(log) == 1 and "repeats every week" in log[0]["content"] and "7 sessions" in log[0]["content"]
    # Cancel from the 3rd session on: 5 cancelled, first 2 kept
    third = sorted(mine, key=lambda x: x["start_time"])[2]
    r = client.post(f"/api/appointments/{third['id']}/cancel-series", json={"reason": "travelling"})
    assert r.status_code == 200 and r.json()["cancelled"] == 5
    statuses = [x["status"] for x in sorted(client.get(f"/api/appointments/?client_id={c['id']}").json(), key=lambda x: x["start_time"])]
    assert statuses == ["scheduled"] * 2 + ["cancelled"] * 5


def test_confirmation_result_explains_why_nothing_was_sent(client):
    svc = client.get("/api/services/").json()[0]
    c = client.post("/api/clients/", json={"name": "Silent Client", "phone": "0507770002", "notify_whatsapp": False, "notify_email": False}).json()
    r = client.post("/api/appointments/", json={"client_id": c["id"], "service_id": svc["id"], "start_time": next_weekday_at(8, days_ahead=30).isoformat()})
    res = r.json()["notify_result"]
    assert res[0]["status"] == "skipped" and "notifications switched off" in res[0]["detail"]


def test_owner_reminder_and_unpaid_bills(client):
    from backend.database import SessionLocal
    from backend import notifications, models
    from backend.tz import utcnow
    client.put("/api/settings/", json={"business_phone": "0501234567", "admin_reminder_hours": 12})
    svc = client.get("/api/services/").json()[0]
    c = client.post("/api/clients/", json={"name": "Soon Client", "phone": "0507770003"}).json()
    soon = datetime.now(timezone.utc) + timedelta(hours=5)
    a = client.post("/api/appointments/", json={"client_id": c["id"], "service_id": svc["id"], "start_time": soon.isoformat(),
                                                "force": True, "send_notification": False}).json()
    db = SessionLocal()
    try:
        notifications.run_admin_reminder_job(db)
        notifications.run_admin_reminder_job(db)  # second run must not send again
        logs = db.query(models.NotificationLog).filter(models.NotificationLog.appointment_id == a["id"],
                                                       models.NotificationLog.type == "admin_session_reminder").all()
        assert len(logs) == 1 and logs[0].recipient == "971501234567" and "Soon Client" in logs[0].content
    finally:
        db.close()

    now = datetime.now(timezone.utc)
    e = client.post("/api/expenses/", json={"date": now.isoformat(), "category": "Electricity", "amount": 420, "notes": "DEWA October", "paid": False}).json()
    assert e["paid"] is False
    s = client.get(f"/api/expenses/summary?year={now.year}&month={now.month}").json()
    assert s["unpaid_count"] >= 1 and s["unpaid_total"] >= 420
    assert client.put(f"/api/expenses/{e['id']}", json={"paid": True}).json()["paid"] is True


def test_expense_category_cleanup(client):
    from backend.migrate import clean_category, run_migrations
    assert clean_category("Somke") == "Smoke" and clean_category("coffee shop") == "Coffee"
    assert clean_category("Smoke 🚬") == "Smoke" and clean_category("🚬 Tabby ") == "Tabby"
    now = datetime.now(timezone.utc)
    e = client.post("/api/expenses/", json={"date": now.isoformat(), "category": "Somke 🚬", "amount": 20}).json()
    assert e["category"] == "Smoke"
    from backend.database import SessionLocal
    from backend import models
    db = SessionLocal()
    try:
        db.add(models.Expense(date=datetime.utcnow(), category="Coffee shop", amount=15)); db.commit()
    finally:
        db.close()
    run_migrations()
    cats = client.get("/api/expenses/categories").json()
    assert "Coffee" in cats and "Coffee shop" not in cats and "Somke" not in cats


def _fake_device():
    """A stand-in for a phone: its key pair and auth secret, as a browser would hand them over."""
    import os as _os
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from backend import push
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = priv.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = _os.urandom(16)
    return priv, push.b64u(pub), push.b64u(auth), auth


def _decrypt_like_a_phone(body, priv, auth_secret):
    """RFC 8291 receiver side, written independently of backend.push.encrypt."""
    import struct
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    salt, rs, idlen = body[:16], struct.unpack(">I", body[16:20])[0], body[20]
    sender_raw, ciphertext = body[21:21 + idlen], body[21 + idlen:]
    assert rs == 4096 and idlen == 65
    sender = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), sender_raw)
    my_raw = priv.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = priv.exchange(ec.ECDH(), sender)
    kdf = lambda s, ikm, info, n: HKDF(algorithm=hashes.SHA256(), length=n, salt=s, info=info).derive(ikm)
    ikm = kdf(auth_secret, shared, b"WebPush: info\x00" + my_raw + sender_raw, 32)
    plain = AESGCM(kdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)).decrypt(kdf(salt, ikm, b"Content-Encoding: nonce\x00", 12), ciphertext, None)
    assert plain.endswith(b"\x02")
    return plain[:-1]


def test_phone_notifications(client, monkeypatch):
    import base64, json
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
    from backend import push

    with TestClient(app) as anon:
        assert anon.get("/api/push/config").status_code == 401
        assert anon.get("/sw.js").status_code == 200 and "showNotification" in anon.get("/sw.js").text
        assert anon.get("/manifest.webmanifest").json()["display"] == "standalone"
        assert anon.get("/icons/apple-touch-icon.png").status_code == 200
        assert anon.get("/favicon.ico").status_code == 200 and 'rel="icon"' in anon.get("/book").text
    cfg = client.get("/api/push/config").json()
    assert cfg["available"] and len(push.b64u_decode(cfg["public_key"])) == 65 and cfg["devices"] == []

    priv, p256dh, auth, auth_raw = _fake_device()
    endpoint = "https://web.push.apple.com/fake-device-token"
    assert client.post("/api/push/subscribe", json={"endpoint": "http://x", "p256dh": p256dh, "auth": auth}).status_code == 400
    assert client.post("/api/push/subscribe", json={"endpoint": endpoint, "p256dh": "AAAA", "auth": auth}).status_code == 400
    r = client.post("/api/push/subscribe", json={"endpoint": endpoint, "p256dh": p256dh, "auth": auth, "device": "iPhone · home screen app",
                                                 "origin": "https://app.luz.example"})
    assert r.status_code == 200
    client.post("/api/push/subscribe", json={"endpoint": endpoint, "p256dh": p256dh, "auth": auth, "device": "iPhone"})  # same phone again
    assert len(client.get("/api/push/config").json()["devices"]) == 1

    sent = []

    class Res:
        status_code, text = 201, ""

    def fake_post(url, data=None, headers=None, timeout=None):
        sent.append((url, data, headers))
        return Res()
    monkeypatch.setattr(push.requests, "post", fake_post)

    # Test notification: decrypts on the "phone" and carries a valid VAPID signature
    r = client.post("/api/push/test", json={"endpoint": endpoint})
    assert r.status_code == 200 and r.json()["sent"] == 1
    url, body, headers = sent[-1]
    msg = json.loads(_decrypt_like_a_phone(body, priv, auth_raw))
    assert url == endpoint and "notifications are on" in msg["title"] and msg["url"] == "/admin#settings"
    assert headers["Content-Encoding"] == "aes128gcm" and headers["TTL"]
    token, key = headers["Authorization"].removeprefix("vapid t=").split(", k=")
    assert key == cfg["public_key"]
    h, c, sig = token.split(".")
    claims = json.loads(push.b64u_decode(c))
    assert claims["aud"] == "https://web.push.apple.com" and claims["sub"] == "https://app.luz.example" and claims["exp"] > 0
    raw = push.b64u_decode(sig)
    server_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), push.b64u_decode(key))
    server_pub.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
                      f"{h}.{c}".encode(), ec.ECDSA(hashes.SHA256()))

    # A new online booking pushes an alert; the client confirming and cancelling do too
    def next_msg(n_before):
        import time
        for _ in range(100):
            if len(sent) > n_before: break
            time.sleep(0.02)
        assert len(sent) > n_before, "no push was sent"
        return json.loads(_decrypt_like_a_phone(sent[-1][1], priv, auth_raw))

    svc = client.get("/api/services/").json()[0]
    with TestClient(app) as anon:
        n = len(sent)
        start = next_weekday_at(15, days_ahead=6)
        b = anon.post("/api/public/book", json={"name": "Push Client", "phone": "0507771234", "service_id": svc["id"],
                                                "start_time": start.isoformat()})
        assert b.status_code == 200, b.text
        m = next_msg(n)
        assert m["title"] == "New online booking" and "Push Client" in m["body"] and svc["name"] in m["body"] and m["url"] == "/admin#calendar"
        token = b.json()["token"]
        n = len(sent); anon.post(f"/api/public/appointments/{token}/confirm")
        assert next_msg(n)["title"] == "Push Client confirmed"
        n = len(sent); anon.post(f"/api/public/appointments/{token}/confirm")  # already confirmed: no second alert
        n2 = len(sent); assert n2 == n
        assert anon.post(f"/api/public/appointments/{token}/cancel", json={"reason": "travelling"}).status_code == 200
        m = next_msg(n2)
        assert m["title"] == "Push Client cancelled" and "travelling" in m["body"]

    # Switching a category off stops those alerts
    client.put("/api/settings/", json={"push_bookings": False})
    with TestClient(app) as anon:
        n = len(sent)
        anon.post("/api/public/book", json={"name": "Quiet Client", "phone": "0507775678", "service_id": svc["id"],
                                            "start_time": next_weekday_at(16, days_ahead=6).isoformat()})
        import time; time.sleep(0.3)
        assert len(sent) == n
    client.put("/api/settings/", json={"push_bookings": True})
    assert client.put("/api/settings/", json={"push_summary_hour": 30}).status_code == 422

    # Morning summary goes out once a day
    from backend.database import SessionLocal
    from backend import notifications, models
    db = SessionLocal()
    try:
        s = db.query(models.Setting).first(); s.push_summary_hour = 0; s.last_push_summary_on = None; db.commit()
        assert notifications.daily_summary(db) is not None
        n = len(sent); notifications.run_daily_summary_job(db)
        assert next_msg(n)["title"].startswith("Today:")
        n = len(sent); notifications.run_daily_summary_job(db); time.sleep(0.2)
        assert len(sent) == n
    finally:
        db.close()

    # A phone that dropped its subscription (410 Gone) is forgotten
    Res.status_code = 410
    assert client.post("/api/push/test", json={"endpoint": endpoint}).status_code == 502
    assert client.get("/api/push/config").json()["devices"] == []
    assert client.post("/api/push/test").status_code == 404
