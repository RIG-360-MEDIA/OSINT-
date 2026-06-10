"""
Celery task: newspaper clipping substrate enrichment.

A clipping is "an article whose body is an OCR'd crop", so it rides the SAME
substrate path as articles: ONE structured-JSON call (GROQ_SYS_NEWSPAPER) emits
claims/quotes/stances/locations/events/numbers + register + entities, written to
clipping_* child tables for article-parity analytics. Topic + LaBSE embedding
are the two genuinely-separate steps. Entity resolution is the
clipping_entity_mentions matview (no per-item resolver call).

Routing (design §6.2): the `documents` queue — NOT `nlp` (that worker is for
article NLP; sharing it would steal article throughput).

Two entry points:
  * enrich_clipping(clipping_id)      — per-item, enqueued at insert time
  * drain_pending_clippings(limit)    — periodic catch-up safety net

Lifecycle mirrors the article substrate:
  substrate_status pending → processing → ok | extract_failed | junk
  extraction_version = 3 on success.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date as _date
from typing import Any

from backend.celery_app import app

logger = logging.getLogger(__name__)

_EXTRACTION_VERSION = 3
_MIN_BODY_CHARS = 40  # below this the OCR body is too sparse to extract from


# ── Celery entry points ───────────────────────────────────────────────────────

@app.task(name="tasks.enrich_clipping", queue="documents")
def enrich_clipping(clipping_id: str) -> dict:
    """Enrich a single clipping by id (enqueued per-row at insert time)."""
    return asyncio.run(_enrich_one_by_id(clipping_id))


@app.task(name="tasks.drain_pending_clippings", queue="documents")
def drain_pending_clippings(limit: int = 50) -> dict:
    """Periodic catch-up: enrich up to `limit` pending clippings."""
    return asyncio.run(_drain(limit))


# ── Async orchestration ───────────────────────────────────────────────────────

async def _drain(limit: int) -> dict:
    from sqlalchemy import text
    from backend.database import get_db

    done = failed = 0
    for _ in range(max(1, limit)):
        async with get_db() as db:
            row = (
                await db.execute(
                    text(
                        """
                        UPDATE clippings
                           SET substrate_status = 'processing'
                         WHERE id = (
                            SELECT id FROM clippings
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
            cid = str(row.id)
            await db.commit()
        ok = await _enrich_claimed(cid)
        if ok:
            done += 1
        else:
            failed += 1
    logger.info("drain_pending_clippings: %d enriched, %d failed", done, failed)
    return {"enriched": done, "failed": failed}


async def _enrich_one_by_id(clipping_id: str) -> dict:
    """Claim a specific clipping (idempotent) then enrich it."""
    from sqlalchemy import text
    from backend.database import get_db

    async with get_db() as db:
        row = (
            await db.execute(
                text(
                    """
                    UPDATE clippings
                       SET substrate_status = 'processing'
                     WHERE id = :id
                       AND substrate_status IN ('pending', 'extract_failed')
                    RETURNING id
                    """
                ),
                {"id": clipping_id},
            )
        ).fetchone()
        await db.commit()
    if not row:
        # already processed / processing — nothing to do
        return {"clipping_id": clipping_id, "status": "skipped"}
    ok = await _enrich_claimed(clipping_id)
    return {"clipping_id": clipping_id, "status": "ok" if ok else "failed"}


async def _enrich_claimed(clipping_id: str) -> bool:
    """Run the full substrate enrichment on an already-claimed clipping."""
    from sqlalchemy import text
    from backend.database import get_db
    from backend.nlp.newspaper_prompt import (
        prompt_for_language,
        body_cap,
        sanitize_extraction,
        TASK_TYPE,
    )
    from backend.nlp.groq_client import call_groq, FAST_MODEL

    async with get_db() as db:
        clip = (
            await db.execute(
                text(
                    "SELECT id, headline, body_text, "
                    "       COALESCE(detected_language, language, 'en') AS lang "
                    "FROM clippings WHERE id = :id"
                ),
                {"id": clipping_id},
            )
        ).fetchone()

    if not clip:
        return False

    headline = (clip.headline or "").strip()
    body = (clip.body_text or "").strip()
    lang = (clip.lang or "en").lower()

    # Junk guard — too little grounded text to extract from.
    if len(body) < _MIN_BODY_CHARS:
        await _mark_status(clipping_id, "junk")
        return True  # terminal, not an error

    sys_prompt, max_tok = prompt_for_language(lang)
    user_msg = f"HEADLINE: {headline}\n\nBODY (OCR):\n{body[:body_cap(lang)]}"

    parsed = await _call_with_retry(
        call_groq, FAST_MODEL, sys_prompt, user_msg, max_tok, TASK_TYPE
    )
    if parsed is None:
        await _mark_status(clipping_id, "extract_failed")
        return False

    parsed = sanitize_extraction(parsed)
    _normalize_arrays(parsed)

    # Topic (reuse the article taxonomy) + LaBSE embedding.
    topic_fine, topic_coarse = await _classify_topic(headline, parsed)
    embedding = _embed(headline, parsed)

    try:
        await _persist(clipping_id, parsed, topic_fine, topic_coarse, embedding, lang)
    except Exception:
        logger.exception("clipping enrich persist failed for %s", clipping_id)
        await _mark_status(clipping_id, "extract_failed")
        return False
    return True


# ── LLM call with 2-attempt retry + robust parse (mirror substrate) ───────────

async def _call_with_retry(
    call_groq, model, sys_prompt: str, user_msg: str, max_tok: int, task_type: str
) -> dict[str, Any] | None:
    import json
    import re

    from backend.nlp.groq_client import GroqCallFailed, GroqQuotaExhausted

    raw_for_parse = ""
    for attempt in range(2):
        try:
            raw = await call_groq(
                system=sys_prompt,
                user=user_msg,
                model=model,
                task_type=task_type,
                json_response=True,
                max_tokens_override=max_tok,
            )
        except (GroqCallFailed, GroqQuotaExhausted) as exc:
            logger.warning("clipping enrich: groq failed (attempt %d): %s", attempt + 1, exc)
            if attempt == 0:
                continue
            return None

        raw_for_parse = (raw or "").strip() if isinstance(raw, str) else ""
        if not isinstance(raw, str):
            # call_groq already returned a dict
            if isinstance(raw, dict):
                return raw
            return None
        try:
            return json.loads(raw_for_parse)
        except (TypeError, ValueError):
            cleaned = raw_for_parse
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```\s*$", "", cleaned)
            first, last = cleaned.find("{"), cleaned.rfind("}")
            if first >= 0 and last > first:
                cleaned = cleaned[first:last + 1]
            try:
                return json.loads(cleaned)
            except (TypeError, ValueError):
                if attempt == 0:
                    continue
                logger.warning(
                    "clipping enrich: json parse failed after 2 attempts. raw[:200]=%r",
                    raw_for_parse[:200],
                )
                return None
    return None


def _normalize_arrays(parsed: dict[str, Any]) -> None:
    """Coerce structural defaults so persist never trips on a wrong type."""
    for k in ("locations", "events", "quotes", "actor_stances", "claims",
              "numbers", "entities_extracted"):
        if not isinstance(parsed.get(k), list):
            parsed[k] = []
    if not isinstance(parsed.get("summaries"), dict):
        parsed["summaries"] = {}
    if not isinstance(parsed.get("register"), dict):
        parsed["register"] = {}


async def _classify_topic(headline: str, parsed: dict[str, Any]) -> tuple[str | None, str | None]:
    from backend.nlp.nlp_topic import classify_topic_fine, coarse_from_fine

    # Prefer English translation (Indic), else the snippet, else headline only.
    lead = (
        parsed.get("english_translation")
        or parsed.get("summaries", {}).get("snippet")
        or parsed.get("primary_subject")
        or ""
    )
    try:
        fine = await classify_topic_fine(headline, lead[:500] if lead else None)
        return fine, coarse_from_fine(fine)
    except Exception as exc:  # noqa: BLE001
        logger.warning("clipping topic classify failed: %s", exc)
        return None, None


def _embed(headline: str, parsed: dict[str, Any]) -> list[float] | None:
    from backend.nlp.nlp_embedding import generate_embedding

    snippet = parsed.get("summaries", {}).get("snippet") or ""
    text_for_embed = f"{headline}\n{snippet}".strip()[:512]
    if not text_for_embed:
        return None
    try:
        return generate_embedding(text_for_embed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("clipping embed failed: %s", exc)
        return None


# ── Persistence ───────────────────────────────────────────────────────────────

async def _persist(
    clipping_id: str,
    parsed: dict[str, Any],
    topic_fine: str | None,
    topic_coarse: str | None,
    embedding: list[float] | None,
    lang: str,
) -> None:
    from sqlalchemy import text
    from backend.database import get_db

    sums = parsed.get("summaries", {})
    reg = parsed.get("register", {})
    entities = parsed.get("entities_extracted", [])
    locations = parsed.get("locations", [])
    geo_primary, geo_district = _derive_geo(locations)
    translation = parsed.get("english_translation")

    async with get_db() as db:
        await db.execute(
            text(
                """
                UPDATE clippings SET
                    article_type         = :atype,
                    primary_subject      = :ps,
                    body_text_translated = COALESCE(:tr, body_text_translated),
                    summary_preview      = :sp,
                    summary_snippet      = :ss,
                    summary_executive    = :se,
                    register_style       = :rs,
                    register_emotion     = :re,
                    register_is_breaking = :rb,
                    topic_fine           = COALESCE(:tf, topic_fine),
                    topic_category       = COALESCE(:tc, topic_category),
                    entities_extracted   = CAST(:ents AS JSONB),
                    geo_primary          = :gp,
                    geo_district         = :gd,
                    labse_embedding      = :emb,
                    substrate_status     = 'ok',
                    extraction_version   = :ev,
                    enriched_at          = NOW()
                WHERE id = :id
                """
            ),
            {
                "id": clipping_id,
                "atype": (parsed.get("article_type") or "other")[:20],
                "ps": (parsed.get("primary_subject") or None),
                "tr": translation,
                "sp": (sums.get("preview") or None),
                "ss": (sums.get("snippet") or None),
                "se": (sums.get("executive") or None),
                "rs": (reg.get("rhetorical_style") or None),
                "re": (reg.get("primary_emotion") or None),
                "rb": bool(reg.get("is_breaking", False)),
                "tf": topic_fine,
                "tc": topic_coarse,
                "ents": _json_dump(entities),
                "gp": geo_primary,
                "gd": geo_district,
                "emb": (str(embedding) if embedding else None),
                "ev": _EXTRACTION_VERSION,
            },
        )
        await _persist_claims(db, clipping_id, parsed.get("claims", []))
        await _persist_quotes(db, clipping_id, parsed.get("quotes", []))
        await _persist_stances(db, clipping_id, parsed.get("actor_stances", []))
        await _persist_locations(db, clipping_id, locations)
        await _persist_events(db, clipping_id, parsed.get("events", []))
        await _persist_numbers(db, clipping_id, parsed.get("numbers", []))
        await db.commit()


def _json_dump(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return "[]"


def _derive_geo(locations: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """Pick the primary India region/city for the flat geo_* convenience cols."""
    primary = None
    for loc in locations:
        if isinstance(loc, dict) and loc.get("is_primary"):
            primary = loc
            break
    if primary is None and locations and isinstance(locations[0], dict):
        primary = locations[0]
    if not primary:
        return None, None
    region = (primary.get("region") or "").strip() or None
    city = (primary.get("city") or "").strip() or None
    return region, city


async def _mark_status(clipping_id: str, status: str) -> None:
    from sqlalchemy import text
    from backend.database import get_db

    async with get_db() as db:
        await db.execute(
            text(
                "UPDATE clippings SET substrate_status = :s, "
                "extraction_version = :ev, enriched_at = NOW() WHERE id = :id"
            ),
            {
                "s": status,
                "ev": _EXTRACTION_VERSION if status in ("ok", "junk") else 0,
                "id": clipping_id,
            },
        )
        await db.commit()


# ── Child-table persisters (mirror substrate _persist_*; FK = clipping_id) ────

async def _persist_claims(db, cid: str, claims: list[dict[str, Any]]) -> None:
    from sqlalchemy import text

    await db.execute(text("DELETE FROM clipping_claims WHERE clipping_id = :id"), {"id": cid})
    for c in claims[:5]:
        if not isinstance(c, dict):
            continue
        claim_text = (c.get("text") or "").strip()
        if not claim_text:
            continue
        subject = (c.get("subject") or "").strip() or (c.get("claimant") or "article")
        predicate = (c.get("predicate") or "").strip() or None
        obj = (c.get("object") or "").strip() or None
        confidence = 0.85 if bool(c.get("verifiable", False)) else 0.5
        await db.execute(
            text(
                """
                INSERT INTO clipping_claims
                  (clipping_id, claim_text, subject_text, predicate, object_text, confidence)
                VALUES (:id, :tx, :sub, :pr, :ob, :cf)
                """
            ),
            {
                "id": cid, "tx": claim_text[:4000],
                "sub": subject[:200] if subject else None,
                "pr": predicate[:200] if predicate else None,
                "ob": obj[:600] if obj else None,
                "cf": confidence,
            },
        )


async def _persist_quotes(db, cid: str, quotes: list[dict[str, Any]]) -> None:
    from sqlalchemy import text

    valid_ctx = {
        "press_conference", "interview", "statement", "parliament",
        "court", "press_release", "article", "other",
    }
    await db.execute(text("DELETE FROM clipping_quotes WHERE clipping_id = :id"), {"id": cid})
    for q in quotes[:5]:
        if not isinstance(q, dict):
            continue
        qtext = (q.get("text") or "").strip()
        speaker = (q.get("speaker") or "").strip()
        if not qtext or not speaker:
            continue
        raw_ctx = (q.get("context") or "").strip().lower().replace(" ", "_")
        await db.execute(
            text(
                """
                INSERT INTO clipping_quotes
                  (clipping_id, speaker_name, quote_text, is_direct, context)
                VALUES (:id, :sp, :tx, :vb, :ctx)
                """
            ),
            {
                "id": cid, "sp": speaker[:200], "tx": qtext[:4000],
                "vb": bool(q.get("is_verbatim", True)),
                "ctx": raw_ctx if raw_ctx in valid_ctx else None,
            },
        )


async def _persist_stances(db, cid: str, stances: list[dict[str, Any]]) -> None:
    from sqlalchemy import text

    await db.execute(text("DELETE FROM clipping_stances WHERE clipping_id = :id"), {"id": cid})
    for s in stances[:5]:
        if not isinstance(s, dict):
            continue
        actor = (s.get("actor") or "").strip()
        if not actor:
            continue
        try:
            intensity = max(0.0, min(1.0, float(s.get("intensity") or 0.5)))
        except (TypeError, ValueError):
            intensity = 0.5
        await db.execute(
            text(
                """
                INSERT INTO clipping_stances (clipping_id, actor, stance, intensity)
                VALUES (:id, :ac, :st, :it)
                """
            ),
            {"id": cid, "ac": actor[:200], "st": (s.get("stance") or "neutral")[:40], "it": intensity},
        )


async def _persist_locations(db, cid: str, locs: list[dict[str, Any]]) -> None:
    from sqlalchemy import text

    await db.execute(text("DELETE FROM clipping_locations WHERE clipping_id = :id"), {"id": cid})
    for loc in locs[:5]:
        if not isinstance(loc, dict):
            continue
        ltext = (loc.get("text") or "").strip()
        if not ltext:
            continue
        await db.execute(
            text(
                """
                INSERT INTO clipping_locations
                  (clipping_id, location_text, country, region, city, is_primary)
                VALUES (:id, :t, :c, :r, :ct, :p)
                """
            ),
            {
                "id": cid, "t": ltext[:200],
                "c": (loc.get("country") or "").strip() or None,
                "r": (loc.get("region") or "").strip() or None,
                "ct": (loc.get("city") or "").strip() or None,
                "p": bool(loc.get("is_primary")),
            },
        )


async def _persist_events(db, cid: str, evs: list[dict[str, Any]]) -> None:
    from sqlalchemy import text

    await db.execute(text("DELETE FROM clipping_events WHERE clipping_id = :id"), {"id": cid})
    for i, ev in enumerate(evs[:6]):
        if not isinstance(ev, dict):
            continue
        desc = (ev.get("description") or "").strip()
        if not desc:
            continue
        date_val = None
        try:
            if ev.get("date"):
                date_val = _date.fromisoformat(ev["date"])
        except (TypeError, ValueError):
            date_val = None
        actors = ev.get("actors") or []
        if not isinstance(actors, list):
            actors = []
        await db.execute(
            text(
                """
                INSERT INTO clipping_events
                  (clipping_id, event_date, event_description, event_type, actors, position, is_future)
                VALUES (:id, :d, :desc, :et, :ac, :p, :fut)
                """
            ),
            {
                "id": cid, "d": date_val, "desc": desc[:600],
                "et": (ev.get("event_type") or "other")[:40],
                "ac": [str(a)[:200] for a in actors][:8],
                "p": i, "fut": bool(ev.get("is_future", False)),
            },
        )


async def _persist_numbers(db, cid: str, numbers: list[dict[str, Any]]) -> None:
    from sqlalchemy import text

    await db.execute(text("DELETE FROM clipping_numbers WHERE clipping_id = :id"), {"id": cid})
    for i, n in enumerate(numbers[:5]):
        if not isinstance(n, dict):
            continue
        value = n.get("value")
        if value is None or value == "":
            continue
        await db.execute(
            text(
                """
                INSERT INTO clipping_numbers (clipping_id, value, unit, context, position)
                VALUES (:id, :v, :u, :c, :p)
                """
            ),
            {
                "id": cid, "v": str(value)[:200],
                "u": (n.get("unit") or None),
                "c": (n.get("context") or "")[:400], "p": i,
            },
        )
