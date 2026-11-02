"""Populate a realistic demo dataset (clients, history, packages, payments) for staging.

Usage:  LUZ_DATA_DIR=data-staging venv/bin/python scripts/seed_demo.py
Safe to re-run: it skips when demo data already exists.
"""
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.migrate import run_migrations  # noqa: E402
from backend.seed import seed_data  # noqa: E402
from backend.database import SessionLocal  # noqa: E402
from backend import models  # noqa: E402
from backend.tz import local_to_utc, local_today  # noqa: E402

random.seed(7)
NAMES = ["Sarah Ahmed", "Omar Khalil", "Layla Hassan", "Yousef Nasser", "Maryam Al Ali", "Khalid Saeed", "Noor Rashid",
         "Hamad Al Marzouqi", "Dina Farouk", "Rania Mansour", "Ali Hussein", "Fatima Zayed", "Tariq Abdullah",
         "Hana Youssef", "Salem Al Kaabi", "Jana Saleh", "Majid Al Amiri", "Reem Haddad", "Bilal Karim", "Aisha Noor"]
SOURCES = ["instagram", "referral", "walk-in", "online", "google"]


def main():
    run_migrations()
    seed_data()
    db = SessionLocal()
    try:
        if db.query(models.Client).count() >= 10:
            print("Demo data already present, skipping.")
            return
        settings = db.query(models.Setting).first()
        tz = settings.timezone
        services = {s.name: s for s in db.query(models.Service).all()}
        staff = db.query(models.Staff).all()
        plans = {p.name: p for p in db.query(models.SubscriptionPlan).all()}
        today = local_today(tz)
        now = datetime.utcnow()

        clients = []
        for i, name in enumerate(NAMES):
            created = now - timedelta(days=random.randint(5, 120))
            c = models.Client(name=name, phone=f"05{random.randint(0, 5)}{random.randint(1000000, 9999999)}",
                              email=name.lower().replace(" ", ".") + "@example.com", source=random.choice(SOURCES),
                              created_at=created, notify_sms=False)
            db.add(c)
            clients.append(c)
        db.commit()

        # Packages for about half the clients
        subs = {}
        for c in clients[::2]:
            plan = random.choice([plans["5 Sessions Pack"], plans["10 Sessions Pack"], plans["10 Sessions Pack"], plans["Monthly Unlimited"]])
            start = max(c.created_at, now - timedelta(days=random.randint(10, 70)))
            s = models.Subscription(client_id=c.id, plan_id=plan.id, start_date=start,
                                    end_date=start + timedelta(days=plan.duration_days), sessions_total=plan.sessions_included,
                                    sessions_used=0, price_paid=plan.price, status="active", created_at=start)
            db.add(s)
            db.commit()
            db.add(models.Payment(client_id=c.id, subscription_id=s.id, amount=plan.price,
                                  method=random.choice(["card", "card", "transfer", "cash"]), paid_at=start, notes=plan.name))
            subs[c.id] = s
        db.commit()

        # 8 weeks of history + 2 weeks ahead
        slots = ["07:00", "08:00", "09:00", "10:00", "11:00", "12:00", "16:00", "17:00", "18:00", "19:00", "20:00"]
        for day_offset in range(-56, 15):
            d = today + timedelta(days=day_offset)
            if d.weekday() == 6:
                continue
            n = random.randint(3, 7) if d.weekday() < 5 else random.randint(2, 4)
            day_slots = random.sample(slots, n)
            for hm in day_slots:
                h, m = map(int, hm.split(":"))
                if d.weekday() == 5 and (h < 9 or h >= 18):
                    continue
                c = random.choice(clients)
                if c.created_at.date() > d:
                    continue
                svc = random.choice([services["EMS Body Sculpting"], services["EMS Body Sculpting"], services["EMS Strength"],
                                     services["EMS Recovery"], services["EMS Trial Session"]])
                start = local_to_utc(datetime(d.year, d.month, d.day, h, m), tz)
                end = start + timedelta(minutes=svc.duration_minutes)
                sub = subs.get(c.id)
                use_sub = sub is not None and sub.start_date <= start and sub.sessions_used < sub.sessions_total and svc.price
                price = 0.0 if use_sub else float(svc.price or 0)
                if start < now:
                    status = random.choices(["completed", "cancelled", "no_show"], [88, 7, 5])[0]
                else:
                    status = random.choices(["scheduled", "confirmed"], [55, 45])[0]
                a = models.Appointment(client_id=c.id, service_id=svc.id, staff_id=random.choice(staff).id,
                                       subscription_id=sub.id if use_sub else None, start_time=start, end_time=end,
                                       status=status, price=price, source=random.choice(["admin", "admin", "online"]),
                                       created_at=start - timedelta(days=random.randint(1, 7)),
                                       reminder_sent_at=start - timedelta(hours=12) if start < now else None,
                                       follow_up_sent_at=end + timedelta(hours=2) if status == "completed" else None,
                                       completed_at=end if status == "completed" else None,
                                       confirmed_at=start - timedelta(hours=20) if status in ("confirmed", "completed") else None,
                                       cancelled_at=start - timedelta(hours=6) if status == "cancelled" else None,
                                       cancelled_by="client" if status == "cancelled" else None)
                db.add(a)
                db.flush()
                if use_sub and status != "cancelled":
                    sub.sessions_used += 1
                if status == "completed" and price > 0 and random.random() < 0.9:
                    db.add(models.Payment(client_id=c.id, appointment_id=a.id, amount=price,
                                          method=random.choice(["cash", "card", "card", "transfer"]), paid_at=end + timedelta(minutes=5)))
        db.commit()
        print(f"Seeded {len(clients)} clients, {db.query(models.Appointment).count()} appointments, "
              f"{db.query(models.Payment).count()} payments, {db.query(models.Subscription).count()} packages.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
