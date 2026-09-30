"""Helpers to load (and refresh) a user's Instagram access token."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.models.instagram import InstagramAccount, InstagramToken, ensure_aware

log = logging.getLogger(__name__)

# Refresh proactively when fewer than 7 days remain on the long-lived token.
REFRESH_THRESHOLD = timedelta(days=7)


async def get_valid_access_token(
    session: AsyncSession, account: InstagramAccount, provider=None
) -> str:
    """Return a usable access token, refreshing it first if it is near expiry.

    Raises ValueError when no token is stored; raises TokenExpiredError when
    Meta rejects the refresh (caller should mark the account for reconnect).
    """
    result = await session.execute(
        select(InstagramToken).where(InstagramToken.instagram_account_id == account.id)
    )
    token_row = result.scalar_one_or_none()
    if token_row is None:
        raise ValueError("No Instagram token stored for this account")

    now = datetime.now(UTC)
    expires_at = ensure_aware(token_row.expires_at)
    needs_refresh = expires_at is not None and (expires_at - now) < REFRESH_THRESHOLD

    if not needs_refresh:
        return security.decrypt_token(token_row.access_token_encrypted)

    if provider is None:
        from app.services.providers.base import get_provider

        provider = get_provider()
    old_token = security.decrypt_token(token_row.access_token_encrypted)
    log.info("Refreshing Instagram token for account %s", account.instagram_user_id)
    refreshed = await provider.refresh_long_lived_token(old_token)
    token_row.access_token_encrypted = security.encrypt_token(refreshed.access_token)
    if refreshed.expires_in:
        token_row.expires_at = now + timedelta(seconds=refreshed.expires_in)
    await session.commit()
    return refreshed.access_token


async def store_token(
    session: AsyncSession,
    account: InstagramAccount,
    access_token: str,
    expires_in: int | None,
    scopes: list[str],
) -> InstagramToken:
    now = datetime.now(UTC)
    result = await session.execute(
        select(InstagramToken).where(InstagramToken.instagram_account_id == account.id)
    )
    row = result.scalar_one_or_none()
    expires_at = now + timedelta(seconds=expires_in) if expires_in else None
    if row is None:
        row = InstagramToken(
            instagram_account_id=account.id,
            access_token_encrypted=security.encrypt_token(access_token),
            expires_at=expires_at,
            scopes=",".join(scopes),
        )
        session.add(row)
    else:
        row.access_token_encrypted = security.encrypt_token(access_token)
        row.expires_at = expires_at
        row.scopes = ",".join(scopes)
    await session.commit()
    await session.refresh(row)
    return row


def token_status(token_row: InstagramToken | None) -> dict:
    """Safe, non-secret token status for API responses."""
    if token_row is None:
        return {"connected": False}
    now = datetime.now(UTC)
    expires_at = ensure_aware(token_row.expires_at)
    expired = expires_at is not None and expires_at <= now
    return {
        "connected": True,
        "expired": expired,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "scopes": (token_row.scopes or "").split(",") if token_row.scopes else [],
    }


def meta_configured() -> bool:
    return bool(settings.META_APP_ID and settings.META_APP_SECRET)
