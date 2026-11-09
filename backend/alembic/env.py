"""Alembic environment.

Imports the SQLAlchemy metadata from the app so autogenerate can diff the
models against a database. Run from `backend/`:

    alembic upgrade head                 # apply migrations
    alembic revision --autogenerate -m "..."   # create one
    alembic stamp head                   # mark an existing DB as migrated

`DATABASE_URL` (environment variable) overrides the URL in alembic.ini.
"""

import sys
from pathlib import Path

from alembic import context

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import Base, engine  # noqa: E402
from app import models  # noqa: F401,E402  (import registers the tables on Base.metadata)

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    import os

    return os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
