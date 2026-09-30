"""Pydantic schemas for the Instagram analytics API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


class ConnectResponse(BaseModel):
    authorize_url: str
    note: str = (
        "You will be redirected to Instagram to authorize this app. "
        "We never ask for or store your Instagram password."
    )


class InstagramAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instagram_user_id: str
    username: str
    account_type: str | None = None
    profile_picture_url: str | None = None
    followers_count: int | None = None
    follows_count: int | None = None
    media_count: int | None = None
    connected_at: datetime
    token: dict = {}


class DisconnectResponse(BaseModel):
    ok: bool = True


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


class SyncResponse(BaseModel):
    status: str
    message: str | None = None
    records_synced: int | None = None
    synced_at: str | None = None
    last_synced_at: str | None = None


class SyncStatusOut(BaseModel):
    last_synced_at: str | None = None
    last_status: str | None = None
    syncing: bool = False


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------


class SummaryOut(BaseModel):
    range_days: int
    totals: dict[str, float | None]
    deltas: dict[str, float | None]  # vs previous equal-length period
    followers: int | None = None


class TimeSeriesPoint(BaseModel):
    date: str  # ISO date
    values: dict[str, float | None]


class TimeSeriesOut(BaseModel):
    metric_names: list[str]
    points: list[TimeSeriesPoint]


class UnavailableMetricNote(BaseModel):
    metric: str
    reason: str


class InsightsMeta(BaseModel):
    """Describes which metrics the official API provides, honestly."""

    available: list[str]
    unavailable: list[UnavailableMetricNote]
    provider: str
    data_delay_note: str = (
        "Instagram insights can be delayed up to 48 hours and are not "
        "available for some very recent media."
    )


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


class MediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    instagram_media_id: str
    media_type: str | None = None
    media_product_type: str | None = None
    caption: str | None = None
    permalink: str | None = None
    thumbnail_url: str | None = None
    posted_at: datetime | None = None
    metrics: dict[str, float | None] = {}


class MediaListOut(BaseModel):
    items: list[MediaOut]
    total: int


class MediaDetailOut(MediaOut):
    media_url: str | None = None


class MediaInsightsOut(BaseModel):
    """Lifetime per-media metrics, keyed by metric name."""

    media_id: int
    instagram_media_id: str
    metrics: dict[str, float | None] = {}


# ---------------------------------------------------------------------------
# Audience
# ---------------------------------------------------------------------------


class AudienceOut(BaseModel):
    breakdown: str
    timeframe: str
    buckets: list[dict]
    note: str | None = None


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


class CommentOut(BaseModel):
    comment_id: str
    text: str | None = None
    username: str | None = None
    timestamp: datetime | None = None
    like_count: int | None = None
    hidden: bool = False


class CommentReplyRequest(BaseModel):
    message: str


class CommentListOut(BaseModel):
    media_id: int
    items: list[CommentOut]


class ErrorOut(BaseModel):
    detail: str
    code: str = "error"
