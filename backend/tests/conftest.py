"""Test configuration.

Tests run against a real PostgreSQL database:
- set TEST_DATABASE_URL (e.g. in Docker: postgresql+psycopg://mip:mip@db:5432/mip_test), or
- if unset, an embedded PostgreSQL is started via the `pgserver` pip package.
"""

import os
import shutil
import tempfile

import pytest


def _database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    import pgserver  # dev dependency

    data_dir = tempfile.mkdtemp(prefix="mip_test_pg_")
    server = pgserver.get_server(data_dir, cleanup_mode="stop")
    pytest._mip_pg = (server, data_dir)  # keep a reference so it isn't garbage collected
    server.psql("CREATE DATABASE mip_test;")
    return server.get_uri("mip_test").replace("postgresql://", "postgresql+psycopg://", 1)


os.environ["DATABASE_URL"] = _database_url()
os.environ["ENVIRONMENT"] = "test"
os.environ["ENRICHMENT_ENABLED"] = "false"
os.environ["LLM_PROVIDER"] = "extractive"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-secret-key-that-is-long-enough-for-hs256"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.rate_limit import ALL_LIMITERS  # noqa: E402
from app.services.bootstrap import seed_reference_data  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_db():
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    with SessionLocal() as db:
        seed_reference_data(db)
    for limiter in ALL_LIMITERS:
        limiter.reset()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register(client, email="alice@example.com", password="Passw0rd!", name="Alice") -> dict:
    resp = client.post("/auth/register", json={"email": email, "password": password, "full_name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def alice(client):
    data = register(client)
    return auth_headers(data["access_token"])


@pytest.fixture
def bob(client):
    data = register(client, email="bob@example.com", name="Bob")
    return auth_headers(data["access_token"])


def pytest_sessionfinish(session, exitstatus):
    pg = getattr(pytest, "_mip_pg", None)
    if pg:
        import logging

        logging.getLogger("pgserver").disabled = True  # avoid logging to closed stdout at exit
        server, data_dir = pg
        try:
            server.cleanup()
        except Exception:
            pass
        shutil.rmtree(data_dir, ignore_errors=True)
