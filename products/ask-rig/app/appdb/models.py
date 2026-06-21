"""SQLAlchemy ORM models for per-user state. Portable across SQLite / Postgres."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    pwd_hash: Mapped[str] = mapped_column(String(128))
    pwd_salt: Mapped[str] = mapped_column(String(64))
    # user-specific defaults, applied when a request doesn't override them
    default_languages: Mapped[str | None] = mapped_column(String(64), default=None)  # csv
    home_geo: Mapped[str | None] = mapped_column(String(64), default=None)
    last_catchup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    tokens: Mapped[list["Token"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Token(Base):
    __tablename__ = "user_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 hex
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship(back_populates="tokens")


class QueryHistory(Base):
    __tablename__ = "query_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(Text)
    languages: Mapped[str | None] = mapped_column(String(64), default=None)
    n_results: Mapped[int] = mapped_column(Integer, default=0)
    used_web: Mapped[int] = mapped_column(Integer, default=0)  # 0/1
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_saved_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    query: Mapped[str] = mapped_column(Text)
    languages: Mapped[str | None] = mapped_column(String(64), default=None)
    # high-water mark: latest published_at seen → alert = matches newer than this
    last_seen_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WatchedEntity(Base):
    __tablename__ = "watched_entities"
    __table_args__ = (UniqueConstraint("user_id", "entity_id", name="uq_watch_user_entity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[str] = mapped_column(String(36))  # corpus entity_dictionary.id
    canonical_name: Mapped[str] = mapped_column(String(200))
    last_seen_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Mute(Base):
    __tablename__ = "mutes"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "value", name="uq_mute_user_kind_value"),
        Index("ix_mute_user_kind", "user_id", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))  # source | language | keyword | entity
    value: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ReadArticle(Base):
    __tablename__ = "read_articles"
    __table_args__ = (UniqueConstraint("user_id", "article_id", name="uq_read_user_article"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[str] = mapped_column(String(36))
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---- Bucket 2: annotations, scheduled brief, delivery channels ----

class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[str] = mapped_column(String(36), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BriefSchedule(Base):
    """One brief config per user — cadence + hour. A cron hits /me/brief to deliver."""
    __tablename__ = "brief_schedules"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    cadence: Mapped[str] = mapped_column(String(16), default="daily")  # daily | weekly | off
    hour_utc: Mapped[int] = mapped_column(Integer, default=2)
    languages: Mapped[str | None] = mapped_column(String(64), default=None)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DeliveryChannel(Base):
    """Where to push alerts/briefs — webhook now; email/slack share the same shape."""
    __tablename__ = "delivery_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # webhook | email | slack
    target: Mapped[str] = mapped_column(String(500))  # url or address
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---- Bucket 3: agent conversation threads ----

class AgentMessage(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (Index("ix_agent_thread", "thread_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
