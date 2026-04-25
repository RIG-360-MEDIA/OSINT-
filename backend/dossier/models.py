"""Pydantic models for the Dossier API surface.

Kept dependency-light — no SQLAlchemy ORM here. Worker uses `text()` queries
against the new tables defined in scripts/migrations/018_dossier.sql.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

TargetType = Literal["name", "email", "phone", "username", "domain", "image"]
DossierStatus = Literal["pending", "running", "completed", "failed", "partial"]


class DossierRunRequest(BaseModel):
    target: str = Field(..., min_length=1, max_length=500)
    target_type: TargetType
    purpose_note: str | None = Field(default=None, max_length=2000)
    allow_sensitive: bool = False


class FindingOut(BaseModel):
    source: str
    field: str
    value: Any
    source_url: str | None = None
    confidence: float
    found_at: datetime


class DossierOut(BaseModel):
    id: UUID
    target: str
    target_type: TargetType
    status: DossierStatus
    summary: dict[str, Any] | None = None
    error: str | None = None
    purpose_note: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    findings: list[FindingOut] = Field(default_factory=list)


class DossierListItem(BaseModel):
    id: UUID
    target: str
    target_type: TargetType
    status: DossierStatus
    created_at: datetime
    completed_at: datetime | None = None
    finding_count: int = 0
