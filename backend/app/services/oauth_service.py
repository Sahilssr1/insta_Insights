"""Instagram OAuth connect / callback orchestration.

Uses single-use, hashed, expiring ``state`` values for CSRF protection.
All Meta token exchanges happen server-side; the frontend never sees tokens.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.models.instagram import InstagramAccount, OAuthState, ensure_aware
from app.services import token_store
from app.services.providers.base import InstagramAPIError, InstagramDataProvider

log = logging.getLogger(__name__)

STATE_TTL = timedelta(minutes=15)


class OAuthFlowError(Exception):
    """User-facing OAuth failure with a safe message and machine code."""

    def __init__(self, message: str, code: str = "oauth_failed") -> None:
        super().__init__(message)
        self.code = code


async def start_connect(
    session: AsyncSession, user_id: int, provider: InstagramDataProvider
) -> str:
    """Create a one-shot state and return the Meta authorization URL."""
    if not token_store.meta_configured() and provider.name == "meta":
        raise OAuthFlowError(
            "Instagram connection is not configured on this server yet. "
            "The administrator must set META_APP_ID / META_APP_SECRET. "
            "See META_INSTAGRAM_SETUP.md.",
            code="not_configured",
        )
    state = security.generate_oauth_state()
    now = datetime.now(UTC)
    session.add(
        OAuthState(
            state_hash=security.hash_state(state),
            user_id=user_id,
            expires_at=now + STATE_TTL,
        )
    )
    # Retire older unused states for this user to keep the table small.
    await session.execute(
        delete(OAuthState).where(
            OAuthState.user_id == user_id,
            OAuthState.used.is_(True),
        )
    )
    await session.commit()
    return await provider.build_authorize_url(state)


async def _consume_state(session: AsyncSession, state: str, user_id: int | None) -> OAuthState:
    result = await session.execute(
        select(OAuthState).where(OAuthState.state_hash == security.hash_state(state))
    )
    row = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None:
        raise OAuthFlowError(
            "Invalid or unknown authorization request. Please try connecting again.",
            code="invalid_state",
        )
    if row.used:
        raise OAuthFlowError(
            "This authorization request was already used. Please try connecting again.",
            code="state_reused",
        )
    if (ensure_aware(row.expires_at) or now) <= now:
        raise OAuthFlowError(
            "The authorization request expired. Please try connecting again.", code="state_expired"
        )
    if user_id is not None and row.user_id != user_id:
        raise OAuthFlowError(
            "Authorization request does not match your session.", code="state_mismatch"
        )
    row.used = True
    await session.commit()
    return row


async def finish_connect(
    session: AsyncSession,
    provider: InstagramDataProvider,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
    user_id: int | None = None,
) -> InstagramAccount:
    """Handle the OAuth callback: validate state, exchange tokens, link account."""
    if error:
        if error == "access_denied":
            raise OAuthFlowError(
                "You cancelled the Instagram authorization. No account was connected.",
                code="access_denied",
            )
        raise OAuthFlowError(f"Instagram authorization failed ({error}).", code="oauth_error")
    if not code or not state:
        raise OAuthFlowError("Missing authorization code or state.", code="missing_params")

    state_row = await _consume_state(session, state, user_id)

    try:
        short = await provider.exchange_code(code)
        long_lived = await provider.exchange_long_lived_token(short.access_token)
        account_info = await provider.get_account(long_lived.access_token)
    except InstagramAPIError as exc:
        log.warning("Instagram OAuth exchange failed: %s", exc.message)
        raise OAuthFlowError(
            "Could not complete the Instagram connection. Please try again.",
            code="exchange_failed",
        ) from exc

    result = await session.execute(
        select(InstagramAccount).where(
            InstagramAccount.instagram_user_id == account_info.instagram_user_id
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        account = InstagramAccount(
            user_id=state_row.user_id,
            instagram_user_id=account_info.instagram_user_id,
            username=account_info.username,
        )
        session.add(account)
        await session.flush()
    else:
        if account.user_id != state_row.user_id:
            raise OAuthFlowError(
                "This Instagram account is already connected to a different user.",
                code="account_taken",
            )
    account.username = account_info.username
    account.account_type = account_info.account_type
    account.profile_picture_url = account_info.profile_picture_url
    account.followers_count = account_info.followers_count
    account.follows_count = account_info.follows_count
    account.media_count = account_info.media_count
    await session.commit()

    await token_store.store_token(
        session,
        account,
        long_lived.access_token,
        long_lived.expires_in,
        long_lived.granted_scopes,
    )
    await session.refresh(account)
    log.info("Instagram account @%s connected for user %d", account.username, state_row.user_id)
    return account
