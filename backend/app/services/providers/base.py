"""Provider abstraction for Instagram data.

Production MUST use :class:`MetaInstagramProvider`, which talks only to
Meta's official APIs. :class:`MockInstagramProvider` exists purely so the UI
can be developed without Meta credentials, and the application refuses to
boot with it outside development (see ``get_provider()``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InstagramAPIError(Exception):
    """Raised for any failure talking to the Instagram/Meta API."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        http_status: int | None = None,
        error_type: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status
        self.error_type = error_type
        self.retryable = retryable

    @property
    def is_auth_error(self) -> bool:
        """Invalid/expired token or revoked permissions."""
        return (
            self.http_status in (400, 401, 403) and self.code in (190, 102, 10, None)
        ) or self.http_status == 401

    @property
    def is_rate_limited(self) -> bool:
        return self.http_status == 429 or self.code in (4, 17, 32)

    @property
    def is_permission_error(self) -> bool:
        return self.code == 10 and "permission" in self.message.lower()


class TokenExpiredError(InstagramAPIError):
    pass


# ---------------------------------------------------------------------------
# Normalized data containers (provider-agnostic)
# ---------------------------------------------------------------------------


@dataclass
class TokenResult:
    access_token: str
    expires_in: int | None  # seconds
    user_id: str | None = None
    granted_scopes: list[str] = field(default_factory=list)


@dataclass
class AccountInfo:
    instagram_user_id: str
    username: str
    account_type: str | None = None
    name: str | None = None
    profile_picture_url: str | None = None
    followers_count: int | None = None
    follows_count: int | None = None
    media_count: int | None = None


@dataclass
class MediaInfo:
    instagram_media_id: str
    media_type: str | None = None
    media_product_type: str | None = None
    caption: str | None = None
    permalink: str | None = None
    thumbnail_url: str | None = None
    media_url: str | None = None
    posted_at: datetime | None = None
    like_count: int | None = None
    comments_count: int | None = None


@dataclass
class DailyMetricPoint:
    """One day of one account-level metric."""

    metric_name: str
    date: datetime
    value: float | None


@dataclass
class CommentInfo:
    comment_id: str
    text: str | None
    username: str | None
    timestamp: datetime | None
    like_count: int | None = None
    hidden: bool = False
    replies: list[CommentInfo] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------


class InstagramDataProvider(ABC):
    """Abstract Instagram data source. Only Meta's official API in production."""

    name: str = "base"

    # -- OAuth ------------------------------------------------------------
    @abstractmethod
    async def build_authorize_url(self, state: str) -> str:
        """Return the Meta authorization URL the user must visit."""

    @abstractmethod
    async def exchange_code(self, code: str) -> TokenResult:
        """Exchange an authorization code for a short-lived token."""

    @abstractmethod
    async def exchange_long_lived_token(self, short_lived_token: str) -> TokenResult:
        """Exchange a short-lived token for a long-lived (60-day) token."""

    @abstractmethod
    async def refresh_long_lived_token(self, long_lived_token: str) -> TokenResult:
        """Refresh a long-lived token, extending it another 60 days."""

    # -- Reads -------------------------------------------------------------
    @abstractmethod
    async def get_account(self, access_token: str) -> AccountInfo: ...

    @abstractmethod
    async def list_media(
        self, access_token: str, limit: int = 25, after: str | None = None
    ) -> tuple[list[MediaInfo], str | None]:
        """Return (media, next_cursor)."""

    @abstractmethod
    async def get_account_insights(
        self,
        access_token: str,
        metrics: list[str],
        since: datetime,
        until: datetime,
    ) -> list[DailyMetricPoint]:
        """Daily account-level insights for [since, until]."""

    @abstractmethod
    async def get_media_insights(
        self,
        access_token: str,
        media_id: str,
        metrics: list[str],
        media_type: str | None = None,
    ) -> dict[str, float]:
        """Lifetime media-level insights keyed by metric name.

        ``media_type`` (e.g. "REEL", "IMAGE", "VIDEO", "CAROUSEL_ALBUM", "STORY")
        lets the provider choose metrics the official API actually supports for
        that media kind.
        """

    @abstractmethod
    async def get_audience_demographics(
        self, access_token: str, breakdown: str, timeframe: str
    ) -> list[dict]:
        """Audience demographics buckets, e.g. [{'value': '25-34', 'count': 120}]."""

    # -- Comments -----------------------------------------------------------
    @abstractmethod
    async def list_comments(
        self, access_token: str, media_id: str, limit: int = 25
    ) -> list[CommentInfo]: ...

    @abstractmethod
    async def reply_to_comment(self, access_token: str, comment_id: str, message: str) -> str:
        """Return the new reply's comment id."""

    @abstractmethod
    async def hide_comment(self, access_token: str, comment_id: str, hide: bool) -> None: ...

    @abstractmethod
    async def delete_comment(self, access_token: str, comment_id: str) -> None: ...

    @abstractmethod
    async def get_comment_media_owner(self, access_token: str, comment_id: str) -> str:
        """Return the Instagram user id that owns the media a comment is on.

        Used to prove a comment id belongs to the connected account's own
        media before reply/hide/delete are allowed.
        """


# ---------------------------------------------------------------------------
# Metric catalogues (verified against Meta's official documentation)
# ---------------------------------------------------------------------------

# Account-level metrics valid on GET /me/insights (period=day).
ACCOUNT_METRICS = [
    "views",
    "reach",
    "accounts_engaged",
    "total_interactions",
    "likes",
    "comments",
    "shares",
    "saves",
    "replies",
    "reposts",
    "follows_and_unfollows",
    "profile_links_taps",
    "follower_count",
]

# Media-level metrics valid on GET /{media-id}/insights (period=lifetime).
MEDIA_METRICS = [
    "views",
    "reach",
    "likes",
    "comments",
    "saved",
    "shares",
    "total_interactions",
    "reposts",
    "follows",
    "profile_visits",
    "profile_activity",
    "ig_reels_avg_watch_time",
    "ig_reels_video_view_total_time",
]

# Metrics Meta supports across media kinds; used as the safe fallback when a
# media-type-specific combination is rejected.
CORE_MEDIA_METRICS = [
    "views",
    "reach",
    "likes",
    "comments",
    "saved",
    "shares",
    "total_interactions",
]

# Metrics beyond the core set that the official docs associate with each media
# kind. Kept conservative: anything Meta rejects is retried with the core set.
_MEDIA_TYPE_EXTRA_METRICS: dict[str, list[str]] = {
    "IMAGE": ["reposts", "follows", "profile_visits", "profile_activity"],
    "VIDEO": ["reposts", "follows", "profile_visits", "profile_activity"],
    "CAROUSEL_ALBUM": ["reposts", "follows", "profile_visits", "profile_activity"],
    "REEL": [
        "reposts",
        "ig_reels_avg_watch_time",
        "ig_reels_video_view_total_time",
    ],
    # Stories have limited insights; request only the core set.
    "STORY": [],
}


def _metrics_for_media_type(metrics: list[str], media_type: str | None) -> list[str]:
    """Pick the metric subset valid for a media kind, preserving order."""
    allowed = [m for m in metrics if m in MEDIA_METRICS]
    if not allowed:
        return []
    extras = set(_MEDIA_TYPE_EXTRA_METRICS.get((media_type or "").upper(), []))
    chosen = [m for m in allowed if m in CORE_MEDIA_METRICS or m in extras or media_type is None]
    return chosen or [m for m in allowed if m in CORE_MEDIA_METRICS]


def get_provider() -> InstagramDataProvider:
    """Resolve the configured provider, enforcing the mock-data safety gate."""
    from app.core.config import settings
    from app.services.providers.meta_provider import MetaInstagramProvider
    from app.services.providers.mock_provider import MockInstagramProvider

    choice = settings.INSTAGRAM_PROVIDER.strip().lower()
    if choice == "mock":
        if settings.is_production:
            raise RuntimeError(
                "INSTAGRAM_PROVIDER=mock is not allowed in production. "
                "Set INSTAGRAM_PROVIDER=meta and configure Meta credentials."
            )
        return MockInstagramProvider()
    return MetaInstagramProvider()
