"""Provider selection safety gate and Meta provider plumbing."""

from __future__ import annotations

import pytest

from app.services.providers.base import (
    CORE_MEDIA_METRICS,
    MEDIA_METRICS,
    InstagramAPIError,
    TokenExpiredError,
    _metrics_for_media_type,
    get_provider,
)
from app.services.providers.meta_provider import (
    MetaInstagramProvider,
    _parse_meta_error,
)
from app.services.providers.mock_provider import MockInstagramProvider


def test_mock_provider_allowed_in_development(rebuild_settings):
    rebuild_settings(INSTAGRAM_PROVIDER="mock", ENVIRONMENT="development")
    provider = get_provider()
    assert isinstance(provider, MockInstagramProvider)


def test_mock_provider_rejected_in_production(rebuild_settings):
    rebuild_settings(
        INSTAGRAM_PROVIDER="mock",
        ENVIRONMENT="production",
        JWT_SECRET="a-very-long-and-strong-test-secret-value-1234567890",
        TOKEN_ENCRYPTION_KEY="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    with pytest.raises(RuntimeError, match="not allowed in production"):
        get_provider()


def test_meta_provider_is_default(rebuild_settings):
    rebuild_settings(INSTAGRAM_PROVIDER="meta", ENVIRONMENT="development")
    provider = get_provider()
    assert isinstance(provider, MetaInstagramProvider)


def test_production_settings_require_secrets(rebuild_settings):
    with pytest.raises(Exception, match="Production misconfiguration"):
        rebuild_settings(
            INSTAGRAM_PROVIDER="meta",
            ENVIRONMENT="production",
            JWT_SECRET="change-me-in-production",
            TOKEN_ENCRYPTION_KEY="",
        )


def test_is_auth_error_precedence():
    # expired token: 400 + code 190
    e = InstagramAPIError("expired", code=190, http_status=400)
    assert e.is_auth_error
    # plain 401 without code
    e = InstagramAPIError("unauthorized", http_status=401)
    assert e.is_auth_error
    # rate limit is NOT an auth error
    e = InstagramAPIError("rate limited", code=4, http_status=429)
    assert not e.is_auth_error
    assert e.is_rate_limited


def test_parse_meta_error_expired_token():
    err = _parse_meta_error(
        400,
        {"error": {"message": "Error validating access token: Session has expired", "code": 190}},
    )
    assert isinstance(err, TokenExpiredError)


def test_parse_meta_error_rate_limit_retryable():
    err = _parse_meta_error(429, {"error": {"message": "slow down", "code": 4}})
    assert err.is_rate_limited and err.retryable


async def test_mock_comment_owner_matches_mock_account():
    provider = MockInstagramProvider()
    owner = await provider.get_comment_media_owner("MOCK_LONG_LIVED", "mock_c1")
    account = await provider.get_account("MOCK_LONG_LIVED")
    assert owner == account.instagram_user_id


def test_metrics_for_media_type_reel_gets_watch_time():
    chosen = _metrics_for_media_type(MEDIA_METRICS, "REEL")
    assert "ig_reels_avg_watch_time" in chosen
    assert "follows" not in chosen  # feed-only extra
    assert "views" in chosen  # core always included


def test_metrics_for_media_type_feed_gets_profile_metrics():
    chosen = _metrics_for_media_type(MEDIA_METRICS, "IMAGE")
    assert "profile_visits" in chosen
    assert "ig_reels_avg_watch_time" not in chosen


def test_metrics_for_media_type_story_core_only():
    chosen = _metrics_for_media_type(MEDIA_METRICS, "STORY")
    assert chosen == [m for m in MEDIA_METRICS if m in CORE_MEDIA_METRICS]


def test_metrics_for_media_type_unknown_media_type_keeps_valid():
    chosen = _metrics_for_media_type(MEDIA_METRICS, None)
    assert set(chosen) == set(MEDIA_METRICS)


async def test_meta_media_insights_falls_back_to_core(monkeypatch):
    """Unsupported per-type combination -> retry with core metrics."""
    provider = MetaInstagramProvider()
    calls: list[list[str]] = []

    async def fake_fetch(access_token, media_id, metrics):
        calls.append(metrics)
        if len(calls) == 1:
            raise InstagramAPIError("unsupported metric combination", code=100)
        return {"views": 10.0}

    monkeypatch.setattr(provider, "_fetch_media_insights", fake_fetch)
    result = await provider.get_media_insights("tok", "mid", MEDIA_METRICS, media_type="REEL")
    assert result == {"views": 10.0}
    assert len(calls) == 2
    assert set(calls[1]) <= set(CORE_MEDIA_METRICS)


async def test_meta_media_insights_gives_up_gracefully(monkeypatch):
    """Both attempts rejected -> empty dict, auth/rate-limit still raise."""
    provider = MetaInstagramProvider()

    async def always_fail(access_token, media_id, metrics):
        raise InstagramAPIError("bad metric", code=100)

    monkeypatch.setattr(provider, "_fetch_media_insights", always_fail)
    assert await provider.get_media_insights("tok", "mid", MEDIA_METRICS, media_type="IMAGE") == {}

    async def auth_fail(access_token, media_id, metrics):
        raise InstagramAPIError("expired", code=190, http_status=400)

    monkeypatch.setattr(provider, "_fetch_media_insights", auth_fail)
    with pytest.raises(InstagramAPIError):
        await provider.get_media_insights("tok", "mid", MEDIA_METRICS, media_type="IMAGE")
