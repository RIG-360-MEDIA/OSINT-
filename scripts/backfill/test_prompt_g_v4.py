"""test_prompt_g_v4.py — Validate a fix for the article_claims placeholder bug.

Picks N articles from sources where subject_text='article' is dominant,
re-runs the claims-extraction LLM with the OLD prompt and a candidate NEW
prompt side-by-side, and reports the comparison.

The NEW prompt adds explicit instructions:
  - subject MUST be a named entity (person / organization / place)
  - subject must NEVER be a generic noun like "article", "story", "report"
  - if no clear named subject can be found, OMIT that claim

This script does NOT write to the DB — it only prints the comparison.

Run inside rig-backend:
    docker exec rig-backend python /app/scripts/backfill/test_prompt_g_v4.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402
from backend.nlp.groq_client import call_groq  # noqa: E402

# ── Prompts ────────────────────────────────────────────────────────────────

OLD_PROMPT = (
    "You extract factual claims and attributed quotes from a news article. "
    "Return STRICT JSON: { "
    "claims: [{text: 'short factual claim', subject: 'entity name', "
    "predicate: 'verb-phrase', object: 'short object'}, ...] (max 6), "
    "quotes: [{speaker: 'name AS WRITTEN in source', "
    "speaker_en: 'speaker name in natural English/transliterated', "
    "text: 'exact quote in source language', "
    "text_en: 'natural English translation of the quote', "
    "is_direct: true|false}, ...] (max 6) }. "
    "If the source article is already in English, set speaker_en "
    "= speaker and text_en = text (just normalised). For non-English "
    "articles (Telugu, Tamil, Bengali, Hindi etc.), translate "
    "faithfully — preserve meaning over literal word order. "
    "Skip opinion / editorial commentary — only verifiable factual claims. "
    "No prose outside JSON. No fences."
)

# Candidate v4 prompt — adds explicit subject-must-be-named-entity rule
NEW_PROMPT = (
    "You extract factual claims and attributed quotes from a news article. "
    "Return STRICT JSON: { "
    "claims: [{text: 'short factual claim', subject: 'named entity', "
    "predicate: 'verb-phrase', object: 'short object'}, ...] (max 6), "
    "quotes: [{speaker: 'name AS WRITTEN in source', "
    "speaker_en: 'speaker name in natural English/transliterated', "
    "text: 'exact quote in source language', "
    "text_en: 'natural English translation of the quote', "
    "is_direct: true|false}, ...] (max 6) }. "
    "\n\n"
    "CRITICAL — `subject` rules:\n"
    "  * `subject` MUST be a specific named entity: a person, organization, "
    "    place, government body, company, or product.\n"
    "  * `subject` must NEVER be a generic noun like 'article', 'story', "
    "    'report', 'piece', 'news', 'author', 'we', 'they', 'someone'.\n"
    "  * If you cannot identify a specific named subject for a claim, "
    "    OMIT THAT CLAIM ENTIRELY — do not invent one and do not use a "
    "    placeholder.\n"
    "  * Better to return 2 well-attributed claims than 6 vague ones.\n\n"
    "If the source article is already in English, set speaker_en "
    "= speaker and text_en = text (just normalised). For non-English "
    "articles (Telugu, Tamil, Bengali, Hindi etc.), translate "
    "faithfully — preserve meaning over literal word order. "
    "Skip opinion / editorial commentary — only verifiable factual claims. "
    "No prose outside JSON. No fences."
)


# ── Sample selection ───────────────────────────────────────────────────────

async def pick_samples(n: int = 15) -> list[dict]:
    """Sample articles from sources where placeholder rate is highest.

    Stratified across the worst offenders so we test diverse failure modes."""
    sql = """
        WITH bad_sources AS (
          SELECT a.source_id, s.name AS sname,
                 COUNT(*) FILTER (WHERE LOWER(ac.subject_text)='article') AS bad
            FROM article_claims ac JOIN articles a ON a.id=ac.article_id
            JOIN sources s ON s.id=a.source_id
           GROUP BY a.source_id, s.name
           HAVING COUNT(*) FILTER (WHERE LOWER(ac.subject_text)='article') >= 50
           ORDER BY bad DESC LIMIT 8
        ),
        sampled AS (
          SELECT a.id::text AS aid, a.title, s.name AS source,
                 a.language_detected AS lang,
                 COALESCE(a.full_text_scraped,
                          a.lead_text_translated,
                          a.lead_text_original) AS body,
                 ROW_NUMBER() OVER (PARTITION BY a.source_id
                                    ORDER BY md5(a.id::text)) AS rn
            FROM articles a
            JOIN sources s ON s.id=a.source_id
            JOIN bad_sources bs ON bs.source_id = a.source_id
            JOIN article_claims ac ON ac.article_id = a.id
           WHERE a.substrate_status='ok'
             AND LOWER(ac.subject_text)='article'
             AND COALESCE(a.full_text_scraped, a.lead_text_translated,
                          a.lead_text_original) IS NOT NULL
             AND LENGTH(COALESCE(a.full_text_scraped, a.lead_text_translated,
                                 a.lead_text_original)) > 300
        )
        SELECT * FROM sampled WHERE rn <= 2 LIMIT :n
    """
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"n": int(n)})).fetchall()
    return [dict(r._mapping) for r in rows]


# ── Run one article through both prompts ───────────────────────────────────

async def extract(system: str, title: str, body: str) -> dict:
    user = f"Title: {title}\n\nBody:\n{body[:3500]}"
    try:
        raw = await call_groq(
            system=system, user=user,
            task_type="classification", json_response=True,
            max_tokens_override=600,
        )
        return json.loads(raw)
    except Exception as exc:
        return {"error": str(exc)[:200]}


# ── Summary ────────────────────────────────────────────────────────────────

PLACEHOLDERS = {"article", "story", "report", "piece", "news",
                "author", "writer", "we", "they"}


def is_placeholder(s: str | None) -> bool:
    if not s:
        return True
    return s.strip().lower() in PLACEHOLDERS


async def main() -> int:
    print("Picking samples…")
    samples = await pick_samples(n=15)
    print(f"Got {len(samples)} samples")
    print()

    old_results: list[list[str]] = []
    new_results: list[list[str]] = []

    for i, s in enumerate(samples, 1):
        print(f"━━━ Article {i}/{len(samples)} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"Source : {s['source']}  ({s['lang']})")
        print(f"Title  : {s['title'][:120]}")
        print()

        old = await extract(OLD_PROMPT, s["title"], s["body"])
        new = await extract(NEW_PROMPT, s["title"], s["body"])

        old_subjects = [
            c.get("subject", "?") for c in (old.get("claims") or [])[:6]
        ]
        new_subjects = [
            c.get("subject", "?") for c in (new.get("claims") or [])[:6]
        ]
        old_results.append(old_subjects)
        new_results.append(new_subjects)

        print("OLD prompt subjects:")
        for j, sub in enumerate(old_subjects):
            mark = "⚠ PLACEHOLDER" if is_placeholder(sub) else "✓"
            print(f"  {j+1}. {mark}  {sub}")
        print()
        print("NEW prompt subjects:")
        for j, sub in enumerate(new_subjects):
            mark = "⚠ PLACEHOLDER" if is_placeholder(sub) else "✓"
            print(f"  {j+1}. {mark}  {sub}")
        print()
        # First claim text for both
        old_claim = (old.get("claims") or [{}])[0].get("text", "")[:140]
        new_claim = (new.get("claims") or [{}])[0].get("text", "")[:140]
        print(f"OLD claim 1: {old_claim}")
        print(f"NEW claim 1: {new_claim}")
        print()

    # Aggregate verdict
    old_total = sum(len(r) for r in old_results)
    old_ph = sum(1 for r in old_results for s in r if is_placeholder(s))
    new_total = sum(len(r) for r in new_results)
    new_ph = sum(1 for r in new_results for s in r if is_placeholder(s))

    print("═════ AGGREGATE ═══════════════════════════════════════════════")
    print(f"OLD prompt: {old_ph}/{old_total} placeholders "
          f"({100*old_ph/max(old_total,1):.0f}%)")
    print(f"NEW prompt: {new_ph}/{new_total} placeholders "
          f"({100*new_ph/max(new_total,1):.0f}%)")
    avg_claims_old = old_total / max(len(samples), 1)
    avg_claims_new = new_total / max(len(samples), 1)
    print(f"Avg claims/article — OLD: {avg_claims_old:.1f}, "
          f"NEW: {avg_claims_new:.1f}  "
          f"(NEW omits unclear subjects → expect lower count)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
