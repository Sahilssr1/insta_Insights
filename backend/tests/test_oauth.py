"""OAuth connect/callback orchestration with the mock provider."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.instagram import InstagramToken, OAuthState
from app.services import oauth_service
from app.services.providers.mock_provider import MockInstagramProvider


@pytest.fixture
def provider():
    return MockInstagramProvider()


async def test_start_connect_creates_state_and_url(db, user, provider):
    url = await oauth_service.start_connect(db, user.id, provider)
    assert "code=mock_dev_" in url and "&state=" in url
    result = await db.execute(select(OAuthState).where(OAuthState.user_id == user.id))
    row = result.scalar_one()
    assert not row.used


async def test_finish_connect_links_account(db, user, provider):
    url = await oauth_service.start_connect(db, user.id, provider)
    state = url.split("state=")[1]
    account = await oauth_service.finish_connect(
        db, provider, code="mock_code", state=state, error=None
    )
    # code "mock_code" has no dev suffix -> legacy suffix "1"
    assert account.username == "mock.creator.1"
    assert account.instagram_user_id == "mock_ig_1"
    assert account.user_id == user.id
    # Token stored encrypted.
    result = await db.execute(
        select(InstagramToken).where(InstagramToken.instagram_account_id == account.id)
    )
    token = result.scalar_one()
    assert token.access_token_encrypted != "MOCK_LONG_LIVED"
    # State is single-use.
    with pytest.raises(oauth_service.OAuthFlowError) as exc_info:
        await oauth_service.finish_connect(db, provider, code="mock_code", state=state, error=None)
    assert exc_info.value.code == "state_reused"


async def test_finish_connect_unknown_state_rejected(db, provider):
    with pytest.raises(oauth_service.OAuthFlowError) as exc_info:
        await oauth_service.finish_connect(db, provider, code="x", state="forged", error=None)
    assert exc_info.value.code == "invalid_state"


async def test_finish_connect_access_denied(db, provider):
    with pytest.raises(oauth_service.OAuthFlowError) as exc_info:
        await oauth_service.finish_connect(
            db, provider, code=None, state=None, error="access_denied"
        )
    assert exc_info.value.code == "access_denied"


async def test_finish_connect_account_taken(db, user, provider):
    """The same Instagram account cannot be linked to two users."""
    from app.core import security
    from app.models.instagram import User

    url = await oauth_service.start_connect(db, user.id, provider)
    state = url.split("state=")[1]
    await oauth_service.finish_connect(db, provider, code="c", state=state, error=None)

    other = User(
        name="Other", email="other@example.com", password_hash=security.hash_password("password123")
    )
    db.add(other)
    await db.commit()
    await db.refresh(other)

    url2 = await oauth_service.start_connect(db, other.id, provider)
    state2 = url2.split("state=")[1]
    with pytest.raises(oauth_service.OAuthFlowError) as exc_info:
        await oauth_service.finish_connect(db, provider, code="c", state=state2, error=None)
    assert exc_info.value.code == "account_taken"
