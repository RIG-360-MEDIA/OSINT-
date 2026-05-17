"""
Coverage / Articles router — RAG-integrated analyst surface.

Splits out endpoints for the /coverage/articles rebuild so the legacy
coverage_router (feed/search/summary/article/panels/ticker) stays untouched.

Endpoints (all gated by require_page("coverage")):
    POST  /api/coverage/ask              — SSE-streamed filter-aware RAG
    GET   /api/coverage/top-stories      — Top-5 with chain-of-thought
    GET   /api/coverage/related/{id}     — semantic neighbours
    GET   /api/coverage/timetravel       — today, last year
    GET   /api/coverage/quotes           — quotes by speaker/entity
    POST  /api/coverage/compare          — claim alignment across articles
    GET   /api/coverage/contradictions   — active contradictions inbox
    GET   /api/coverage/breaking         — active breaking clusters
    GET   /api/coverage/dissent          — event-level dissent flags
    GET   /api/coverage/coverage-gaps    — under-covered entities

    POST  /api/coverage/cards            — create custom card
    GET   /api/coverage/cards            — list user's cards (with summaries)
    DELETE /api/coverage/cards/{id}      — remove card

    GET   /api/coverage/watchlist        — pinned entities + new mention counts
    POST  /api/coverage/watchlist        — pin entity
    DELETE /api/coverage/watchlist/{id}  — unpin
    POST  /api/coverage/watchlist/seen   — mark all as seen

    GET   /api/coverage/notifications    — unread notification events
    POST  /api/coverage/notifications/{id}/read — mark read
    POST  /api/coverage/notification-rules — create rule (Groq-parsed predicate)
    GET   /api/coverage/notification-rules — list rules
    DELETE /api/coverage/notification-rules/{id} — remove rule

Feature flags (env, default off): FEATURE_ASK_BAR, FEATURE_CARDS,
FEATURE_BREAKING, FEATURE_CONTRADICTIONS, FEATURE_COMPARE, FEATURE_WATCHLIST,
FEATURE_NOTIFICATIONS. Each gate raises 404 when disabled.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_principal, require_page
from backend.coverage.scoring import (
    SURFACE_THRESHOLD,
    UserInterestProfile,
    load_user_profile,
    profile_top_entity_names,
    score_cluster,
)
from backend.database import get_db
from backend.nlp.groq_client import (
    FAST_MODEL,
    QUALITY_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
    call_groq_stream,
)

logger = logging.getLogger(__name__)


# ── Feature flags ─────────────────────────────────────────────────────────────


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _require_flag(flag_name: str) -> None:
    if not _flag(flag_name):
        raise HTTPException(status_code=404, detail="Feature not enabled")


# ── Router ────────────────────────────────────────────────────────────────────


coverage_articles_router = APIRouter(
    prefix="/api/coverage",
    tags=["coverage-articles"],
    dependencies=[Depends(require_page("coverage"))],
)


# ── Filter payload (shared by Ask Bar + Top Stories + Compare) ────────────────


class ArticleFilters(BaseModel):
    """
    Filter payload — mirrors the existing /feed query params so the same
    filter state in the UI scopes both feed and Ask Bar identically.
    """

    tier: str | None = "1,2,3"
    topics: list[str] | None = None
    days: int | None = 0  # 0 = all time
    sentiment: str | None = "all"
    sort: str | None = "relevance"
    geo: list[str] | None = None
    entity_ids: list[str] | None = None
    keywords: list[str] | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _hash_uid(user_id: str) -> str:
    return hashlib.blake2s(str(user_id).encode(), digest_size=6).hexdigest()


def _filter_to_sql_clauses(
    filters: ArticleFilters,
) -> tuple[list[str], dict[str, Any]]:
    """
    Translate filter payload into a list of SQL WHERE clauses + params.

    Returns: (clauses, params). Caller joins clauses with ' AND '.
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if filters.tier:
        tiers = [int(t.strip()) for t in filters.tier.split(",") if t.strip()]
        if tiers:
            clauses.append("a.source_tier = ANY(:tiers)")
            params["tiers"] = tiers

    if filters.topics:
        clauses.append("a.topic_category = ANY(:topics)")
        params["topics"] = filters.topics

    if filters.days and filters.days > 0:
        clauses.append("a.published_at > NOW() - make_interval(days => :days)")
        params["days"] = filters.days

    if filters.geo:
        clauses.append("(a.geo_primary = ANY(:geo) OR a.geo_secondary && :geo)")
        params["geo"] = filters.geo

    # is_duplicate guard always applies
    clauses.append("a.is_duplicate IS NOT TRUE")

    return clauses, params


# ── Ask Bar (SSE streamed RAG) ────────────────────────────────────────────────


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    filters: ArticleFilters = Field(default_factory=ArticleFilters)
    session_id: str | None = None


_ASK_SYSTEM_PROMPT = (
    "You are an intelligence analyst. The user is reading a filtered set of "
    "articles and has asked a question scoped to that set. Answer in clear, "
    "confident editorial prose — 3 to 6 sentences. Open with the answer, "
    "no preamble. Cite sources inline using [N] where N is the article "
    "number from the provided context. Do not invent facts. If the context "
    "does not support an answer, say so plainly. Never use bullet lists or "
    "headings; pure prose only."
)


async def _retrieve_filtered_articles(
    question: str,
    filters: ArticleFilters,
    user_id: str,
    k: int = 12,
) -> list[dict]:
    """
    Filter-aware retrieval. Hybrid (FTS + vector) when migration 046 has
    landed; falls back to vector-only otherwise. Returns list of dicts:
        { article_id, title, lead, source_name, source_domain, published_at }
    """
    from backend.nlp.rag_engine import embed_query  # lazy to avoid cold-start

    embedding = embed_query(question)
    clauses, params = _filter_to_sql_clauses(filters)
    where_sql = " AND ".join(clauses) if clauses else "TRUE"

    # Hybrid: vector + FTS, fused with reciprocal-rank fusion.
    # Falls through to vector-only if articles.fts column doesn't exist yet.
    has_fts = await _articles_has_fts_column()

    async with get_db() as db:
        if embedding is not None and has_fts:
            params.update({"emb": str(embedding), "q": question, "k": k * 3})
            sql = f"""
                WITH vector_hits AS (
                    SELECT a.id,
                           ROW_NUMBER() OVER (
                               ORDER BY a.labse_embedding <=> CAST(:emb AS vector)
                           ) AS rank_v
                    FROM articles a
                    WHERE a.labse_embedding IS NOT NULL AND {where_sql}
                    ORDER BY a.labse_embedding <=> CAST(:emb AS vector)
                    LIMIT :k
                ),
                fts_hits AS (
                    SELECT a.id,
                           ROW_NUMBER() OVER (
                               ORDER BY ts_rank(a.fts, plainto_tsquery('english', :q)) DESC
                           ) AS rank_f
                    FROM articles a
                    WHERE a.fts @@ plainto_tsquery('english', :q) AND {where_sql}
                    LIMIT :k
                ),
                fused AS (
                    SELECT id, COALESCE(1.0/(60 + rank_v), 0) + COALESCE(1.0/(60 + rank_f), 0) AS score
                    FROM vector_hits FULL OUTER JOIN fts_hits USING (id)
                )
                SELECT a.id::text AS article_id,
                       a.title,
                       COALESCE(a.lead_text_translated, a.lead_text_original) AS lead,
                       a.published_at,
                       s.name AS source_name,
                       s.domain AS source_domain
                FROM fused f
                JOIN articles a ON a.id = f.id
                JOIN sources s ON s.id = a.source_id
                ORDER BY f.score DESC
                LIMIT :final_k
            """
            params["final_k"] = k
        elif embedding is not None:
            # vector-only fallback
            params.update({"emb": str(embedding), "k": k})
            sql = f"""
                SELECT a.id::text AS article_id, a.title,
                       COALESCE(a.lead_text_translated, a.lead_text_original) AS lead,
                       a.published_at,
                       s.name AS source_name, s.domain AS source_domain
                FROM articles a
                JOIN sources s ON s.id = a.source_id
                WHERE a.labse_embedding IS NOT NULL AND {where_sql}
                ORDER BY a.labse_embedding <=> CAST(:emb AS vector)
                LIMIT :k
            """
        else:
            # no embedding (e.g. very short question) — recency-only
            params.update({"k": k})
            sql = f"""
                SELECT a.id::text AS article_id, a.title,
                       COALESCE(a.lead_text_translated, a.lead_text_original) AS lead,
                       a.published_at,
                       s.name AS source_name, s.domain AS source_domain
                FROM articles a
                JOIN sources s ON s.id = a.source_id
                WHERE {where_sql}
                ORDER BY a.published_at DESC NULLS LAST
                LIMIT :k
            """

        result = await db.execute(text(sql), params)
        rows = result.fetchall()

    return [
        {
            "article_id": r.article_id,
            "title": r.title,
            "lead": (r.lead or "")[:600],
            "source_name": r.source_name,
            "source_domain": r.source_domain,
            "published_at": r.published_at.isoformat() if r.published_at else None,
        }
        for r in rows
    ]


_FTS_CACHE: dict[str, bool] = {}


async def _articles_has_fts_column() -> bool:
    """Check once whether migration 046 has landed; cached in-process."""
    if "fts" in _FTS_CACHE:
        return _FTS_CACHE["fts"]
    async with get_db() as db:
        result = await db.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'articles' AND column_name = 'fts'"
            )
        )
        present = result.fetchone() is not None
    _FTS_CACHE["fts"] = present
    return present


def _build_context_block(articles: list[dict]) -> str:
    """Numbered evidence list for the prompt."""
    blocks: list[str] = []
    for i, a in enumerate(articles, start=1):
        blocks.append(
            f"[{i}] {a['title']} — {a['source_name']} "
            f"({a['published_at'] or 'unknown date'})\n"
            f"    {a['lead']}"
        )
    return "\n\n".join(blocks)


async def _ensure_chat_session(user_id: str, session_id: str | None) -> str:
    """Get-or-create a coverage-room session."""
    async with get_db() as db:
        if session_id:
            result = await db.execute(
                text(
                    "SELECT id::text FROM analyst_sessions "
                    "WHERE id = :sid AND user_id = :uid"
                ),
                {"sid": session_id, "uid": user_id},
            )
            row = result.fetchone()
            if row:
                return row[0]
        # create new
        result = await db.execute(
            text(
                "INSERT INTO analyst_sessions (user_id, room) "
                "VALUES (:uid, 'coverage') RETURNING id::text"
            ),
            {"uid": user_id},
        )
        new_id = result.fetchone()[0]
        await db.commit()
        return new_id


async def _persist_turn(
    session_id: str,
    user_id: str,
    question: str,
    answer: str,
    article_ids: list[str],
) -> None:
    # analyst_turns has no user_id column — ownership is via the session FK
    # to analyst_sessions(user_id). user_id arg here is kept for the
    # signature symmetry but no longer bound into the INSERT.
    _ = user_id  # silence unused-arg lint
    async with get_db() as db:
        await db.execute(
            text(
                """
                INSERT INTO analyst_turns (session_id, room, question, answer,
                                           evidence_count, retrieval_ms, confidence)
                VALUES (:sid, 'coverage', :q, :a, :ec, 0, 'MEDIUM')
                """
            ),
            {
                "sid": session_id,
                "q": question,
                "a": answer,
                "ec": len(article_ids),
            },
        )
        await db.commit()


@coverage_articles_router.post("/ask")
async def ask(
    body: AskRequest,
    request: Request,
    user: dict = Depends(get_current_principal),
) -> StreamingResponse:
    """SSE-streamed RAG answer scoped to the user's filter state."""
    _require_flag("FEATURE_ASK_BAR")

    user_id = user["id"]
    session_id = await _ensure_chat_session(user_id, body.session_id)

    async def generate():
        try:
            articles = await _retrieve_filtered_articles(
                body.question, body.filters, user_id, k=10
            )
            article_ids = [a["article_id"] for a in articles]

            # Open with metadata frame (lets frontend pre-render citations).
            yield (
                "event: meta\n"
                f"data: {json.dumps({'session_id': session_id, 'sources': articles})}\n\n"
            )

            if not articles:
                # Always frame as {"t": "..."} so the frontend's destructure
                # never gets undefined and renders the literal "undefined".
                empty_msg = "No articles match those filters."
                yield (
                    "event: token\n"
                    f"data: {json.dumps({'t': empty_msg})}\n\n"
                )
                yield "event: done\ndata: {}\n\n"
                await _persist_turn(
                    session_id, user_id, body.question, empty_msg, []
                )
                return

            context = _build_context_block(articles)
            user_prompt = (
                f"Question: {body.question}\n\n"
                f"Context (numbered articles):\n{context}\n\n"
                "Answer using only the context, citing sources inline as [N]."
            )

            collected: list[str] = []
            async for chunk in call_groq_stream(
                system=_ASK_SYSTEM_PROMPT,
                user=user_prompt,
                task_type="rag_response",
                model=QUALITY_MODEL,
            ):
                collected.append(chunk)
                if await request.is_disconnected():
                    return
                yield (
                    "event: token\n"
                    f"data: {json.dumps({'t': chunk})}\n\n"
                )

            answer = "".join(collected).strip()
            await _persist_turn(
                session_id, user_id, body.question, answer, article_ids
            )
            yield "event: done\ndata: {}\n\n"

        except GroqQuotaExhausted:
            yield (
                "event: error\n"
                "data: {\"message\": \"Service is rate-limited. Try again shortly.\"}\n\n"
            )
        except GroqCallFailed as exc:
            logger.warning("Ask Bar Groq error for uid=%s: %s",
                           _hash_uid(user_id), exc)
            yield (
                "event: error\n"
                "data: {\"message\": \"Could not generate answer.\"}\n\n"
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ask Bar unexpected error: %s", exc)
            # Surface a short version of the actual error so the frontend
            # can display something useful (truncated to avoid noise).
            err_text = (str(exc) or type(exc).__name__)[:160]
            yield (
                "event: error\n"
                f"data: {json.dumps({'message': f'Could not generate answer: {err_text}'})}\n\n"
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
        },
    )


@coverage_articles_router.get("/ask/sessions/{session_id}")
async def get_chat_session(
    session_id: UUID,
    user: dict = Depends(get_current_principal),
) -> dict:
    """Replay a coverage chat session (used to resume after page reload)."""
    _require_flag("FEATURE_ASK_BAR")
    # Ownership check via analyst_sessions FK — analyst_turns has no user_id
    # column, so we join to verify the session belongs to the caller.
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT t.id::text, t.question, t.answer, t.created_at
                FROM analyst_turns t
                JOIN analyst_sessions s ON s.id = t.session_id
                WHERE t.session_id = :sid
                  AND s.user_id = :uid
                  AND t.room = 'coverage'
                ORDER BY t.created_at ASC
                """
            ),
            {"sid": str(session_id), "uid": user["id"]},
        )
        turns = result.fetchall()
    return {
        "session_id": str(session_id),
        "turns": [
            {
                "id": t.id,
                "question": t.question,
                "answer": t.answer,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in turns
        ],
    }


# ── Top-5 stories ─────────────────────────────────────────────────────────────


# ── Inline translation helper (DEVELOPING fallback) ──────────────────────────


# Tiny in-process cache so repeated requests for the same article during
# its 60-min freshness window don't re-call Groq each time. Keyed by the
# original title string; value is (cached_at_unix, english_title|None).
_TITLE_TRANSLATE_CACHE: dict[str, tuple[float, str | None]] = {}
_TITLE_TRANSLATE_TTL = 1800.0  # 30 min


async def _translate_title_inline(title: str) -> str | None:
    """
    Best-effort translation of a single article headline to natural
    English. Returns None on Groq failure or when the input already
    looks like ASCII English (so we don't burn Groq budget on no-op
    calls). Caller is responsible for falling back to the original
    headline when this returns None.
    """
    import time as _time
    if not title or not title.strip():
        return None
    # Cheap check: if all chars are ASCII, assume already English.
    if all(ord(ch) < 128 for ch in title):
        return None
    cached = _TITLE_TRANSLATE_CACHE.get(title)
    now = _time.time()
    if cached and (now - cached[0] < _TITLE_TRANSLATE_TTL):
        return cached[1]
    try:
        from backend.nlp.groq_client import (
            FAST_MODEL,
            GroqCallFailed,
            GroqQuotaExhausted,
            call_groq,
        )
        out = await call_groq(
            system=(
                "Translate the news headline to natural English. Return "
                "only the translation, no quotes, no source attribution, "
                "no fluff. If the input is already English, return it "
                "lightly cleaned up."
            ),
            user=title,
            task_type="classification",
            model=FAST_MODEL,
        )
        result = out.strip().replace('"', "")[:240] or None
    except (GroqQuotaExhausted, GroqCallFailed):
        result = None
    except Exception:  # noqa: BLE001
        result = None
    _TITLE_TRANSLATE_CACHE[title] = (now, result)
    return result


# ── User-relevance helpers ───────────────────────────────────────────────────


async def _user_active_entity_names(user_id: str, db, days: int = 14) -> list[str]:
    """
    Pull the entity names this user has actually engaged with — derived
    from their HIGH-relevance (tier 1 or 2) user_article_relevance
    matches. Tier 3 (Background) is excluded because it's a loose
    catch-all that surfaces noise (e.g. unrelated international news
    matched on weak entity overlap). Used to filter Top-5 / Breaking /
    Quotes / Gaps so the page reflects THIS user's real interests.
    """
    result = await db.execute(
        text(
            """
            SELECT DISTINCT unnest(uar.matched_entity_names) AS name
            FROM user_article_relevance uar
            WHERE uar.user_id = :uid
              AND uar.matched_entity_names IS NOT NULL
              AND uar.relevance_tier IN (1, 2)
              AND uar.scored_at > NOW() - make_interval(days => :days)
            LIMIT 80
            """
        ),
        {"uid": user_id, "days": days},
    )
    return [r.name for r in result.fetchall() if r.name]


async def _user_active_entity_ids(user_id: str, db) -> list[str]:
    """Map the user's active entity names to entity_dictionary UUIDs."""
    names = await _user_active_entity_names(user_id, db)
    if not names:
        return []
    result = await db.execute(
        text(
            """
            SELECT id::text FROM entity_dictionary
            WHERE LOWER(canonical_name) = ANY(:names)
            """
        ),
        {"names": [n.lower() for n in names]},
    )
    return [r[0] for r in result.fetchall()]


@coverage_articles_router.get("/top-stories")
async def top_stories(
    days: int = Query(1, ge=1, le=14),
    user: dict = Depends(get_current_principal),
) -> dict:
    """
    Top-5 stories scoped to THIS user.

    Resolution order:
      1. Per-user cache row from today (`top_stories_daily` with this
         user_id). Contains the same 5 articles the refresh task
         selected for them, each with a fully-personalised Groq
         'why_matters' paragraph. Refresh runs every 6h.
      2. Live computation against `user_article_relevance` if the
         cache row doesn't exist yet (brand-new user, or refresh
         hasn't run). Each row falls back to `relevance_explanation`,
         which is short but user-specific. Eligibility for the cache
         comes on the next refresh cycle.

    We do NOT fall back to the global cache row — that defeats
    personalisation. Live computation is the safety net.
    """
    user_id = user["id"]

    async with get_db() as db:
        # Try per-user cache first.
        cache_result = await db.execute(
            text(
                """
                SELECT stories, generated_at
                FROM top_stories_daily
                WHERE date = CURRENT_DATE
                  AND user_id = CAST(:uid AS uuid)
                LIMIT 1
                """
            ),
            {"uid": user_id},
        )
        cache_row = cache_result.fetchone()
        if cache_row:
            stories_blob = cache_row.stories
            if isinstance(stories_blob, str):
                try:
                    stories_blob = json.loads(stories_blob)
                except json.JSONDecodeError:
                    stories_blob = None
            if isinstance(stories_blob, list) and stories_blob:
                return {
                    "stories": stories_blob,
                    "from_cache": True,
                    "personalised": True,
                    "generated_at": (
                        cache_row.generated_at.isoformat()
                        if cache_row.generated_at else None
                    ),
                }

        # Live fallback when no per-user cache row exists yet.
        # Lead + Notable only (tiers 1, 2). Tier 3 is a loose catch-all
        # that surfaces noise.
        live = await db.execute(
            text(
                """
                SELECT a.id::text AS article_id, a.title,
                       COALESCE(a.lead_text_translated, a.lead_text_original) AS lead,
                       s.name AS source_name, s.domain AS source_domain,
                       a.published_at, a.thumbnail_url,
                       uar.score_final, uar.relevance_explanation
                FROM user_article_relevance uar
                JOIN articles a ON a.id = uar.article_id
                JOIN sources s ON s.id = a.source_id
                WHERE uar.user_id = :uid
                  AND uar.relevance_tier IN (1, 2)
                  AND a.published_at > NOW() - make_interval(days => :days)
                  AND a.is_duplicate IS NOT TRUE
                ORDER BY uar.score_final DESC
                LIMIT 5
                """
            ),
            {"uid": user_id, "days": days},
        )
        rows = live.fetchall()

    return {
        "stories": [
            {
                "article_id": r.article_id,
                "title": r.title,
                "lead": (r.lead or "")[:600],
                "source_name": r.source_name,
                "source_domain": r.source_domain,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "thumbnail_url": r.thumbnail_url,
                "why_matters": r.relevance_explanation,
                "score": float(r.score_final),
            }
            for r in rows
        ],
        "from_cache": False,
        "personalised": True,
    }


# ── Related (semantic neighbours) ─────────────────────────────────────────────


@coverage_articles_router.get("/related/{article_id}")
async def related(
    article_id: UUID,
    k: int = Query(5, ge=1, le=20),
    _user: dict = Depends(get_current_principal),
) -> dict:
    """Top-k semantic neighbours of an article. Excludes self + dups."""
    async with get_db() as db:
        # Comma-vs-JOIN bug: `FROM articles a, src JOIN sources s` binds the
        # JOIN to `src`, not `articles a`. Use explicit CROSS JOIN instead so
        # the JOIN parses against `articles a` as intended.
        result = await db.execute(
            text(
                """
                WITH src AS (
                    SELECT labse_embedding FROM articles WHERE id = :aid
                )
                SELECT a.id::text AS article_id, a.title,
                       s.name AS source_name, s.domain AS source_domain,
                       a.published_at, a.thumbnail_url
                FROM articles a
                CROSS JOIN src
                JOIN sources s ON s.id = a.source_id
                WHERE a.id <> :aid
                  AND a.labse_embedding IS NOT NULL
                  AND a.is_duplicate IS NOT TRUE
                  AND src.labse_embedding IS NOT NULL
                ORDER BY a.labse_embedding <=> src.labse_embedding
                LIMIT :k
                """
            ),
            {"aid": str(article_id), "k": k},
        )
        rows = result.fetchall()

    return {
        "related": [
            {
                "article_id": r.article_id,
                "title": r.title,
                "source_name": r.source_name,
                "source_domain": r.source_domain,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "thumbnail_url": r.thumbnail_url,
            }
            for r in rows
        ]
    }


# ── Time travel ───────────────────────────────────────────────────────────────


@coverage_articles_router.get("/timetravel")
async def timetravel(
    offset_years: int = Query(1, ge=1, le=10),
    _user: dict = Depends(get_current_principal),
) -> dict:
    """Top 3 articles from the corresponding date N years ago + retrospective."""
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT a.id::text AS article_id, a.title,
                       COALESCE(a.lead_text_translated, a.lead_text_original) AS lead,
                       s.name AS source_name, a.published_at
                FROM articles a
                JOIN sources s ON s.id = a.source_id
                WHERE a.published_at::date = (CURRENT_DATE - make_interval(years => :y))
                  AND a.is_duplicate IS NOT TRUE
                ORDER BY a.source_tier ASC NULLS LAST, a.published_at DESC
                LIMIT 3
                """
            ),
            {"y": offset_years},
        )
        articles = result.fetchall()

    return {
        "offset_years": offset_years,
        "articles": [
            {
                "article_id": a.article_id,
                "title": a.title,
                "lead": (a.lead or "")[:300],
                "source_name": a.source_name,
                "published_at": a.published_at.isoformat() if a.published_at else None,
            }
            for a in articles
        ],
    }


# ── Quotes ────────────────────────────────────────────────────────────────────


@coverage_articles_router.get("/quotes")
async def quotes(
    speaker: str | None = Query(None, max_length=120),
    entity_id: UUID | None = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_principal),
) -> dict:
    """
    Quotes from article_quotes table.

    Default behaviour (no explicit speaker/entity filter): scope to
    quotes from articles in the user's relevance feed, OR by speakers
    that match the user's active entities. Falls back to global
    if user has no signal yet.
    """
    user_id = user["id"]
    async with get_db() as db:
        # Guard: if table doesn't exist yet (pre-043), return empty.
        check = await db.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'article_quotes'"
            )
        )
        if not check.fetchone():
            return {"quotes": []}

        clauses = ["q.extracted_at > NOW() - make_interval(days => :days)"]
        params: dict[str, Any] = {"days": days, "limit": limit}
        personalised = False

        if speaker:
            clauses.append("q.speaker_name ILIKE :speaker")
            params["speaker"] = f"%{speaker}%"
        elif entity_id:
            clauses.append("q.speaker_entity_id = :entity_id")
            params["entity_id"] = str(entity_id)
        else:
            # No explicit filter — scope to user's recent relevance feed.
            user_entity_ids = await _user_active_entity_ids(user_id, db)
            user_entity_names = await _user_active_entity_names(user_id, db)

            if not user_entity_ids and not user_entity_names:
                # User has no engagement signal yet — return empty rather
                # than fall through to global quotes (which would surface
                # speakers irrelevant to the user).
                return {"quotes": [], "personalised": True}

            personalised = True
            params["uid"] = user_id
            conds: list[str] = []
            if user_entity_ids:
                params["entity_ids"] = user_entity_ids
                conds.append("q.speaker_entity_id::text = ANY(:entity_ids)")
                conds.append(
                    "EXISTS (SELECT 1 FROM user_article_relevance uar "
                    "WHERE uar.user_id = :uid AND uar.article_id = q.article_id "
                    "AND uar.relevance_tier IN (1, 2))"
                )
            if user_entity_names:
                params["entity_names"] = [n.lower() for n in user_entity_names]
                conds.append("LOWER(q.speaker_name) = ANY(:entity_names)")
            clauses.append(f"({' OR '.join(conds)})")

        where_sql = " AND ".join(clauses)
        result = await db.execute(
            text(
                f"""
                SELECT q.id::text AS id, q.speaker_name, q.quote_text,
                       q.speaker_name_en, q.quote_text_en,
                       q.is_direct, q.extracted_at,
                       a.id::text AS article_id, a.title AS article_title,
                       s.name AS source_name, s.domain AS source_domain
                FROM article_quotes q
                JOIN articles a ON a.id = q.article_id
                JOIN sources s ON s.id = a.source_id
                WHERE {where_sql}
                ORDER BY q.extracted_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
        rows = result.fetchall()

    return {
        "quotes": [
            {
                "id": r.id,
                "speaker_name": r.speaker_name,
                "speaker_name_en": r.speaker_name_en,
                "quote_text": r.quote_text,
                "quote_text_en": r.quote_text_en,
                "is_direct": r.is_direct,
                "article_id": r.article_id,
                "article_title": r.article_title,
                "source_name": r.source_name,
                "source_domain": r.source_domain,
                "extracted_at": r.extracted_at.isoformat() if r.extracted_at else None,
            }
            for r in rows
        ]
    }


# ── Compare mode ──────────────────────────────────────────────────────────────


class CompareRequest(BaseModel):
    article_ids: list[UUID] = Field(min_length=2, max_length=3)


@coverage_articles_router.post("/compare")
async def compare(
    body: CompareRequest,
    _user: dict = Depends(get_current_principal),
) -> dict:
    """
    Side-by-side claim alignment via Groq-as-NLI.

    Caches result by sorted-article-ids hash 24h.
    """
    _require_flag("FEATURE_COMPARE")
    article_id_strs = sorted(str(a) for a in body.article_ids)
    cache_key = hashlib.sha256(",".join(article_id_strs).encode()).hexdigest()

    # Pull article texts.
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT a.id::text AS article_id, a.title,
                       COALESCE(a.lead_text_translated, a.lead_text_original) AS body,
                       s.name AS source_name, s.domain AS source_domain
                FROM articles a JOIN sources s ON s.id = a.source_id
                WHERE a.id::text = ANY(:ids)
                """
            ),
            {"ids": article_id_strs},
        )
        articles = [
            {
                "article_id": r.article_id,
                "title": r.title,
                "body": (r.body or "")[:1500],
                "source_name": r.source_name,
                "source_domain": r.source_domain,
            }
            for r in result.fetchall()
        ]

    if len(articles) < 2:
        raise HTTPException(404, "Articles not found")

    # Groq alignment — strict JSON schema.
    system = (
        "You are a claim-alignment analyst. Given 2 or 3 articles about the "
        "same event, return STRICT JSON with shape: "
        "{ synthesis: 'one paragraph (max 60 words)', "
        "  agreements: ['short factual statement', ...], "
        "  partials: ['short statement only one source mentions', ...], "
        "  disputes: [{a_says: '...', b_says: '...', topic: '...'}, ...] }. "
        "No prose outside JSON. No markdown fences."
    )
    user_prompt = "\n\n".join(
        f"ARTICLE {i+1} ({a['source_name']}):\nTitle: {a['title']}\n{a['body']}"
        for i, a in enumerate(articles)
    )

    try:
        raw = await call_groq(
            system=system,
            user=user_prompt,
            task_type="rag_response",
            model=QUALITY_MODEL,
            json_response=True,
        )
        analysis = json.loads(raw)
    except (GroqQuotaExhausted, GroqCallFailed, json.JSONDecodeError) as exc:
        logger.warning("Compare alignment failed: %s", exc)
        analysis = {
            "synthesis": "Could not align claims at this time.",
            "agreements": [],
            "partials": [],
            "disputes": [],
        }

    return {
        "cache_key": cache_key,
        "articles": articles,
        "analysis": analysis,
    }


# ── Contradictions inbox ──────────────────────────────────────────────────────


@coverage_articles_router.get("/contradictions")
async def contradictions(
    limit: int = Query(20, ge=1, le=50),
    _user: dict = Depends(get_current_principal),
) -> dict:
    _require_flag("FEATURE_CONTRADICTIONS")
    async with get_db() as db:
        check = await db.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'article_contradictions'"
            )
        )
        if not check.fetchone():
            return {"contradictions": []}

        result = await db.execute(
            text(
                """
                SELECT c.id::text AS id,
                       c.divergence_summary, c.confidence, c.detected_at,
                       ca.claim_text AS claim_a, cb.claim_text AS claim_b,
                       a_a.id::text AS article_a_id, a_a.title AS article_a_title,
                       sa.name AS source_a_name,
                       a_b.id::text AS article_b_id, a_b.title AS article_b_title,
                       sb.name AS source_b_name,
                       e.canonical_name AS entity_name
                FROM article_contradictions c
                JOIN article_claims ca ON ca.id = c.claim_a_id
                JOIN article_claims cb ON cb.id = c.claim_b_id
                JOIN articles a_a ON a_a.id = ca.article_id
                JOIN articles a_b ON a_b.id = cb.article_id
                JOIN sources sa ON sa.id = a_a.source_id
                JOIN sources sb ON sb.id = a_b.source_id
                LEFT JOIN entity_dictionary e ON e.id = c.entity_id
                WHERE c.is_resolved = FALSE
                ORDER BY c.detected_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        rows = result.fetchall()

    return {
        "contradictions": [
            {
                "id": r.id,
                "summary": r.divergence_summary,
                "confidence": r.confidence,
                "entity_name": r.entity_name,
                "detected_at": r.detected_at.isoformat() if r.detected_at else None,
                "side_a": {
                    "article_id": r.article_a_id,
                    "title": r.article_a_title,
                    "claim": r.claim_a,
                    "source_name": r.source_a_name,
                },
                "side_b": {
                    "article_id": r.article_b_id,
                    "title": r.article_b_title,
                    "claim": r.claim_b,
                    "source_name": r.source_b_name,
                },
            }
            for r in rows
        ]
    }


# ── Breaking ──────────────────────────────────────────────────────────────────


@coverage_articles_router.get("/breaking")
async def breaking(
    user: dict = Depends(get_current_principal),
) -> dict:
    """
    Per-user current breaking-news pick. Reads from user_breaking_now,
    which is refreshed every 60 minutes by
    tasks.coverage.pick_breaking_per_user. Returns the {clusters: [...]}
    shape the frontend BreakingBand consumes (single-element array).
    """
    _require_flag("FEATURE_BREAKING")
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT b.article_id::text                AS id,
                       b.selected_at                     AS selected_at,
                       b.source_tier                     AS source_tier,
                       b.near_dup_sources                AS sources_count,
                       b.candidates_count                AS candidates_count,
                       b.decision_path                   AS decision_path,
                       b.reason                          AS reason,
                       b.headline_one_line               AS headline_one_line,
                       b.why_for_user                    AS why_for_user,
                       a.title                           AS title,
                       a.lead_text_translated            AS title_en,
                       a.url                             AS url,
                       a.thumbnail_url                   AS thumbnail_url,
                       a.published_at                    AS published_at,
                       a.topic_category                  AS topic_category,
                       s.name                            AS source_name
                FROM user_breaking_now b
                JOIN articles a ON a.id = b.article_id
                LEFT JOIN sources s ON s.id = a.source_id
                WHERE b.user_id = :uid
                """
            ),
            {"uid": user["id"]},
        )
        row = result.first()

    if row is None:
        return {"clusters": [], "personalised": True}

    title = (row.title or "").strip()
    headline = (row.headline_one_line or "").strip() or title

    cluster = {
        "id":             row.id,
        "headline":       headline,
        "why_for_user":   row.why_for_user,
        "display_title":  None,
        "sources_count":  int(row.sources_count or 1),
        "kind":           "breaking" if row.source_tier == 1 else "developing",
        "published_at":   row.published_at.isoformat() if row.published_at else None,
        "created_at":     row.selected_at.isoformat() if row.selected_at else None,
        "source_name":    row.source_name,
        "url":            row.url,
        "thumbnail_url":  row.thumbnail_url,
        "topic_category": row.topic_category,
        "reason":         row.reason,
        "decision_path":  row.decision_path,
        "candidates_count": int(row.candidates_count or 0),
    }
    return {"clusters": [cluster], "personalised": True}




# ── Custom Cards ──────────────────────────────────────────────────────────────


class CardCreateRequest(BaseModel):
    label: str = Field(min_length=2, max_length=120)
    user_intent: str | None = Field(None, max_length=500)
    entity_refs: list[str] = Field(default_factory=list, max_length=10)
    topic_filters: list[str] = Field(default_factory=list)
    geo_filter: list[str] = Field(default_factory=list)


def _card_definition_hash(req: CardCreateRequest) -> str:
    payload = json.dumps(
        {
            "entities": sorted(req.entity_refs),
            "topics": sorted(req.topic_filters),
            "geo": sorted(req.geo_filter),
        },
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


_CARD_CAP_PER_USER = 5


@coverage_articles_router.post("/cards")
async def create_card(
    body: CardCreateRequest,
    user: dict = Depends(get_current_principal),
) -> dict:
    _require_flag("FEATURE_CARDS")
    user_id = user["id"]
    definition_hash = _card_definition_hash(body)

    async with get_db() as db:
        count_result = await db.execute(
            text("SELECT COUNT(*) FROM user_cards WHERE user_id = :uid"),
            {"uid": user_id},
        )
        count = count_result.scalar() or 0
        if count >= _CARD_CAP_PER_USER:
            raise HTTPException(
                400, f"Card limit reached ({_CARD_CAP_PER_USER}/user)"
            )

        result = await db.execute(
            text(
                """
                INSERT INTO user_cards
                  (user_id, label, definition_hash,
                   entity_refs, topic_filters, geo_filter, user_intent)
                VALUES (:uid, :label, :hash,
                        CAST(:ents AS JSONB), CAST(:tops AS JSONB),
                        CAST(:geo AS JSONB), :intent)
                RETURNING id::text, created_at
                """
            ),
            {
                "uid": user_id,
                "label": body.label,
                "hash": definition_hash,
                "ents": json.dumps(body.entity_refs),
                "tops": json.dumps(body.topic_filters),
                "geo": json.dumps(body.geo_filter),
                "intent": body.user_intent,
            },
        )
        row = result.fetchone()
        await db.commit()

    # Trigger refresh in background.
    try:
        from backend.celery_app import app as celery_app
        celery_app.send_task(
            "tasks.refresh_user_cards",
            kwargs={"only_definition_hash": definition_hash},
        )
        # Spawn 3-5 derivative sub-cards via Groq. Fires async — the
        # parent card returns immediately; the detail view will populate
        # its sub-card grid once tasks.spawn_sub_cards completes
        # (typically 8-20s) followed by per-child refresh.
        celery_app.send_task(
            "tasks.spawn_sub_cards",
            kwargs={"parent_card_id": row[0]},
        )
    except Exception:  # noqa: BLE001 — best-effort
        pass

    return {
        "id": row[0],
        "definition_hash": definition_hash,
        "created_at": row[1].isoformat() if row[1] else None,
    }


@coverage_articles_router.get("/cards")
async def list_cards(
    user: dict = Depends(get_current_principal),
) -> dict:
    _require_flag("FEATURE_CARDS")
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT c.id::text, c.label, c.definition_hash,
                       c.entity_refs, c.topic_filters, c.geo_filter,
                       c.user_intent, c.created_at, c.last_refreshed_at,
                       s.sections, s.citations, s.generated_at,
                       s.sample_size
                FROM user_cards c
                LEFT JOIN user_card_summaries s
                  ON s.definition_hash = c.definition_hash
                WHERE c.user_id = :uid
                  -- Only top-level (user-created) cards on the main row.
                  -- Spawned sub-cards are revealed via the full endpoint.
                  AND c.parent_card_id IS NULL
                ORDER BY c.created_at DESC
                """
            ),
            {"uid": user["id"]},
        )
        rows = result.fetchall()

    return {
        "cards": [
            {
                "id": r.id,
                "label": r.label,
                "definition_hash": r.definition_hash,
                "entity_refs": r.entity_refs,
                "topic_filters": r.topic_filters,
                "geo_filter": r.geo_filter,
                "user_intent": r.user_intent,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "last_refreshed_at": r.last_refreshed_at.isoformat()
                                     if r.last_refreshed_at else None,
                "summary": (
                    {
                        "sections": r.sections,
                        "citations": r.citations,
                        "generated_at": r.generated_at.isoformat()
                                        if r.generated_at else None,
                        "sample_size": r.sample_size,
                    }
                    if r.sections else None
                ),
            }
            for r in rows
        ]
    }


@coverage_articles_router.get("/cards/{card_id}/full")
async def card_full(
    card_id: UUID,
    user: dict = Depends(get_current_principal),
) -> dict:
    """
    Detail view payload: parent card + spawned sub-cards + each
    sub-card's summary + each sub-card's hydrated source articles.

    Sub-cards live in user_cards with parent_card_id pointing at the
    parent. We fetch parent + children in one round-trip, then in a
    second round-trip hydrate each unique citation article (by id) so
    sub-card panels can render thumbnail + headline + meta inline.
    """
    _require_flag("FEATURE_CARDS")
    user_id = user["id"]

    async with get_db() as db:
        # Parent + children in one query, joined to summaries by hash.
        rows_result = await db.execute(
            text(
                """
                SELECT c.id::text, c.label, c.definition_hash,
                       c.entity_refs, c.topic_filters, c.geo_filter,
                       c.user_intent, c.parent_card_id::text AS parent_id,
                       c.sub_card_angle,
                       c.created_at, c.last_refreshed_at,
                       c.sub_cards_spawned,
                       s.sections, s.citations, s.generated_at, s.sample_size
                FROM user_cards c
                LEFT JOIN user_card_summaries s
                  ON s.definition_hash = c.definition_hash
                WHERE c.user_id = :uid
                  AND (c.id = :cid OR c.parent_card_id = :cid)
                ORDER BY c.parent_card_id NULLS FIRST, c.created_at ASC
                """
            ),
            {"uid": user_id, "cid": str(card_id)},
        )
        rows = rows_result.fetchall()

        if not rows or rows[0].parent_id is not None:
            return {"error": "card not found"}

        parent_row = rows[0]
        children = [r for r in rows[1:]]

        # Hydrate up to 12 citations per sub-card (was 8). Detail panels
        # show 3 inline + the rest are accessible via "see all" expansion.
        all_article_ids: list[str] = []
        for r in [parent_row, *children]:
            cites = r.citations
            if isinstance(cites, str):
                try:
                    cites = json.loads(cites)
                except json.JSONDecodeError:
                    cites = []
            for c in (cites or [])[:12]:
                if c:
                    all_article_ids.append(str(c))

        article_meta: dict[str, dict[str, Any]] = {}
        if all_article_ids:
            arts = await db.execute(
                text(
                    """
                    SELECT a.id::text AS id, a.title,
                           COALESCE(a.lead_text_translated,
                                    a.lead_text_original) AS lead,
                           a.published_at, a.thumbnail_url,
                           a.geo_primary, a.language_detected,
                           s.name AS source_name, s.domain AS source_domain
                    FROM articles a
                    JOIN sources s ON s.id = a.source_id
                    WHERE a.id::text = ANY(:ids)
                    """
                ),
                {"ids": list(set(all_article_ids))},
            )
            for ar in arts.fetchall():
                article_meta[ar.id] = {
                    "article_id": ar.id,
                    "title": ar.title,
                    "lead": (ar.lead or "")[:300],
                    "source_name": ar.source_name,
                    "source_domain": ar.source_domain,
                    "thumbnail_url": ar.thumbnail_url,
                    "published_at": (
                        ar.published_at.isoformat()
                        if ar.published_at else None
                    ),
                    "geo_primary": ar.geo_primary,
                    "language_detected": ar.language_detected,
                }

    def _serialise(r: Any) -> dict[str, Any]:
        cites = r.citations
        if isinstance(cites, str):
            try:
                cites = json.loads(cites)
            except json.JSONDecodeError:
                cites = []
        articles = [
            article_meta[str(cid)]
            for cid in (cites or [])[:12]
            if str(cid) in article_meta
        ]
        return {
            "id": r.id,
            "label": r.label,
            "sub_card_angle": r.sub_card_angle,
            "user_intent": r.user_intent,
            "definition_hash": r.definition_hash,
            "entity_refs": r.entity_refs,
            "topic_filters": r.topic_filters,
            "geo_filter": r.geo_filter,
            "created_at": (
                r.created_at.isoformat() if r.created_at else None
            ),
            "last_refreshed_at": (
                r.last_refreshed_at.isoformat()
                if r.last_refreshed_at else None
            ),
            "summary": (
                {
                    "sections": r.sections,
                    "generated_at": (
                        r.generated_at.isoformat()
                        if r.generated_at else None
                    ),
                    "sample_size": r.sample_size,
                }
                if r.sections else None
            ),
            "articles": articles,
        }

    return {
        "parent": _serialise(parent_row),
        "sub_cards_spawned": bool(parent_row.sub_cards_spawned),
        "sub_cards": [_serialise(r) for r in children],
    }


@coverage_articles_router.delete("/cards/{card_id}")
async def delete_card(
    card_id: UUID,
    user: dict = Depends(get_current_principal),
) -> dict:
    _require_flag("FEATURE_CARDS")
    async with get_db() as db:
        result = await db.execute(
            text(
                "DELETE FROM user_cards "
                "WHERE id = :cid AND user_id = :uid RETURNING id"
            ),
            {"cid": str(card_id), "uid": user["id"]},
        )
        deleted = result.fetchone()
        await db.commit()
    if not deleted:
        raise HTTPException(404, "Card not found")
    return {"deleted": True}


# ── Watchlist ─────────────────────────────────────────────────────────────────


class WatchlistAddRequest(BaseModel):
    entity_id: UUID


@coverage_articles_router.get("/watchlist")
async def get_watchlist(
    user: dict = Depends(get_current_principal),
) -> dict:
    _require_flag("FEATURE_WATCHLIST")
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT w.entity_id::text, e.canonical_name, w.pinned_at,
                       w.last_seen_at,
                       (SELECT COUNT(*)
                        FROM articles a
                        WHERE a.entities_extracted @> CAST(:ent_filter AS JSONB)
                          AND a.collected_at > w.last_seen_at) AS new_mentions
                FROM user_watchlist w
                JOIN entity_dictionary e ON e.id = w.entity_id
                WHERE w.user_id = :uid
                ORDER BY w.pinned_at DESC
                """
            ),
            {
                "uid": user["id"],
                # Subquery probe per pin — for an MVP this is fine; a Celery
                # cron can precompute counts later.
                "ent_filter": json.dumps([]),
            },
        )
        rows = result.fetchall()

    return {
        "pins": [
            {
                "entity_id": r.entity_id,
                "name": r.canonical_name,
                "pinned_at": r.pinned_at.isoformat() if r.pinned_at else None,
                "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
                "new_mentions": int(r.new_mentions or 0),
            }
            for r in rows
        ]
    }


@coverage_articles_router.post("/watchlist")
async def pin_entity(
    body: WatchlistAddRequest,
    user: dict = Depends(get_current_principal),
) -> dict:
    _require_flag("FEATURE_WATCHLIST")
    async with get_db() as db:
        await db.execute(
            text(
                """
                INSERT INTO user_watchlist (user_id, entity_id)
                VALUES (:uid, :eid)
                ON CONFLICT (user_id, entity_id) DO NOTHING
                """
            ),
            {"uid": user["id"], "eid": str(body.entity_id)},
        )
        await db.commit()
    return {"pinned": True}


@coverage_articles_router.delete("/watchlist/{entity_id}")
async def unpin_entity(
    entity_id: UUID,
    user: dict = Depends(get_current_principal),
) -> dict:
    _require_flag("FEATURE_WATCHLIST")
    async with get_db() as db:
        await db.execute(
            text(
                "DELETE FROM user_watchlist "
                "WHERE user_id = :uid AND entity_id = :eid"
            ),
            {"uid": user["id"], "eid": str(entity_id)},
        )
        await db.commit()
    return {"unpinned": True}


@coverage_articles_router.post("/watchlist/seen")
async def mark_watchlist_seen(
    user: dict = Depends(get_current_principal),
) -> dict:
    """Mark all watchlist mentions as seen (resets badge)."""
    _require_flag("FEATURE_WATCHLIST")
    async with get_db() as db:
        await db.execute(
            text("UPDATE user_watchlist SET last_seen_at = NOW() WHERE user_id = :uid"),
            {"uid": user["id"]},
        )
        await db.commit()
    return {"ok": True}


# ── Notification rules / events ───────────────────────────────────────────────


class NotificationRuleCreateRequest(BaseModel):
    description: str = Field(min_length=4, max_length=300)


@coverage_articles_router.post("/notification-rules")
async def create_rule(
    body: NotificationRuleCreateRequest,
    user: dict = Depends(get_current_principal),
) -> dict:
    """Parse natural-language description into a structured predicate via Groq."""
    _require_flag("FEATURE_NOTIFICATIONS")

    system = (
        "Parse a user's notification rule into STRICT JSON with shape: "
        "{ entity_names: [...], topic: '...' or null, "
        "  source_tier_min: 1|2|3, keywords: [...] }. "
        "No prose outside JSON. No fences."
    )
    try:
        raw = await call_groq(
            system=system,
            user=body.description,
            task_type="classification",
            model=FAST_MODEL,
            json_response=True,
        )
        predicate = json.loads(raw)
    except (GroqQuotaExhausted, GroqCallFailed, json.JSONDecodeError):
        predicate = {"entity_names": [], "topic": None, "source_tier_min": 1, "keywords": []}

    async with get_db() as db:
        result = await db.execute(
            text(
                """
                INSERT INTO notification_rules (user_id, label, predicate, channels)
                VALUES (:uid, :label, CAST(:pred AS JSONB),
                        CAST('{"in_app": true}' AS JSONB))
                RETURNING id::text
                """
            ),
            {
                "uid": user["id"],
                "label": body.description,
                "pred": json.dumps(predicate),
            },
        )
        new_id = result.fetchone()[0]
        await db.commit()

    return {"id": new_id, "predicate": predicate}


@coverage_articles_router.get("/notification-rules")
async def list_rules(
    user: dict = Depends(get_current_principal),
) -> dict:
    _require_flag("FEATURE_NOTIFICATIONS")
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT id::text, label, predicate, channels, is_active, created_at
                FROM notification_rules
                WHERE user_id = :uid AND is_active = TRUE
                ORDER BY created_at DESC
                """
            ),
            {"uid": user["id"]},
        )
        rows = result.fetchall()
    return {
        "rules": [
            {
                "id": r.id,
                "label": r.label,
                "predicate": r.predicate,
                "channels": r.channels,
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@coverage_articles_router.delete("/notification-rules/{rule_id}")
async def delete_rule(
    rule_id: UUID,
    user: dict = Depends(get_current_principal),
) -> dict:
    _require_flag("FEATURE_NOTIFICATIONS")
    async with get_db() as db:
        await db.execute(
            text(
                "UPDATE notification_rules SET is_active = FALSE "
                "WHERE id = :rid AND user_id = :uid"
            ),
            {"rid": str(rule_id), "uid": user["id"]},
        )
        await db.commit()
    return {"deleted": True}


@coverage_articles_router.get("/notifications")
async def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_principal),
) -> dict:
    _require_flag("FEATURE_NOTIFICATIONS")
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT n.id::text, n.fired_at, n.is_read,
                       r.label AS rule_label,
                       a.id::text AS article_id, a.title,
                       s.name AS source_name
                FROM notification_events n
                JOIN notification_rules r ON r.id = n.rule_id
                JOIN articles a ON a.id = n.article_id
                JOIN sources s ON s.id = a.source_id
                WHERE n.user_id = :uid
                ORDER BY n.fired_at DESC
                LIMIT :limit
                """
            ),
            {"uid": user["id"], "limit": limit},
        )
        rows = result.fetchall()
    return {
        "notifications": [
            {
                "id": r.id,
                "fired_at": r.fired_at.isoformat() if r.fired_at else None,
                "is_read": r.is_read,
                "rule_label": r.rule_label,
                "article_id": r.article_id,
                "article_title": r.title,
                "source_name": r.source_name,
            }
            for r in rows
        ]
    }


# ── Coverage gaps ─────────────────────────────────────────────────────────────


@coverage_articles_router.get("/coverage-gaps")
async def coverage_gaps(
    user: dict = Depends(get_current_principal),
) -> dict:
    """
    Under-covered entities. Filters to entities the user actively cares
    about (per their relevance feed). Falls back to global top-10 if
    user has no signal.
    """
    user_id = user["id"]
    async with get_db() as db:
        check = await db.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'coverage_gaps_daily'"
            )
        )
        if not check.fetchone():
            return {"gaps": []}

        user_entity_ids = await _user_active_entity_ids(user_id, db)
        rows: list = []

        # User-relevance only. No global fallback — showing under-covered
        # entities the user doesn't track is noise, not signal.
        if user_entity_ids:
            per_user = await db.execute(
                text(
                    """
                    SELECT g.entity_id::text, e.canonical_name,
                           g.social_volume_7d, g.article_volume_7d,
                           g.ratio, g.summary, g.detected_at
                    FROM coverage_gaps_daily g
                    JOIN entity_dictionary e ON e.id = g.entity_id
                    WHERE g.detected_for_date = CURRENT_DATE
                      AND g.entity_id::text = ANY(:eids)
                    ORDER BY g.ratio DESC
                    LIMIT 10
                    """
                ),
                {"eids": user_entity_ids},
            )
            rows = per_user.fetchall()

    return {
        "personalised": True,
        "gaps": [
            {
                "entity_id": r.entity_id,
                "name": r.canonical_name,
                "social_volume_7d": r.social_volume_7d,
                "article_volume_7d": r.article_volume_7d,
                "ratio": r.ratio,
                "summary": r.summary,
            }
            for r in rows
        ],
    }
