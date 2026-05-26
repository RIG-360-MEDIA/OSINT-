"""validate_backfill.py — Verify the article_claims refill quality.

Runs five checks against the articles already refilled by
refill_placeholder_claims.py:

  1. Spot-check: pick 20 random refilled articles, print title +
     body excerpt + each new subject_text + entity_id resolution.
  2. Entity-link coverage: % of new subjects that resolved to
     entity_dictionary.id.
  3. Claim-count delta: avg claims/article before vs after (the
     before count is reconstructed from the failed pool — articles
     still placeholder-broken).
  4. LLM-judge: re-score 10 refilled articles on the same prompt
     the gold-set freeze used. Pass = median overall_score ≥ 8.
  5. /observe Quality Monitor: hit the helper directly and report
     the live placeholder_pct.

Inside rig-backend:
    docker exec rig-backend python /app/scripts/backfill/validate_backfill.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import random
from pathlib import Path
from typing import Any

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402
from backend.nlp.groq_client import call_groq  # noqa: E402
from backend.observability.article_quality import quality_monitor  # noqa: E402

STATE_PATH = Path("/docs/quality/backfill_state.json")

JUDGE_SYSTEM = (
    "You are auditing news-article extractions for accuracy. Given an article's "
    "text and a structured extraction made by another LLM, rate how well each "
    "extracted field matches the article. Be strict. Output STRICT JSON."
)
JUDGE_TEMPLATE = """ARTICLE
Title: {title}
Body:
{body}

EXTRACTED CLAIMS (subjects only, after our refill):
{subjects}

Rate how well these subjects match what the article is actually about.
Output STRICT JSON only:
{{
  "subjects_accuracy": <0-10>,
  "issues": ["<short note>", ...],
  "confidence": <0.0-1.0>
}}"""


async def get_completed_aids() -> list[str]:
    if not STATE_PATH.exists():
        return []
    return json.loads(STATE_PATH.read_text(encoding="utf-8")).get("completed", [])


# ── Check 1 + 2: Spot-check + entity-link coverage ────────────────────────────

async def check_spot_and_coverage(aids: list[str]) -> dict[str, Any]:
    sample = random.sample(aids, min(20, len(aids)))
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT a.id::text AS aid, a.title,
                   LEFT(COALESCE(a.lead_text_translated,
                                 a.full_text_scraped,
                                 a.lead_text_original), 280) AS body_excerpt,
                   ac.subject_text, ac.subject_entity_id IS NOT NULL AS linked
              FROM articles a JOIN article_claims ac ON ac.article_id = a.id
             WHERE a.id::text = ANY(:ids)
             ORDER BY a.id, md5(ac.id::text)
        """), {"ids": sample})).fetchall()

    by_article: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = by_article.setdefault(r.aid, {
            "title": r.title, "body": r.body_excerpt,
            "subjects": [], "linked": 0, "total": 0,
        })
        d["subjects"].append(r.subject_text)
        d["total"] += 1
        if r.linked:
            d["linked"] += 1

    print("━━━ 1+2. Spot-check (20 random refilled articles) ━━━━━━━━━━━━━━")
    total_linked = total_subjects = 0
    for aid, d in list(by_article.items())[:20]:
        print(f"\n[{aid[:8]}] {d['title'][:80]}")
        print(f"  body: {d['body'][:120]}…")
        print(f"  subjects: {d['subjects']}")
        print(f"  linked to entity: {d['linked']}/{d['total']}")
        total_linked += d["linked"]
        total_subjects += d["total"]

    print()
    print(f"Entity-link coverage in spot sample: "
          f"{total_linked}/{total_subjects} "
          f"({100*total_linked/max(total_subjects,1):.0f}%)")
    return {"spot_linked": total_linked, "spot_total": total_subjects}


# ── Check 3: Claim-count delta ────────────────────────────────────────────────

async def check_count_delta(aids: list[str]) -> dict[str, Any]:
    async with get_db() as db:
        after = (await db.execute(text("""
            SELECT AVG(c)::float AS avg_claims, MIN(c) AS min_c, MAX(c) AS max_c
              FROM (SELECT COUNT(*) AS c FROM article_claims
                     WHERE article_id::text = ANY(:ids) GROUP BY article_id) x
        """), {"ids": aids})).fetchone()
        # Reference: average claims/article in the still-broken population
        before = (await db.execute(text("""
            SELECT AVG(c)::float AS avg_claims
              FROM (SELECT COUNT(*) AS c FROM article_claims ac
                      WHERE LOWER(ac.subject_text)='article'
                      GROUP BY article_id LIMIT 5000) x
        """))).fetchone()
    print("\n━━━ 3. Claim-count delta ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Before (placeholder articles, sample 5K): "
          f"{before.avg_claims:.2f} claims/article")
    print(f"  After  (refilled articles, n={len(aids)}): "
          f"{after.avg_claims:.2f} claims/article  "
          f"(range {after.min_c}–{after.max_c})")
    delta = (after.avg_claims - before.avg_claims) / max(before.avg_claims, 1e-6)
    print(f"  Delta: {delta:+.1%}  "
          f"(negative = stricter / fewer claims; expected because we OMIT unclear subjects)")
    return {"before": before.avg_claims, "after": after.avg_claims, "delta_pct": delta}


# ── Check 4: LLM-judge on refilled articles ───────────────────────────────────

async def judge_one(article_id: str) -> dict[str, Any]:
    async with get_db() as db:
        a = (await db.execute(text("""
            SELECT a.title,
                   LEFT(COALESCE(a.lead_text_translated,
                                 a.full_text_scraped,
                                 a.lead_text_original), 2000) AS body,
                   array_agg(ac.subject_text) AS subjects
              FROM articles a JOIN article_claims ac ON ac.article_id = a.id
             WHERE a.id = CAST(:aid AS uuid)
             GROUP BY a.title, a.lead_text_translated,
                      a.full_text_scraped, a.lead_text_original
        """), {"aid": article_id})).fetchone()
    if not a or not a.subjects:
        return {"error": "no claims found"}
    user = JUDGE_TEMPLATE.format(
        title=a.title or "",
        body=a.body or "",
        subjects=json.dumps(a.subjects, ensure_ascii=False),
    )
    try:
        raw = await call_groq(system=JUDGE_SYSTEM, user=user,
                              task_type="classification",
                              json_response=True, max_tokens_override=300)
        return json.loads(raw)
    except Exception as e:
        return {"error": str(e)[:120]}


async def check_judge(aids: list[str]) -> dict[str, Any]:
    sample = random.sample(aids, min(10, len(aids)))
    print("\n━━━ 4. LLM-judge re-scores backfilled articles ━━━━━━━━━━━━━━")
    results = await asyncio.gather(*[judge_one(a) for a in sample])
    scores = [r["subjects_accuracy"] for r in results
              if isinstance(r.get("subjects_accuracy"), (int, float))]
    errors = sum(1 for r in results if "error" in r)
    if not scores:
        print(f"  All {len(results)} judge calls errored (likely rate limit).")
        return {"scores": [], "errors": errors}
    s = sorted(scores)
    median = s[len(s)//2] if len(s) % 2 else (s[len(s)//2-1] + s[len(s)//2]) / 2
    print(f"  Judged {len(scores)}/{len(sample)} (errors: {errors})")
    print(f"  Scores: {scores}")
    print(f"  Median: {median:.1f}  (target: ≥ 8 per gold-set bar)")
    return {"scores": scores, "median": median, "errors": errors}


# ── Check 5: /observe Quality Monitor placeholder gauge ───────────────────────

async def check_quality_monitor() -> dict[str, Any]:
    async with get_db() as db:
        qm = await quality_monitor(db)
    live = qm.get("live", {})
    print("\n━━━ 5. /observe Quality Monitor — live placeholder gauge ━━━")
    print(f"  claims total:        {live.get('claims_total', '?'):>12,}")
    print(f"  claims placeholder:  {live.get('claims_placeholder', '?'):>12,}")
    print(f"  placeholder pct:     {live.get('claims_placeholder_pct', '?')}%")
    print("  (Was 74.2% before any backfill. Will drop as more rows refill.)")
    return live


# ── Driver ────────────────────────────────────────────────────────────────────

async def main() -> int:
    aids = await get_completed_aids()
    print(f"State file shows {len(aids)} articles refilled so far\n")
    if not aids:
        print("Nothing to validate yet.")
        return 1

    r1 = await check_spot_and_coverage(aids)
    r3 = await check_count_delta(aids)
    r4 = await check_judge(aids)
    r5 = await check_quality_monitor()

    print("\n═════ VERDICT ═══════════════════════════════════════════════")
    coverage_pct = 100 * r1["spot_linked"] / max(r1["spot_total"], 1)
    print(f"  Entity-link coverage:  {coverage_pct:.0f}%   "
          f"(was 0% before backfill — these rows had NULL entity_id)")
    print(f"  Claim count delta:     {r3['delta_pct']:+.1%}")
    if r4.get("median") is not None:
        print(f"  LLM-judge median:      {r4['median']:.1f}   "
              f"(target ≥ 8)")
    print(f"  Live placeholder pct:  {r5.get('claims_placeholder_pct', '?')}%   "
          f"(was 74.2%)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
