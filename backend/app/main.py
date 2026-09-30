"""InsightBoard backend — Instagram analytics via Meta's official APIs."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from alembic import command
from app.api import auth as auth_router
from app.api import instagram as instagram_router
from app.core.config import settings
from app.services.providers.base import InstagramAPIError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]


async def run_migrations() -> None:
    """Apply pending Alembic migrations on startup (single source of truth).

    Runs in a worker thread because alembic's env.py drives its own
    ``asyncio.run()``, which cannot nest inside the lifespan's event loop.
    Paths are absolute so the app boots from any working directory.
    """
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    await asyncio.to_thread(command.upgrade, cfg, "head")
    log.info("Database migrations applied")


def validate_provider_config() -> None:
    """Fail fast if mock data could leak into production."""
    from app.services.providers.base import get_provider

    provider = get_provider()  # raises if mock + production
    log.info("Instagram data provider: %s", provider.name)
    if provider.name == "meta" and settings.is_production:
        from app.services.token_store import meta_configured

        if not meta_configured():
            log.warning(
                "META_APP_ID / META_APP_SECRET are not set; Instagram connect will "
                "return a configuration error until they are provided."
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_provider_config()
    await run_migrations()
    yield


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(instagram_router.router)


@app.exception_handler(InstagramAPIError)
async def instagram_api_error_handler(request: Request, exc: InstagramAPIError):
    # Never leak raw provider details or tokens to the client.
    status = 502
    if exc.is_auth_error:
        status = 401
    elif exc.is_rate_limited:
        status = 429
    return JSONResponse(
        status_code=status,
        content={
            "detail": "Instagram request failed. Please try again.",
            "code": "instagram_api_error",
        },
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/api/config")
async def public_config():
    """Non-secret config the frontend needs."""
    from app.services.token_store import meta_configured

    return {
        "provider": __import__("app.services.providers.base", fromlist=["get_provider"])
        .get_provider()
        .name,
        "meta_configured": meta_configured(),
        "environment": settings.ENVIRONMENT,
    }
