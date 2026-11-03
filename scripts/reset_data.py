"""Clear all bookings, payments, packages, blocked times and message logs (keeps settings, services, staff, plans, templates).

Usage:  venv/bin/python scripts/reset_data.py            # clears everything incl. clients
        venv/bin/python scripts/reset_data.py --keep-clients
Set LUZ_DATA_DIR to target a specific database (e.g. data-staging).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.migrate import run_migrations  # noqa: E402
from backend.database import SessionLocal, DB_PATH  # noqa: E402
from backend.routers.settings import reset_business_data  # noqa: E402

if __name__ == "__main__":
    run_migrations()
    keep = "--keep-clients" in sys.argv
    if "--yes" not in sys.argv:
        ans = input(f"Clear all data in {DB_PATH}{' (keeping clients)' if keep else ''}? Type DELETE: ")
        if ans.strip().upper() != "DELETE":
            print("Aborted."); sys.exit(1)
    db = SessionLocal()
    try:
        counts = reset_business_data(db, keep)
    finally:
        db.close()
    for k, v in counts.items():
        print(f"  {k}: {v} deleted")
    print("Done.")
