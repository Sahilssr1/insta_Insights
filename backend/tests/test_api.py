"""End-to-end API tests (mock provider): auth, connect, sync, insights, media, comments."""

from __future__ import annotations

import pytest


@pytest.fixture
async def connected_client(authed_client):
    """Client with a linked mock Instagram account (via the real OAuth callback)."""
    connect_res = await authed_client.get("/api/instagram/connect")
    assert connect_res.status_code == 200
    state = connect_res.json()["authorize_url"].split("state=")[1]
    cb = await authed_client.get(
        "/api/instagram/callback", params={"code": "mock_code", "state": state}
    )
    assert cb.status_code == 302
    assert "connected=1" in cb.headers["location"]
    return authed_client


async def test_register_and_login(client):
    res = await client.post(
        "/api/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    assert res.status_code == 201
    assert "access_token" in res.json()

    res = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()

    # Duplicate email rejected.
    res = await client.post(
        "/api/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    assert res.status_code == 409


async def test_unauthenticated_blocked(client):
    res = await client.get("/api/instagram/account")
    assert res.status_code == 401


async def test_account_404_before_connect(authed_client):
    res = await authed_client.get("/api/instagram/account")
    assert res.status_code == 404


async def test_connect_flow_and_account(connected_client):
    res = await connected_client.get("/api/instagram/account")
    assert res.status_code == 200
    body = res.json()
    assert body["username"].startswith("mock.creator")
    assert body["token"]["connected"] is True
    assert body["token"]["expired"] is False
    # The raw access token must never be exposed.
    assert "MOCK_LONG_LIVED" not in res.text


async def test_oauth_error_redirect(authed_client):
    res = await authed_client.get("/api/instagram/callback", params={"error": "access_denied"})
    assert res.status_code == 302
    assert "error=access_denied" in res.headers["location"]


async def test_sync_then_insights(connected_client):
    sync = await connected_client.post("/api/instagram/sync")
    assert sync.status_code == 200
    assert sync.json()["status"] == "success"

    status = await connected_client.get("/api/instagram/sync/status")
    assert status.json()["last_status"] == "success"

    for path in ("/api/instagram/insights", "/api/instagram/insights/summary"):
        res = await connected_client.get(path, params={"days": 30})
        assert res.status_code == 200
        body = res.json()
        assert body["range_days"] == 30
        assert body["totals"]["views"] is not None

    ts = await connected_client.get(
        "/api/instagram/insights/timeseries", params={"days": 7, "metrics": "views,reach"}
    )
    assert ts.status_code == 200
    assert ts.json()["metric_names"] == ["views", "reach"]
    assert len(ts.json()["points"]) > 0

    bad = await connected_client.get("/api/instagram/insights", params={"days": 13})
    assert bad.status_code == 400


async def test_media_list_sort_and_detail(connected_client):
    await connected_client.post("/api/instagram/sync")
    for sort in ("latest", "views", "likes", "comments", "shares", "saves"):
        res = await connected_client.get("/api/instagram/media", params={"sort": sort})
        assert res.status_code == 200, sort
    res = await connected_client.get("/api/instagram/media")
    body = res.json()
    assert body["total"] > 0
    first = body["items"][0]

    detail = await connected_client.get(f"/api/instagram/media/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["instagram_media_id"] == first["instagram_media_id"]

    insights = await connected_client.get(f"/api/instagram/media/{first['id']}/insights")
    assert insights.status_code == 200
    assert insights.json()["media_id"] == first["id"]

    missing = await connected_client.get("/api/instagram/media/999999")
    assert missing.status_code == 404


async def test_audience(connected_client):
    res = await connected_client.get(
        "/api/instagram/audience", params={"breakdown": "age", "timeframe": "last_30_days"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["breakdown"] == "age"
    assert len(body["buckets"]) > 0

    bad = await connected_client.get("/api/instagram/audience", params={"breakdown": "nope"})
    assert bad.status_code == 400


async def test_comments_flow(connected_client):
    await connected_client.post("/api/instagram/sync")
    res = await connected_client.get("/api/instagram/media")
    media_id = res.json()["items"][0]["id"]

    comments = await connected_client.get(f"/api/instagram/media/{media_id}/comments")
    assert comments.status_code == 200
    assert len(comments.json()["items"]) > 0

    reply = await connected_client.post(
        "/api/instagram/comments/mock_c1/replies", json={"message": "Thanks!"}
    )
    assert reply.status_code == 200
    assert reply.json()["text"] == "Thanks!"

    hide = await connected_client.post(
        "/api/instagram/comments/mock_c1/hide", params={"hide": True}
    )
    assert hide.status_code == 200

    delete = await connected_client.delete("/api/instagram/comments/mock_c1")
    assert delete.status_code == 200


async def test_cross_user_isolation(app, session_factory):
    """User B must not access user A's connected Instagram account."""
    from httpx import ASGITransport, AsyncClient

    from app.core import security
    from app.models.instagram import User

    async with session_factory() as db:
        for name, email in (("UserA", "a@example.com"), ("UserB", "b@example.com")):
            db.add(
                User(name=name, email=email, password_hash=security.hash_password("password123"))
            )
        await db.commit()

    transport = ASGITransport(app=app)

    async def login_as(email: str) -> AsyncClient:
        c = AsyncClient(transport=transport, base_url="http://test")
        res = await c.post("/api/auth/login", json={"email": email, "password": "password123"})
        assert res.status_code == 200
        c.headers["Authorization"] = f"Bearer {res.json()['access_token']}"
        return c

    client_a = await login_as("a@example.com")
    client_b = await login_as("b@example.com")

    # A connects their Instagram account.
    connect_res = await client_a.get("/api/instagram/connect")
    state = connect_res.json()["authorize_url"].split("state=")[1]
    cb = await client_a.get("/api/instagram/callback", params={"code": "c", "state": state})
    assert cb.status_code == 302

    # B sees no account, and B's sync is rejected.
    assert (await client_b.get("/api/instagram/account")).status_code == 404
    assert (await client_b.post("/api/instagram/sync")).status_code == 404
    assert (await client_b.get("/api/instagram/media")).status_code == 404

    await client_a.aclose()
    await client_b.aclose()
