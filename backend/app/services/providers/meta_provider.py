"""Real Instagram data provider using Meta's official APIs.

Flow: "Instagram API with Instagram Login" (Business Login for Instagram),
host ``graph.instagram.com``, Graph API version configurable
(default ``v26.0``).

Endpoints (verified against Meta's official documentation):
- Authorize:   GET  https://www.instagram.com/oauth/authorize
- Code -> short-lived token: POST https://api.instagram.com/oauth/access_token
- Short -> long-lived (60d):  GET  https://graph.instagram.com/access_token
- Refresh long-lived:         GET  https://graph.instagram.com/refresh_access_token
- Profile:     GET  /{v}/me
- Media:       GET  /{v}/me/media
- Account insights: GET /{v}/me/insights
- Media insights:   GET /{v}/{media-id}/insights
- Comments:    GET  /{v}/{media-id}/comments

Note: the token-exchange/refresh endpoints are intentionally UNVERSIONED
(https://graph.instagram.com/access_token) per Meta's token documentation;
all other Graph calls carry the version prefix.

Scopes: instagram_business_basic, instagram_business_manage_insights,
instagram_business_manage_comments.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.services.providers.base import (
    ACCOUNT_METRICS,
    CORE_MEDIA_METRICS,
    AccountInfo,
    CommentInfo,
    DailyMetricPoint,
    InstagramAPIError,
    InstagramDataProvider,
    MediaInfo,
    TokenExpiredError,
    TokenResult,
    _metrics_for_media_type,
)

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
TOKEN_EXCHANGE_URL = "https://api.instagram.com/oauth/access_token"
GRAPH_HOST = "https://graph.instagram.com"

# Scopes for "Instagram API with Instagram Login" (Business Login for Instagram).
SCOPES = [
    "instagram_business_basic",
    "instagram_business_manage_insights",
    "instagram_business_manage_comments",
]


def _parse_meta_error(status: int, payload: dict | None) -> InstagramAPIError:
    """Convert Meta's error envelope into a typed exception (no secrets logged)."""
    err = (payload or {}).get("error") or {}
    message = str(err.get("message") or f"Meta API request failed (HTTP {status})")
    code = err.get("code")
    error_type = err.get("type")
    retryable = status in (429, 500, 502, 503, 504) or code in (4, 17, 32, 1)
    if code == 190 or (status == 400 and "expired" in message.lower()):
        return TokenExpiredError(message, code=code, http_status=status, error_type=error_type)
    return InstagramAPIError(
        message, code=code, http_status=status, error_type=error_type, retryable=retryable
    )


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


class MetaInstagramProvider(InstagramDataProvider):
    """Production provider backed by Meta's official Instagram APIs."""

    name = "meta"

    def __init__(self) -> None:
        self.api_version = settings.META_API_VERSION
        self._client: httpx.AsyncClient | None = None

    # -- HTTP plumbing -----------------------------------------------------
    async def _client_get(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _graph(self, method: str, path: str, access_token: str | None, **kwargs) -> dict:
        return await self._call(
            method, f"{GRAPH_HOST}/{self.api_version}{path}", access_token, **kwargs
        )

    async def _token_endpoint(
        self, method: str, path: str, access_token: str | None, **kwargs
    ) -> dict:
        """Call an unversioned graph.instagram.com endpoint (token exchange/refresh)."""
        return await self._call(method, f"{GRAPH_HOST}{path}", access_token, **kwargs)

    async def _call(self, method: str, url: str, access_token: str | None, **kwargs) -> dict:
        client = await self._client_get()
        params = dict(kwargs.pop("params", {}) or {})
        if method.upper() == "GET":
            # Explicitly provided access_token params (e.g. token exchange
            # endpoints) take precedence; never silently overwrite them.
            params.setdefault("access_token", access_token or "")
        else:
            data = dict(kwargs.pop("data", {}) or {})
            data["access_token"] = access_token
            kwargs["data"] = data
        last_error: InstagramAPIError | None = None
        for attempt in range(3):
            resp = await client.request(method, url, params=params, **kwargs)
            payload = None
            try:
                payload = resp.json()
            except ValueError:
                payload = None
            if resp.status_code < 400:
                return payload or {}
            last_error = _parse_meta_error(resp.status_code, payload)
            if last_error.is_rate_limited and attempt < 2:
                # Exponential backoff respecting Meta's rate limits.
                wait = 2 ** (attempt + 1)
                log.warning("Meta rate limit hit; backing off %ss (attempt %d)", wait, attempt + 1)
                await asyncio.sleep(wait)
                continue
            raise last_error
        raise last_error or InstagramAPIError("Meta API request failed")

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -- OAuth --------------------------------------------------------------
    async def build_authorize_url(self, state: str) -> str:
        if not settings.META_APP_ID:
            raise InstagramAPIError("META_APP_ID is not configured. See META_INSTAGRAM_SETUP.md.")
        params = {
            "client_id": settings.META_APP_ID,
            "redirect_uri": settings.META_REDIRECT_URI,
            "response_type": "code",
            "scope": ",".join(SCOPES),
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> TokenResult:
        client = await self._client_get()
        resp = await client.post(
            TOKEN_EXCHANGE_URL,
            data={
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": settings.META_REDIRECT_URI,
                "code": code,
            },
        )
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code >= 400:
            raise _parse_meta_error(resp.status_code, payload)
        return TokenResult(
            access_token=payload["access_token"],
            expires_in=payload.get("expires_in", 3600),
            user_id=str(payload.get("user_id") or ""),
            granted_scopes=[s for s in str(payload.get("permissions", "")).split(",") if s],
        )

    async def exchange_long_lived_token(self, short_lived_token: str) -> TokenResult:
        payload = await self._token_endpoint(
            "GET",
            "/access_token",
            None,
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": settings.META_APP_SECRET,
                "access_token": short_lived_token,
            },
        )
        return TokenResult(
            access_token=payload["access_token"],
            expires_in=payload.get("expires_in"),
            granted_scopes=SCOPES.copy(),
        )

    async def refresh_long_lived_token(self, long_lived_token: str) -> TokenResult:
        payload = await self._token_endpoint(
            "GET",
            "/refresh_access_token",
            None,
            params={
                "grant_type": "ig_refresh_token",
                "access_token": long_lived_token,
            },
        )
        return TokenResult(
            access_token=payload["access_token"],
            expires_in=payload.get("expires_in"),
            granted_scopes=SCOPES.copy(),
        )

    # -- Reads ----------------------------------------------------------------
    async def get_account(self, access_token: str) -> AccountInfo:
        payload = await self._graph(
            "GET",
            "/me",
            access_token,
            params={
                "fields": ",".join(
                    [
                        "id",
                        "username",
                        "name",
                        "account_type",
                        "followers_count",
                        "follows_count",
                        "media_count",
                        "profile_picture_url",
                    ]
                )
            },
        )
        return AccountInfo(
            instagram_user_id=str(payload["id"]),
            username=payload.get("username", ""),
            account_type=payload.get("account_type"),
            name=payload.get("name"),
            profile_picture_url=payload.get("profile_picture_url"),
            followers_count=payload.get("followers_count"),
            follows_count=payload.get("follows_count"),
            media_count=payload.get("media_count"),
        )

    async def list_media(
        self, access_token: str, limit: int = 25, after: str | None = None
    ) -> tuple[list[MediaInfo], str | None]:
        params: dict = {
            "fields": ",".join(
                [
                    "id",
                    "caption",
                    "media_type",
                    "media_product_type",
                    "permalink",
                    "thumbnail_url",
                    "media_url",
                    "timestamp",
                    "like_count",
                    "comments_count",
                ]
            ),
            "limit": max(1, min(limit, 100)),
        }
        if after:
            params["after"] = after
        payload = await self._graph("GET", "/me/media", access_token, params=params)
        items: list[MediaInfo] = []
        for raw in payload.get("data", []):
            items.append(
                MediaInfo(
                    instagram_media_id=str(raw["id"]),
                    media_type=raw.get("media_type"),
                    media_product_type=raw.get("media_product_type"),
                    caption=raw.get("caption"),
                    permalink=raw.get("permalink"),
                    thumbnail_url=raw.get("thumbnail_url"),
                    media_url=raw.get("media_url"),
                    posted_at=_parse_iso8601(raw.get("timestamp")),
                    like_count=raw.get("like_count"),
                    comments_count=raw.get("comments_count"),
                )
            )
        next_cursor = (payload.get("paging") or {}).get("cursors", {}).get("after")
        return items, next_cursor

    async def get_account_insights(
        self,
        access_token: str,
        metrics: list[str],
        since: datetime,
        until: datetime,
    ) -> list[DailyMetricPoint]:
        valid = [m for m in metrics if m in ACCOUNT_METRICS]
        if not valid:
            return []
        payload = await self._graph(
            "GET",
            "/me/insights",
            access_token,
            params={
                "metric": ",".join(valid),
                "period": "day",
                "since": int(since.timestamp()),
                "until": int(until.timestamp()),
            },
        )
        points: list[DailyMetricPoint] = []
        for entry in payload.get("data", []):
            name = entry.get("name", "")
            for value in entry.get("values", []):
                end_time = _parse_iso8601(value.get("end_time"))
                if end_time is None:
                    continue
                points.append(
                    DailyMetricPoint(
                        metric_name=name,
                        date=end_time,
                        value=float(value["value"]) if value.get("value") is not None else None,
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
        """Lifetime media insights with per-media-type metric sets and fallback.

        Meta only supports certain metrics per media kind (reel watch-time
        metrics apply to reels, story metrics are limited, album children have
        none). We request the metrics valid for the media type first; if Meta
        rejects the combination we retry with the universal core set, and only
        then give up on that media (sync continues with the rest).
        """
        requested = _metrics_for_media_type(metrics, media_type)
        if not requested:
            return {}
        try:
            return await self._fetch_media_insights(access_token, media_id, requested)
        except InstagramAPIError as exc:
            if exc.is_auth_error or exc.is_rate_limited:
                raise
            log.warning(
                "Media insights request rejected for %s (%s); retrying with core metrics",
                media_id,
                exc.code,
            )
        core = [m for m in CORE_MEDIA_METRICS if m in metrics]
        if core and core != requested:
            try:
                return await self._fetch_media_insights(access_token, media_id, core)
            except InstagramAPIError as exc:
                if exc.is_auth_error or exc.is_rate_limited:
                    raise
                log.warning("Core media metrics also rejected for %s; skipping", media_id)
        return {}

    async def _fetch_media_insights(
        self, access_token: str, media_id: str, metrics: list[str]
    ) -> dict[str, float]:
        payload = await self._graph(
            "GET",
            f"/{media_id}/insights",
            access_token,
            params={"metric": ",".join(metrics)},
        )
        result: dict[str, float] = {}
        for entry in payload.get("data", []):
            values = entry.get("values", [])
            if values and values[0].get("value") is not None:
                result[entry.get("name", "")] = float(values[0]["value"])
        return result

    async def get_audience_demographics(
        self, access_token: str, breakdown: str, timeframe: str
    ) -> list[dict]:
        metric = "follower_demographics"
        payload = await self._graph(
            "GET",
            "/me/insights",
            access_token,
            params={
                "metric": metric,
                "metric_type": "total_value",
                "period": "lifetime",
                "timeframe": timeframe,
                "breakdown": breakdown,
            },
        )
        buckets: list[dict] = []
        for entry in payload.get("data", []):
            total = entry.get("total_value") or {}
            for group in total.get("breakdowns", []):
                keys = group.get("dimension_keys", [])
                for row in group.get("results", []):
                    dim_values = row.get("dimension_values", [])
                    buckets.append(
                        {
                            "dimensions": dict(zip(keys, dim_values, strict=False)),
                            "value": row.get("value"),
                        }
                    )
        return buckets

    # -- Comments ---------------------------------------------------------------
    async def list_comments(
        self, access_token: str, media_id: str, limit: int = 25
    ) -> list[CommentInfo]:
        payload = await self._graph(
            "GET",
            f"/{media_id}/comments",
            access_token,
            params={
                "fields": "id,text,username,timestamp,like_count,hidden",
                "limit": max(1, min(limit, 100)),
            },
        )
        return [self._to_comment(raw) for raw in payload.get("data", [])]

    def _to_comment(self, raw: dict) -> CommentInfo:
        return CommentInfo(
            comment_id=str(raw["id"]),
            text=raw.get("text"),
            username=raw.get("username"),
            timestamp=_parse_iso8601(raw.get("timestamp")),
            like_count=raw.get("like_count"),
            hidden=bool(raw.get("hidden")),
        )

    async def reply_to_comment(self, access_token: str, comment_id: str, message: str) -> str:
        payload = await self._graph(
            "POST", f"/{comment_id}/replies", access_token, data={"message": message}
        )
        return str(payload.get("id", ""))

    async def hide_comment(self, access_token: str, comment_id: str, hide: bool) -> None:
        await self._graph(
            "POST", f"/{comment_id}", access_token, data={"hide": "true" if hide else "false"}
        )

    async def delete_comment(self, access_token: str, comment_id: str) -> None:
        await self._graph("DELETE", f"/{comment_id}", access_token)

    async def get_comment_media_owner(self, access_token: str, comment_id: str) -> str:
        """Prove a comment sits on the connected account's own media.

        The comment node's ``media`` field returns the parent media, and the
        media node's ``owner`` field returns its IG user id. Callers compare
        this with the connected account's instagram_user_id before allowing
        reply/hide/delete.
        """
        payload = await self._graph(
            "GET", f"/{comment_id}", access_token, params={"fields": "media{owner}"}
        )
        media = payload.get("media") or {}
        owner = media.get("owner") or {}
        owner_id = str(owner.get("id") or "")
        if not owner_id:
            raise InstagramAPIError(
                "Could not verify the owner of this comment's media.", http_status=403
            )
        return owner_id
