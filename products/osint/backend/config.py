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
    )
