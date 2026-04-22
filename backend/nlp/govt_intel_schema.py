"""
Pydantic schema for structured intelligence extracted from government documents.

A single GovtDocIntel object captures 17 fields about a doc's meaning,
impact, and concrete actions. Used as the validated return type of
backend.nlp.govt_intel.extract_intel().
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DocumentNature = Literal[
    "ORDER", "NOTIFICATION", "CIRCULAR", "GAZETTE", "POLICY",
    "AMENDMENT", "TENDER", "JUDGMENT", "AUDIT_REPORT", "BUDGET",
    "RTI_RESPONSE", "COMMITTEE_REPORT", "BILL", "MINUTES", "OTHER",
]
ActionPosture = Literal[
    "NEW_POLICY", "EXPANSION", "RESTRICTION", "REPEAL", "EXEMPTION",
    "PUNITIVE", "REWARD", "INVESTIGATION", "TRANSPARENCY",
    "ROUTINE_ADMIN", "OTHER",
]
EnforcementStrength = Literal["BINDING", "ADVISORY", "ASPIRATIONAL"]


def _coerce_date(value):
    """Lenient date coercion: accept date, ISO string, or None.

    Groq sometimes returns the empty string, "null", or a partial ISO
    date — we treat all those as None rather than raising.
    """
    if value is None or value == "" or value == "null":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
                return None
    return None


class GovtDocIntel(BaseModel):
    """Structured intelligence extracted from a govt-doc text by Groq."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    what_it_does:           str = Field(..., description="One-sentence verb-led action description")
    who_it_affects:         list[str] = Field(default_factory=list)
    what_changes:           str | None = None
    financial_magnitude_inr: int | None = None  # in rupees, not crores
    effective_date:         date | None = None
    deadline_dates:         list[date] = Field(default_factory=list)
    geography_affected:     list[str] = Field(default_factory=list)
    sectors_affected:       list[str] = Field(default_factory=list)
    winners:                list[str] = Field(default_factory=list)
    losers:                 list[str] = Field(default_factory=list)
    contradicts_prior:      bool = False
    contradicts_what:       str | None = None
    precedent_setting:      bool = False
    enforcement_strength:   EnforcementStrength | None = None
    document_nature:        DocumentNature = "OTHER"
    action_posture:         ActionPosture = "OTHER"

    @field_validator("effective_date", mode="before")
    @classmethod
    def _v_effective_date(cls, v):
        return _coerce_date(v)

    @field_validator("deadline_dates", mode="before")
    @classmethod
    def _v_deadline_dates(cls, v):
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        coerced = [_coerce_date(item) for item in v]
        return [d for d in coerced if d is not None]

    @field_validator(
        "who_it_affects", "geography_affected", "sectors_affected",
        "winners", "losers",
        mode="before",
    )
    @classmethod
    def _v_string_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return []

    @field_validator("financial_magnitude_inr", mode="before")
    @classmethod
    def _v_money(cls, v):
        if v is None or v == "" or v == "null":
            return None
        try:
            n = int(float(v))
            return n if n > 0 else None
        except (TypeError, ValueError):
            return None

    @field_validator("document_nature", mode="before")
    @classmethod
    def _v_nature(cls, v):
        if not v or not isinstance(v, str):
            return "OTHER"
        upper = v.strip().upper()
        valid = {
            "ORDER", "NOTIFICATION", "CIRCULAR", "GAZETTE", "POLICY",
            "AMENDMENT", "TENDER", "JUDGMENT", "AUDIT_REPORT", "BUDGET",
            "RTI_RESPONSE", "COMMITTEE_REPORT", "BILL", "MINUTES", "OTHER",
        }
        return upper if upper in valid else "OTHER"

    @field_validator("action_posture", mode="before")
    @classmethod
    def _v_posture(cls, v):
        if not v or not isinstance(v, str):
            return "OTHER"
        upper = v.strip().upper()
        valid = {
            "NEW_POLICY", "EXPANSION", "RESTRICTION", "REPEAL", "EXEMPTION",
            "PUNITIVE", "REWARD", "INVESTIGATION", "TRANSPARENCY",
            "ROUTINE_ADMIN", "OTHER",
        }
        return upper if upper in valid else "OTHER"

    @field_validator("enforcement_strength", mode="before")
    @classmethod
    def _v_enforcement(cls, v):
        if not v or not isinstance(v, str):
            return None
        upper = v.strip().upper()
        return upper if upper in {"BINDING", "ADVISORY", "ASPIRATIONAL"} else None
