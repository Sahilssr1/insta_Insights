"""Instagram connection, sync, insights, media, audience and comments API.

All routes require our own app authentication; users can only access their
own connected Instagram account. Instagram access tokens never leave the
backend — every Meta API call is made server-side.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.rate_limit import limit, sync_limiter
from app.db.session import get_session
from app.models.instagram import (
    InstagramAccount,
    InstagramDailyInsight,
    InstagramInsight,
    InstagramMedia,
    InstagramToken,
    User,
)
from app.schemas.instagram import (
    AudienceOut,
    CommentListOut,
    CommentOut,
    CommentReplyRequest,
    ConnectResponse,
    DisconnectResponse,
    InsightsMeta,
    InstagramAccountOut,
    MediaDetailOut,
    MediaInsightsOut,
    MediaListOut,
    MediaOut,
    SummaryOut,
    SyncResponse,
    SyncStatusOut,
    TimeSeriesOut,
    TimeSeriesPoint,
    UnavailableMetricNote,
)
from app.services import oauth_service, sync_service, token_store
from app.services.providers.base import (
    ACCOUNT_METRICS,
    MEDIA_METRICS,
    InstagramAPIError,
    get_provider,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instagram", tags=["instagram"])

# Metrics the official API does NOT provide (verified against Meta docs).
UNAVAILABLE_METRICS = [
    UnavailableMetricNote(
        metric="impressions",
        reason=(
            "Deprecated by Meta for media created after July 2, 2024 "
            "and removed from account insights."
        ),
    ),
    UnavailableMetricNote(
        metric="profile_views",
        reason=(
            "Deprecated by Meta (Graph API v21); not returned by the official insights endpoints."
        ),
    ),
    UnavailableMetricNote(
        metric="website_clicks",
        reason="Deprecated by Meta; use profile_links_taps where available.",
    ),
    UnavailableMetricNote(
        metric="email_contacts / phone_call_clicks / text_message_clicks",
        reason="Deprecated by Meta; not available through the official API.",
    ),
]


async def _get_account(session: AsyncSession, user: User) -> InstagramAccount:
    result = await session.execute(
        select(InstagramAccount).where(InstagramAccount.user_id == user.id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No Instagram account connected")
    return account


async def _get_media_or_404(
    session: AsyncSession, account: InstagramAccount, media_id: int
) -> InstagramMedia:
    result = await session.execute(
        select(InstagramMedia).where(
            InstagramMedia.id == media_id,
            InstagramMedia.instagram_account_id == account.id,
        )
    )
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
    return media


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


@router.get("/connect", response_model=ConnectResponse)
async def connect(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    provider = get_provider()
    try:
        url = await oauth_service.start_connect(session, user.id, provider)
    except oauth_service.OAuthFlowError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.args[0]) from exc
    return ConnectResponse(authorize_url=url)


@router.get("/callback")
async def callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Meta redirects the user here. We validate, exchange, then redirect to the app."""
    provider = get_provider()
    try:
        await oauth_service.finish_connect(session, provider, code=code, state=state, error=error)
    except oauth_service.OAuthFlowError as exc:
        log.info("OAuth callback failed: %s", exc.code)
        return RedirectResponse(
            f"{settings.FRONTEND_URL}/connect?error={exc.code}", status_code=302
        )
    return RedirectResponse(f"{settings.FRONTEND_URL}/connect?connected=1", status_code=302)


@router.get("/account", response_model=InstagramAccountOut)
async def get_account(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    account = await _get_account(session, user)
    result = await session.execute(
        select(InstagramToken).where(InstagramToken.instagram_account_id == account.id)
    )
    # Build explicitly: account.token is a lazy relationship that must not be
    # touched by pydantic's from_attributes extraction.
    return InstagramAccountOut(
        id=account.id,
        instagram_user_id=account.instagram_user_id,
        username=account.username,
        account_type=account.account_type,
        profile_picture_url=account.profile_picture_url,
        followers_count=account.followers_count,
        follows_count=account.follows_count,
        media_count=account.media_count,
        connected_at=account.connected_at,
        token=token_store.token_status(result.scalar_one_or_none()),
    )


@router.post("/disconnect", response_model=DisconnectResponse)
async def disconnect(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    account = await _get_account(session, user)
    await sync_service.disconnect_account(session, account)
    return DisconnectResponse(ok=True)


@router.get("/meta", response_model=InsightsMeta)
async def api_meta():
    return InsightsMeta(
        available=sorted(set(ACCOUNT_METRICS + MEDIA_METRICS)),
        unavailable=UNAVAILABLE_METRICS,
        provider=get_provider().name,
    )


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


@router.post(
    "/sync",
    response_model=SyncResponse,
    dependencies=[Depends(limit(sync_limiter, "sync"))],
)
async def sync_now(
    force: bool = Query(default=False),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    account = await _get_account(session, user)
    result = await sync_service.sync_account(session, account, get_provider(), force=force)
    return SyncResponse(**result)


@router.get("/sync/status", response_model=SyncStatusOut)
async def sync_status(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    account = await _get_account(session, user)
    last = await sync_service.get_last_sync(session, account.id)
    if last is None:
        return SyncStatusOut()
    return SyncStatusOut(
        last_synced_at=last.sync_completed_at.isoformat() if last.sync_completed_at else None,
        last_status=last.status,
        syncing=last.status == "running",
    )


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------


def _parse_days(days: int) -> int:
    if days not in (7, 30, 90):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "days must be 7, 30 or 90")
    return days


@router.get("/insights", response_model=SummaryOut)
@router.get("/insights/summary", response_model=SummaryOut)
async def insights_summary(
    days: int = Query(default=30),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    days = _parse_days(days)
    account = await _get_account(session, user)
    now = datetime.now(UTC)

    async def totals_for(start: datetime, end: datetime) -> dict[str, float]:
        cols = [
            func.coalesce(func.sum(getattr(InstagramDailyInsight, c)), 0).label(c)
            for c in (
                "reach",
                "views",
                "likes",
                "comments",
                "shares",
                "saves",
                "total_interactions",
                "accounts_engaged",
                "profile_links_taps",
            )
        ]
        result = await session.execute(
            select(*cols).where(
                InstagramDailyInsight.instagram_account_id == account.id,
                InstagramDailyInsight.metric_date >= start,
                InstagramDailyInsight.metric_date < end,
            )
        )
        row = result.one()
        return {c: float(row._mapping[c]) for c in row._mapping}

    end = now
    start = end - timedelta(days=days)
    prev_end = start
    prev_start = prev_end - timedelta(days=days)

    totals = await totals_for(start, end)
    prev = await totals_for(prev_start, prev_end)
    deltas: dict[str, float | None] = {
        k: ((totals[k] - prev[k]) / prev[k] * 100 if prev[k] else None) for k in totals
    }
    totals_out: dict[str, float | None] = dict(totals)
    return SummaryOut(
        range_days=days,
        totals=totals_out,
        deltas=deltas,
        followers=account.followers_count,
    )


@router.get("/insights/timeseries", response_model=TimeSeriesOut)
async def insights_timeseries(
    days: int = Query(default=30),
    metrics: str = Query(default="views,reach"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    days = _parse_days(days)
    account = await _get_account(session, user)
    wanted = [m.strip() for m in metrics.split(",") if m.strip() in ACCOUNT_METRICS]
    if not wanted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No valid metrics requested")
    now = datetime.now(UTC)
    start = now - timedelta(days=days)
    result = await session.execute(
        select(InstagramDailyInsight)
        .where(
            InstagramDailyInsight.instagram_account_id == account.id,
            InstagramDailyInsight.metric_date >= start,
        )
        .order_by(InstagramDailyInsight.metric_date.asc())
    )
    points = [
        TimeSeriesPoint(
            date=row.metric_date.date().isoformat(),
            values={m: getattr(row, m) for m in wanted},
        )
        for row in result.scalars()
    ]
    return TimeSeriesOut(metric_names=wanted, points=points)


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


async def _media_metrics(session: AsyncSession, media_db_id: int) -> dict[str, float | None]:
    result = await session.execute(
        select(InstagramInsight).where(InstagramInsight.media_id == media_db_id)
    )
    return {row.metric_name: row.metric_value for row in result.scalars()}


@router.get("/media", response_model=MediaListOut)
async def list_media(
    sort: str = Query(default="latest"),
    limit: int = Query(default=25, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    account = await _get_account(session, user)
    stmt = select(InstagramMedia).where(InstagramMedia.instagram_account_id == account.id)

    metric_sort = {
        "views": "views",
        "likes": "likes",
        "comments": "comments",
        "shares": "shares",
        "saves": "saved",
    }.get(sort)
    if metric_sort:
        # Sort by the stored lifetime metric value (NULLs last).
        metric_alias = (
            select(InstagramInsight.metric_value)
            .where(
                InstagramInsight.media_id == InstagramMedia.id,
                InstagramInsight.metric_name == metric_sort,
            )
            .scalar_subquery()
        )
        stmt = stmt.order_by(metric_alias.desc().nulls_last(), InstagramMedia.posted_at.desc())
    else:
        if sort != "latest":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid sort")
        stmt = stmt.order_by(InstagramMedia.posted_at.desc().nulls_last())

    result = await session.execute(stmt.limit(limit))
    items = []
    for media in result.scalars():
        out = MediaOut.model_validate(media)
        out.metrics = await _media_metrics(session, media.id)
        items.append(out)
    total_result = await session.execute(
        select(func.count())
        .select_from(InstagramMedia)
        .where(InstagramMedia.instagram_account_id == account.id)
    )
    return MediaListOut(items=items, total=total_result.scalar_one())


@router.get("/media/{media_id}", response_model=MediaDetailOut)
async def media_detail(
    media_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    account = await _get_account(session, user)
    media = await _get_media_or_404(session, account, media_id)
    out = MediaDetailOut.model_validate(media)
    out.metrics = await _media_metrics(session, media.id)
    return out


# ---------------------------------------------------------------------------
# Audience
# ---------------------------------------------------------------------------


@router.get("/audience", response_model=AudienceOut)
async def audience(
    breakdown: str = Query(default="age"),
    timeframe: str = Query(default="last_30_days"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if breakdown not in ("age", "gender", "city", "country"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid breakdown")
    if timeframe not in (
        "last_14_days",
        "last_30_days",
        "last_90_days",
        "this_month",
        "prev_month",
        "this_week",
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid timeframe")
    account = await _get_account(session, user)
    if (account.followers_count or 0) < 100 and get_provider().name == "meta":
        return AudienceOut(
            breakdown=breakdown,
            timeframe=timeframe,
            buckets=[],
            note=(
                "Instagram only provides audience demographics for accounts "
                "with at least 100 followers."
            ),
        )
    try:
        access_token = await token_store.get_valid_access_token(session, account)
        buckets = await get_provider().get_audience_demographics(access_token, breakdown, timeframe)
    except InstagramAPIError as exc:
        log.warning("Demographics fetch failed: %s", exc.message)
        return AudienceOut(
            breakdown=breakdown,
            timeframe=timeframe,
            buckets=[],
            note="Instagram currently does not provide this metric through the connected API.",
        )
    return AudienceOut(breakdown=breakdown, timeframe=timeframe, buckets=buckets)


async def _verify_comment_owner(
    session: AsyncSession, account: InstagramAccount, access_token: str, comment_id: str
) -> None:
    """Prove the comment belongs to the connected account's own media.

    Fetches the parent media's owner from Meta and compares it with the
    connected account's Instagram user id. Arbitrary comment ids belonging to
    other accounts are rejected with 403 before any write happens.
    """
    try:
        owner_id = await get_provider().get_comment_media_owner(access_token, comment_id)
    except InstagramAPIError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Could not verify that this comment belongs to your account.",
        ) from exc
    if owner_id != account.instagram_user_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This comment does not belong to your connected Instagram account.",
        )


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


@router.get("/media/{media_id}/insights", response_model=MediaInsightsOut)
async def media_insights(
    media_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Lifetime per-media metrics for one of the connected account's media objects."""
    account = await _get_account(session, user)
    media = await _get_media_or_404(session, account, media_id)
    return MediaInsightsOut(
        media_id=media.id,
        instagram_media_id=media.instagram_media_id,
        metrics=await _media_metrics(session, media.id),
    )


@router.get("/media/{media_id}/comments", response_model=CommentListOut)
async def list_comments(
    media_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    account = await _get_account(session, user)
    media = await _get_media_or_404(session, account, media_id)
    try:
        access_token = await token_store.get_valid_access_token(session, account)
        comments = await get_provider().list_comments(access_token, media.instagram_media_id)
    except InstagramAPIError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Could not load comments: {exc.message}"
        ) from exc
    return CommentListOut(
        media_id=media.id,
        items=[CommentOut(**c.__dict__) for c in comments],
    )


@router.post(
    "/comments/{comment_id}/replies",
    response_model=CommentOut,
    dependencies=[Depends(limit(sync_limiter, "comments"))],
)
async def reply_comment(
    comment_id: str,
    body: CommentReplyRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not body.message.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message cannot be empty")
    account = await _get_account(session, user)
    try:
        access_token = await token_store.get_valid_access_token(session, account)
        await _verify_comment_owner(session, account, access_token, comment_id)
        new_id = await get_provider().reply_to_comment(
            access_token, comment_id, body.message.strip()
        )
    except InstagramAPIError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Could not post reply: {exc.message}"
        ) from exc
    return CommentOut(comment_id=new_id, text=body.message.strip(), username=account.username)


@router.post("/comments/{comment_id}/hide", dependencies=[Depends(limit(sync_limiter, "comments"))])
async def hide_comment(
    comment_id: str,
    hide: bool = Query(default=True),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    account = await _get_account(session, user)
    try:
        access_token = await token_store.get_valid_access_token(session, account)
        await _verify_comment_owner(session, account, access_token, comment_id)
        await get_provider().hide_comment(access_token, comment_id, hide)
    except InstagramAPIError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Could not update comment: {exc.message}"
        ) from exc
    return {"ok": True, "hidden": hide}


@router.delete("/comments/{comment_id}", dependencies=[Depends(limit(sync_limiter, "comments"))])
async def delete_comment(
    comment_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    account = await _get_account(session, user)
    try:
        access_token = await token_store.get_valid_access_token(session, account)
        await _verify_comment_owner(session, account, access_token, comment_id)
        await get_provider().delete_comment(access_token, comment_id)
    except InstagramAPIError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Could not delete comment: {exc.message}"
        ) from exc
    return {"ok": True}
