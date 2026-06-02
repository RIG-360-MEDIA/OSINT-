#!/usr/bin/env python3
"""
verify_vernacular.py — is the vernacular-blob problem a TRANSLATION GAP or a GENUINE
clustering/embedding weakness?

The whole-corpus blob-watch surfaced single-source Indic "section" blobs (one outlet's
recipes/columns/awards fused into one cluster). Hypothesis: those articles lack
lead_text_translated, so the V4 recipe (COALESCE(lead_text_translated, lead_text_original))
embedded raw vernacular -> clustered by language/script, not topic.

Decisive test: translation coverage of Indic articles INSIDE high-ratio blobs (A) vs the
Indic V4 corpus baseline (B).
  * A << B  -> translation gap (the blobs ARE the untranslated articles) -> fix = backfill
  * A ~= B  -> genuine weakness (translated Indic articles blob anyway) -> fix = clustering

Loads /tmp/whole_corpus.csv (the locked whole-corpus run) into a TEMP table; read-only on
articles. Prints raw numbers for transcription into the verify doc.
"""
from __future__ import annotations

import os
import sys

import psycopg2

CSV = os.environ.get("CSV", "/tmp/whole_corpus.csv")
INDIC = "('kn','te','hi','ml','ta','mr','bn','gu','pa','or','as','ne')"
RATIO = os.environ.get("RATIO", "4")   # blob-watch threshold (digest used ratio>=4)
SIZE = os.environ.get("SIZE", "10")


def main() -> int:
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE _wc(article_id uuid, cluster_id uuid, source_id uuid)")
    with open(CSV) as fh:
        cur.copy_expert("COPY _wc FROM STDIN WITH (FORMAT csv, HEADER true)", fh)

    blob_cte = (f"cl AS (SELECT cluster_id, count(*) sz, count(DISTINCT source_id) src "
                f"FROM _wc GROUP BY 1), "
                f"hb AS (SELECT cluster_id FROM cl WHERE sz>={SIZE} "
                f"AND sz::numeric/greatest(src,1)>={RATIO})")
    tr = "a.lead_text_translated IS NOT NULL AND length(trim(a.lead_text_translated))>0"
    tr2 = "lead_text_translated IS NOT NULL AND length(trim(lead_text_translated))>0"

    print(f"=== [VERDICT] translation coverage: blob-Indic (A) vs corpus-Indic baseline (B) "
          f"[blob = ratio>={RATIO}, size>={SIZE}] ===")
    cur.execute(f"""
        WITH {blob_cte}
        SELECT 'A. Indic IN high-ratio blobs', count(*),
               round(100.0*count(*) FILTER (WHERE {tr})/nullif(count(*),0),1),
               round(avg(a.word_count),0)
        FROM _wc w JOIN hb ON hb.cluster_id=w.cluster_id JOIN articles a ON a.id=w.article_id
        WHERE a.language_detected IN {INDIC}
        UNION ALL
        SELECT 'B. ALL Indic V4 (baseline)', count(*),
               round(100.0*count(*) FILTER (WHERE {tr2})/nullif(count(*),0),1),
               round(avg(word_count),0)
        FROM articles WHERE embedding_revision='v4-tr-title-1024' AND language_detected IN {INDIC}
    """)
    for sc, n, pct, wc in cur.fetchall():
        print(f"  {sc:32s} n={n:7d}  translated={pct}%  avg_words={wc}")

    print(f"\n=== top high-ratio blobs (ALL languages — incl NULL-tagged — per-cluster translation %) ===")
    cur.execute(f"""
        WITH cl AS (SELECT cluster_id, count(*) sz, count(DISTINCT source_id) src FROM _wc GROUP BY 1)
        SELECT c.sz, c.src, round(c.sz::numeric/greatest(c.src,1),1) ratio,
               COALESCE(mode() WITHIN GROUP (ORDER BY a.language_detected),'NULL') dl,
               count(*) FILTER (WHERE a.language_detected IS NULL) n_nulllang,
               round(100.0*count(*) FILTER (WHERE {tr})/count(*),1) pct_tr,
               round(avg(a.word_count),0) wc, left(min(a.title),44) sample
        FROM cl c JOIN _wc w ON w.cluster_id=c.cluster_id JOIN articles a ON a.id=w.article_id
        WHERE c.sz>={SIZE} AND c.sz::numeric/greatest(c.src,1)>={RATIO}
        GROUP BY c.cluster_id, c.sz, c.src
        ORDER BY ratio DESC LIMIT 15
    """)
    for sz, src, ratio, dl, nnull, pct, wc, sample in cur.fetchall():
        print(f"  sz={sz:4d} src={src:3d} ratio={str(ratio):5} lang={dl:4s} nullLang={nnull:3d} "
              f"tr={str(pct):5}% w={str(wc):4} | {sample}")

    print(f"\n=== high-ratio blob count by dominant-language family ===")
    cur.execute(f"""
        WITH cl AS (SELECT cluster_id, count(*) sz, count(DISTINCT source_id) src FROM _wc GROUP BY 1),
        bl AS (SELECT cluster_id FROM cl WHERE sz>={SIZE} AND sz::numeric/greatest(src,1)>={RATIO}),
        dom AS (SELECT w.cluster_id, mode() WITHIN GROUP (ORDER BY a.language_detected) dl
                FROM _wc w JOIN bl ON bl.cluster_id=w.cluster_id JOIN articles a ON a.id=w.article_id
                GROUP BY 1)
        SELECT CASE WHEN dl IN {INDIC} THEN 'Indic-dominant'
                    WHEN dl='en' THEN 'English-dominant'
                    WHEN dl IS NULL THEN 'NULL/undetected-lang'
                    ELSE 'other('||dl||')' END fam, count(*)
        FROM dom GROUP BY 1 ORDER BY 2 DESC
    """)
    for fam, n in cur.fetchall():
        print(f"  {fam:22s} {n} blobs")

    print(f"\n=== pathology enrichment: blob articles vs all-V4 baseline (the REAL mechanism) ===")
    cur.execute(f"""
        WITH {blob_cte}
        SELECT 'blob articles' scope, count(*) n,
          round(100.0*count(*) FILTER (WHERE a.title ~ '[^[:ascii:]]' AND a.language_detected='en')/nullif(count(*),0),1),
          round(100.0*count(*) FILTER (WHERE a.word_count<30)/nullif(count(*),0),1),
          round(100.0*count(*) FILTER (WHERE a.lead_text_translated=a.lead_text_original)/nullif(count(*),0),1)
        FROM _wc w JOIN hb ON hb.cluster_id=w.cluster_id JOIN articles a ON a.id=w.article_id
        UNION ALL
        SELECT 'all V4 baseline', count(*),
          round(100.0*count(*) FILTER (WHERE title ~ '[^[:ascii:]]' AND language_detected='en')/nullif(count(*),0),1),
          round(100.0*count(*) FILTER (WHERE word_count<30)/nullif(count(*),0),1),
          round(100.0*count(*) FILTER (WHERE lead_text_translated=lead_text_original)/nullif(count(*),0),1)
        FROM articles WHERE embedding_revision='v4-tr-title-1024'
    """)
    for sc, n, mis, stub, pt in cur.fetchall():
        print(f"  {sc:16s} n={n:7d}  vernac-mistagged-en={mis}%  stub(<30w)={stub}%  passthrough={pt}%")

    print(f"\n=== corpus-wide translation gap by language (Aryan confirmation #1) ===")
    cur.execute("""
        SELECT language_detected,
          count(*) FILTER (WHERE lead_text_translated IS NULL OR length(trim(lead_text_translated))=0) untrans,
          count(*) total
        FROM articles WHERE embedding_revision='v4-tr-title-1024'
        GROUP BY 1 HAVING count(*)>400 ORDER BY untrans DESC LIMIT 10
    """)
    for lang, unt, tot in cur.fetchall():
        print(f"  {(lang or 'NULL'):5s} untranslated={unt:6d} / {tot:6d}")

    print(f"\n=== eyeball: members of the single highest-ratio blob (style-blob or one event?) ===")
    cur.execute("""
        WITH cl AS (SELECT cluster_id, count(*) sz, count(DISTINCT source_id) src FROM _wc GROUP BY 1),
        top AS (SELECT cluster_id, sz, src FROM cl WHERE sz>=10
                ORDER BY sz::numeric/greatest(src,1) DESC LIMIT 1)
        SELECT a.language_detected lang, a.word_count w, left(a.title,58) title
        FROM _wc w JOIN top ON top.cluster_id=w.cluster_id JOIN articles a ON a.id=w.article_id
        ORDER BY a.word_count DESC LIMIT 10
    """)
    for lang, w, title in cur.fetchall():
        print(f"  [{(lang or 'NULL'):4s}/{(w if w is not None else 0):4}w] {title}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
