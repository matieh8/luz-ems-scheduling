from datetime import datetime, timedelta
from backend.database import SessionLocal
from backend import models


def seed_data():
    db = SessionLocal()
    try:
        # Ensure settings row exists
        settings = db.query(models.Setting).first()
        if not settings:
            settings = models.Setting(business_name="LUZ EMS", demo_mode=True)
            db.add(settings)

        # Seed services if none
        if db.query(models.Service).count() == 0:
            services = [
                models.Service(
                    name="EMS Body Sculpting",
                    duration_minutes=45,
                    price=250.0,
                    color="#8b5cf6",
                    description="Full body EMS sculpting session",
                ),
                models.Service(
                    name="EMS Recovery",
                    duration_minutes=30,
                    price=150.0,
                    color="#10b981",
                    description="Post-workout recovery session",
                ),
                models.Service(
                    name="EMS Trial Session",
                    duration_minutes=20,
                    price=0.0,
                    color="#f59e0b",
                    description="First-time trial session",
                ),
            ]
            db.add_all(services)

        # Seed demo clients if none
        if db.query(models.Client).count() == 0:
            clients = [
                models.Client(name="Demo Client", phone="0501234567", email="demo@example.com"),
                models.Client(name="Sarah Ahmed", phone="0559876543", email="sarah@example.com"),
            ]
            db.add_all(clients)

        # Seed subscription plans if none
        if db.query(models.SubscriptionPlan).count() == 0:
            plans = [
                models.SubscriptionPlan(
                    name="10 Sessions Pack",
                    sessions_included=10,
                    duration_days=90,
                    price=2000.0,
                    description="10 EMS sessions, valid 90 days",
                ),
                models.SubscriptionPlan(
                    name="Monthly Unlimited",
                    sessions_included=30,
                    duration_days=30,
                    price=3000.0,
                    description="Up to one session per day",
                ),
            ]
            db.add_all(plans)

        db.commit()
    finally:
        db.close()
