from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema_additions(bind=None) -> None:
    """Apply lightweight column additions that create_all will not perform.

    Base.metadata.create_all only creates missing tables; it never ALTERs an
    existing table. Older databases are missing evaluation_runs.case_details
    (and cases_evaluated), which would break evaluation history.
    """
    target = bind or engine
    inspector = inspect(target)
    tables = set(inspector.get_table_names())

    if "evaluation_runs" in tables:
        columns = {col["name"] for col in inspector.get_columns("evaluation_runs")}
        with target.begin() as conn:
            if "cases_evaluated" not in columns:
                conn.execute(
                    text("ALTER TABLE evaluation_runs ADD COLUMN cases_evaluated INTEGER DEFAULT 0")
                )
            if "case_details" not in columns:
                conn.execute(
                    text("ALTER TABLE evaluation_runs ADD COLUMN case_details JSON")
                )

    if "users" in tables:
        columns = {col["name"] for col in inspector.get_columns("users")}
        with target.begin() as conn:
            if "token_version" not in columns:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0")
                )
