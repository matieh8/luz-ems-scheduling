from backend.database import SessionLocal
from backend import models
from backend.notifications import ensure_templates


DEFAULT_HOURS = {  # 0 = Monday
    0: ("07:00", "21:00", False), 1: ("07:00", "21:00", False), 2: ("07:00", "21:00", False),
    3: ("07:00", "21:00", False), 4: ("07:00", "21:00", False), 5: ("09:00", "18:00", False),
    6: ("09:00", "14:00", True),
}


def seed_data():
    db = SessionLocal()
    try:
        settings = db.query(models.Setting).first()
        if not settings:
            settings = models.Setting(business_name="LUZ EMS", demo_mode=True, business_phone="0501234567")
            db.add(settings)

        if db.query(models.BusinessHours).count() == 0:
            for dow, (o, c, closed) in DEFAULT_HOURS.items():
                db.add(models.BusinessHours(day_of_week=dow, open_time=o, close_time=c, closed=closed))

        if db.query(models.Service).count() == 0:
            db.add_all([
                models.Service(name="EMS Body Sculpting", duration_minutes=45, buffer_minutes=15, price=250.0,
                               color="#2a78d6", category="EMS", description="Full body EMS sculpting session"),
                models.Service(name="EMS Recovery", duration_minutes=30, buffer_minutes=15, price=150.0,
                               color="#1baf7a", category="EMS", description="Post-workout recovery session"),
                models.Service(name="EMS Strength", duration_minutes=45, buffer_minutes=15, price=250.0,
                               color="#eb6834", category="EMS", description="Strength-focused EMS training"),
                models.Service(name="EMS Trial Session", duration_minutes=20, buffer_minutes=10, price=0.0,
                               color="#eda100", category="Trial", description="First-time trial session"),
            ])

        if db.query(models.Staff).count() == 0:
            db.add_all([
                models.Staff(name="Coach Luz", role="Head Trainer", color="#6250d6"),
                models.Staff(name="Coach Maya", role="Trainer", color="#e87ba4"),
            ])

        if db.query(models.SubscriptionPlan).count() == 0:
            db.add_all([
                models.SubscriptionPlan(name="5 Sessions Pack", sessions_included=5, duration_days=45, price=1100.0,
                                        description="5 EMS sessions, valid 45 days"),
                models.SubscriptionPlan(name="10 Sessions Pack", sessions_included=10, duration_days=90, price=2000.0,
                                        description="10 EMS sessions, valid 90 days"),
                models.SubscriptionPlan(name="Monthly Unlimited", sessions_included=30, duration_days=30, price=3000.0,
                                        description="Up to one session per day"),
            ])

        if db.query(models.Expense).count() == 0:
            from datetime import datetime, timedelta
            base = datetime.utcnow().replace(day=1)
            demo = [
                ("Fast food", 45.00, "Lunch break", "Card"),
                ("Fast food", 32.50, "Drive-through", "Card"),
                ("Fast food", 28.00, "Snacks", "Cash"),
                ("Fast food", 52.00, "Dinner", "Card"),
                ("Fuel", 120.00, "Petrol station", "Card"),
                ("Fuel", 85.00, "Top-up", "Card"),
                ("Fuel", 140.00, "Full tank", "Card"),
                ("Groceries", 250.00, "Weekly shop", "Card"),
                ("Groceries", 75.50, "Fresh produce", "Cash"),
                ("Groceries", 180.00, "Supermarket run", "Card"),
                ("Utilities", 450.00, "Electricity bill", "Card"),
                ("Utilities", 120.00, "Internet", "Card"),
                ("Subscriptions", 55.00, "Music streaming", "Card"),
                ("Subscriptions", 30.00, "Cloud storage", "Card"),
                ("Transport", 25.00, "Taxi", "Cash"),
                ("Transport", 18.00, "Parking", "Cash"),
                ("Health", 200.00, "Gym membership", "Card"),
                ("Health", 90.00, "Supplements", "Card"),
                ("Shopping", 350.00, "New trainers", "Card"),
                ("Shopping", 120.00, "Accessories", "Card"),
            ]
            for i, (cat, amt, note, pmt) in enumerate(demo):
                day_offset = (i * 3) % 28
                db.add(models.Expense(
                    date=base + timedelta(days=day_offset),
                    category=cat,
                    payment_method=pmt,
                    amount=amt,
                    notes=note
                ))
        db.commit()
        ensure_templates(db)
    finally:
        db.close()
