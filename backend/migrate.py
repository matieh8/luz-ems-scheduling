"""Tiny additive migration: adds any model column missing from the SQLite tables.

SQLAlchemy's create_all only creates missing *tables*, so upgrading a live
database that already has the old tables needs this step. It never drops or
renames anything, so it is safe to run on every start.
"""
import re
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


def _schema_changes_pending(inspector) -> bool:
    """True when this start will alter an existing table (new column or a table rebuild below)."""
    names = inspector.get_table_names()
    for table in Base.metadata.sorted_tables:
        if table.name in names:
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            if any(col.name not in existing for col in table.columns):
                return True
    nullable = lambda t, c: {x["name"]: x["nullable"] for x in inspector.get_columns(t)}.get(c) if t in names else None
    return nullable("payments", "client_id") is False or nullable("notification_logs", "appointment_id") is False


def run_migrations():
    inspector = inspect(engine)
    if _schema_changes_pending(inspector):
        # Never change a live database without a fresh copy to go back to. If the copy fails, the app doesn't
        # start, so the deploy rolls back instead of migrating unprotected.
        from backend.backups import make_backup
        made = make_backup()
        print(f"[migrate] backup before schema change: {made['name']}")
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
        if "subscriptions.sessions_used_before" in added:
            # One time: keep each package's old "used" number; the part the bookings don't explain becomes "used before".
            conn.execute(text(
                "UPDATE subscriptions SET sessions_used_before = MAX(COALESCE(sessions_used, 0) - (SELECT COUNT(*) FROM appointments a "
                "WHERE a.subscription_id = subscriptions.id AND a.status != 'cancelled'), 0)"
            ))
        # Income that isn't from a client (social media, ads) has no client: rebuild payments once with client_id nullable.
        if "payments" in inspector.get_table_names():
            if {c["name"]: c["nullable"] for c in inspect(conn).get_columns("payments")}.get("client_id") is False:
                sql = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='payments'")).scalar()
                new_sql = re.sub(r'("?client_id"?\s+INTEGER)\s+NOT NULL', r'\1', sql, count=1)
                new_sql = re.sub(r'CREATE TABLE\s+"?payments"?', 'CREATE TABLE payments_new', new_sql, count=1)
                assert new_sql != sql and "payments_new" in new_sql
                conn.execute(text(new_sql))
                conn.execute(text("INSERT INTO payments_new SELECT * FROM payments"))
                conn.execute(text("DROP TABLE payments"))
                conn.execute(text("ALTER TABLE payments_new RENAME TO payments"))
                for ix in models.Payment.__table__.indexes:
                    ix.create(bind=conn, checkfirst=True)
        if "notification_logs.client_id" in added:
            conn.execute(text(
                "UPDATE notification_logs SET client_id = (SELECT client_id FROM appointments WHERE appointments.id = notification_logs.appointment_id) "
                "WHERE client_id IS NULL AND appointment_id IS NOT NULL"
            ))
        # notification_logs.appointment_id must be nullable so subscription_purchase logs can be stored
        if "notification_logs" in inspector.get_table_names():
            not_null = {c["name"]: c["nullable"] for c in inspector.get_columns("notification_logs")}
            if not_null.get("appointment_id") is False:
                conn.execute(text("""
                    CREATE TABLE notification_logs_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        appointment_id INTEGER,
                        type VARCHAR NOT NULL,
                        channel VARCHAR NOT NULL,
                        client_id INTEGER,
                        recipient TEXT,
                        status VARCHAR NOT NULL,
                        subject TEXT,
                        content TEXT NOT NULL,
                        external_response TEXT,
                        attempts INTEGER DEFAULT 0,
                        next_retry_at DATETIME,
                        created_at DATETIME
                    )
                """))
                conn.execute(text("""
                    INSERT INTO notification_logs_new
                    SELECT id, appointment_id, type, channel, client_id, recipient, status, subject, content, external_response, attempts, next_retry_at, created_at
                    FROM notification_logs
                """))
                conn.execute(text("DROP TABLE notification_logs"))
                conn.execute(text("ALTER TABLE notification_logs_new RENAME TO notification_logs"))
                added.append("notification_logs.appointment_id nullable")
    _normalize_expense_categories()
    if added:
        print(f"[migrate] added columns: {', '.join(added)}")
    return added


EXPENSE_CATEGORY_RENAMES = {"coffee shop": "Coffee", "somke": "Smoke"}


def clean_category(name: str) -> str:
    """Category names are plain text: the app draws the icon itself, so emoji typed into the name
    (which ends up on the wrong side of the label) are stripped, and known typos are corrected."""
    import re
    s = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]", "", name or "")
    s = re.sub(r"\s+", " ", s).strip()
    return EXPENSE_CATEGORY_RENAMES.get(s.lower(), s)


def _normalize_expense_categories():
    inspector = inspect(engine)
    if "expenses" not in inspector.get_table_names():
        return
    with engine.begin() as conn:
        for (cat,) in conn.execute(text("SELECT DISTINCT category FROM expenses")).fetchall():
            fixed = clean_category(cat)
            if fixed and fixed != cat:
                conn.execute(text("UPDATE expenses SET category = :new WHERE category = :old"), {"new": fixed, "old": cat})
                print(f"[migrate] expense category {cat!r} -> {fixed!r}")
