"""
Celery task: YouTube clip substrate enrichment.

A clip is "a timestamped entity-mention extracted from a YouTube transcript",
so it rides the SAME substrate path as articles and clippings: ONE structured-
JSON call (TRANSCRIPT_SYS) emits claims/quotes/stances/locations written to
youtube_clip_* child tables for article-parity analytics. Topic + LaBSE
embedding follow. Entity resolution is the youtube_clip_entity_mentions matview.

Routing: the `youtube` queue — NOT `nlp` (that worker is for article NLP;
NOT `documents` (that's newspaper/govt). Clips get their own bounded queue
to avoid stealing throughput from other pillars during cloud-only windows.

Two entry points:
  * enrich_clip(clip_id)         — per-item, enqueued at insert time
  * drain_pending_clips(limit)   — periodic catch-up safety net

Lifecycle mirrors the article substrate:
  substrate_status pending → processing → ok | extract_failed | junk
  extraction_version = 3 on success.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.celery_app import app

logger = logging.getLogger(__name__)

_EXTRACTION_VERSION = 4   # v4: multi-entity + all-English quotes/claims/stances, no placeholder speakers
_MIN_SEGMENT_CHARS = 20       # below this the transcript segment is too sparse
_MAX_SEGMENT_CHARS = 2200     # mirrors extraction.py _MAX_CHUNK_CHARS
_MAX_OUTPUT_TOKENS = 4000     # was 1500 — too low: multi-field English-translated
                              # extraction of long/Indic transcripts overflowed it,
                              # so strict json_object mode returned truncated → 400 →
                              # cloud chain exhausted → 0 clips. 4000 fits the output.

# Intensity string → numeric (TRANSCRIPT_SYS emits high/medium/low strings)
_INTENSITY_MAP = {"high": 0.9, "medium": 0.5, "low": 0.3}

# Dedicated enrichment prompt — the clip is ALREADY identified, so we extract
# structured fields directly (no clip-finding, no [Ns] timestamps). Reusing the
# extraction prompt here returned clips=[] because the stored transcript_segment
# has no timestamp markers.
_ENRICH_SYS = """You are a political-intelligence analyst. You are given the transcript of ONE already-selected news clip about {entity}. Extract structured intelligence from it.

Output VALID JSON only — no markdown, no prose — with EXACTLY these keys:
{{
  "segment_type": "debate|interview|speech|press_conference|news_report|panel",
  "speaker": "<name of the main speaker, or null>",
  "quotes": [{{"speaker": "<real named speaker, or null — never 'Speaker'/'Anchor'>", "text": "<what was said, TRANSLATED TO ENGLISH>", "is_verbatim": false}}],
  "claims": [{{"subject": "<actor>", "predicate": "<action or assertion>", "object": "<target, topic or figure>"}}],
  "stances": [{{"actor": "<real named person/org>", "target": "<the SPECIFIC person, party, policy, scheme or issue — not a bare state/region>", "stance": "supports|opposes|criticises|praises|neutral", "intensity": "high|medium|low"}}],
  "locations": [{{"country": "<full English name e.g. India>", "region": "<state or null>", "city": "<city or null>"}}],
  "entities": [{{"name": "<canonical name of a person / party / organisation / place / scheme the clip mentions>", "type": "person|party|org|place|scheme|other"}}]
}}

RULES:
- ALL output text — quotes, claims (subject/predicate/object), stances (actor/target), locations, entities — MUST be in ENGLISH. Translate/transliterate from the transcript language; NEVER output native script (Telugu/Hindi/Urdu/etc.).
- Extract EVERY factual/political assertion as a subject-predicate-object claim. Political speech usually has 2-5.
- quotes: statements actually made, translated to English; attribute each to a REAL named speaker — if you cannot identify one, use null. NEVER 'Speaker', 'Anchor', 'Host', 'Unknown'.
- stances: who is for/against whom. Use real named actors only — never 'Speaker', 'Anchor', 'Host', 'Unknown'. The target must be a SPECIFIC person, party, policy, scheme or issue — not a bare state/region name.
- entities: list EVERY distinct named person, political party, organisation, place or government scheme the clip mentions — NOT only {entity}. Give each one's STANDARD ENGLISH name, translating/transliterating from the transcript language: e.g. 'సుప్రీంకోర్టు' → 'Supreme Court of India', 'కాంగ్రెస్' → 'Indian National Congress', 'బిజెపి' → 'BJP', 'KCR' → 'K. Chandrashekar Rao'. English canonical names ONLY (never native script), so the clip is findable and entities resolve across pillars.
- Any array with nothing to extract = []. Never invent.
- The clip is ALREADY chosen — do NOT judge newsworthiness or emit a 'clips' wrapper, just extract these fields."""


# ── Celery entry points ───────────────────────────────────────────────────────

@app.task(name="tasks.enrich_clip", queue="youtube")
def enrich_clip(clip_id: int) -> dict:
    """Enrich a single clip by id (enqueued per-row at insert time)."""
    return asyncio.run(_enrich_one_by_id(clip_id))


@app.task(name="tasks.drain_pending_clips", queue="youtube")
def drain_pending_clips(limit: int = 20) -> dict:
    """Periodic catch-up: enrich up to `limit` pending clips."""
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
                        UPDATE youtube_clips_v2
                           SET substrate_status = 'processing'
                         WHERE id = (
                            SELECT id FROM youtube_clips_v2
                             WHERE substrate_status = 'pending'
                             ORDER BY created_at
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
            cid: int = int(row.id)
            await db.commit()
        try:
            ok = await _enrich_claimed(cid)
        except Exception:  # noqa: BLE001
            # Never let one bad row kill the loop and leave it wedged in
            # 'processing'. Mark it failed (retryable) and move on.
            logger.exception("clip enrich crashed for %s; marking extract_failed", cid)
            await _mark_status(cid, "extract_failed")
            ok = False
        if ok:
            done += 1
        else:
            failed += 1
    logger.info("drain_pending_clips: %d enriched, %d failed", done, failed)
    return {"enriched": done, "failed": failed}


async def _enrich_one_by_id(clip_id: int) -> dict:
    """Claim a specific clip (idempotent) then enrich it."""
    from sqlalchemy import text
    from backend.database import get_db

    async with get_db() as db:
        row = (
            await db.execute(
                text(
                    """
                    UPDATE youtube_clips_v2
                       SET substrate_status = 'processing'
                     WHERE id = :id
                       AND substrate_status IN ('pending', 'extract_failed')
                    RETURNING id
                    """
                ),
                {"id": clip_id},
            )
        ).fetchone()
        await db.commit()
    if not row:
        return {"clip_id": clip_id, "status": "skipped"}
    ok = await _enrich_claimed(clip_id)
    return {"clip_id": clip_id, "status": "ok" if ok else "failed"}


async def _enrich_claimed(clip_id: int) -> bool:
    """Run the full substrate enrichment on an already-claimed clip."""
    from sqlalchemy import text
    from backend.database import get_db
    from backend.collectors.youtube_v2.prompts import build_transcript_sys
    from backend.nlp.groq_client import call_groq, FAST_MODEL

    async with get_db() as db:
        clip = (
            await db.execute(
                text(
                    "SELECT id, video_title, channel_name, matched_entity, "
                    "       summary, transcript_segment, transcript_language "
                    "FROM youtube_clips_v2 WHERE id = :id"
                ),
                {"id": clip_id},
            )
        ).fetchone()

    if not clip:
        return False

    segment = (clip.transcript_segment or "").strip()
    lang = (clip.transcript_language or "en").lower()

    if len(segment) < _MIN_SEGMENT_CHARS:
        await _mark_status(clip_id, "junk")
        return True  # terminal, not an error

    entity = clip.matched_entity
    sys_prompt = _ENRICH_SYS.format(entity=entity)
    user_msg = (
        f"Clip is about: {entity}\n"
        f"Transcript language: {lang}\n\n"
        f"Clip transcript:\n{segment[:_MAX_SEGMENT_CHARS]}"
    )

    parsed = await _call_with_retry(
        call_groq, "youtube", sys_prompt, user_msg,
        _MAX_OUTPUT_TOKENS, "transcript_analysis",
    )
    if parsed is None:
        await _mark_status(clip_id, "extract_failed")
        return False

    # Flat structured fields extracted directly from this already-identified clip
    # (no clip-finding, no timestamps — the old code reused the extraction prompt
    # which needs [Ns]-marked input and returned clips=[] on these segments).
    all_claims: list[dict] = parsed.get("claims", []) or []
    all_quotes: list[dict] = parsed.get("quotes", []) or []
    all_stances: list[dict] = parsed.get("stances", []) or []
    all_locations: list[dict] = parsed.get("locations", []) or []
    all_entities: list[dict] = parsed.get("entities", []) or []
    segment_type = parsed.get("segment_type") or None
    _sp = parsed.get("speaker")
    speaker = str(_sp).strip() if _sp and str(_sp).strip() else None

    topic_fine, topic_coarse = await _classify_topic(clip.summary, entity)

    try:
        await _persist(
            clip_id=clip_id,
            entity=entity,
            segment_type=segment_type,
            speaker=speaker,
            claims=all_claims,
            quotes=all_quotes,
            stances=all_stances,
            locations=all_locations,
            entities=all_entities,
            topic_fine=topic_fine,
            topic_coarse=topic_coarse,
        )
    except Exception:
        logger.exception("clip enrich persist failed for %s", clip_id)
        await _mark_status(clip_id, "extract_failed")
        return False
    # event-driven per-user relevance (mirrors articles' nlp→score_relevance_batch)
    try:
        app.send_task("tasks.relevance.score_one_clip", args=[clip_id], queue="relevance")
    except Exception:  # noqa: BLE001
        logger.debug("relevance dispatch failed for clip %s (non-fatal)", clip_id)
    return True


# ── LLM call with 2-attempt retry + robust parse (mirror substrate) ───────────

async def _call_with_retry(
    call_groq, pillar: str, sys_prompt: str,
    user_msg: str, max_tok: int, task_type: str,
) -> dict[str, Any] | None:
    """Try the cheap local-first pool; on ANY failure fall back to cloud-direct.

    The unified pool prefers local TabbyAPI slots and raises ConnectError when
    the local tunnel is down (rather than falling back), which otherwise stalls
    the clip backlog. Cloud fallback (Groq gpt-oss-120b → Cerebras) keeps rows
    processing when local is flaky; local is still preferred when up.
    """
    import os
    from backend.nlp.groq_client import GroqCallFailed, GroqQuotaExhausted
    from backend.nlp.cloud_fallback import cloud_call

    # Backfill mode: route extraction straight to cloud (parallel) instead of
    # queuing behind the one saturated local GPU. Runs IN the worker (LaBSE
    # cached → no OOM). Toggle with DRAIN_CLOUD_FIRST=1.
    if os.getenv("DRAIN_CLOUD_FIRST") == "1":
        for attempt in range(2):
            try:
                raw = await cloud_call(sys_prompt, user_msg, max_tok)
            except Exception:  # noqa: BLE001
                raw = None
            parsed = _loads_lenient(raw)
            if parsed is not None:
                return parsed
        return None

    # 1) local-first pool (2 attempts)
    for attempt in range(2):
        try:
            raw = await call_groq(
                system=sys_prompt,
                user=user_msg,
                pillar=pillar,
                task_type=task_type,
                json_response=True,
                max_tokens_override=max_tok,
            )
        except (GroqCallFailed, GroqQuotaExhausted) as exc:
            logger.warning("clip enrich: groq pool failed (attempt %d): %s", attempt + 1, exc)
            break  # pool unhealthy → go straight to cloud fallback
        except Exception as exc:  # noqa: BLE001
            # Wedge-proofing: ANY error (e.g. httpx.ConnectError when the local
            # LLM tunnel is down) must NOT propagate; fall through to cloud.
            logger.warning("clip enrich: pool call errored (attempt %d): %s", attempt + 1, exc)
            break
        if isinstance(raw, dict):
            return raw
        parsed = _loads_lenient(raw)
        if parsed is not None:
            return parsed
        if attempt == 0:
            continue

    # 2) cloud-direct fallback (Groq → Cerebras, key rotation; never raises)
    try:
        raw = await cloud_call(sys_prompt, user_msg, max_tok)
    except Exception:  # noqa: BLE001
        raw = None
    parsed = _loads_lenient(raw)
    if parsed is None:
        logger.warning("clip enrich: pool + cloud fallback both failed")
    return parsed


def _loads_lenient(raw: Any) -> dict[str, Any] | None:
    """Parse a JSON object from a possibly-fenced / prose-wrapped LLM string."""
    import json
    import re

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


async def _classify_topic(
    summary: str, entity: str,
) -> tuple[str | None, str | None]:
    import os
    # Backfill mode: skip the extra local topic call (queues behind the
    # saturated local node). COALESCE preserves any existing topic.
    if os.getenv("DRAIN_CLOUD_FIRST") == "1":
        return None, None
    from backend.nlp.nlp_topic import classify_topic_fine, coarse_from_fine

    lead = f"{entity}: {summary[:400]}" if summary else entity
    try:
        fine = await classify_topic_fine(entity, lead)
        return fine, coarse_from_fine(fine)
    except Exception as exc:  # noqa: BLE001
        logger.warning("clip topic classify failed: %s", exc)
        return None, None


def _merge_entities(anchor: str, llm_entities: list[dict]) -> list[dict]:
    """Anchor first, then every distinct LLM-extracted entity. Deduped
    case-insensitively by name; keeps optional `type`. Mirrors the
    article/clipping [{"name": ...}] shape the entity-mention matview reads."""
    out: list[dict] = []
    seen: set[str] = set()
    anchor = (anchor or "").strip()
    if anchor:
        out.append({"name": anchor})
        seen.add(anchor.lower())
    for e in llm_entities or []:
        name = str((e or {}).get("name", "")).strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        item: dict[str, Any] = {"name": name}
        etype = str((e or {}).get("type", "")).strip()
        if etype:
            item["type"] = etype
        out.append(item)
    return out


# ── Persistence ───────────────────────────────────────────────────────────────

async def _persist(
    *,
    clip_id: int,
    entity: str,
    segment_type: str | None,
    speaker: str | None,
    claims: list[dict],
    quotes: list[dict],
    stances: list[dict],
    locations: list[dict],
    entities: list[dict],
    topic_fine: str | None,
    topic_coarse: str | None,
) -> None:
    from sqlalchemy import text
    from backend.database import get_db

    # Multi-entity (parity with articles/cuttings): every entity the clip's
    # transcript mentions, with the matched_entity kept FIRST as the anchor and
    # always present even if the LLM omitted it. matched_entity column stays the
    # canonical anchor; entities_extracted now powers cross-entity analytics
    # (co-mentions, "every clip mentioning X", heatmaps).
    entities_extracted = _merge_entities(entity, entities)

    async with get_db() as db:
        await db.execute(
            text(
                """
                UPDATE youtube_clips_v2 SET
                    segment_type       = COALESCE(:st, segment_type),
                    speaker            = :sp,
                    primary_subject    = COALESCE(primary_subject, :ps),
                    topic_fine         = COALESCE(:tf, topic_fine),
                    topic_category     = COALESCE(:tc, topic_category),
                    entities_extracted = CAST(:ents AS JSONB),
                    substrate_status   = 'ok',
                    extraction_version = :ev,
                    enriched_at        = NOW()
                WHERE id = :id
                """
            ),
            {
                "id": clip_id,
                "st": segment_type,
                "sp": (speaker or None),
                "ps": entity,
                "tf": topic_fine,
                "tc": topic_coarse,
                "ents": _json_dump(entities_extracted),
                "ev": _EXTRACTION_VERSION,
            },
        )
        await _persist_claims(db, clip_id, claims)
        await _persist_quotes(db, clip_id, quotes)
        await _persist_stances(db, clip_id, stances)
        await _persist_locations(db, clip_id, locations)
        await db.commit()


def _json_dump(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return "[]"


async def _mark_status(clip_id: int, status: str) -> None:
    from sqlalchemy import text
    from backend.database import get_db

    async with get_db() as db:
        await db.execute(
            text(
                "UPDATE youtube_clips_v2 SET substrate_status = :s, "
                "extraction_version = :ev, enriched_at = NOW() WHERE id = :id"
            ),
            {
                "s": status,
                "ev": _EXTRACTION_VERSION if status in ("ok", "junk") else 0,
                "id": clip_id,
            },
        )
        await db.commit()


# ── Child-table persisters (FK = clip_id BIGINT) ─────────────────────────────

_PLACEHOLDER_ACTORS = frozenset({
    "speaker", "anchor", "host", "unknown", "n/a", "presenter",
    "reporter", "journalist", "correspondent",
})


async def _persist_claims(db, clip_id: int, claims: list[dict[str, Any]]) -> None:
    from sqlalchemy import text

    await db.execute(
        text("DELETE FROM youtube_clip_claims WHERE clip_id = :id"), {"id": clip_id}
    )
    for c in claims[:5]:
        if not isinstance(c, dict):
            continue
        subject = (c.get("subject") or "").strip() or None
        predicate = (c.get("predicate") or "").strip() or None
        obj = (c.get("object") or "").strip() or None
        # The transcript prompt emits SPO triples with NO free-text 'text'
        # field, so synthesise claim_text from the triple (falling back to an
        # explicit 'text' if a future prompt revision adds one). Without this
        # every claim was dropped as empty — youtube_clip_claims stayed at 0.
        claim_text = (c.get("text") or "").strip() or " ".join(
            p for p in (subject, predicate, obj) if p
        ).strip()
        if not claim_text:
            continue
        await db.execute(
            text(
                """
                INSERT INTO youtube_clip_claims
                  (clip_id, claim_text, subject_text, predicate, object_text, confidence)
                VALUES (:id, :tx, :sub, :pr, :ob, :cf)
                """
            ),
            {
                "id": clip_id,
                "tx": claim_text[:4000],
                "sub": subject[:200] if subject else None,
                "pr": predicate[:200] if predicate else None,
                "ob": obj[:600] if obj else None,
                "cf": 0.85,
            },
        )


async def _persist_quotes(db, clip_id: int, quotes: list[dict[str, Any]]) -> None:
    from sqlalchemy import text

    await db.execute(
        text("DELETE FROM youtube_clip_quotes WHERE clip_id = :id"), {"id": clip_id}
    )
    for q in quotes[:5]:
        if not isinstance(q, dict):
            continue
        qtext = (q.get("text") or "").strip()
        speaker = (q.get("speaker") or "").strip()
        # Drop placeholder speakers ('Speaker'/'Anchor'/…): a misattributed quote
        # is worse than none. Mirrors the stance actor filter.
        if not qtext or not speaker or speaker.lower() in _PLACEHOLDER_ACTORS:
            continue
        qtext = qtext[:4000]
        # is_direct = the quote is a VERBATIM substring of the clip transcript
        # (a real, checkable signal). The prompt's is_verbatim flag is hardcoded
        # false for ASR captions, so it can never populate this honestly.
        await db.execute(
            text(
                """
                INSERT INTO youtube_clip_quotes
                  (clip_id, speaker_name, quote_text, is_direct)
                SELECT :id, :sp, :tx,
                       position(:tx IN COALESCE(c.transcript_segment, '')) > 0
                  FROM youtube_clips_v2 c
                 WHERE c.id = :id
                """
            ),
            {
                "id": clip_id,
                "sp": speaker[:200],
                "tx": qtext,
            },
        )


async def _persist_stances(db, clip_id: int, stances: list[dict[str, Any]]) -> None:
    from sqlalchemy import text

    await db.execute(
        text("DELETE FROM youtube_clip_stances WHERE clip_id = :id"), {"id": clip_id}
    )
    for s in stances[:5]:
        if not isinstance(s, dict):
            continue
        actor = (s.get("actor") or "").strip()
        if not actor or actor.lower() in _PLACEHOLDER_ACTORS:
            continue
        target = (s.get("target") or "").strip() or None
        if target and target.lower() in _PLACEHOLDER_ACTORS:
            target = None
        raw_intensity = str(s.get("intensity") or "medium").strip().lower()
        intensity = _INTENSITY_MAP.get(raw_intensity, 0.5)
        await db.execute(
            text(
                """
                INSERT INTO youtube_clip_stances (clip_id, actor, target, stance, intensity)
                VALUES (:id, :ac, :tg, :st, :it)
                """
            ),
            {
                "id": clip_id,
                "ac": actor[:200],
                "tg": target[:200] if target else None,
                "st": (s.get("stance") or "neutral")[:40],
                "it": intensity,
            },
        )


async def _persist_locations(db, clip_id: int, locs: list[dict[str, Any]]) -> None:
    from sqlalchemy import text

    await db.execute(
        text("DELETE FROM youtube_clip_locations WHERE clip_id = :id"), {"id": clip_id}
    )
    for i, loc in enumerate(locs[:5]):
        if not isinstance(loc, dict):
            continue
        country = (loc.get("country") or "").strip() or None
        region = (loc.get("region") or "").strip() or None
        city = (loc.get("city") or "").strip() or None
        if not any([country, region, city]):
            continue
        location_text = ", ".join(filter(None, [city, region, country]))
        await db.execute(
            text(
                """
                INSERT INTO youtube_clip_locations
                  (clip_id, location_text, country, region, city, is_primary)
                VALUES (:id, :t, :c, :r, :ct, :p)
                """
            ),
            {
                "id": clip_id,
                "t": location_text[:200],
                "c": country,
                "r": region[:200] if region else None,
                "ct": city[:200] if city else None,
                "p": (i == 0),
            },
        )
