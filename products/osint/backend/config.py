"""Read OSINT_* env vars from .env or process environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _require(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


@dataclass(frozen=True)
class Settings:
    db_url: str
    cors_origins: tuple[str, ...]
    db_pool_size: int
    db_max_overflow: int
    host: str
    port: int
    log_level: str
    story_source: str


def _story_source() -> str:
    """Kill-switch for the Defining-Stories read path (STEP 4a).

    'new' → read the fresh shared story layer (analytics.story_*).
    'old' → read the legacy public.event_clusters engine (the rollback path).
    Defaults to 'old' so the switch ships dark; one env flip + restart reverts
    the whole product. Any unrecognised value falls back to 'old' (fail-safe).
    """
    v = (os.environ.get("OSINT_STORY_SOURCE", "old") or "old").strip().lower()
    return v if v in ("new", "old") else "old"


def load_settings() -> Settings:
    return Settings(
        db_url=_require("OSINT_DB_URL"),
        cors_origins=tuple(
            o.strip() for o in os.environ.get("OSINT_CORS_ORIGINS", "").split(",") if o.strip()
        ),
        db_pool_size=int(os.environ.get("OSINT_DB_POOL_SIZE", "5")),
        db_max_overflow=int(os.environ.get("OSINT_DB_MAX_OVERFLOW", "10")),
        host=os.environ.get("OSINT_HOST", "0.0.0.0"),
        port=int(os.environ.get("OSINT_PORT", "8000")),
        log_level=os.environ.get("OSINT_LOG_LEVEL", "INFO"),
        story_source=_story_source(),
    )
