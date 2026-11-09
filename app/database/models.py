"""SQLAlchemy models. Every tenant-owned row carries guild_id."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Naive UTC timestamp (consistent across SQLite and PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class GuildSettings(Base):
    __tablename__ = "guild_settings"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    plan: Mapped[str] = mapped_column(String(16), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Subscription(Base):
    __tablename__ = "subreddit_subscriptions"
    __table_args__ = (UniqueConstraint("guild_id", "subreddit", name="uq_sub_guild_subreddit"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("guild_settings.guild_id", ondelete="CASCADE"), index=True
    )
    subreddit: Mapped[str] = mapped_column(String(21))
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Delivery(Base):
    """One row per (subscription, reddit post). The unique constraint prevents duplicates."""

    __tablename__ = "delivery_records"
    __table_args__ = (UniqueConstraint("subscription_id", "post_id", name="uq_delivery_sub_post"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subreddit_subscriptions.id", ondelete="CASCADE"), index=True
    )
    post_id: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|sent|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
