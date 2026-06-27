"""_bge_ab_export.py — BGE-M3 A/B Step 1: build query set + haystack.

Samples 60 story clusters (40% te/hi) + 8K distractor articles from Hetzner DB.
Outputs two files to /root/rig/docs/research/:
  bge_ab_queries.json   — [{cluster_id, query_text, relevant_ids, lang}]
  bge_ab_haystack.jsonl — one article per line: {id, title, lead, lang, labse_emb}

Run: docker exec rig-backend python /app/scripts/research/_bge_ab_export.py
"""
from __future__ import annotations
import ast, json, os, sys, time

sys.path.insert(0, "/app")
import psycopg2
from psycopg2.extras import RealDictCursor

DSN = os.environ.get("DATABASE_URL_SYNC", "postgresql://rig:rig@rig-postgres:5432/rig")
OUT = "/app/docs/research"
os.makedirs(OUT, exist_ok=True)

N_TEHI   = 24   # te/hi clusters
N_OTHER  = 36   # en/other clusters
N_DIST   = 8000 # random distractors

CLUSTER_COLS = "4 AND 12"  # article_count BETWEEN


def vec_to_list(v: str) -> list[float]:
    """Parse pgvector text '[f1,f2,...]' → list of floats."""
    return list(ast.literal_eval(v))


def main() -> None:
    conn = psycopg2.connect(DSN)
    cur  = conn.cursor(cursor_factory=RealDictCursor)
    t0   = time.time()

    # ── Step 1a: sample 60 clusters ─────────────────────────────────────────
    print("sampling clusters...", flush=True)
    cur.execute(f"""
        WITH te_hi AS (
            SELECT sc.story_id::text AS cluster_id,
                   sc.representative_title AS query_text,
                   a.language_iso AS lang
            FROM   analytics.story_clusters_v8 sc
            JOIN   articles a ON a.id = sc.representative_article_id
            WHERE  sc.article_count BETWEEN {CLUSTER_COLS}
              AND  sc.independent_source_count >= 3
              AND  sc.representative_title IS NOT NULL
              AND  NOT sc.is_template_family
              AND  sc.suppression_reason IS NULL
              AND  a.language_iso IN ('te', 'hi')
              AND  a.labse_embedding_v4 IS NOT NULL
            ORDER  BY random()
            LIMIT  {N_TEHI}
        ),
        other AS (
            SELECT sc.story_id::text AS cluster_id,
                   sc.representative_title AS query_text,
                   coalesce(a.language_iso, 'en') AS lang
            FROM   analytics.story_clusters_v8 sc
            JOIN   articles a ON a.id = sc.representative_article_id
            WHERE  sc.article_count BETWEEN {CLUSTER_COLS}
              AND  sc.independent_source_count >= 3
              AND  sc.representative_title IS NOT NULL
              AND  NOT sc.is_template_family
              AND  sc.suppression_reason IS NULL
              AND  coalesce(a.language_iso, 'en') NOT IN ('te', 'hi')
              AND  a.labse_embedding_v4 IS NOT NULL
              AND  sc.story_id NOT IN (SELECT cluster_id::uuid FROM te_hi)
            ORDER  BY random()
            LIMIT  {N_OTHER}
        )
        SELECT * FROM te_hi UNION ALL SELECT * FROM other
    """)
    clusters = list(cur.fetchall())
    cluster_ids = [c["cluster_id"] for c in clusters]
    print(f"  {len(clusters)} clusters sampled "
          f"(te/hi={sum(1 for c in clusters if c['lang'] in ('te','hi'))})", flush=True)

    # ── Step 1b: get member article IDs per cluster ──────────────────────────
    print("fetching cluster members...", flush=True)
    ids_str = ",".join(f"'{x}'" for x in cluster_ids)
    cur.execute(f"""
        SELECT m.story_id::text, m.article_id::text
        FROM   analytics.story_cluster_members_v8 m
        WHERE  m.story_id::text IN ({ids_str})
    """)
    member_rows = cur.fetchall()
    cluster_members: dict[str, list[str]] = {}
    all_member_ids: set[str] = set()
    for r in member_rows:
        cluster_members.setdefault(r["story_id"], []).append(r["article_id"])
        all_member_ids.add(r["article_id"])
    print(f"  {len(all_member_ids)} unique member articles", flush=True)

    # ── attach relevant_ids to query records ─────────────────────────────────
    queries = []
    for c in clusters:
        cid = c["cluster_id"]
        queries.append({
            "cluster_id": cid,
            "query_text": c["query_text"],
            "lang": c["lang"],
            "relevant_ids": cluster_members.get(cid, []),
        })

    # ── Step 1c: sample distractors ──────────────────────────────────────────
    print(f"sampling {N_DIST} distractors...", flush=True)
    member_ids_str = ",".join(f"'{x}'" for x in all_member_ids) if all_member_ids else "''"
    cur.execute(f"""
        SELECT id::text
        FROM   articles
        WHERE  substrate_status = 'ok'
          AND  NOT is_duplicate
          AND  labse_embedding_v4 IS NOT NULL
          AND  id::text NOT IN ({member_ids_str})
        ORDER  BY random()
        LIMIT  {N_DIST}
    """)
    distractor_ids = {r["id"] for r in cur.fetchall()}
    all_haystack_ids = all_member_ids | distractor_ids
    print(f"  haystack size: {len(all_haystack_ids)} articles "
          f"({len(all_member_ids)} members + {len(distractor_ids)} distractors)", flush=True)

    # ── export haystack articles with LaBSE embeddings ───────────────────────
    print("exporting haystack articles + embeddings...", flush=True)
    hay_ids_str = ",".join(f"'{x}'" for x in all_haystack_ids)
    cur.execute(f"""
        SELECT id::text, title,
               coalesce(lead_text_original, '') AS lead,
               coalesce(language_iso, 'en') AS lang,
               labse_embedding_v4::text AS labse_emb
        FROM   articles
        WHERE  id::text IN ({hay_ids_str})
          AND  labse_embedding_v4 IS NOT NULL
    """)

    hay_path = f"{OUT}/bge_ab_haystack.jsonl"
    written = 0
    labse_missing = 0
    with open(hay_path, "w", encoding="utf-8") as f:
        while True:
            batch = cur.fetchmany(500)
            if not batch:
                break
            for r in batch:
                try:
                    emb = vec_to_list(r["labse_emb"])
                except Exception:
                    labse_missing += 1
                    continue
                f.write(json.dumps({
                    "id": r["id"],
                    "title": r["title"] or "",
                    "lead": r["lead"],
                    "lang": r["lang"],
                    "labse_emb": emb,
                }, ensure_ascii=False) + "\n")
                written += 1
    print(f"  wrote {written} haystack rows ({labse_missing} skipped no-emb)", flush=True)

    # ── save query set ────────────────────────────────────────────────────────
    q_path = f"{OUT}/bge_ab_queries.json"
    with open(q_path, "w", encoding="utf-8") as f:
        json.dump(queries, f, ensure_ascii=False, indent=2)
    print(f"  wrote {len(queries)} queries to {q_path}", flush=True)

    # ── summary ───────────────────────────────────────────────────────────────
    lang_counts: dict[str, int] = {}
    for q in queries:
        lang_counts[q["lang"]] = lang_counts.get(q["lang"], 0) + 1
    print(f"\n=== A/B dataset built in {time.time()-t0:.0f}s ===")
    print(f"  queries: {len(queries)}  lang={dict(sorted(lang_counts.items()))}")
    print(f"  haystack: {written} articles at {hay_path}")
    conn.close()


if __name__ == "__main__":
    main()
