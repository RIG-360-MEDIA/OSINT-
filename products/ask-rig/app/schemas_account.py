"""Request/response models for Set 2 (accounts/personalization) + Set 3 (web)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import Citation, RetrievedDoc

MuteKind = Literal["source", "language", "keyword", "entity"]


class SignupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class TokenResponse(BaseModel):
    token: str
    user_id: str
    username: str


class UserOut(BaseModel):
    user_id: str
    username: str
    default_languages: list[str] | None
    home_geo: str | None
    created_at: datetime


class SettingsPatch(BaseModel):
    default_languages: list[str] | None = None
    home_geo: str | None = None


class HistoryOut(BaseModel):
    id: int
    query: str
    languages: str | None
    n_results: int
    used_web: bool
    created_at: datetime


class SavedSearchIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    query: str = Field(..., min_length=2, max_length=2000)
    languages: list[str] | None = None


class SavedSearchOut(BaseModel):
    id: int
    name: str
    query: str
    languages: list[str] | None
    last_seen_published_at: datetime | None
    last_checked_at: datetime | None
    created_at: datetime


class WatchIn(BaseModel):
    entity_id: str = Field(..., min_length=8, max_length=36)
    canonical_name: str | None = None


class WatchOut(BaseModel):
    id: int
    entity_id: str
    canonical_name: str
    last_seen_published_at: datetime | None
    created_at: datetime


class MuteIn(BaseModel):
    kind: MuteKind
    value: str = Field(..., min_length=1, max_length=200)


class MuteOut(BaseModel):
    id: int
    kind: str
    value: str
    created_at: datetime


class AlertResponse(BaseModel):
    """New items since the high-water mark, for a saved search or watched entity."""
    new_count: int
    items: list[RetrievedDoc]


class WebResult(BaseModel):
    title: str
    url: str
    snippet: str | None = None
    engine: str | None = None


class ResearchRequest(BaseModel):
    question: str = Field(..., min_length=4, max_length=2000)
    languages: list[str] | None = None
    use_web: bool = True
    web_k: int = Field(6, ge=0, le=12)  # how many live-web results to pull (0 = none)


class NoteIn(BaseModel):
    article_id: str = Field(..., min_length=8, max_length=36)
    body: str = Field(..., min_length=1, max_length=5000)


class NoteOut(BaseModel):
    id: int
    article_id: str
    body: str
    created_at: datetime


class BriefScheduleIn(BaseModel):
    cadence: Literal["daily", "weekly", "off"] = "daily"
    hour_utc: int = Field(2, ge=0, le=23)
    languages: list[str] | None = None


class BriefScheduleOut(BaseModel):
    cadence: str
    hour_utc: int
    languages: list[str] | None
    last_sent_at: datetime | None


class ChannelIn(BaseModel):
    kind: Literal["webhook", "email", "slack"]
    target: str = Field(..., min_length=3, max_length=500)


class ChannelOut(BaseModel):
    id: int
    kind: str
    target: str
    active: bool
    created_at: datetime


class BriefResponse(BaseModel):
    digest: str | None
    faithful: bool = True
    citations: list[Citation] = []
    sources: list[RetrievedDoc] = []
    contributors: list[dict] = []
    notes: str | None = None


class ResearchResponse(BaseModel):
    question: str
    answer: str | None
    faithful: bool
    citations: list[Citation]
    sources: list[RetrievedDoc]  # fused corpus+web, in [S#] citation order
    web_sources: list[WebResult]  # raw web hits (provenance / extras)
    notes: str | None = None


class AgentRequest(BaseModel):
    message: str = Field(..., min_length=2, max_length=2000)
    thread_id: str | None = None  # continue a conversation
    max_steps: int = Field(5, ge=1, le=8)


class AgentResponse(BaseModel):
    thread_id: str
    answer: str | None
    faithful: bool
    citations: list[Citation]
    sources: list[RetrievedDoc]
    trace: list[dict]  # tool calls made ("show your work")
    steps: int
