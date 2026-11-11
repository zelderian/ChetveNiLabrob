import os

os.environ.setdefault(
    "DATABASE_URL",
    os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/libra_test"),
)
os.environ.setdefault("REDIS_URL", os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15"))
os.environ.setdefault("CACHE_URL", os.getenv("TEST_CACHE_URL", "redis://localhost:6379/14"))

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.cache import cache_client  # noqa: E402
from app.redis_client import redis_client  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session", autouse=True)
def _schema():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "migrations"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE loans, books, members RESTART IDENTITY CASCADE"))
    redis_client.flushdb()
    cache_client.flushdb()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def member(client):
    r = client.post(
        "/api/v1/members",
        json={"full_name": "Ivan Franko", "email": "ivan@example.com", "password": "secret123",
              "max_active_loans": 2},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def auth(client, member):
    r = client.post("/api/v1/auth/login", json={"email": "ivan@example.com", "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def make_book(client):
    counter = iter(range(1000))

    def _make(copies=1, title="Clean Architecture", author="Robert Martin"):
        n = next(counter)
        r = client.post(
            "/api/v1/books",
            json={"isbn": f"978000000{n:04d}", "title": f"{title} {n}", "author": author,
                  "published_year": 2017, "total_copies": copies},
        )
        assert r.status_code == 201, r.text
        return r.json()

    return _make
