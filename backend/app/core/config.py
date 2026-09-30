"""Application configuration via pydantic-settings.

All secrets come from environment variables (``.env`` supported locally).
See ../../.env.example and META_INSTAGRAM_SETUP.md for how to obtain the
Meta/Instagram values. Never commit real secrets.
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "InsightBoard — Instagram Analytics"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"  # development | production

    # sqlite+aiosqlite:///./insightboard.db  (dev default)
    # production example: postgresql+asyncpg://user:pass@host:5432/insightboard
    DATABASE_URL: str = "sqlite+aiosqlite:///./insightboard.db"

    JWT_SECRET: str = "change-me-in-production"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Fernet key (base64 urlsafe, 32 bytes) used to encrypt Instagram tokens at rest.
    # Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    TOKEN_ENCRYPTION_KEY: str = ""

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Where the OAuth callback redirects after success/failure.
    FRONTEND_URL: str = "http://localhost:5173"

    # ---- Meta / Instagram OAuth + API ----
    # Obtain from https://developers.facebook.com/apps (see META_INSTAGRAM_SETUP.md)
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    # Must exactly match a redirect URI registered in the Meta app dashboard,
    # e.g. http://localhost:8000/api/instagram/callback
    META_REDIRECT_URI: str = "http://localhost:8000/api/instagram/callback"
    META_API_VERSION: str = "v26.0"

    # Which Instagram data provider to use.
    # "meta"  -> real Meta/Instagram official APIs (production).
    # "mock"  -> clearly-labelled development fixtures. ONLY allowed when
    #            ENVIRONMENT=development; the app refuses to boot otherwise.
    INSTAGRAM_PROVIDER: str = "meta"

    # Sync behaviour
    SYNC_ACCOUNT_INSIGHT_DAYS: int = 30  # how many days back to pull daily account insights
    SYNC_MEDIA_LIMIT: int = 50  # max media objects per sync
    SYNC_MIN_INTERVAL_SECONDS: int = 300  # throttle manual "Sync now" calls

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @model_validator(mode="after")
    def _require_production_secrets(self) -> Settings:
        """Fail fast in production: development secret fallbacks must never be used.

        The mock-provider gate lives in ``get_provider()`` (single source of truth).
        """
        if self.is_production:
            problems: list[str] = []
            if not self.JWT_SECRET or self.JWT_SECRET == "change-me-in-production":
                problems.append("JWT_SECRET must be set to a strong random value")
            if not self.TOKEN_ENCRYPTION_KEY:
                problems.append("TOKEN_ENCRYPTION_KEY must be set (Fernet key)")
            if problems:
                raise ValueError("Production misconfiguration: " + "; ".join(problems))
        return self


settings = Settings()
