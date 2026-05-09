"""
Phase 3 — quote / sentiment / framing extraction.

For each newsroom_segments row produced by Phase 2, we ask the LLM
(Groq with auto-failover to Cerebras) to classify:

  is_quote      — does this segment contain a direct quote?
  is_editorial  — anchor opinion vs reported speech (e.g. anchor
                  saying "this is outrageous" vs anchor saying
                  "the CM said it was outrageous")
  sentiment     — float -1..+1 (negative ↔ positive)
  framing       — one of {adversarial, aligned, neutral} relative to
                  whatever entity is the segment's primary subject

Idempotency: rows with framing IS NOT NULL are considered already
processed and skipped on re-run.

Driven by:
  - Beat tick `extract-quotes-every-5-min` (added to celery_app.py)
  - Direct call from process_broadcast.py orchestrator after segments
    are written, so VOD ingestion is fully classified before the
    task returns.

Batched 8 segments per LLM call. One VOD of ~30 minutes typically
classifies in 25 calls / ~20 K tokens — well within Cerebras quota.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import psycopg2
import psycopg2.extras

from backend.celery_app import app
from backend.nlp.groq_client import call_groq, GroqCallFailed, GroqQuotaExhausted

logger = logging.getLogger(__name__)


def _pg_url() -> str:
    return os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://rig:rigpassword@rig-postgres:5432/rig",
    )


_BATCH_SIZE = 8
_VALID_FRAMING = {"adversarial", "aligned", "neutral"}

_SYSTEM_PROMPT = (
    "You are a political-media classifier. For each transcript segment, "
    "decide:\n"
    "  is_quote (bool): does the segment contain a direct quote spoken by "
    "    a named person — NOT just the anchor's narration?\n"
    "  is_editorial (bool): is the speaker pushing an OPINION as anchor "
    "    (\"this is outrageous\", \"the government has failed\") rather "
    "    than reporting fact or relaying someone else's quote?\n"
    "  sentiment (float -1..1): emotional tone, -1=hostile/critical, "
    "    0=neutral/factual, +1=praise/celebratory.\n"
    "  framing (string): adversarial / aligned / neutral. \"Adversarial\" "
    "    when the segment attacks or undermines its primary subject; "
    "    \"aligned\" when it defends or boosts; \"neutral\" otherwise.\n"
    "Output STRICT JSON only — no prose, no markdown."
)


@app.task(
    name="tasks.newsroom.extract_quotes",
    queue="nlp",
    max_retries=2,
)
def extract_quotes(broadcast_id: str | None = None, limit: int = 200) -> dict:
    """Classify unprocessed segments. If broadcast_id is given, scoped
    to that broadcast; otherwise picks up the oldest unclassified
    segments globally up to `limit`.

    Returns counts per classification + skipped.
    """
    conn = psycopg2.connect(_pg_url())
    conn.autocommit = False
    stats = {"updated": 0, "skipped": 0, "batches": 0, "errors": 0}

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if broadcast_id:
                cur.execute(
                    """
                    SELECT id, text_native, text_en
                      FROM newsroom_segments
                     WHERE broadcast_id = %s
                       AND framing IS NULL
                     ORDER BY start_sec
                     LIMIT %s
                    """,
                    (broadcast_id, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, text_native, text_en
                      FROM newsroom_segments
                     WHERE framing IS NULL
                     ORDER BY created_at ASC
                     LIMIT %s
                    """,
                    (limit,),
                )
            rows = cur.fetchall()

        if not rows:
            return stats

        for batch_start in range(0, len(rows), _BATCH_SIZE):
            batch = rows[batch_start:batch_start + _BATCH_SIZE]
            try:
                results = asyncio.run(_classify_batch(batch))
            except (GroqCallFailed, GroqQuotaExhausted) as exc:
                logger.warning("extract_quotes: LLM batch failed: %s", exc)
                stats["errors"] += 1
                continue

            stats["batches"] += 1

            with conn.cursor() as cur:
                for seg, cls in zip(batch, results):
                    framing = (cls.get("framing") or "").lower()
                    if framing not in _VALID_FRAMING:
                        framing = "neutral"
                    sentiment = cls.get("sentiment")
                    try:
                        sentiment = max(-1.0, min(1.0, float(sentiment)))
                    except (TypeError, ValueError):
                        sentiment = 0.0
                    cur.execute(
                        """
                        UPDATE newsroom_segments
                           SET is_quote     = %s,
                               is_editorial = %s,
                               sentiment    = %s,
                               framing      = %s
                         WHERE id = %s
                        """,
                        (
                            bool(cls.get("is_quote")),
                            bool(cls.get("is_editorial")),
                            sentiment,
                            framing,
                            seg["id"],
                        ),
                    )
                    stats["updated"] += 1
            conn.commit()

        return stats
    except Exception:
        conn.rollback()
        logger.exception("extract_quotes failed")
        raise
    finally:
        conn.close()


async def _classify_batch(rows) -> list[dict]:
    """Send a batch of segments to the LLM, return list of classification
    dicts in the same order."""
    items = []
    for i, r in enumerate(rows):
        text = r["text_en"] or r["text_native"] or ""
        items.append({"i": i, "text": text[:600]})

    user_prompt = (
        "Classify each item. Output: "
        "{\"items\": {\"0\": {...}, \"1\": {...}, ...}} where each entry has "
        "is_quote (bool), is_editorial (bool), sentiment (float -1..1), "
        "framing (str: adversarial/aligned/neutral).\n"
        f"Input:\n{json.dumps(items, ensure_ascii=False)}"
    )

    raw = await call_groq(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        task_type="brief_generation",
        json_response=True,
    )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [{} for _ in rows]

    items_out = parsed.get("items", {}) if isinstance(parsed, dict) else {}
    out: list[dict] = []
    for i in range(len(rows)):
        e = items_out.get(str(i)) or items_out.get(i) or {}
        if not isinstance(e, dict):
            e = {}
        out.append(e)
    return out
