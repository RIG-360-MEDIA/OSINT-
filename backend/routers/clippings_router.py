"""
Cutting Room API — newspaper clippings feed (P16).

Endpoints:
    GET  /api/clippings/feed            — paginated clipping feed
    GET  /api/clippings/papers          — newsstand mastheads (active papers)
    GET  /api/clippings/{id}/image      — base64 PNG of rendered clipping
    GET  /api/clippings/{id}/full       — full clipping (both languages)
    GET  /api/newspapers/{id}/pdf       — stream the day's PDF on demand
"""

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user, require_page
from backend.collectors.newspaper_collector import (
    get_pdf_url_from_careerswave,
)
from backend.database import get_db

logger = logging.getLogger(__name__)

clippings_router = APIRouter(
    prefix="/api/clippings",
    tags=["clippings"],
    dependencies=[Depends(require_page("cuttings"))],
)

newspapers_router = APIRouter(
    prefix="/api/newspapers",
    tags=["newspapers"],
    dependencies=[Depends(require_page("cuttings"))],
)

# How long a cached Drive URL stays fresh before we re-resolve it.
_PDF_URL_TTL = timedelta(hours=6)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _parse_feed_cursor(raw: str) -> tuple[float, str, str] | None:
    """
    DB-1: composite cursor for the feed.

    Encoded as "<relevance_score>|<collected_at_iso>|<clipping_uuid>" so
    that page-2 onward can apply a tuple comparison
    `(rs, ca, id) < (cur_rs, cur_ca, cur_id)` matching the same sort key
    the ORDER BY uses (relevance_score DESC, collected_at DESC, id).

    Returns (rs, ca_iso, id_str) or None for empty/malformed input.
    """
    if not raw:
        return None
    try:
        score_s, ca_s, id_s = raw.split("|", 2)
        return float(score_s), ca_s, id_s
    except (ValueError, AttributeError):
        return None


@clippings_router.get("/feed")
async def get_clippings_feed(
    newspaper: str = Query(default="all"),
    language: str = Query(default="all"),
    days: int = Query(default=7),
    limit: int = Query(default=20, ge=1, le=200),
    cursor: str = Query(default=""),
    user: dict = Depends(get_current_user),
):
    """Return recent relevant clippings grouped-ready for display.

    SEC-1: results are filtered to clippings whose `entities_extracted`
    overlaps the calling user's `user_entities` set. Users with zero
    entities configured fall back to the global view (graceful default).

    DB-1: cursor is composite `(relevance_score, collected_at, id)` so
    pagination matches the ORDER BY key and never skips/duplicates rows.
    """
    cur = _parse_feed_cursor(cursor)
    # asyncpg validates bind types eagerly: it wants real datetime / UUID
    # instances, not ISO strings — even when the surrounding SQL has an
    # explicit CAST. Build native sentinels for page-1 ("infinity" tuple)
    # and parsed values for page-2+.
    sentinel_ca = datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    sentinel_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    if cur is not None:
        cur_score_v: float = cur[0]
        try:
            cur_ca_v: datetime = datetime.fromisoformat(cur[1])
        except ValueError:
            cur_ca_v = sentinel_ca
        try:
            cur_id_v: UUID = UUID(cur[2])
        except (ValueError, AttributeError):
            cur_id_v = sentinel_id
    else:
        cur_score_v = 1e9
        cur_ca_v = sentinel_ca
        cur_id_v = sentinel_id

    async with get_db() as db:
        params: dict = {
            "days": days,
            "limit": limit + 1,
            "paper": newspaper,
            "lang": language,
            "user_id": user["id"],
            "cur_score": cur_score_v,
            "cur_ca": cur_ca_v,
            "cur_id": cur_id_v,
        }

        # SEC-1 — JOIN against the user's entity set with graceful fallback.
        # Users with zero entities configured see everything (current behavior
        # is preserved); users with entities see only clippings whose
        # `entities_extracted` array contains at least one matching name.
        result = await db.execute(
            text(
                """
                SELECT
                    nc.id::text AS clipping_id,
                    nc.newspaper_name,
                    nc.newspaper_language,
                    nc.edition_date,
                    nc.page_number,
                    nc.headline,
                    nc.headline_translated,
                    LEFT(nc.article_text, 300) AS text_preview,
                    LEFT(nc.article_text_translated, 300)
                        AS translated_preview,
                    (nc.clipping_image_b64 IS NOT NULL) AS has_image,
                    nc.relevance_score,
                    nc.relevance_explanation,
                    nc.collected_at
                FROM newspaper_clippings nc
                WHERE nc.collected_at > NOW() - (:days * INTERVAL '1 day')
                  AND nc.relevance_score >= 0.3
                  AND (:paper = 'all' OR nc.newspaper_name = :paper)
                  AND (:lang  = 'all' OR nc.newspaper_language = :lang)
                  AND (nc.relevance_score, nc.collected_at, nc.id)
                       < (:cur_score, CAST(:cur_ca AS timestamptz), CAST(:cur_id AS uuid))
                  AND (
                    NOT EXISTS (
                      SELECT 1 FROM user_entities WHERE user_id = CAST(:user_id AS uuid)
                    )
                    OR EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements(nc.entities_extracted) AS ent
                      JOIN user_entities ue
                        ON LOWER(ue.canonical_name) = LOWER(ent->>'name')
                       AND ue.user_id = CAST(:user_id AS uuid)
                    )
                  )
                ORDER BY nc.relevance_score DESC, nc.collected_at DESC, nc.id
                LIMIT :limit
                """
            ),
            params,
        )
        clippings = result.fetchall()
        has_more = len(clippings) > limit
        clippings = clippings[:limit]

        next_cursor: str | None = None
        if has_more and clippings:
            last = clippings[-1]
            next_cursor = (
                f"{last.relevance_score}|{last.collected_at.isoformat()}|"
                f"{last.clipping_id}"
            )

        # CODE-1: removed a second unbounded GROUP BY query that aggregated
        # papers across the last `days` window on every /feed call. The
        # frontend never consumed it (Newsstand uses the dedicated /papers
        # endpoint), and at scale this was a full-table scan per request.
        return {
            "clippings": [
                {
                    "clipping_id": c.clipping_id,
                    "newspaper_name": c.newspaper_name,
                    "newspaper_language": c.newspaper_language,
                    "edition_date": (
                        c.edition_date.isoformat()
                        if c.edition_date
                        else None
                    ),
                    "page_number": c.page_number,
                    "headline": c.headline,
                    "headline_translated": c.headline_translated,
                    "text_preview": c.text_preview,
                    "translated_preview": c.translated_preview,
                    "has_image": c.has_image,
                    "relevance_score": c.relevance_score,
                    "relevance_explanation": c.relevance_explanation,
                    "collected_at": c.collected_at.isoformat(),
                }
                for c in clippings
            ],
            "has_more": has_more,
            "next_cursor": next_cursor,
        }


@clippings_router.get("/papers")
async def list_active_papers(
    days: int = Query(default=7, ge=1, le=30),
    user: dict = Depends(get_current_user),
):
    """
    List newspapers visible on the Newsstand. A paper appears if EITHER:
        - it has at least one relevant clipping in the last `days`
          *that matches the calling user's entity set* (SEC-1), OR
        - we have a resolvable PDF edition for today (so the user can still
          click through and read the full broadcast even when entity
          matching produced zero hits).

    Sorted clip_count DESC, then name ASC. Drives /cuttings.

    SEC-1: clip_count is the user-filtered count. Users with zero entities
    configured fall back to the global behavior (no entity filter applied).
    """
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT
                    ns.id::text                                  AS newspaper_id,
                    ns.name                                      AS name,
                    ns.language                                  AS language,
                    COALESCE(
                        MAX(nc.edition_date),
                        MAX(ne.edition_date)
                    )                                            AS edition_date,
                    COUNT(nc.id)                                 AS clip_count,
                    BOOL_OR(ne.pdf_url IS NOT NULL)              AS pdf_available
                FROM newspaper_sources ns
                LEFT JOIN newspaper_editions ne
                       ON ne.newspaper_id = ns.id
                      AND ne.edition_date = CURRENT_DATE
                LEFT JOIN newspaper_clippings nc
                       ON nc.newspaper_id = ns.id
                      AND nc.collected_at > NOW() - (:days * INTERVAL '1 day')
                      AND nc.relevance_score >= 0.3
                      AND (
                        NOT EXISTS (
                          SELECT 1 FROM user_entities WHERE user_id = CAST(:user_id AS uuid)
                        )
                        OR EXISTS (
                          SELECT 1
                          FROM jsonb_array_elements(nc.entities_extracted) AS ent
                          JOIN user_entities ue
                            ON LOWER(ue.canonical_name) = LOWER(ent->>'name')
                           AND ue.user_id = CAST(:user_id AS uuid)
                        )
                      )
                WHERE ns.is_active = TRUE
                GROUP BY ns.id, ns.name, ns.language
                HAVING COUNT(nc.id) > 0 OR BOOL_OR(ne.pdf_url IS NOT NULL)
                ORDER BY clip_count DESC, name ASC
                """
            ),
            {"days": days, "user_id": user["id"]},
        )
        rows = result.fetchall()
        return {
            "papers": [
                {
                    "newspaper_id": r.newspaper_id,
                    "name": r.name,
                    "language": r.language,
                    "edition_date": (
                        r.edition_date.isoformat() if r.edition_date else None
                    ),
                    "clip_count": int(r.clip_count),
                    "pdf_available": bool(r.pdf_available),
                }
                for r in rows
            ]
        }


@clippings_router.get("/{clipping_id}/image")
async def get_clipping_image(
    clipping_id: UUID,
    user: dict = Depends(get_current_user),
):
    """Return the base64 PNG of the rendered clipping.

    SEC-1: row-level access check. Users with zero entities configured
    fall back to global access (graceful default). Otherwise the row
    must overlap their entity set.
    """
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT clipping_image_b64
                FROM newspaper_clippings nc
                WHERE nc.id = CAST(:cid AS uuid)
                  AND (
                    NOT EXISTS (
                      SELECT 1 FROM user_entities WHERE user_id = CAST(:user_id AS uuid)
                    )
                    OR EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements(nc.entities_extracted) AS ent
                      JOIN user_entities ue
                        ON LOWER(ue.canonical_name) = LOWER(ent->>'name')
                       AND ue.user_id = CAST(:user_id AS uuid)
                    )
                  )
                """
            ),
            {"cid": str(clipping_id), "user_id": user["id"]},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(
                status_code=404, detail="Clipping not found"
            )
        return {"image_b64": row.clipping_image_b64}


@clippings_router.get("/{clipping_id}/full")
async def get_clipping_full(
    clipping_id: UUID,
    user: dict = Depends(get_current_user),
):
    """Return full clipping text (original + translated).

    SEC-1: same row-level entity-overlap check as /image.
    """
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT
                    id,
                    headline,
                    headline_translated,
                    article_text,
                    article_text_translated,
                    newspaper_name,
                    edition_date
                FROM newspaper_clippings nc
                WHERE nc.id = CAST(:cid AS uuid)
                  AND (
                    NOT EXISTS (
                      SELECT 1 FROM user_entities WHERE user_id = CAST(:user_id AS uuid)
                    )
                    OR EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements(nc.entities_extracted) AS ent
                      JOIN user_entities ue
                        ON LOWER(ue.canonical_name) = LOWER(ent->>'name')
                       AND ue.user_id = CAST(:user_id AS uuid)
                    )
                  )
                """
            ),
            {"cid": str(clipping_id), "user_id": user["id"]},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(
                status_code=404, detail="Clipping not found"
            )
        return {
            "clipping_id": str(row.id),
            "headline": row.headline,
            "headline_translated": row.headline_translated,
            "article_text": row.article_text,
            "article_text_translated": row.article_text_translated,
            "newspaper_name": row.newspaper_name,
            "edition_date": (
                row.edition_date.isoformat()
                if row.edition_date
                else None
            ),
        }


# ─────────────────────────────────────────────────────────────────────────
# /api/newspapers/{id}/pdf — re-fetch the day's edition on demand.
# ─────────────────────────────────────────────────────────────────────────


async def _resolve_edition_pdf_url(
    db, newspaper_id: str, edition_date: date,
) -> str | None:
    """
    Return a usable Drive URL for the requested edition.

    Uses newspaper_editions cache when fresh; otherwise re-resolves via
    careerswave and upserts. Returns None if no edition can be located.
    """
    cached = await db.execute(
        text(
            """
            SELECT pdf_url, fetched_at
            FROM newspaper_editions
            WHERE newspaper_id = CAST(:nid AS uuid) AND edition_date = :ed
            """
        ),
        {"nid": newspaper_id, "ed": edition_date},
    )
    row = cached.fetchone()
    if row and (datetime.now(timezone.utc) - row.fetched_at) < _PDF_URL_TTL:
        return row.pdf_url

    src = await db.execute(
        text(
            """
            SELECT careerswave_url
            FROM newspaper_sources
            WHERE id = CAST(:nid AS uuid) AND is_active = TRUE
            """
        ),
        {"nid": newspaper_id},
    )
    src_row = src.fetchone()
    if not src_row or not src_row.careerswave_url:
        return None

    pdf_url = await get_pdf_url_from_careerswave(src_row.careerswave_url)
    if not pdf_url:
        return None

    await db.execute(
        text(
            """
            INSERT INTO newspaper_editions (newspaper_id, edition_date, pdf_url, fetched_at)
            VALUES (CAST(:nid AS uuid), :ed, :url, NOW())
            ON CONFLICT (newspaper_id, edition_date)
            DO UPDATE SET pdf_url = EXCLUDED.pdf_url, fetched_at = NOW()
            """
        ),
        {"nid": newspaper_id, "ed": edition_date, "url": pdf_url},
    )
    await db.commit()
    return pdf_url


@newspapers_router.get("/{newspaper_id}/pdf")
async def stream_edition_pdf(
    newspaper_id: UUID,
    date_str: str = Query(default="", alias="date"),
    user: dict = Depends(get_current_user),
):
    """Stream the requested newspaper edition PDF (re-fetched on demand)."""
    if date_str:
        try:
            ed_date = date.fromisoformat(date_str)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="date must be YYYY-MM-DD"
            ) from exc
    else:
        ed_date = date.today()

    async with get_db() as db:
        pdf_url = await _resolve_edition_pdf_url(db, str(newspaper_id), ed_date)

    if not pdf_url:
        raise HTTPException(
            status_code=404,
            detail="No edition available for this newspaper on this date",
        )

    # RUN-2: validate the upstream actually returns a PDF, not Drive's
    # "can't scan for viruses, click to download" HTML interstitial. The
    # symptom previously was a 2.4 KB body labelled application/pdf that
    # was actually HTML — viewers rendered nothing.
    async def iter_pdf():
        async with httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            async with client.stream("GET", pdf_url) as upstream:
                if upstream.status_code != 200:
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            f"Upstream PDF host returned {upstream.status_code}"
                        ),
                    )
                first_chunk = True
                async for chunk in upstream.aiter_bytes(chunk_size=65536):
                    if first_chunk:
                        first_chunk = False
                        if not chunk.startswith(b"%PDF-"):
                            logger.warning(
                                "stream_edition_pdf: upstream returned non-PDF "
                                "for newspaper_id=%s date=%s (first 32 bytes: %r)",
                                newspaper_id, ed_date, chunk[:32],
                            )
                            raise HTTPException(
                                status_code=502,
                                detail=(
                                    "Upstream returned non-PDF content "
                                    "(likely Drive interstitial). Please retry."
                                ),
                            )
                    yield chunk

    return StreamingResponse(
        iter_pdf(),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )
