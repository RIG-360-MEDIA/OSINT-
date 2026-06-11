"""Stage 2B — single-source interrogation (Mode B).

When a cluster has only ONE article (singletons that Stage 0 didn't merge
in, or stories with a sole reporter), we cannot triangulate. Instead we
interrogate the article: ask whether each SPO claim is sourced, hedged,
contradicted internally, or unverifiable. The output drives Stage 4's body
composer to either elevate or downplay each claim.

Does NOT depend on Stage 2A's triangulation table — operates directly on
`article_claims` rows for a single article.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from sqlalchemy import text

from backend.database import get_db
from backend.nlp.groq_client import (
    FAST_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logger = logging.getLogger(__name__)


INTERROGATION_SYS = """You are a fact-checker reading a single news article.
For each (subject, predicate, object) claim provided, return STRICT JSON:
{
  "claims": [
    {
      "claim_id": "<id from input>",
      "status": "sourced" | "hedged" | "contradicted" | "unverifiable",
      "evidence": "<brief quote or paraphrase from the body, <=120 chars>",
      "confidence": 0.0 - 1.0
    }
  ]
}

status meanings:
  sourced       — claim has a named source / attribution / numerical anchor in the body.
  hedged        — body uses "reportedly", "allegedly", "may", etc. without firm sourcing.
  contradicted  — another sentence in the body refutes or significantly weakens this claim.
  unverifiable  — claim appears once with no source and no contradiction.

No prose outside the JSON. No markdown fences.
"""


@dataclass(frozen=True)
class InterrogatedClaim:
    claim_id: str
    status: str
    evidence: str
    confidence: float


async def interrogate_article(article_id: str) -> list[InterrogatedClaim]:
    """Interrogate every SPO claim in `article_id`. Returns annotated claims."""
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT id::text AS cid, subject_text, predicate, object_text, claim_text
              FROM article_claims
             WHERE article_id::text = :aid
               AND subject_text IS NOT NULL
               AND predicate IS NOT NULL
               AND object_text IS NOT NULL
        """), {"aid": article_id})).mappings().all()
        body_row = (await db.execute(text("""
            SELECT COALESCE(NULLIF(full_text_translated, ''), full_text_scraped) AS body
              FROM articles WHERE id::text = :aid
        """), {"aid": article_id})).mappings().first()
    if not rows or not body_row or not body_row["body"]:
        return []

    payload = {
        "body": (body_row["body"] or "")[:6000],
        "claims": [
            {
                "claim_id": r["cid"],
                "subject": r["subject_text"],
                "predicate": r["predicate"],
                "object": r["object_text"],
            }
            for r in rows
        ],
    }
    user = (
        "ARTICLE BODY:\n" + payload["body"] + "\n\nCLAIMS TO INTERROGATE:\n"
        + json.dumps(payload["claims"], ensure_ascii=False) + "\n\nReturn the JSON object."
    )
    try:
        raw = await call_groq(
            system=INTERROGATION_SYS,
            user=user,
            model=FAST_MODEL,
            task_type="classification",
            json_response=True,
            max_tokens_override=1200,
        )
    except (GroqCallFailed, GroqQuotaExhausted) as e:
        logger.warning("interrogate failed on %s: %s", article_id, e)
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("interrogate JSON parse failed on %s", article_id)
        return []
    items = parsed.get("claims") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return []
    out: list[InterrogatedClaim] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        out.append(InterrogatedClaim(
            claim_id=str(it.get("claim_id", "")),
            status=str(it.get("status", "unverifiable")),
            evidence=str(it.get("evidence", ""))[:240],
            confidence=float(it.get("confidence") or 0.0),
        ))
    return out
