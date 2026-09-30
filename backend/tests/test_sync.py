"""Sync service with the mock provider: idempotent, throttled, recorded."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models.instagram import (
    InstagramAccount,
    InstagramDailyInsight,
    InstagramInsight,
    InstagramMedia,
    InstagramToken,
)
from app.services import sync_service, token_store
from app.services.providers.mock_provider import MockInstagramProvider


async def _linked_account(db, user):
    account = InstagramAccount(
        user_id=user.id, instagram_user_id="mock_ig_1", username="mock.creator"
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    await token_store.store_token(
        db, account, "MOCK_LONG_LIVED", 5184000, ["instagram_business_basic"]
    )
    return account


async def test_full_sync_populates_tables(db, user):
    account = await _linked_account(db, user)
    provider = MockInstagramProvider()
    result = await sync_service.sync_account(db, account, provider)
    assert result["status"] == "success"
    assert result["records_synced"] and result["records_synced"] > 0

    media_count = (await db.execute(select(func.count()).select_from(InstagramMedia))).scalar_one()
    assert media_count > 0
    daily_count = (
        await db.execute(select(func.count()).select_from(InstagramDailyInsight))
    ).scalar_one()
    assert daily_count > 0
    insight_count = (
        await db.execute(select(func.count()).select_from(InstagramInsight))
    ).scalar_one()
    assert insight_count > 0

    # Followers snapshot recorded.
    result = await db.execute(select(InstagramAccount).where(InstagramAccount.id == account.id))
    assert result.scalar_one().followers_count is not None


async def test_sync_is_idempotent(db, user):
    account = await _linked_account(db, user)
    provider = MockInstagramProvider()
    await sync_service.sync_account(db, account, provider)
    first = (await db.execute(select(func.count()).select_from(InstagramMedia))).scalar_one()
    await sync_service.sync_account(db, account, provider, force=True)
    second = (await db.execute(select(func.count()).select_from(InstagramMedia))).scalar_one()
    assert first == second > 0


async def test_sync_throttling(db, user):
    account = await _linked_account(db, user)
    provider = MockInstagramProvider()
    await sync_service.sync_account(db, account, provider)
    result = await sync_service.sync_account(db, account, provider)
    assert result["status"] == "throttled"


async def test_disconnect_removes_everything(db, user):
    account = await _linked_account(db, user)
    provider = MockInstagramProvider()
    await sync_service.sync_account(db, account, provider)
    await sync_service.disconnect_account(db, account)
    assert (await db.execute(select(func.count()).select_from(InstagramAccount))).scalar_one() == 0
    assert (await db.execute(select(func.count()).select_from(InstagramToken))).scalar_one() == 0
    assert (await db.execute(select(func.count()).select_from(InstagramMedia))).scalar_one() == 0
