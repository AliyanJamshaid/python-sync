import time

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from client import retry
from main import app, get_db
from models import Base


def test_retry_recovers_after_transient_failures(monkeypatch):
    """The decorator retries on network errors and returns the eventual result."""
    monkeypatch.setattr(time, "sleep", lambda _: None)
    calls = {"count": 0}

    @retry(times=3, delay=0.1)
    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise httpx.ConnectError("connection refused")
        return "ok"

    assert flaky() == "ok"
    assert calls["count"] == 3


def test_retry_reraises_once_attempts_are_exhausted(monkeypatch):
    """After the last attempt the original exception must escape, not vanish."""
    monkeypatch.setattr(time, "sleep", lambda _: None)

    @retry(times=2, delay=0.1)
    def always_fails():
        raise httpx.ConnectError("connection refused")

    with pytest.raises(httpx.ConnectError):
        always_fails()


def test_sync_is_idempotent(monkeypatch):
    """Running the sync twice updates rather than duplicates."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    fake_api_response = [
        {"name": "bulbasaur", "url": "https://pokeapi.co/api/v2/pokemon/1/"},
        {"name": "ivysaur", "url": "https://pokeapi.co/api/v2/pokemon/2/"},
    ]
    monkeypatch.setattr(main, "iter_pokemon", lambda max_items=40: iter(fake_api_response))

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        first = client.post("/sync?limit=2").json()
        second = client.post("/sync?limit=2").json()
        items = client.get("/items").json()
    finally:
        app.dependency_overrides.clear()

    assert first == {"created": 2, "updated": 0}
    assert second == {"created": 0, "updated": 2}
    assert len(items) == 2
    assert items[0]["name"] == "bulbasaur"
