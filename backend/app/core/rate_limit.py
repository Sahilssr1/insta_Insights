"""Tiny in-memory sliding-window rate limiter for abuse-prone endpoints.

This is a single-process limiter: it protects against casual abuse and
credential-stuffing on the auth endpoints. Deployments running multiple
workers should front the app with a shared limiter (e.g. nginx limit_req
or a Redis-backed limiter).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._prune(key, now)
        if len(hits) >= self.max_requests:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests. Please slow down and try again shortly.",
            )
        hits.append(now)
        # Opportunistic cleanup so idle keys don't accumulate forever.
        if len(self._hits) > 10000:
            for stale in [k for k, v in self._hits.items() if not self._prune(k, now)]:
                del self._hits[stale]


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "?"


def limit(limiter: RateLimiter, scope: str = ""):
    """FastAPI dependency factory: rate-limit by client IP (+ optional scope)."""

    async def _dependency(request: Request) -> None:
        limiter.check(f"{scope}:{_client_key(request)}" if scope else _client_key(request))

    return _dependency


# Prebuilt limiters. Tune via constructor args where they are applied.
auth_limiter = RateLimiter(max_requests=30, window_seconds=60)
sync_limiter = RateLimiter(max_requests=20, window_seconds=60)
