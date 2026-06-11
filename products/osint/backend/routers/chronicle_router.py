"""Chronicle — deep investigative story intelligence.

Routes:
  GET  /api/chronicle/{story_id}        — full Chronicle (LLM-generated, cached 24h)
  GET  /api/chronicle/{story_id}/meta   — story metadata + assignment check (fast)
  POST /api/admin/chronicle/assign      — assign a story to a user  [super_admin]
  DELETE /api/admin/chronicle/assign    — remove an assignment       [super_admin]
  GET  /api/admin/chronicle/assignments — list all assignments        [super_admin]

Auth: every endpoint requires a valid JWT. Chronicle endpoints additionally
require the story to be assigned to the caller (super_admins bypass the gate).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from auth.middleware import get_current_principal, require_super_admin
from db import get_db

logger = logging.getLogger("osint-backend.chronicle")

router = APIRouter(tags=["chronicle"])

_CACHE_TTL_HOURS = 24

# ── LLM system prompt ────────────────────────────────────────────────────────

_SYSTEM = """/no_think

You are a senior political intelligence analyst. A client has paid for a deep investigative briefing on a news story cluster.

Your job is NOT to summarise. Your job is to REASON. Think like a CNN investigative reporter who has read every article, noticed every anomaly, and can explain what the data really means.

Produce three outputs:

── OUTPUT 1 — EVENT CHAIN ──
Reconstruct the story as 5–9 causally linked real-world events.
For each event:
  date: "YYYY-MM-DD"
  event: What actually happened in the real world. Not "articles were published." What changed? Who acted? What was announced, blocked, escalated, revealed?
  why_it_happened: Your inference about the root cause. Reference specific evidence. Explain the political, institutional, or social logic behind the timing.
  caused: What this event set in motion. The explicit chain link to what followed next.
  evidence: 1–3 partial article titles that establish this event happened.
  key_quote: One notable translated quote from the data, or null.
  signal_type: One of: "organic" | "manufactured" | "reactive" | "escalation" | "dormant" | "resolution"

Events must be causally linked. The "caused" field of event N must connect directly to event N+1.

── OUTPUT 2 — INSIGHT BOMBS ──
Produce 4–6 analytical deductions a reader could NOT make by reading the headlines. These are the revelations that reframe the story.

For each insight:
  question: The anomaly you are addressing. Start with "Why" or "What explains".
  evidence: The specific data — numbers, patterns, silences, source behaviours — that establish the anomaly.
  inference: Your reasoned conclusion. The thing not visible in the raw data.
  confidence: "high" | "medium" | "low"
  confidence_reason: One sentence explaining your certainty level.
  implication: What this means for what comes next, or what it reveals about the actors.

High-quality insight examples:
  — 80% supportive coverage is BELOW the 90%+ baseline for AP government initiatives. The gap is not political — Sakshi (Congress-aligned) is supportive. It is implementation friction.
  — One outlet published 5 articles in one day. That is a manufactured burst, not a news event.
  — The principal's quotes disappear after day 12. That is a distancing signal, not a resolution.
  — CITU's opposition is territorial, not ideological — zone HQ = jobs = union membership growth.
  — A 5-day gap after the announcement is the bureaucratic absorption window, not inaction.

── OUTPUT 3 — THE PLAYERS ──
For each significant actor (maximum 5):
  name: Actor's name or organisation.
  role: Their role in this story: "Principal" | "Antagonist" | "Enabler" | "Bureaucratic executor" | "Media amplifier" | "Peripheral"
  presence_start: Day number (1-indexed from story start date) when they first appear.
  presence_end: Day number or "ongoing".
  behavior_pattern: How their engagement evolved — led then withdrew? Entered late? Escalated continuously?
  stated_position: What they said publicly.
  actual_agenda: Your inference about their real motivation. Be specific and bold.
  watch_for: The signal that would confirm your inference or trigger a new development.

Return ONLY a single valid JSON object with NO markdown fences, NO preamble, NO commentary after:
{"event_chain":[...],"insights":[...],"actors":[...]}"""

# ── Data fetcher ─────────────────────────────────────────────────────────────

async def _fetch_story_data(db, story_id: str) -> dict[str, Any]:
    cluster = (await db.execute(text("""
        SELECT c.story_id::text, c.representative_title,
               c.article_count, c.independent_source_count,
               c.importance_score, c.topic, c.subject_country
          FROM analytics.story_clusters c
         WHERE c.story_id = CAST(:sid AS uuid)
    """), {"sid": story_id})).fetchone()

    if not cluster:
        return {}

    timeline = (await db.execute(text("""
        SELECT first_seen_at::date AS first_seen,
               last_seen_at::date  AS last_seen,
               peak_at::date       AS peak_date,
               peak_articles_per_hour,
               velocity,
               span_hours,
               is_breaking,
               dormant_since::date AS dormant_since
          FROM analytics.story_timeline
         WHERE story_id = CAST(:sid AS uuid)
    """), {"sid": story_id})).fetchone()

    articles = (await db.execute(text("""
        SELECT a.title,
               a.collected_at::date AS pub_date,
               s.name               AS source,
               a.language_iso,
               m.attach_score
          FROM analytics.story_cluster_members m
          JOIN articles a ON a.id = m.article_id
          LEFT JOIN sources s ON s.id = a.source_id
         WHERE m.story_id = CAST(:sid AS uuid)
           AND m.attach_score >= 0.60
         ORDER BY a.collected_at ASC
    """), {"sid": story_id})).fetchall()

    quotes = (await db.execute(text("""
        SELECT sq.speaker, sq.quote_text_en, sq.is_direct,
               a.collected_at::date AS quote_date
          FROM analytics.story_quotes sq
          LEFT JOIN articles a ON a.id = sq.article_id
         WHERE sq.story_id = CAST(:sid AS uuid)
           AND sq.quote_text_en IS NOT NULL
         ORDER BY a.collected_at ASC
         LIMIT 30
    """), {"sid": story_id})).fetchall()

    stance = (await db.execute(text("""
        SELECT stance_distribution, sentiment, n_stances
          FROM analytics.story_stance
         WHERE story_id = CAST(:sid AS uuid)
    """), {"sid": story_id})).fetchone()

    facts = (await db.execute(text("""
        SELECT fact_key, unit, value_min, value_max, value_latest,
               member_count, single_source, sample_claim
          FROM analytics.story_facts
         WHERE story_id = CAST(:sid AS uuid)
         ORDER BY member_count DESC
         LIMIT 15
    """), {"sid": story_id})).fetchall()

    return {
        "cluster": cluster,
        "timeline": timeline,
        "articles": articles,
        "quotes": quotes,
        "stance": stance,
        "facts": facts,
    }


def _build_payload(data: dict[str, Any]) -> str:
    c = data["cluster"]
    tl = data.get("timeline")
    lines: list[str] = []

    lines.append(f"STORY: {c.representative_title or '(untitled)'}")
    lines.append(f"TOPIC: {c.topic or 'unclassified'}")
    lines.append(f"TOTAL ARTICLES: {c.article_count}")
    lines.append(f"INDEPENDENT SOURCES: {c.independent_source_count}")

    if tl:
        span_days = int(tl.span_hours / 24) if tl.span_hours else "?"
        lines.append(f"PERIOD: {tl.first_seen} to {tl.last_seen} ({span_days} days)")
        lines.append(f"PEAK DATE: {tl.peak_date} ({tl.peak_articles_per_hour} articles/hour)")
        if tl.velocity:
            lines.append(f"VELOCITY (first 6h): {tl.velocity:.3f} articles/hr")
        if tl.is_breaking:
            lines.append("STATUS: breaking news velocity detected at launch")
        if tl.dormant_since:
            lines.append(f"DORMANT SINCE: {tl.dormant_since}")

    lines.append("\nARTICLE TIMELINE (date | source | title | fit-score):")
    for a in data["articles"]:
        lines.append(f"  {a.pub_date} | {a.source or 'unknown'} | {a.title} | {a.attach_score:.2f}")

    lines.append("\nKEY QUOTES (speaker | date | type | text):")
    for q in data["quotes"]:
        kind = "direct" if q.is_direct else "attributed"
        text_en = (q.quote_text_en or "")[:220]
        lines.append(f'  [{q.speaker or "unknown"}, {q.quote_date}, {kind}]: "{text_en}"')

    if data.get("stance"):
        st = data["stance"]
        dist = st.stance_distribution or {}
        lines.append(f"\nSTANCE DISTRIBUTION: {json.dumps(dist)}")
        lines.append(f"STANCES MEASURED: {st.n_stances}")
        if st.sentiment:
            sent = st.sentiment
            lines.append(
                f"SENTIMENT: mean_intensity={float(sent.get('mean_intensity', 0)):.3f}, "
                f"n={sent.get('n', '?')}"
            )

    if data.get("facts"):
        lines.append("\nNUMERICAL FACTS:")
        for f in data["facts"]:
            rng = (
                f"{f.value_min}–{f.value_max}"
                if f.value_min != f.value_max
                else str(f.value_min)
            )
            src = "single-source" if f.single_source else f"{f.member_count} articles"
            lines.append(
                f'  {f.fact_key}: {rng} {f.unit or ""} ({src}) — e.g. "{f.sample_claim}"'
            )

    return "\n".join(lines)


# ── LLM call ─────────────────────────────────────────────────────────────────

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


async def _run_llm(payload: str) -> dict[str, Any] | None:
    try:
        from groq_client import generate  # noqa: PLC0415
    except Exception as exc:
        logger.warning("chronicle: groq unavailable: %s", exc)
        return None

    try:
        raw = await asyncio.wait_for(
            generate(system=_SYSTEM, user=payload, task_type="chronicle_generation"),
            timeout=55.0,
        )
    except asyncio.TimeoutError:
        logger.warning("chronicle: LLM timed out")
        return None
    except Exception as exc:
        logger.warning("chronicle: LLM error: %s", exc)
        return None

    raw = _THINK_RE.sub("", raw or "").strip()
    m = _JSON_RE.search(raw)
    if not m:
        logger.warning("chronicle: no JSON in LLM output")
        return None

    try:
        result = json.loads(m.group())
    except json.JSONDecodeError as exc:
        logger.warning("chronicle: JSON parse error: %s", exc)
        return None

    if not all(k in result for k in ("event_chain", "insights", "actors")):
        logger.warning("chronicle: missing required keys")
        return None

    return result


# ── V2: Two-phase windowed Chronicle generation ───────────────────────────────

_PHASE1_SYSTEM = """/no_think
Extract factual intelligence from news articles covering a specific time window.
Be concrete — extract actual events and actors, NOT topic summaries.
Note what is absent as much as what is present.

Return ONLY valid JSON (no markdown fences):
{
  "window_summary": "2-3 factual sentences of what concretely happened",
  "concrete_events": ["specific action / decision / announcement — not a topic"],
  "active_actors": ["ActorName: what they did or said"],
  "tone": "neutral|supportive|critical|alarmed|manufactured — one word + one sentence why",
  "notable_quotes": ["speaker: quote (max 120 chars)"],
  "silence": "what you would expect covered here but was not — or null"
}"""

_PHASE2_SYSTEM = """/no_think

You are a senior political intelligence analyst. A client has paid for a deep investigative briefing.
You have structured intelligence extracted window-by-window from a full news story arc.

Your job is NOT to summarise. Your job is to REASON.
Think like a CNN investigative reporter who has read every window, noticed every anomaly — who can
explain what the arc of data really means, not just what each window contained.

CROSS-WINDOW MANDATE — the only reason Phase 2 exists:
  — What caused the SHIFT between window N and window N+1? What happened in the gap?
  — Where did coverage go silent precisely when it should have been loudest?
  — What patterns are ONLY visible across the full arc — invisible in any single window?
  — Who entered or vanished at precise moments — and what does the timing reveal?
  — What do the GAPS and silences tell you that the articles never say outright?

── OUTPUT 1 — EVENT CHAIN ──
Reconstruct the full arc as 5–9 causally linked real-world events. Each event MUST be a
concrete action in the real world — not "coverage increased" but "the Minister announced X".

For each event:
  date: "YYYY-MM-DD" (pick the most specific date you can anchor to evidence)
  event: What actually happened. Who acted. What changed, was announced, blocked, or revealed.
  why_it_happened: Your inference about the root cause — cross-window logic welcome here.
    Reference specific evidence. Explain the political, institutional, or social logic behind
    the timing. Two or three analytical sentences minimum.
  caused: The explicit mechanism linking this event to what came next. Be specific.
  evidence: 1–3 partial article titles that establish this event actually happened.
  key_quote: One powerful translated quote from the data, or null.
  signal_type: "organic" | "manufactured" | "reactive" | "escalation" | "dormant" | "resolution"

Events must be causally linked. The "caused" of event N must connect directly to event N+1.

── OUTPUT 2 — INSIGHT BOMBS ──
4–6 deductions a reader could NOT make by reading any single window — or even all windows
individually. These are the cross-arc revelations that reframe everything.

For each insight:
  question: The anomaly. Start with "Why" or "What explains".
  evidence: The specific data — numbers, patterns, silences, source behaviours, timing — that
    establish the anomaly. Be concrete. Cite window numbers, article counts, actor names.
  inference: Your reasoned conclusion. The thing invisible in the raw data. Be bold.
  confidence: "high" | "medium" | "low"
  confidence_reason: One sentence explaining your certainty level.
  implication: What this means for what comes next, or what it reveals about the actors.

Calibration examples of HIGH-QUALITY insights (your outputs should match this standard):
  — "80% supportive coverage is BELOW the 90%+ baseline for AP government initiatives. The gap
     is not political — Sakshi (Congress-aligned) is supportive. It is implementation friction."
  — "One outlet published 5 articles in a single day. That is a manufactured burst, not a news event."
  — "The principal's quotes disappear after window 4. That is a distancing signal, not a resolution."
  — "CITU's opposition is territorial, not ideological — zone HQ = jobs = union membership growth."
  — "A 5-day silence after the announcement is the bureaucratic absorption window, not inaction."
  — "Coverage spiked 400% in window 5 but the GoM had not issued any new findings. The spike is
     media amplification of a stale story, engineered to keep the narrative alive."

── OUTPUT 3 — THE PLAYERS ──
For each significant actor (maximum 5):
  name: Actor's name or organisation.
  role: "Principal" | "Antagonist" | "Enabler" | "Bureaucratic executor" | "Media amplifier" | "Peripheral"
  presence_start: Day number (1-indexed from story start) when they first appear in the data.
  presence_end: Day number or "ongoing".
  behavior_pattern: How their engagement evolved across the windows — led then withdrew?
    Entered late? Escalated continuously? Went quiet at a suspicious moment?
  stated_position: What they said publicly.
  actual_agenda: Your inference about their real motivation. Be specific and bold.
    Use cross-window evidence — what changed in their behaviour across the arc?
  watch_for: The signal that would confirm your inference or trigger a new development.

Return ONLY a single valid JSON object — NO markdown fences, NO preamble, NO commentary after:
{"event_chain":[...],"insights":[...],"actors":[...]}"""


def _bucket_by_window(articles: list, window_days: int = 3) -> list[dict]:
    """Group articles into fixed-size date windows, skipping empty ones."""
    if not articles:
        return []
    windows: list[dict] = []
    current: list = []
    window_start = articles[0].pub_date
    for a in articles:
        if (a.pub_date - window_start).days >= window_days and current:
            windows.append({"start": window_start, "end": current[-1].pub_date, "articles": current})
            current = [a]
            window_start = a.pub_date
        else:
            current.append(a)
    if current:
        windows.append({"start": window_start, "end": current[-1].pub_date, "articles": current})
    return windows


async def _fetch_story_data_v2(db, story_id: str) -> dict[str, Any]:
    """Like _fetch_story_data but includes article text for Phase 1 extraction."""
    cluster = (await db.execute(text("""
        SELECT c.story_id::text, c.representative_title,
               c.article_count, c.independent_source_count,
               c.importance_score, c.topic, c.subject_country
          FROM analytics.story_clusters c
         WHERE c.story_id = CAST(:sid AS uuid)
    """), {"sid": story_id})).fetchone()

    if not cluster:
        return {}

    timeline = (await db.execute(text("""
        SELECT first_seen_at::date AS first_seen,
               last_seen_at::date  AS last_seen,
               peak_at::date       AS peak_date,
               peak_articles_per_hour, velocity,
               span_hours, is_breaking, dormant_since::date AS dormant_since
          FROM analytics.story_timeline
         WHERE story_id = CAST(:sid AS uuid)
    """), {"sid": story_id})).fetchone()

    # Extended article fetch — includes text content for Phase 1
    articles = (await db.execute(text("""
        SELECT a.title,
               a.collected_at::date      AS pub_date,
               s.name                    AS source,
               a.language_iso,
               a.lead_text_translated,
               a.summary_preview,
               m.attach_score
          FROM analytics.story_cluster_members m
          JOIN articles a ON a.id = m.article_id
          LEFT JOIN sources s ON s.id = a.source_id
         WHERE m.story_id = CAST(:sid AS uuid)
           AND m.attach_score >= 0.90
         ORDER BY a.collected_at ASC
    """), {"sid": story_id})).fetchall()

    quotes = (await db.execute(text("""
        SELECT sq.speaker, sq.quote_text_en, sq.is_direct,
               a.collected_at::date AS quote_date
          FROM analytics.story_quotes sq
          LEFT JOIN articles a ON a.id = sq.article_id
         WHERE sq.story_id = CAST(:sid AS uuid)
           AND sq.quote_text_en IS NOT NULL
         ORDER BY a.collected_at ASC LIMIT 30
    """), {"sid": story_id})).fetchall()

    facts = (await db.execute(text("""
        SELECT fact_key, unit, value_min, value_max, value_latest,
               member_count, single_source, sample_claim
          FROM analytics.story_facts
         WHERE story_id = CAST(:sid AS uuid)
         ORDER BY member_count DESC LIMIT 15
    """), {"sid": story_id})).fetchall()

    return {"cluster": cluster, "timeline": timeline, "articles": articles,
            "quotes": quotes, "facts": facts}


async def _run_phase1_window(window: dict, prev_summary: str | None) -> dict:
    """Phase 1: extract structured intelligence from one time window."""
    lines: list[str] = [
        f"WINDOW: {window['start']} → {window['end']} ({len(window['articles'])} articles)",
    ]
    if prev_summary:
        lines.append(f"PREVIOUS WINDOW: {prev_summary}")

    lines.append("\nARTICLES:")
    for a in window["articles"]:
        lines.append(f"\n[{a.pub_date} | {a.source or 'unknown'}] {a.title}")
        body = (a.lead_text_translated or a.summary_preview or "").strip()
        if body:
            lines.append(f"  {body[:380]}")

    try:
        from groq_client import generate  # noqa: PLC0415
        raw = await asyncio.wait_for(
            generate(system=_PHASE1_SYSTEM, user="\n".join(lines), task_type="chronicle_generation"),
            timeout=35.0,
        )
    except Exception as exc:
        logger.warning("chronicle v2 phase1 error (window %s): %s", window["start"], exc)
        return {"window_summary": f"{window['start']}→{window['end']}: extraction failed"}

    raw = _THINK_RE.sub("", raw or "").strip()
    m = _JSON_RE.search(raw)
    if not m:
        return {"window_summary": f"{window['start']}→{window['end']}: no JSON"}
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return {"window_summary": f"{window['start']}→{window['end']}: parse error"}


async def _run_phase2_synthesis(
    cluster: Any,
    timeline: Any,
    windows: list[dict],
    extractions: list[dict],
) -> dict[str, Any] | None:
    """Phase 2: cross-window reasoning → final Chronicle JSON."""
    span_days = int(timeline.span_hours / 24) if timeline and timeline.span_hours else "?"
    lines: list[str] = [
        f"STORY: {cluster.representative_title or '(untitled)'}",
        f"PERIOD: {getattr(timeline, 'first_seen', '?')} to {getattr(timeline, 'last_seen', '?')} ({span_days} days)",
        f"TOTAL ARTICLES: {cluster.article_count}  |  WINDOWS ANALYZED: {len(windows)}",
        "=" * 64,
    ]
    for i, (win, ext) in enumerate(zip(windows, extractions)):
        lines.append(
            f"\n── WINDOW {i + 1}/{len(windows)}: {win['start']} → {win['end']}"
            f" ({len(win['articles'])} articles) ──"
        )
        lines.append(f"SUMMARY: {ext.get('window_summary', '(unavailable)')}")
        for ev in (ext.get("concrete_events") or [])[:4]:
            lines.append(f"  EVENT: {ev}")
        for ac in (ext.get("active_actors") or [])[:3]:
            lines.append(f"  ACTOR: {ac}")
        tone = ext.get("tone")
        if tone:
            lines.append(f"  TONE: {tone}")
        silence = ext.get("silence")
        if silence:
            lines.append(f"  SILENCE: {silence}")
        for q in (ext.get("notable_quotes") or [])[:2]:
            lines.append(f"  QUOTE: {q}")

    try:
        from groq_client import generate  # noqa: PLC0415
        raw = await asyncio.wait_for(
            generate(system=_PHASE2_SYSTEM, user="\n".join(lines), task_type="chronicle_generation"),
            timeout=60.0,
        )
    except Exception as exc:
        logger.warning("chronicle v2 phase2 error: %s", exc)
        return None

    raw = _THINK_RE.sub("", raw or "").strip()
    m = _JSON_RE.search(raw)
    if not m:
        logger.warning("chronicle v2 phase2: no JSON in output")
        return None
    try:
        result = json.loads(m.group())
    except json.JSONDecodeError as exc:
        logger.warning("chronicle v2 phase2: JSON parse error: %s", exc)
        return None
    if not all(k in result for k in ("event_chain", "insights", "actors")):
        logger.warning("chronicle v2 phase2: missing required keys")
        return None
    return result


async def _run_chronicle_v2(data: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict]]:
    """Orchestrate two-phase windowed Chronicle. Returns (result, window_extractions)."""
    articles = data.get("articles", [])
    if not articles:
        return None, []

    windows = _bucket_by_window(articles, window_days=3)
    logger.info("chronicle v2: %d articles → %d windows", len(articles), len(windows))

    extractions: list[dict] = []
    prev_summary: str | None = None
    for win in windows:
        ext = await _run_phase1_window(win, prev_summary)
        extractions.append(ext)
        prev_summary = ext.get("window_summary")
        logger.info(
            "chronicle v2 phase1 %s→%s: %d events extracted",
            win["start"], win["end"],
            len(ext.get("concrete_events") or []),
        )

    result = await _run_phase2_synthesis(
        data["cluster"], data.get("timeline"), windows, extractions
    )

    # Attach per-window intelligence to the result so the frontend can render
    # the Coverage Arc and detected silences without a separate API call.
    if result:
        result["windows"] = [
            {
                "start": str(w["start"]),
                "end": str(w["end"]),
                "n_articles": len(w["articles"]),
                "summary": ext.get("window_summary"),
                "tone": ext.get("tone"),
                "silence": ext.get("silence"),
            }
            for w, ext in zip(windows, extractions)
        ]

    return result, extractions


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/api/chronicle/mine")
async def my_chronicles(
    principal: dict = Depends(get_current_principal),
) -> dict[str, Any]:
    """List the Chronicles an admin has pushed to the current user (fast — no LLM).

    Declared before the ``/{story_id}`` route so the static ``mine`` path wins.
    """
    user_id = principal["id"]
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT c.story_id::text                    AS story_id,
                   c.representative_title,
                   c.article_count,
                   c.independent_source_count,
                   c.topic,
                   t.first_seen_at::date              AS first_seen,
                   t.last_seen_at::date               AS last_seen,
                   t.span_hours,
                   usa.label                          AS label,
                   usa.assigned_at,
                   (cc.story_id IS NOT NULL)          AS has_cache
              FROM analytics.user_story_assignments usa
              JOIN analytics.story_clusters c
                     ON c.story_id = usa.story_id
              LEFT JOIN analytics.story_timeline t
                     ON t.story_id = c.story_id
              LEFT JOIN analytics.chronicle_cache cc
                     ON cc.story_id = c.story_id
                    AND cc.generated_at > now() - INTERVAL '24 hours'
             WHERE usa.user_id = CAST(:uid AS uuid)
             ORDER BY usa.assigned_at DESC
        """), {"uid": user_id})).fetchall()

    items = [
        {
            "story_id": r.story_id,
            "title": r.representative_title or "Untitled Story",
            "article_count": r.article_count,
            "source_count": r.independent_source_count,
            "topic": r.topic,
            "first_seen": str(r.first_seen) if r.first_seen else None,
            "last_seen": str(r.last_seen) if r.last_seen else None,
            "span_days": int(r.span_hours / 24) if r.span_hours else None,
            "label": r.label,
            "assigned_at": r.assigned_at.isoformat() if r.assigned_at else None,
            "ready": bool(r.has_cache),
        }
        for r in rows
    ]
    return {"items": items, "count": len(items)}


@router.get("/api/chronicle/{story_id}/meta")
async def chronicle_meta(
    story_id: str,
    principal: dict = Depends(get_current_principal),
) -> dict[str, Any]:
    """Story header metadata + assignment verification (fast — no LLM)."""
    user_id = principal["id"]
    async with get_db() as db:
        row = (await db.execute(text("""
            SELECT c.story_id::text,
                   c.representative_title,
                   c.article_count,
                   c.independent_source_count,
                   c.topic,
                   t.first_seen_at::date AS first_seen,
                   t.last_seen_at::date  AS last_seen,
                   t.span_hours,
                   usa.label AS assignment_label,
                   usa.assigned_at
              FROM analytics.story_clusters c
              LEFT JOIN analytics.story_timeline t
                     ON t.story_id = c.story_id
              LEFT JOIN analytics.user_story_assignments usa
                     ON usa.story_id = c.story_id
                    AND usa.user_id = CAST(:uid AS uuid)
             WHERE c.story_id = CAST(:sid AS uuid)
        """), {"uid": user_id, "sid": story_id})).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Story not found")

    assigned = row.assignment_label is not None or row.assigned_at is not None
    if not assigned and not principal.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Story not assigned to this user")

    return {
        "story_id": story_id,
        "title": row.representative_title or "Untitled Story",
        "article_count": row.article_count,
        "source_count": row.independent_source_count,
        "topic": row.topic,
        "first_seen": str(row.first_seen) if row.first_seen else None,
        "last_seen": str(row.last_seen) if row.last_seen else None,
        "span_days": int(row.span_hours / 24) if row.span_hours else None,
        "label": row.assignment_label,
    }


@router.get("/api/chronicle/{story_id}/v2-compare")
async def compare_v1_v2(
    story_id: str,
    principal: dict = Depends(get_current_principal),
) -> dict[str, Any]:
    """Generate a v2 Chronicle and return it alongside the cached v1 for comparison.
    Does NOT overwrite the v1 cache. Super-admin only (test endpoint).
    """
    if not principal.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Super-admin only")

    # ── Pull cached v1 ──────────────────────────────────────────────────────
    v1: dict[str, Any] | None = None
    async with get_db() as db:
        cached = (await db.execute(text("""
            SELECT payload FROM analytics.chronicle_cache
             WHERE story_id = CAST(:sid AS uuid)
        """), {"sid": story_id})).fetchone()
        if cached:
            v1 = cached.payload

    # ── Generate v2 (no cache write) ────────────────────────────────────────
    async with get_db() as db:
        data = await _fetch_story_data_v2(db, story_id)
    if not data or not data.get("cluster"):
        raise HTTPException(status_code=404, detail="Story not found")

    v2_result, window_extractions = await _run_chronicle_v2(data)

    # ── Build diff summary ──────────────────────────────────────────────────
    def event_bullets(chain: list) -> list[str]:
        return [f"{e.get('date','?')} [{e.get('signal_type','?')}]: {e.get('event','')[:120]}"
                for e in (chain or [])]

    def insight_bullets(insights: list) -> list[str]:
        return [f"{ins.get('question','')[:120]} [confidence={ins.get('confidence','?')}]"
                for ins in (insights or [])]

    v1_events   = event_bullets(v1.get("event_chain", []) if v1 else [])
    v2_events   = event_bullets(v2_result.get("event_chain", []) if v2_result else [])
    v1_insights = insight_bullets(v1.get("insights", []) if v1 else [])
    v2_insights = insight_bullets(v2_result.get("insights", []) if v2_result else [])

    windows_summary = [
        {
            "window": f"{w['start']}→{w['end']}",
            "n_articles": len(w["articles"]),
            "summary": ext.get("window_summary"),
            "events": ext.get("concrete_events", []),
            "silence": ext.get("silence"),
            "tone": ext.get("tone"),
        }
        for w, ext in zip(
            _bucket_by_window(data["articles"], window_days=3),
            window_extractions,
        )
    ]

    return {
        "story_id": story_id,
        "story_title": data["cluster"].representative_title,
        "article_count": data["cluster"].article_count,
        "n_windows": len(windows_summary),

        "v1": {
            "strategy": "single-pass (titles only)",
            "n_events": len(v1_events),
            "n_insights": len(v1.get("insights", [])) if v1 else 0,
            "n_actors": len(v1.get("actors", [])) if v1 else 0,
            "events": v1_events,
            "insights": v1_insights,
        },

        "v2": {
            "strategy": "two-phase windowed (reads article text)",
            "n_windows_processed": len(windows_summary),
            "n_events": len(v2_events),
            "n_insights": len(v2_result.get("insights", [])) if v2_result else 0,
            "n_actors": len(v2_result.get("actors", [])) if v2_result else 0,
            "events": v2_events,
            "insights": v2_insights,
            "windows": windows_summary,
            "full_result": v2_result,
        },
    }


@router.get("/api/chronicle/{story_id}/articles")
async def get_chronicle_articles(
    story_id: str,
    principal: dict = Depends(get_current_principal),
) -> dict[str, Any]:
    """Source articles used to build this Chronicle (requires assignment)."""
    user_id = principal["id"]
    async with get_db() as db:
        assigned = (await db.execute(text("""
            SELECT 1 FROM analytics.user_story_assignments
             WHERE user_id = CAST(:uid AS uuid)
               AND story_id = CAST(:sid AS uuid)
        """), {"uid": user_id, "sid": story_id})).fetchone()

        if not assigned and not principal.get("is_super_admin"):
            raise HTTPException(status_code=403, detail="Story not assigned to this user")

        rows = (await db.execute(text("""
            SELECT a.title,
                   a.url,
                   a.collected_at::date AS pub_date,
                   s.name               AS source,
                   m.attach_score
              FROM analytics.story_cluster_members m
              JOIN articles a ON a.id = m.article_id
              LEFT JOIN sources s ON s.id = a.source_id
             WHERE m.story_id = CAST(:sid AS uuid)
               AND m.attach_score >= 0.60
             ORDER BY m.attach_score DESC, a.collected_at DESC
             LIMIT 80
        """), {"sid": story_id})).fetchall()

    return {
        "story_id": story_id,
        "articles": [
            {
                "title": r.title,
                "url": r.url,
                "pub_date": str(r.pub_date) if r.pub_date else None,
                "source": r.source or "Unknown",
                "attach_score": round(float(r.attach_score), 2) if r.attach_score else None,
            }
            for r in rows
        ],
    }


@router.get("/api/chronicle/{story_id}")
async def get_chronicle(
    story_id: str,
    principal: dict = Depends(get_current_principal),
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Full Chronicle analysis — V2 two-phase windowed pipeline, cached 24h per story.

    Cache is keyed on model_version='qwen3-32b-v2'. Old V1 caches are treated as
    misses so they regenerate automatically on first open.
    """
    user_id = principal["id"]

    async with get_db() as db:
        # Assignment gate
        assigned = (await db.execute(text("""
            SELECT 1 FROM analytics.user_story_assignments
             WHERE user_id = CAST(:uid AS uuid)
               AND story_id = CAST(:sid AS uuid)
        """), {"uid": user_id, "sid": story_id})).fetchone()

        if not assigned and not principal.get("is_super_admin"):
            raise HTTPException(status_code=403, detail="Story not assigned to this user")

        # Cache read — only accept V2 cache entries
        if not force_refresh:
            cached = (await db.execute(text("""
                SELECT payload, generated_at
                  FROM analytics.chronicle_cache
                 WHERE story_id = CAST(:sid AS uuid)
                   AND generated_at > now() - INTERVAL '24 hours'
                   AND model_version = 'qwen3-32b-v2'
            """), {"sid": story_id})).fetchone()

            if cached:
                return {
                    "story_id": story_id,
                    "cached": True,
                    "generated_at": cached.generated_at.isoformat(),
                    **cached.payload,
                }

        # V2 data fetch — includes article text, threshold 0.90
        data = await _fetch_story_data_v2(db, story_id)

    if not data or not data.get("cluster"):
        raise HTTPException(status_code=404, detail="Story not found")

    cluster = data["cluster"]

    # V2: two-phase windowed LLM generation (outside DB context)
    result, _extractions = await _run_chronicle_v2(data)
    if not result:
        raise HTTPException(
            status_code=503,
            detail="Chronicle analysis temporarily unavailable — try again in a moment",
        )

    # Cache write — result already includes the `windows` field from _run_chronicle_v2
    async with get_db() as db:
        await db.execute(text("""
            INSERT INTO analytics.chronicle_cache
                        (story_id, payload, model_version)
            VALUES (CAST(:sid AS uuid), CAST(:payload AS jsonb), 'qwen3-32b-v2')
            ON CONFLICT (story_id) DO UPDATE
               SET payload       = EXCLUDED.payload,
                   generated_at  = now(),
                   model_version = EXCLUDED.model_version
        """), {"sid": story_id, "payload": json.dumps(result)})
        await db.commit()

    return {
        "story_id": story_id,
        "title": cluster.representative_title or "Untitled Story",
        "article_count": cluster.article_count,
        "cached": False,
        **result,
    }


# ── Admin endpoints ───────────────────────────────────────────────────────────

class AssignIn(BaseModel):
    user_id: str
    story_id: str
    label: str | None = None


@router.post("/api/admin/chronicle/assign")
async def assign_story(
    body: AssignIn,
    principal: dict = Depends(require_super_admin),
) -> dict[str, Any]:
    """Assign a story to a user so they can access its Chronicle."""
    async with get_db() as db:
        await db.execute(text("""
            INSERT INTO analytics.user_story_assignments
                        (user_id, story_id, assigned_by, label)
            VALUES (CAST(:uid AS uuid), CAST(:sid AS uuid), :by, :label)
            ON CONFLICT (user_id, story_id) DO UPDATE
               SET label = EXCLUDED.label,
                   assigned_by = EXCLUDED.assigned_by
        """), {
            "uid": body.user_id,
            "sid": body.story_id,
            "by": principal["email"],
            "label": body.label,
        })
        await db.commit()
    return {"ok": True, "user_id": body.user_id, "story_id": body.story_id}


class UnassignIn(BaseModel):
    user_id: str
    story_id: str


@router.delete("/api/admin/chronicle/assign")
async def unassign_story(
    body: UnassignIn,
    principal: dict = Depends(require_super_admin),
) -> dict[str, Any]:
    """Remove a story assignment."""
    async with get_db() as db:
        await db.execute(text("""
            DELETE FROM analytics.user_story_assignments
             WHERE user_id = CAST(:uid AS uuid)
               AND story_id = CAST(:sid AS uuid)
        """), {"uid": body.user_id, "sid": body.story_id})
        await db.commit()
    return {"ok": True}


@router.get("/api/admin/chronicle/assignments")
async def list_assignments(
    principal: dict = Depends(require_super_admin),
) -> dict[str, Any]:
    """List all story assignments with user + story metadata."""
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT usa.user_id::text,
                   u.email,
                   u.full_name,
                   usa.story_id::text,
                   c.representative_title AS story_title,
                   usa.label,
                   usa.assigned_at,
                   usa.assigned_by,
                   (
                     SELECT cc.generated_at
                       FROM analytics.chronicle_cache cc
                      WHERE cc.story_id = usa.story_id
                   ) AS cache_generated_at
              FROM analytics.user_story_assignments usa
              LEFT JOIN analytics.users u ON u.id = usa.user_id
              LEFT JOIN analytics.story_clusters c ON c.story_id = usa.story_id
             ORDER BY usa.assigned_at DESC
        """))).fetchall()

    return {
        "assignments": [
            {
                "user_id": r.user_id,
                "email": r.email,
                "full_name": r.full_name,
                "story_id": r.story_id,
                "story_title": r.story_title,
                "label": r.label,
                "assigned_at": r.assigned_at.isoformat() if r.assigned_at else None,
                "assigned_by": r.assigned_by,
                "cached": r.cache_generated_at is not None,
                "cache_generated_at": r.cache_generated_at.isoformat() if r.cache_generated_at else None,
            }
            for r in rows
        ]
    }
