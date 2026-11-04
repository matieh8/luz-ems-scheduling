"""Tiny additive migration: adds any model column missing from the SQLite tables.

SQLAlchemy's create_all only creates missing *tables*, so upgrading a live
database that already has the old tables needs this step. It never drops or
renames anything, so it is safe to run on every start.
"""
from sqlalchemy import inspect, text
from backend.database import engine, Base
from backend import models  # noqa: F401  (registers every table on Base.metadata)


def _sql_type(col):
    t = col.type
    name = t.__class__.__name__.upper()
    if name in ("INTEGER", "BOOLEAN"):
        return "INTEGER"
    if name == "FLOAT":
        return "REAL"
    if name == "DATETIME":
        return "DATETIME"
    return "TEXT"


def run_migrations():
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    added = []
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                default = ""
                if col.default is not None and getattr(col.default, "is_scalar", False):
                    val = col.default.arg
                    if isinstance(val, bool):
                        default = f" DEFAULT {int(val)}"
                    elif isinstance(val, (int, float)):
                        default = f" DEFAULT {val}"
                    elif isinstance(val, str):
                        default = f" DEFAULT '{val}'"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {_sql_type(col)}{default}'))
                added.append(f"{table.name}.{col.name}")
        # Older rows have no public token / price snapshot
        if "appointments" in inspector.get_table_names():
            rows = conn.execute(text("SELECT id FROM appointments WHERE public_token IS NULL")).fetchall()
            import secrets
            for (aid,) in rows:
                conn.execute(text("UPDATE appointments SET public_token=:t WHERE id=:i"),
                             {"t": secrets.token_urlsafe(16), "i": aid})
            if "appointments.price" in added:  # column was just created: snapshot the service price onto old rows
                conn.execute(text(
                    "UPDATE appointments SET price = COALESCE((SELECT price FROM services WHERE services.id = appointments.service_id), 0) "
                    "WHERE subscription_id IS NULL"
                ))
        if "notification_logs.client_id" in added:
            conn.execute(text(
                "UPDATE notification_logs SET client_id = (SELECT client_id FROM appointments WHERE appointments.id = notification_logs.appointment_id) "
                "WHERE client_id IS NULL AND appointment_id IS NOT NULL"
            ))
    if added:
        print(f"[migrate] added columns: {', '.join(added)}")
    return added
