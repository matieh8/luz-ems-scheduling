import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Separate data directories let staging and live run side by side on one server.
DATA_DIR = os.environ.get("LUZ_DATA_DIR") or os.path.join(ROOT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.environ.get("LUZ_DB_PATH") or os.path.join(DATA_DIR, "app.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
