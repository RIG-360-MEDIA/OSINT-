"""Ask-RIG settings — read ``ASKRIG_*`` from ``.env`` or the process environment.

Mirrors the night-desk backend pattern (frozen dataclass + ``load_dotenv``) so the
two read-only products stay consistent. Nothing here is secret at rest; secrets
arrive via env: ``ASKRIG_DB_URL`` carries the read-only analytics_user DSN and
``ASKRIG_LLM_API_KEY`` the LLM key.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # --- database (READ-ONLY corpus) ---
    db_url: str
    db_pool_size: int
    db_max_overflow: int
    # --- retrieval ---
    embed_model: str
    k_vec: int
    k_lex: int
    rrf_k: int
    top_k: int
    fts_config: str
    # --- llm / answer ---
    answer_enabled: bool
    llm_provider: str
    llm_model: str
    llm_api_key: str
    llm_api_keys: tuple[str, ...]
    llm_base_url: str
    llm_temperature: float
    # --- reranker ---
    rerank_enabled: bool
    rerank_model: str
    rerank_fetch_k: int   # candidates fetched from hybrid before reranking
    rerank_top_n: int     # keep after rerank, before diversity
    # --- diversity ---
    dedup_threshold: float
    diversity_lambda: float
    max_per_source: int
    # --- app DB (writable, per-user state — SEPARATE from the read-only corpus) ---
    app_db_url: str
    # --- live web (Set 3) ---
    web_enabled: bool
    searxng_url: str
    web_max_results: int
    web_fetch_timeout: int
    web_max_bytes: int
    # --- web full-text extraction (Phase 3: snippet → full article text) ---
    web_extract_enabled: bool
    web_extract_top_n: int    # only the top-N web hits get fetched + extracted
    web_extract_max_chars: int  # cap per web source handed to the writer
    # --- server ---
    cors_origins: tuple[str, ...]
    host: str
    port: int
    log_level: str


def _key_pool() -> tuple[str, ...]:
    """Pooled keys from ASKRIG_LLM_API_KEYS (comma-sep), else the single key."""
    raw = os.environ.get("ASKRIG_LLM_API_KEYS", "")
    keys = tuple(k.strip() for k in raw.split(",") if k.strip())
    if keys:
        return keys
    single = os.environ.get("ASKRIG_LLM_API_KEY", "").strip()
    return (single,) if single else ()


def load_settings() -> Settings:
    key_pool = _key_pool()
    return Settings(
        db_url=_require("ASKRIG_DB_URL"),
        db_pool_size=_int("ASKRIG_DB_POOL_SIZE", 5),
        db_max_overflow=_int("ASKRIG_DB_MAX_OVERFLOW", 10),
        embed_model=os.environ.get("ASKRIG_EMBED_MODEL", "sentence-transformers/LaBSE"),
        k_vec=_int("ASKRIG_K_VEC", 30),
        k_lex=_int("ASKRIG_K_LEX", 30),
        rrf_k=_int("ASKRIG_RRF_K", 60),
        top_k=_int("ASKRIG_TOP_K", 8),
        fts_config=os.environ.get("ASKRIG_FTS_CONFIG", "simple"),
        answer_enabled=_bool("ASKRIG_ANSWER_ENABLED", True),
        llm_provider=os.environ.get("ASKRIG_LLM_PROVIDER", "groq"),
        llm_model=os.environ.get("ASKRIG_LLM_MODEL", "llama-3.3-70b-versatile"),
        llm_api_key=key_pool[0] if key_pool else "",
        llm_api_keys=key_pool,
        llm_base_url=os.environ.get("ASKRIG_LLM_BASE_URL", "https://api.groq.com/openai/v1"),
        llm_temperature=float(os.environ.get("ASKRIG_LLM_TEMPERATURE", "0.2")),
        rerank_enabled=_bool("ASKRIG_RERANK_ENABLED", True),
        rerank_model=os.environ.get("ASKRIG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
        rerank_fetch_k=_int("ASKRIG_RERANK_FETCH_K", 50),
        rerank_top_n=_int("ASKRIG_RERANK_TOP_N", 20),
        dedup_threshold=_float("ASKRIG_DEDUP_THRESHOLD", 0.65),
        diversity_lambda=_float("ASKRIG_DIVERSITY_LAMBDA", 0.65),
        max_per_source=_int("ASKRIG_MAX_PER_SOURCE", 2),
        app_db_url=os.environ.get(
            "ASKRIG_APP_DB_URL", "sqlite+aiosqlite:///./askrig_app.db"
        ),
        web_enabled=_bool("ASKRIG_WEB_ENABLED", True),
        searxng_url=os.environ.get("ASKRIG_SEARXNG_URL", "http://localhost:8888"),
        web_max_results=_int("ASKRIG_WEB_MAX_RESULTS", 6),
        web_fetch_timeout=_int("ASKRIG_WEB_FETCH_TIMEOUT", 8),
        web_max_bytes=_int("ASKRIG_WEB_MAX_BYTES", 2_000_000),
        web_extract_enabled=_bool("ASKRIG_WEB_EXTRACT_ENABLED", True),
        web_extract_top_n=_int("ASKRIG_WEB_EXTRACT_TOP_N", 3),
        web_extract_max_chars=_int("ASKRIG_WEB_EXTRACT_MAX_CHARS", 1600),
        cors_origins=tuple(
            o.strip() for o in os.environ.get("ASKRIG_CORS_ORIGINS", "").split(",") if o.strip()
        ),
        host=os.environ.get("ASKRIG_HOST", "127.0.0.1"),
        port=_int("ASKRIG_PORT", 8010),
        log_level=os.environ.get("ASKRIG_LOG_LEVEL", "INFO"),
    )
