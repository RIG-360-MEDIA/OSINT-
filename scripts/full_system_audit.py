"""
Full system audit for the production user (pranavpuri03@gmail.com).
Each section uses a fresh DB session so one missing table doesn't poison the rest.
"""
from __future__ import annotations

import asyncio
import subprocess

from sqlalchemy import text

from backend.database import get_db


USER_EMAIL = "pranavpuri03@gmail.com"


def hr(title: str) -> None:
    print(f"\n{'=' * 78}\n  {title}\n{'=' * 78}", flush=True)


def section(title: str) -> None:
    print(f"\n── {title} ──", flush=True)


async def safe_query(sql: str, params: dict | None = None):
    """Run one query with a fresh session; return rows or [] on any error."""
    try:
        async with get_db() as db:
            result = await db.execute(text(sql), params or {})
            return result.fetchall()
    except Exception as exc:  # noqa: BLE001
        return [{"_error": str(exc)[:100]}]


async def safe_one(sql: str, params: dict | None = None):
    rows = await safe_query(sql, params)
    if not rows:
        return None
    return rows[0]


async def main() -> None:
    user_row = await safe_one(
        "SELECT id::text AS id FROM users WHERE email = :e", {"e": USER_EMAIL}
    )
    user_id = user_row.id if user_row and hasattr(user_row, "id") else ""
    print(f"User: {USER_EMAIL}  →  {user_id}", flush=True)

    # ─────────────────────── DB CONTENT METRICS ──────────────────────────
    hr("DATABASE / CONTENT METRICS")

    section("Articles (P03 RSS pipeline)")
    a = await safe_one("""
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE nlp_processed) AS nlp_done,
          COUNT(*) FILTER (WHERE NOT nlp_processed) AS nlp_pending,
          COUNT(*) FILTER (WHERE labse_embedding IS NOT NULL) AS embedded,
          COUNT(*) FILTER (WHERE labse_embedding IS NULL AND nlp_processed) AS embed_missing,
          COUNT(*) FILTER (WHERE collected_at > NOW() - INTERVAL '24 hours') AS last_24h
        FROM articles
    """)
    if a:
        print(f"  total: {a.total:>5}  |  NLP done: {a.nlp_done}  pending: {a.nlp_pending}", flush=True)
        print(f"  embedded: {a.embedded}  embedding missing: {a.embed_missing}", flush=True)
        print(f"  collected last 24h: {a.last_24h}", flush=True)

    rows = await safe_query("""
        SELECT relevance_tier, COUNT(*) AS n FROM user_article_relevance
        WHERE user_id = CAST(:uid AS uuid)
        GROUP BY relevance_tier ORDER BY relevance_tier
    """, {"uid": user_id})
    dist = {r.relevance_tier: r.n for r in rows if hasattr(r, "relevance_tier")}
    print(f"  per-user article tier dist: {dist}", flush=True)

    backlog = await safe_one("""
        SELECT COUNT(*) AS n FROM articles a
        WHERE a.nlp_processed = TRUE
          AND NOT EXISTS (SELECT 1 FROM user_article_relevance r
                          WHERE r.article_id = a.id AND r.user_id = CAST(:uid AS uuid))
    """, {"uid": user_id})
    if backlog:
        print(f"  per-user RELEVANCE BACKLOG (NLP'd but unscored): {backlog.n}", flush=True)

    section("Govt Documents (P15)")
    g = await safe_one("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE intrinsic_importance > 0) AS scored,
               COUNT(*) FILTER (WHERE labse_embedding IS NOT NULL) AS embedded
        FROM govt_documents
    """)
    if g:
        print(f"  total: {g.total}  intel-scored: {g.scored}  embedded: {g.embedded}", flush=True)

    chunks = await safe_one("SELECT COUNT(*) AS n FROM govt_document_chunks")
    if chunks:
        print(f"  RAG chunks indexed: {chunks.n}", flush=True)

    rows = await safe_query("""
        SELECT relevance_tier, COUNT(*) AS n FROM user_govt_doc_relevance
        WHERE user_id = CAST(:uid AS uuid)
        GROUP BY relevance_tier ORDER BY relevance_tier
    """, {"uid": user_id})
    dist = {r.relevance_tier: r.n for r in rows if hasattr(r, "relevance_tier")}
    print(f"  per-user doc tier dist: {dist}", flush=True)

    section("YouTube Clips (P14)")
    y = await safe_one("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE collected_at > NOW() - INTERVAL '7 days') AS last_7d
        FROM youtube_clips
    """)
    if y:
        print(f"  total: {y.total}  last 7d: {y.last_7d}", flush=True)

    section("Threads (P11)")
    t = await safe_one("SELECT COUNT(*) AS total FROM threads")
    if t and not getattr(t, "_error", None):
        print(f"  total: {t.total}", flush=True)
    else:
        print(f"  {t}", flush=True)

    section("Briefs for this user (P10)")
    b = await safe_one(
        "SELECT COUNT(*) AS total, MAX(generated_at) AS last_at FROM briefs WHERE user_id = CAST(:uid AS uuid)",
        {"uid": user_id},
    )
    print(f"  {b}", flush=True)

    section("Newspaper Clippings (P16)")
    nc = await safe_one("SELECT COUNT(*) AS total FROM newspaper_clippings")
    print(f"  {nc}", flush=True)

    section("Social Signals (P17)")
    ss = await safe_one("SELECT COUNT(*) AS total FROM social_signals")
    print(f"  {ss}", flush=True)

    section("User profile depth")
    p = await safe_one("""
        SELECT role_type, geo_primary,
               COALESCE(array_length(geo_secondary, 1), 0) AS geo_n
        FROM user_profiles WHERE user_id = CAST(:uid AS uuid)
    """, {"uid": user_id})
    if p:
        print(f"  role_type={getattr(p, 'role_type', '?')}  geo_primary={getattr(p, 'geo_primary', '?')}  geo_secondary_count={getattr(p, 'geo_n', 0)}", flush=True)
    e = await safe_one("SELECT COUNT(*) AS n FROM user_entities WHERE user_id = CAST(:uid AS uuid)",
                       {"uid": user_id})
    print(f"  monitored entities: {e.n if e else '?'}", flush=True)

    # ──────────────────────── WORKER HEALTH ──────────────────────────────
    hr("BACKEND WORKER HEALTH")
    r = subprocess.run(
        ["docker", "exec", "rig-backend", "bash", "-c",
         "ps aux | grep 'celery.*worker' | grep -v grep | head -20"],
        capture_output=True, text=True, timeout=10,
    )
    seen = set()
    for line in r.stdout.strip().split("\n"):
        if "celery" not in line:
            continue
        host = "?"
        queues = "?"
        for tok in line.split():
            if tok.startswith("worker-"):
                host = tok.split("@")[0]
            if "--queues=" in tok:
                queues = tok.split("=", 1)[1]
        key = (host, queues)
        if key in seen or host == "?":
            continue
        seen.add(key)
        print(f"  · {host:<22} → queues: {queues}", flush=True)

    # ──────────────────────── SOURCE HEALTH ──────────────────────────────
    hr("GOVT DOC SOURCE HEALTH (active sources)")
    sources = await safe_query("""
        SELECT s.name, s.source_geography, s.health_score, s.consecutive_failures, s.last_scraped_at,
               COALESCE((SELECT SUM(docs_inserted) FROM govt_collection_runs r WHERE r.source_id = s.id), 0) AS docs_total,
               COALESCE((SELECT COUNT(*) FROM govt_collection_runs r WHERE r.source_id = s.id), 0) AS runs_total
        FROM govt_document_sources s
        WHERE s.is_active = TRUE
        ORDER BY docs_total DESC, s.name
    """)
    sources = [r for r in sources if not getattr(r, "_error", None)]
    productive = [s for s in sources if (s.docs_total or 0) > 0]
    zero = [s for s in sources if (s.docs_total or 0) == 0]
    print(f"  Total active: {len(sources)}  ·  Producing: {len(productive)}  ·  Zero: {len(zero)}", flush=True)
    section("Productive sources (top 10 by doc count)")
    for s in productive[:10]:
        last = s.last_scraped_at.strftime("%Y-%m-%d %H:%M") if s.last_scraped_at else "(never)"
        print(f"  · {s.name:<28} health={s.health_score:.1f} fails={s.consecutive_failures} docs={s.docs_total:>3} runs={s.runs_total} last={last}", flush=True)
    section("Zero-doc sources (need adapter rewrite or are blocked)")
    for s in zero[:15]:
        last = s.last_scraped_at.strftime("%Y-%m-%d %H:%M") if s.last_scraped_at else "(never)"
        print(f"  · {s.name:<28} health={s.health_score:.1f} fails={s.consecutive_failures} runs={s.runs_total} last={last}", flush=True)

    # ──────────────────────── PER-PAGE QUALITY ───────────────────────────
    hr("PER-PAGE QUALITY SAMPLE")

    section("Coverage Room — top 3 articles for this user")
    rows = await safe_query("""
        SELECT a.title, a.source_name, r.score_final, r.relevance_tier
        FROM user_article_relevance r
        JOIN articles a ON a.id = r.article_id
        WHERE r.user_id = CAST(:uid AS uuid)
        ORDER BY r.score_final DESC
        LIMIT 3
    """, {"uid": user_id})
    for r in rows:
        if hasattr(r, "title"):
            print(f"  T{r.relevance_tier} {r.score_final:.2f}  {r.title[:65]}  ({r.source_name})", flush=True)

    section("Document Room — top 3 docs for this user")
    rows = await safe_query("""
        SELECT d.title, d.source_name, r.score_final, r.urgency, r.why_it_matters
        FROM user_govt_doc_relevance r
        JOIN govt_documents d ON d.id = r.doc_id
        WHERE r.user_id = CAST(:uid AS uuid)
        ORDER BY r.score_final DESC
        LIMIT 3
    """, {"uid": user_id})
    for r in rows:
        if hasattr(r, "title"):
            sf = r.score_final or 0.0
            print(f"  {r.urgency or '-':<6} {sf:.2f}  {r.title[:60]}  ({r.source_name})", flush=True)
            why = (r.why_it_matters or "")[:90].replace("\n", " ")
            print(f"         → {why}", flush=True)

    section("Clip Room — most recent 3 clips")
    rows = await safe_query("""
        SELECT video_title, channel_title, importance, matched_entity
        FROM youtube_clips ORDER BY collected_at DESC LIMIT 3
    """)
    for r in rows:
        if hasattr(r, "video_title"):
            print(f"  · imp={r.importance}  {(r.video_title or '')[:55]}  | matched: {r.matched_entity}", flush=True)
        else:
            print(f"  {r}", flush=True)

    section("Threads — top 3")
    rows = await safe_query("SELECT id::text, title, article_count FROM threads ORDER BY article_count DESC LIMIT 3")
    for r in rows:
        if hasattr(r, "title"):
            print(f"  · {r.article_count:>3} articles  {r.title[:70]}", flush=True)
        else:
            print(f"  {r}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
