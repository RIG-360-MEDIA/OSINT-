"""Configuration modules for backend services.

Package layout:
* this module exports :class:`Settings` and the singleton ``settings``
  used across the backend (originally in ``backend/config.py``, but the
  ``backend/config`` package shadows that file so the loose-file
  version was unreachable).
* :mod:`backend.config.govt_config` holds the govt-doc collector
  knobs.
"""
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    # Groq
    GROQ_API_KEYS: str = ""

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    # JWT secret used to verify Supabase access tokens (HS256). Optional in dev:
    # when empty, signatures are NOT verified (decode only). Production must set this.
    SUPABASE_JWT_SECRET: str = ""

    # Optional integrations
    NEWSDATA_API_KEY: Optional[str] = None
    FRESHRSS_URL: Optional[str] = None
    FRESHRSS_USERNAME: str = "admin"
    FRESHRSS_PASSWORD: Optional[str] = None

    # NLP
    NLP_BATCH_SIZE: int = 25
    BRIEF_ARTICLE_LIMIT: int = 30

    # Brief — production-readiness knobs (added by fix/brief-prod-readiness).
    # Recency window for the article SELECT in brief_runner.run_for_user.
    # Defaults to 36h; if fewer than 10 fresh tier-1/2 articles are found,
    # the runner widens to BRIEF_ARTICLE_RECENCY_FALLBACK_HOURS once and
    # logs a warning before refusing to generate.
    BRIEF_ARTICLE_RECENCY_HOURS: int = 36
    BRIEF_ARTICLE_RECENCY_FALLBACK_HOURS: int = 72
    # Per-section LLM call timeout (asyncio.wait_for around generate()).
    BRIEF_SECTION_TIMEOUT_S: int = 25
    # Idempotency window: a fresh /generate within this many seconds of
    # the last successful run returns the existing row instead of
    # fanning out to Groq again.
    BRIEF_IDEMPOTENCY_WINDOW_S: int = 300
    # Minimum word count per section before regen is triggered.
    BRIEF_SECTION_MIN_WORDS: int = 80

    # Environment
    ENVIRONMENT: str = "development"

    @property
    def groq_keys_list(self) -> list[str]:
        return [k.strip() for k in self.GROQ_API_KEYS.split(",") if k.strip()]

    model_config = {"env_file": "infrastructure/.env", "extra": "ignore"}


settings = Settings()


__all__ = ["Settings", "settings"]
