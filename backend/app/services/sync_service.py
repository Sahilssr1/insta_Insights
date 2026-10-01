"""Background-friendly Instagram synchronization service.

Pulls account profile, media, account-level daily insights and per-media
insights from the provider, normalizes them, and upserts them into the
database. Everything is idempotent: re-running a sync never duplicates rows.

Syncs are throttled (SYNC_MIN_INTERVAL_SECONDS) to avoid excessive API calls,
and Meta rate-limit errors are caught and recorded instead of crashing.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.instagram import (
    InstagramAccount,
    InstagramDailyInsight,
    InstagramInsight,
    InstagramMedia,
    InstagramSyncLog,
    ensure_aware,
)
from app.services import token_store
from app.services.providers.base import (
    ACCOUNT_METRICS,
    MEDIA_METRICS,
    InstagramAPIError,
    InstagramDataProvider,
    TokenExpiredError,
)

log = logging.getLogger(__name__)

DAILY_COLUMN_MAP = {
    "reach": "reach",
    "views": "views",
    "likes": "likes",
    "comments": "comments",
    "shares": "shares",
    "saves": "saves",
    "replies": "replies",
    "reposts": "reposts",
    "total_interactions": "total_interactions",
    "accounts_engaged": "accounts_engaged",
    "follows_and_unfollows": "follows_and_unfollows",
    "profile_links_taps": "profile_links_taps",
    "follower_count": "follower_count_delta",
}


class SyncInProgressError(Exception):
    pass


async def get_last_sync(session: AsyncSession, account_id: int) -> InstagramSyncLog | None:
    result = await session.execute(
        select(InstagramSyncLog)
        .where(InstagramSyncLog.instagram_account_id == account_id)
        .order_by(InstagramSyncLog.sync_started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def sync_account(
    session: AsyncSession,
    account: InstagramAccount,
    provider: InstagramDataProvider,
    *,
    force: bool = False,
) -> dict:
    """Run a full sync for one connected Instagram account."""
    last = await get_last_sync(session, account.id)
    now = datetime.now(UTC)
    last_completed = ensure_aware(last.sync_completed_at) if last is not None else None
    if (
        not force
        and last is not None
        and last_completed is not None
        and (now - last_completed).total_seconds() < settings.SYNC_MIN_INTERVAL_SECONDS
    ):
        return {
            "status": "throttled",
            "message": f"Last sync was {(now - last_completed).total_seconds():.0f}s ago. "
            "Please wait a few minutes between syncs.",
            "last_synced_at": last_completed.isoformat(),
        }

    sync_log = InstagramSyncLog(instagram_account_id=account.id, status="running")
    session.add(sync_log)
    await session.commit()

    records = 0
    try:
        access_token = await token_store.get_valid_access_token(session, account, provider)

        # 1. Account profile ------------------------------------------------
        info = await provider.get_account(access_token)
        account.username = info.username
        account.account_type = info.account_type
        account.profile_picture_url = info.profile_picture_url
        account.followers_count = info.followers_count
        account.follows_count = info.follows_count
        account.media_count = info.media_count
        records += 1

        # 2. Media -----------------------------------------------------------
        media_rows = await _sync_media(session, account, provider, access_token)
        records += len(media_rows)

        # 3. Account-level daily insights ------------------------------------
        daily_records = await _sync_daily_insights(
            session, account, provider, access_token, info.followers_count
        )
        records += daily_records

        # 4. Per-media insights -----------------------------------------------
        for media_row in media_rows:
            try:
                records += await _sync_media_insights(
                    session, account, media_row, provider, access_token
                )
            except InstagramAPIError as exc:
                # One bad media object must not fail the whole sync.
                log.warning(
                    "Media insights failed for %s: %s",
                    media_row.instagram_media_id,
                    exc.message,
                )
                if exc.is_rate_limited:
                    raise

        # 5. Roll up media metrics into daily time series --------------------
        await _rollup_media_to_daily(session, account)

        sync_completed_at = datetime.now(UTC)
        sync_log.status = "success"
        sync_log.records_synced = records
        sync_log.sync_completed_at = sync_completed_at
        await session.commit()
        return {
            "status": "success",
            "records_synced": records,
            "synced_at": sync_completed_at.isoformat(),
        }
    except TokenExpiredError as exc:
        return await _fail_sync(
            session,
            sync_log,
            "token_expired",
            "Your Instagram connection expired. Please reconnect your account.",
            exc,
        )
    except InstagramAPIError as exc:
        message = (
            "Instagram is rate-limiting requests right now. Please try again in a few minutes."
            if exc.is_rate_limited
            else f"Instagram API error: {exc.message}"
        )
        return await _fail_sync(session, sync_log, "api_error", message, exc)
    except Exception as exc:  # pragma: no cover - defensive
        log.exception("Unexpected sync failure")
        return await _fail_sync(session, sync_log, "failed", "Sync failed unexpectedly.", exc)


async def _fail_sync(
    session: AsyncSession,
    sync_log: InstagramSyncLog,
    status: str,
    message: str,
    exc: BaseException,
) -> dict:
    sync_log.status = status
    sync_log.error_message = f"{message} (detail: {type(exc).__name__})"
    sync_log.sync_completed_at = datetime.now(UTC)
    await session.commit()
    return {"status": status, "message": message}


# ---------------------------------------------------------------------------
# Sync steps
# ---------------------------------------------------------------------------


async def _sync_media(
    session: AsyncSession,
    account: InstagramAccount,
    provider: InstagramDataProvider,
    access_token: str,
) -> list[InstagramMedia]:
    """Fetch media pages and upsert; returns all synced media rows."""
    fetched: list = []
    after: str | None = None
    remaining = settings.SYNC_MEDIA_LIMIT
    while remaining > 0:
        batch_size = min(remaining, 50)
        items, after = await provider.list_media(access_token, limit=batch_size, after=after)
        fetched.extend(items)
        remaining -= len(items)
        if not after or not items:
            break

    rows: list[InstagramMedia] = []
    for item in fetched:
        result = await session.execute(
            select(InstagramMedia).where(
                InstagramMedia.instagram_account_id == account.id,
                InstagramMedia.instagram_media_id == item.instagram_media_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = InstagramMedia(
                instagram_account_id=account.id,
                instagram_media_id=item.instagram_media_id,
            )
            session.add(row)
        row.media_type = item.media_type
        row.media_product_type = item.media_product_type
        row.caption = item.caption
        row.permalink = item.permalink
        row.thumbnail_url = item.thumbnail_url
        row.media_url = item.media_url
        row.posted_at = item.posted_at
        rows.append(row)
    await session.commit()
    return rows


async def _sync_daily_insights(
    session: AsyncSession,
    account: InstagramAccount,
    provider: InstagramDataProvider,
    access_token: str,
    followers_snapshot: int | None,
) -> int:
    now = datetime.now(UTC)
    since = now - timedelta(days=settings.SYNC_ACCOUNT_INSIGHT_DAYS)
    points = await provider.get_account_insights(access_token, ACCOUNT_METRICS, since, now)

    # Group points by day.
    by_day: dict[datetime, dict[str, float | None]] = {}
    for point in points:
        point_date = ensure_aware(point.date)
        if point_date is None:
            continue
        day = point_date.replace(hour=0, minute=0, second=0, microsecond=0)
        column = DAILY_COLUMN_MAP.get(point.metric_name)
        if column is None:
            continue
        by_day.setdefault(day, {})[column] = point.value

    count = 0
    for day, values in sorted(by_day.items()):
        result = await session.execute(
            select(InstagramDailyInsight).where(
                InstagramDailyInsight.instagram_account_id == account.id,
                InstagramDailyInsight.metric_date == day,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = InstagramDailyInsight(instagram_account_id=account.id, metric_date=day)
            session.add(row)
        for column, value in values.items():
            setattr(row, column, value)
        if followers_snapshot is not None and day.date() == now.date():
            row.followers_snapshot = followers_snapshot
        count += 1
    await session.commit()
    return count


async def _rollup_media_to_daily(session: AsyncSession, account: InstagramAccount) -> None:
    """Roll up per-media insights onto daily insights by media post date."""
    media_list = (
        await session.execute(
            select(InstagramMedia).where(InstagramMedia.instagram_account_id == account.id)
        )
    ).scalars().all()

    by_day: dict[datetime, dict[str, float]] = {}
    for media in media_list:
        if not media.posted_at:
            continue
        posted_at = ensure_aware(media.posted_at)
        if posted_at is None:
            continue
        day = posted_at.replace(hour=0, minute=0, second=0, microsecond=0)
        insights = (
            await session.execute(
                select(InstagramInsight).where(InstagramInsight.media_id == media.id)
            )
        ).scalars().all()
        for ins in insights:
            col = "saves" if ins.metric_name == "saved" else DAILY_COLUMN_MAP.get(ins.metric_name)
            if not col:
                continue
            day_dict = by_day.setdefault(day, {})
            day_dict[col] = (day_dict.get(col) or 0.0) + float(ins.metric_value)

    for day, vals in by_day.items():
        res = await session.execute(
            select(InstagramDailyInsight).where(
                InstagramDailyInsight.instagram_account_id == account.id,
                InstagramDailyInsight.metric_date == day,
            )
        )
        row = res.scalar_one_or_none()
        if row is None:
            row = InstagramDailyInsight(instagram_account_id=account.id, metric_date=day)
            session.add(row)
        for col, val in vals.items():
            if col == "reach":
                row.reach = max(row.reach or 0.0, val)
            else:
                setattr(row, col, val)
    await session.commit()


async def _sync_media_insights(
    session: AsyncSession,
    account: InstagramAccount,
    media_row: InstagramMedia,
    provider: InstagramDataProvider,
    access_token: str,
) -> int:
    metrics = await provider.get_media_insights(
        access_token,
        media_row.instagram_media_id,
        MEDIA_METRICS,
        media_type=media_row.media_type,
    )
    now = datetime.now(UTC)
    count = 0
    for name, value in metrics.items():
        result = await session.execute(
            select(InstagramInsight).where(
                InstagramInsight.media_id == media_row.id,
                InstagramInsight.metric_name == name,
                InstagramInsight.period == "lifetime",
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = InstagramInsight(
                instagram_account_id=account.id,
                media_id=media_row.id,
                metric_name=name,
                period="lifetime",
            )
            session.add(row)
        row.metric_value = value
        row.metric_date = now
        count += 1
    await session.commit()
    return count


async def disconnect_account(session: AsyncSession, account: InstagramAccount) -> None:
    """Remove the connection and all synced data (tokens are destroyed)."""
    await session.delete(account)
    await session.commit()
