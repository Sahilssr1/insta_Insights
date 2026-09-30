"""SQLAlchemy models for the Instagram analytics app."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_aware(dt: datetime | None) -> datetime | None:
    """Attach UTC to naive datetimes coming back from the database.

    We always write UTC; SQLite discards tzinfo on read, which would break
    comparisons against timezone-aware ``now`` values. Idempotent.
    """
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    instagram_accounts: Mapped[list[InstagramAccount]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class InstagramAccount(Base):
    __tablename__ = "instagram_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instagram_user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    account_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # BUSINESS | CREATOR
    profile_picture_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    followers_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    follows_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="instagram_accounts")
    token: Mapped[InstagramToken | None] = relationship(
        back_populates="account", cascade="all, delete-orphan", uselist=False
    )
    media: Mapped[list[InstagramMedia]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class InstagramToken(Base):
    """Secure token storage: the raw access token is stored Fernet-encrypted."""

    __tablename__ = "instagram_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instagram_account_id: Mapped[int] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(32), default="bearer", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # comma separated granted scopes
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    account: Mapped[InstagramAccount] = relationship(back_populates="token")


class InstagramMedia(Base):
    __tablename__ = "instagram_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instagram_account_id: Mapped[int] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instagram_media_id: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # IMAGE | VIDEO | CAROUSEL_ALBUM
    media_product_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # FEED | REELS | STORY
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    permalink: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    account: Mapped[InstagramAccount] = relationship(back_populates="media")
    insights: Mapped[list[InstagramInsight]] = relationship(
        back_populates="media", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "instagram_account_id", "instagram_media_id", name="uq_media_account_media"
        ),
        Index("ix_media_account_posted", "instagram_account_id", "posted_at"),
    )


class InstagramInsight(Base):
    """Per-media metric snapshot (Meta media insights are `lifetime` period)."""

    __tablename__ = "instagram_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instagram_account_id: Mapped[int] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_id: Mapped[int] = mapped_column(
        ForeignKey("instagram_media.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    period: Mapped[str] = mapped_column(String(16), default="lifetime", nullable=False)
    metric_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    media: Mapped[InstagramMedia] = relationship(back_populates="insights")

    __table_args__ = (
        UniqueConstraint(
            "media_id", "metric_name", "period", name="uq_insight_media_metric_period"
        ),
    )


class InstagramDailyInsight(Base):
    """Account-level daily time series (Meta account insights, period=day)."""

    __tablename__ = "instagram_daily_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instagram_account_id: Mapped[int] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    reach: Mapped[float | None] = mapped_column(Float, nullable=True)
    views: Mapped[float | None] = mapped_column(Float, nullable=True)
    likes: Mapped[float | None] = mapped_column(Float, nullable=True)
    comments: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    saves: Mapped[float | None] = mapped_column(Float, nullable=True)
    replies: Mapped[float | None] = mapped_column(Float, nullable=True)
    reposts: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_interactions: Mapped[float | None] = mapped_column(Float, nullable=True)
    accounts_engaged: Mapped[float | None] = mapped_column(Float, nullable=True)
    follows_and_unfollows: Mapped[float | None] = mapped_column(Float, nullable=True)
    profile_links_taps: Mapped[float | None] = mapped_column(Float, nullable=True)
    follower_count_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    followers_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("instagram_account_id", "metric_date", name="uq_daily_account_date"),
        Index("ix_daily_account_date", "instagram_account_id", "metric_date"),
    )


class InstagramSyncLog(Base):
    __tablename__ = "instagram_sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instagram_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sync_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    sync_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="running", nullable=False
    )  # running|success|failed
    records_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class OAuthState(Base):
    """Single-use OAuth state tokens (CSRF protection for the connect flow)."""

    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(default=False, nullable=False)
