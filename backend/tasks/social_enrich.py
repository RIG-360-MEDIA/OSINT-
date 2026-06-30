"""
Celery task: social post substrate enrichment.

A social post rides the same substrate path as articles/clippings/clips: ONE
structured-JSON call (GROQ_SYS_SOCIAL) emits sentiment/emotion/entities/stances/
claims/quotes/locations/events, written to social_post_* child tables. Post +
claim LaBSE embeddings and topic are the separate local steps. Entity resolution
is the social_post_entity_mentions matview (no per-item resolver call).

Routing: the `social` queue. Extraction goes to CLOUD via call_groq (pillar
"social" → Cerebras primary / Groq overflow once wired); embeddings are local.

Two entry points (mirror clipping_enrich):
  * enrich_social_post(post_id)   — per-item, enqueued at insert time
  * drain_pending_social(limit)   — periodic catch-up safety net

Lifecycle: substrate_status pending → processing → ok | extract_failed | junk
           retweets/dupes → skipped (no extraction; same content).
extraction_version = 3 on success.

The 4 code-enforced rules from the prompt bake-off live in
backend.nlp.social_prompt.normalize_extraction (author handle, summary discipline,
intensity/date defaults) and are applied here before persist.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from typing import Any

from backend.celery_app import app

logger = logging.getLogger(__name__)

_EXTRACTION_VERSION = 3
_MIN_TEXT_CHARS = 25          # below this a post is too sparse to extract from
_SUMMARY_MIN_CHARS = 300      # summary discipline (also enforced in normalize)
_MAX_TOK = 2000
_PILLAR = "social"
_TASK_TYPE = "social_extraction"

_LINK_ONLY = re.compile(r"^\s*(https?://\S+\s*)+$", re.IGNORECASE)


# ── Celery entry points ───────────────────────────────────────────────────────

@app.task(name="tasks.enrich_social_post", queue="social")
def enrich_social_post(post_id: int) -> dict:
    """Enrich a single social post by id (enqueued per-row at insert time)."""
    return asyncio.run(_enrich_one_by_id(int(post_id)))


@app.task(name="tasks.drain_pending_social", queue="social")
def drain_pending_social(limit: int = 50) -> dict:
    """Periodic catch-up: enrich up to `limit` pending social posts."""
    return asyncio.run(_drain(limit))


# ── Async orchestration ───────────────────────────────────────────────────────

async def _drain(limit: int) -> dict:
    from sqlalchemy import text
    from backend.database import get_db

    done = failed = skipped = 0
    for _ in range(max(1, limit)):
        async with get_db() as db:
            row = (
                await db.execute(
                    text(
                        """
                        UPDATE social_posts
                           SET substrate_status = 'processing'
                         WHERE id = (
                            SELECT id FROM social_posts
                             WHERE substrate_status = 'pending'
                             ORDER BY collected_at
                             FOR UPDATE SKIP LOCKED
                             LIMIT 1
                         )
                        RETURNING id
                        """
                    )
                )
            ).fetchone()
            if not row:
                await db.commit()
                break
            pid = int(row.id)
            await db.commit()
        outcome = await _enrich_claimed(pid)
        if outcome == "ok":
            done += 1
        elif outcome == "skipped":
            skipped += 1
        else:
            failed += 1
    logger.info("drain_pending_social: %d ok, %d skipped, %d failed", done, skipped, failed)
    return {"enriched": done, "skipped": skipped, "failed": failed}


async def _enrich_one_by_id(post_id: int) -> dict:
    from sqlalchemy import text
    from backend.database import get_db

    async with get_db() as db:
        row = (
            await db.execute(
                text(
                    """
                    UPDATE social_posts
                       SET substrate_status = 'processing'
                     WHERE id = :id
                       AND substrate_status IN ('pending', 'extract_failed')
                    RETURNING id
                    """
                ),
                {"id": post_id},
            )
        ).fetchone()
        await db.commit()
    if not row:
        return {"post_id": post_id, "status": "skipped"}
    outcome = await _enrich_claimed(post_id)
    return {"post_id": post_id, "status": outcome}


async def _enrich_claimed(post_id: int) -> str:
    """Run full substrate enrichment on an already-claimed post. Returns
    'ok' | 'skipped' | 'failed'."""
    from sqlalchemy import text
    from backend.database import get_db
    from backend.nlp.social_prompt import (
        GROQ_SYS_SOCIAL,
        build_user_message,
        normalize_extraction,
    )

    async with get_db() as db:
        post = (
            await db.execute(
                text(
                    """
                    SELECT sp.id, sp.post_text, sp.posted_at, sp.is_retweet,
                           COALESCE(a.username, '') AS author_handle
                    FROM social_posts sp
                    LEFT JOIN social_authors a ON a.id = sp.author_id
                    WHERE sp.id = :id
                    """
                ),
                {"id": post_id},
            )
        ).fetchone()

    if not post:
        return "failed"

    text_body = (post.post_text or "").strip()
    author_handle = (post.author_handle or "").strip() or "poster"

    # Skip retweets/dupes (same content) and junk (too sparse / link-only).
    if post.is_retweet:
        await _mark_status(post_id, "skipped")
        return "skipped"
    if len(text_body) < _MIN_TEXT_CHARS or _LINK_ONLY.match(text_body):
        await _mark_status(post_id, "junk")
        return "skipped"

    posted_iso = post.posted_at.isoformat() if post.posted_at else None
    user_msg = build_user_message(posted_iso, text_body[:4000])

    parsed = await _call_with_retry(GROQ_SYS_SOCIAL, user_msg)
    if parsed is None:
        await _mark_status(post_id, "extract_failed")
        return "failed"

    # Apply the 4 code-enforced rules (author handle, summary discipline, defaults).
    parsed = normalize_extraction(parsed, author_handle=author_handle, post_text=text_body)
    _normalize_arrays(parsed)

    # Post embedding (local LaBSE).
    embedding = _embed(text_body)
    # Topic (reuse the shared taxonomy).
    topic_fine, topic_coarse = await _classify_topic(parsed, text_body)

    try:
        await _persist(post_id, parsed, topic_fine, topic_coarse, embedding)
    except Exception:
        logger.exception("social enrich persist failed for %s", post_id)
        await _mark_status(post_id, "extract_failed")
        return "failed"
    return "ok"


# ── LLM call with 2-attempt retry + robust parse ──────────────────────────────

async def _call_with_retry(sys_prompt: str, user_msg: str) -> dict[str, Any] | None:
    from backend.nlp.groq_client import call_groq, GroqCallFailed, GroqQuotaExhausted

    for attempt in range(2):
        try:
            raw = await call_groq(
                system=sys_prompt,
                user=user_msg,
                pillar=_PILLAR,
                task_type=_TASK_TYPE,
                json_response=True,
                max_tokens_override=_MAX_TOK,
            )
        except (GroqCallFailed, GroqQuotaExhausted) as exc:
            logger.warning("social enrich: groq failed (attempt %d): %s", attempt + 1, exc)
            if attempt == 0:
                continue
            return None

        if isinstance(raw, dict):
            return raw
        parsed = _loads_lenient(raw)
        if parsed is not None:
            return parsed
        if attempt == 0:
            continue
        logger.warning("social enrich: json parse failed after 2 attempts; raw[:200]=%r",
                       (raw or "")[:200] if isinstance(raw, str) else raw)
    return None


def _loads_lenient(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        pass
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    first, last = s.find("{"), s.rfind("}")
    if first >= 0 and last > first:
        try:
            return json.loads(s[first:last + 1])
        except (TypeError, ValueError):
            return None
    return None


def _normalize_arrays(parsed: dict[str, Any]) -> None:
    for k in ("entities", "directed_stances", "claims", "quotes",
              "locations", "event_times", "hashtags", "mentions"):
        if not isinstance(parsed.get(k), list):
            parsed[k] = []


def _embed(text_body: str) -> list[float] | None:
    from backend.nlp.nlp_embedding import generate_embedding
    t = (text_body or "").strip()[:512]
    if not t:
        return None
    try:
        return generate_embedding(t)
    except Exception as exc:  # noqa: BLE001
        logger.warning("social embed failed: %s", exc)
        return None


async def _classify_topic(parsed: dict[str, Any], text_body: str) -> tuple[str | None, str | None]:
    from backend.nlp.nlp_topic import classify_topic_fine, coarse_from_fine
    lead = parsed.get("primary_subject") or text_body[:300]
    try:
        fine = await classify_topic_fine(lead, None)
        return fine, coarse_from_fine(fine)
    except Exception as exc:  # noqa: BLE001
        logger.warning("social topic classify failed: %s", exc)
        return parsed.get("topic_category"), None


# ── Persistence ───────────────────────────────────────────────────────────────

async def _persist(
    post_id: int,
    parsed: dict[str, Any],
    topic_fine: str | None,
    topic_coarse: str | None,
    embedding: list[float] | None,
) -> None:
    from sqlalchemy import text
    from backend.database import get_db

    entities = parsed.get("entities", [])
    locations = parsed.get("locations", [])

    async with get_db() as db:
        await db.execute(
            text(
                """
                UPDATE social_posts SET
                    lang                = COALESCE(:lng, lang),
                    language_confidence = :lc,
                    sentiment           = :sent,
                    sentiment_score     = :sscore,
                    emotion             = :emo,
                    toxicity            = :tox,
                    topic_category      = COALESCE(:tc, :tcat),
                    primary_subject     = :ps,
                    summary             = :summ,
                    entities_extracted  = CAST(:ents AS JSONB),
                    labse_embedding     = :emb,
                    extraction_tier     = 'full',
                    extraction_confidence = :ec,
                    substrate_status    = 'ok',
                    extraction_version  = :ev,
                    enriched_at         = NOW()
                WHERE id = :id
                """
            ),
            {
                "id": post_id,
                "lng": (parsed.get("language") or None),
                "lc": _as_float(parsed.get("language_confidence")),
                "sent": (parsed.get("sentiment") or None),
                "sscore": _as_float(parsed.get("sentiment_score")),
                "emo": (parsed.get("emotion") or None),
                "tox": _as_float(parsed.get("toxicity")),
                "tc": topic_coarse,
                "tcat": (parsed.get("topic_category") or None),
                "ps": (parsed.get("primary_subject") or None),
                "summ": (parsed.get("summary") or None),
                "ents": _json_dump(entities),
                "emb": (str(embedding) if embedding else None),
                "ec": _as_float(parsed.get("extraction_confidence")) or 0.8,
                "ev": _EXTRACTION_VERSION,
            },
        )
        await _persist_claims(db, post_id, parsed.get("claims", []))
        await _persist_quotes(db, post_id, parsed.get("quotes", []))
        await _persist_stances(db, post_id, parsed.get("directed_stances", []))
        await _persist_locations(db, post_id, locations)
        await _persist_events(db, post_id, parsed.get("event_times", []))
        await _persist_hashtags(db, post_id, parsed.get("hashtags", []))
        await _persist_mentions(db, post_id, parsed.get("mentions", []))
        await db.commit()


def _as_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _json_dump(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return "[]"


def _fingerprint(s: str) -> str:
    """Normalized hash for near-dup / astroturf clustering of claims."""
    norm = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (s or "").lower())).strip()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16] if norm else ""


async def _mark_status(post_id: int, status: str) -> None:
    from sqlalchemy import text
    from backend.database import get_db

    async with get_db() as db:
        await db.execute(
            text(
                "UPDATE social_posts SET substrate_status = :s, "
                "extraction_version = :ev, enriched_at = NOW() WHERE id = :id"
            ),
            {
                "s": status,
                "ev": _EXTRACTION_VERSION if status in ("ok", "junk", "skipped") else 0,
                "id": post_id,
            },
        )
        await db.commit()


# ── Child-table persisters (DELETE-then-INSERT; FK = post_id) ──────────────────

async def _persist_claims(db, pid: int, claims: list[dict[str, Any]]) -> None:
    from sqlalchemy import text
    from backend.nlp.nlp_embedding import generate_embedding

    await db.execute(text("DELETE FROM social_post_claims WHERE post_id = :id"), {"id": pid})
    for c in claims[:8]:
        if not isinstance(c, dict):
            continue
        claim_text = (c.get("text") or "").strip()
        if not claim_text:
            continue
        claim_en = (c.get("text_en") or "").strip() or None
        # embed the English form (or original) for corroboration / counter-narrative
        emb = None
        try:
            emb = generate_embedding((claim_en or claim_text)[:512])
        except Exception:  # noqa: BLE001
            emb = None
        await db.execute(
            text(
                """
                INSERT INTO social_post_claims
                  (post_id, claim_text, claim_text_en, subject_text, predicate,
                   object_text, confidence, claim_embedding, claim_fingerprint)
                VALUES (:id, :tx, :en, :sub, :pr, :ob, :cf, :emb, :fp)
                """
            ),
            {
                "id": pid, "tx": claim_text[:4000], "en": claim_en[:4000] if claim_en else None,
                "sub": (c.get("subject") or "").strip()[:200] or None,
                "pr": (c.get("predicate") or "").strip()[:200] or None,
                "ob": (c.get("object") or "").strip()[:600] or None,
                "cf": _as_float(c.get("confidence")) or 0.6,
                "emb": (str(emb) if emb else None),
                "fp": _fingerprint(claim_en or claim_text),
            },
        )


async def _persist_quotes(db, pid: int, quotes: list[dict[str, Any]]) -> None:
    from sqlalchemy import text
    await db.execute(text("DELETE FROM social_post_quotes WHERE post_id = :id"), {"id": pid})
    for q in quotes[:8]:
        if not isinstance(q, dict):
            continue
        qtext = (q.get("text") or "").strip()
        if not qtext:
            continue
        await db.execute(
            text(
                """
                INSERT INTO social_post_quotes (post_id, speaker_name, quote_text, is_direct)
                VALUES (:id, :sp, :tx, :dir)
                """
            ),
            {
                "id": pid, "sp": (q.get("speaker") or "").strip()[:200] or None,
                "tx": qtext[:4000], "dir": bool(q.get("is_direct", False)),
            },
        )


async def _persist_stances(db, pid: int, stances: list[dict[str, Any]]) -> None:
    from sqlalchemy import text
    valid = {"supports", "opposes", "criticises", "praises", "neutral"}
    await db.execute(text("DELETE FROM social_post_stances WHERE post_id = :id"), {"id": pid})
    for s in stances[:8]:        # keep all (intensity-weighted); modest safety cap
        if not isinstance(s, dict):
            continue
        actor = (s.get("actor") or "").strip()
        target = (s.get("target") or "").strip()
        stance = (s.get("stance") or "").strip().lower()
        if not actor or not target or stance not in valid:
            continue
        await db.execute(
            text(
                """
                INSERT INTO social_post_stances (post_id, actor, target, stance, intensity)
                VALUES (:id, :ac, :tg, :st, :it)
                """
            ),
            {
                "id": pid, "ac": actor[:200], "tg": target[:200], "st": stance,
                "it": _as_float(s.get("intensity")) or 0.5,
            },
        )


async def _persist_locations(db, pid: int, locations: list[dict[str, Any]]) -> None:
    from sqlalchemy import text
    await db.execute(text("DELETE FROM social_post_locations WHERE post_id = :id"), {"id": pid})
    for i, loc in enumerate(locations[:6]):
        if not isinstance(loc, dict):
            continue
        ltext = (loc.get("text") or "").strip()
        if not ltext:
            continue
        await db.execute(
            text(
                """
                INSERT INTO social_post_locations (post_id, location_text, region, is_primary)
                VALUES (:id, :tx, :rg, :pr)
                """
            ),
            {"id": pid, "tx": ltext[:200], "rg": (loc.get("state") or "").strip()[:100] or None,
             "pr": (i == 0)},
        )


async def _persist_events(db, pid: int, events: list[dict[str, Any]]) -> None:
    from sqlalchemy import text
    await db.execute(text("DELETE FROM social_post_events WHERE post_id = :id"), {"id": pid})
    for e in events[:6]:
        if not isinstance(e, dict):
            continue
        mention = (e.get("mention") or "").strip()
        if not mention:
            continue
        resolved = (e.get("resolved") or None)
        await db.execute(
            text(
                """
                INSERT INTO social_post_events
                  (post_id, mention_raw, resolved_at, date_confidence)
                VALUES (:id, :mn, :rs, :cf)
                """
            ),
            {"id": pid, "mn": mention[:200], "rs": (resolved if resolved else None),
             "cf": _as_float(e.get("confidence")) or 0.3},
        )


async def _persist_hashtags(db, pid: int, tags: list[Any]) -> None:
    from sqlalchemy import text
    await db.execute(text("DELETE FROM social_post_hashtags WHERE post_id = :id"), {"id": pid})
    seen = set()
    for t in tags[:20]:
        tag = (t if isinstance(t, str) else (t.get("tag") if isinstance(t, dict) else "")) or ""
        tag = tag.strip().lstrip("#")
        if not tag or tag.lower() in seen:
            continue
        seen.add(tag.lower())
        await db.execute(
            text("INSERT INTO social_post_hashtags (post_id, tag) VALUES (:id, :t)"),
            {"id": pid, "t": tag[:140]},
        )


async def _persist_mentions(db, pid: int, mentions: list[Any]) -> None:
    from sqlalchemy import text
    await db.execute(text("DELETE FROM social_post_mentions WHERE post_id = :id"), {"id": pid})
    seen = set()
    for m in mentions[:20]:
        u = (m if isinstance(m, str) else (m.get("username") if isinstance(m, dict) else "")) or ""
        u = u.strip().lstrip("@")
        if not u or u.lower() in seen:
            continue
        seen.add(u.lower())
        await db.execute(
            text("INSERT INTO social_post_mentions (post_id, mentioned_username) VALUES (:id, :u)"),
            {"id": pid, "u": u[:200]},
        )
