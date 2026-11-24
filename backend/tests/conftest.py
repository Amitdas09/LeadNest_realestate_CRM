"""Test setup.

Tests run against a separate PostgreSQL database (leadflow_test) on the
Docker Compose server. The schema is rebuilt from Alembic migrations at the
start of each run, so migrations are exercised by every test run.
"""

import os
from pathlib import Path

# Must be set before any app module reads settings.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://leadflow:leadflow@127.0.0.1:5433/leadflow_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-that-is-long-enough-123456")
# Tests never talk to Google or Meta; WhatsApp sends are monkeypatched.
os.environ.update({
    "WORKERS_ENABLED": "false",
    "GOOGLE_SHEET_ID": "",
    "WHATSAPP_PHONE_NUMBER_ID": "test-phone-id",
    "WHATSAPP_BUSINESS_ACCOUNT_ID": "",  # no template lookups against Meta in tests
    "WHATSAPP_ACCESS_TOKEN": "test-token",
    "WHATSAPP_APP_SECRET": "test-app-secret",
    "WHATSAPP_VERIFY_TOKEN": "test-verify-token",
    "WHATSAPP_OPENING_TEMPLATE": "hello_world",
})

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _ensure_database(url: str) -> None:
    target = make_url(url)
    admin_engine = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"),
                             {"n": target.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def database():
    _ensure_database(TEST_DATABASE_URL)
    engine = create_engine(TEST_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = TEST_DATABASE_URL
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables(database):
    from app.core.db import engine

    yield
    # TRUNCATE does not fire row-level triggers, so the append-only audit
    # trigger does not block test cleanup.
    with engine.begin() as conn:
        tables = conn.scalars(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'")).all()
        conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    from app.core.db import SessionLocal

    with SessionLocal() as session:
        yield session


DEFAULT_PASSWORD = "correct-horse-battery"


@pytest.fixture
def make_user(db):
    from app.core.security import hash_password
    from app.models import User

    def _make(role: str = "agent", email: str | None = None, active: bool = True):
        user = User(
            email=email or f"{role}-{os.urandom(3).hex()}@example.com",
            full_name=f"Test {role.title()}",
            role=role,
            password_hash=hash_password(DEFAULT_PASSWORD),
            is_active=active,
        )
        db.add(user)
        db.commit()
        return user

    return _make


@pytest.fixture
def login(client):
    def _login(user) -> dict[str, str]:
        r = client.post("/api/v1/auth/login",
                        json={"email": user.email, "password": DEFAULT_PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login
