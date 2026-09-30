"""Development-only mock Instagram provider.

Produces deterministic, clearly fake fixture data so the UI can be built
without Meta credentials. It is IMPOSSIBLE to use in production:
:func:`get_provider` raises if INSTAGRAM_PROVIDER=mock while
ENVIRONMENT=production.

Never import this module from production code paths directly.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.services.providers.base import (
    AccountInfo,
    CommentInfo,
    DailyMetricPoint,
    InstagramDataProvider,
    MediaInfo,
    TokenResult,
)


class MockInstagramProvider(InstagramDataProvider):
    name = "mock"

    def __init__(self) -> None:
        self._now = datetime.now(UTC)

    async def build_authorize_url(self, state: str) -> str:
        # Development-only: point the browser at the real local callback with a
        # mock code so the full connect flow works end-to-end without Meta.
        # The code is unique per attempt so that each dev user connects their
        # own distinct mock Instagram account (mirrors production, where each
        # real Instagram account maps to one app user).
        code = f"mock_dev_{uuid.uuid4().hex[:12]}"
        base = settings.META_REDIRECT_URI or "http://localhost:8000/api/instagram/callback"
        return f"{base}?code={code}&state={state}"

    @staticmethod
    def _suffix(code_or_token: str) -> str:
        # "mock_dev_<suffix>" / "mock_at_<suffix>" -> "<suffix>"; "1" for legacy values.
        parts = code_or_token.split("_", 2)
        return parts[2] if len(parts) == 3 else "1"

    async def exchange_code(self, code: str) -> TokenResult:
        suffix = self._suffix(code)
        return TokenResult(
            access_token=f"mock_at_{suffix}", expires_in=3600, user_id=f"mock_ig_{suffix}"
        )

    async def exchange_long_lived_token(self, short_lived_token: str) -> TokenResult:
        suffix = self._suffix(short_lived_token)
        return TokenResult(
            access_token=f"mock_at_{suffix}", expires_in=5184000, user_id=f"mock_ig_{suffix}"
        )

    async def refresh_long_lived_token(self, long_lived_token: str) -> TokenResult:
        suffix = self._suffix(long_lived_token)
        return TokenResult(access_token=f"mock_at_{suffix}", expires_in=5184000)

    async def get_account(self, access_token: str) -> AccountInfo:
        suffix = self._suffix(access_token)
        return AccountInfo(
            instagram_user_id=f"mock_ig_{suffix}",
            username=f"mock.creator.{suffix[:6]}",
            account_type="CREATOR",
            name="Mock Creator",
            profile_picture_url=None,
            followers_count=1284,
            follows_count=210,
            media_count=42,
        )

    async def list_media(
        self, access_token: str, limit: int = 25, after: str | None = None
    ) -> tuple[list[MediaInfo], str | None]:
        items = []
        for i in range(min(limit, 10)):
            items.append(
                MediaInfo(
                    instagram_media_id=f"mock_media_{i}",
                    media_type="VIDEO" if i % 3 == 0 else "IMAGE",
                    media_product_type="REELS" if i % 3 == 0 else "FEED",
                    caption=f"Mock post #{i} — development fixture data",
                    permalink=f"https://www.instagram.com/p/mock{i}/",
                    thumbnail_url=None,
                    media_url=None,
                    posted_at=self._now - timedelta(days=i * 2),
                    like_count=100 + i * 7,
                    comments_count=5 + i,
                )
            )
        return items, None

    async def get_account_insights(
        self, access_token: str, metrics: list[str], since: datetime, until: datetime
    ) -> list[DailyMetricPoint]:
        points: list[DailyMetricPoint] = []
        days = max(0, (until - since).days)
        for day in range(days + 1):
            date = since + timedelta(days=day)
            wave = 0.6 + 0.4 * math.sin(day / 3.0)
            base = {
                "views": 900 * wave,
                "reach": 700 * wave,
                "likes": 45 * wave,
                "comments": 4 * wave,
                "shares": 6 * wave,
                "saves": 8 * wave,
                "total_interactions": 60 * wave,
                "accounts_engaged": 120 * wave,
            }
            for metric in metrics:
                points.append(
                    DailyMetricPoint(
                        metric_name=metric, date=date, value=round(base.get(metric, 10 * wave), 1)
                    )
                )
        return points

    async def get_media_insights(
        self,
        access_token: str,
        media_id: str,
        metrics: list[str],
        media_type: str | None = None,
    ) -> dict[str, float]:
        seed = sum(ord(c) for c in media_id)
        base = {
            "views": 800 + seed % 500,
            "reach": 600 + seed % 400,
            "likes": 40 + seed % 30,
            "comments": 3 + seed % 8,
            "saved": 5 + seed % 10,
            "shares": 4 + seed % 9,
            "total_interactions": 55 + seed % 40,
            "reposts": seed % 5,
            "profile_visits": 12 + seed % 20,
        }
        return {m: float(base.get(m, 0)) for m in metrics}

    async def get_audience_demographics(
        self, access_token: str, breakdown: str, timeframe: str
    ) -> list[dict]:
        return [
            {"dimensions": {"age": "25-34"}, "value": 420},
            {"dimensions": {"age": "18-24"}, "value": 310},
            {"dimensions": {"age": "35-44"}, "value": 180},
        ]

    async def list_comments(
        self, access_token: str, media_id: str, limit: int = 25
    ) -> list[CommentInfo]:
        return [
            CommentInfo(
                comment_id="mock_c1",
                text="Mock comment (development fixture)",
                username="mock.fan",
                timestamp=self._now - timedelta(hours=3),
                like_count=2,
            )
        ]

    async def reply_to_comment(self, access_token: str, comment_id: str, message: str) -> str:
        return "mock_reply_1"

    async def hide_comment(self, access_token: str, comment_id: str, hide: bool) -> None:
        return None

    async def delete_comment(self, access_token: str, comment_id: str) -> None:
        return None

    async def get_comment_media_owner(self, access_token: str, comment_id: str) -> str:
        """Owner of the media the comment belongs to (mock account)."""
        return f"mock_ig_{self._suffix(access_token)}"
