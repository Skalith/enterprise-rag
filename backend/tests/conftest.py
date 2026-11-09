"""Shared test fixtures.

Environment must be set before any `app.*` import so pydantic Settings pick
it up (settings is constructed at import time).
"""

import os
import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("ENV", "development")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-32chars-min")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://raguser:ragpassword@localhost:5432/enterprise_rag",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("LANGFUSE_ENABLED", "false")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine, ensure_schema_additions  # noqa: E402
from app.main import app  # noqa: E402
from app.rbac_seed import seed_rbac_and_permissions  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _prepare_database():
    Base.metadata.create_all(bind=engine)
    ensure_schema_additions(engine)
    seed_rbac_and_permissions(SessionLocal)
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def register_user(client):
    """Register a unique employee and return (email, password, access_token)."""

    def _register(password: str = "password123", full_name: str | None = None):
        email = f"user_{uuid.uuid4().hex[:10]}@example.com"
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": full_name or "Test User",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        return email, password, body["access_token"]

    return _register
