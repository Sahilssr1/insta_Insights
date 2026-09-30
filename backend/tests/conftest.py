"""Test fixtures: in-memory async SQLite DB, mock provider, dependency overrides."""

from __future__ import annotations

import os

os.environ["INSTAGRAM_PROVIDER"] = "mock"
os.environ["ENVIRONMENT"] = "development"

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import auth as auth_router
from app.api import instagram as instagram_router
from app.core import security
from app.db.session import Base, get_session
from app.models.instagram import User


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def db(session_factory):
    async with session_factory() as session:
        yield session


@pytest.fixture
async def user(db):
    u = User(
        name="Test User",
        email="test@example.com",
        password_hash=security.hash_password("password123"),
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture
def app(session_factory):
    """FastAPI app wired to the in-memory DB (no lifespan migrations)."""
    test_app = FastAPI()

    async def override_session():
        async with session_factory() as session:
            yield session

    test_app.dependency_overrides[get_session] = override_session
    test_app.include_router(auth_router.router)
    test_app.include_router(instagram_router.router)
    return test_app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def authed_client(client, user):
    token = security.create_access_token(user.id)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def rebuild_settings(monkeypatch):
    """Rebuild the global settings object from (possibly patched) env vars.

    The module-level ``settings`` is constructed at import time, so tests
    that change env vars must rebuild it for ``get_provider()`` to see them.
    """

    def _rebuild(**env: str):
        import app.core.config as config_module

        for key, value in env.items():
            monkeypatch.setenv(key, value)
        fresh = config_module.Settings()
        monkeypatch.setattr(config_module, "settings", fresh)
        return fresh

    return _rebuild
