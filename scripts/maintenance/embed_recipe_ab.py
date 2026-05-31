#!/usr/bin/env python3
"""
embed_recipe_ab.py — Embedding-Recipe A/B (Worldwide Phase 0c precursor).

Spec: rig-news/docs/plans/embedding-recipe-ab-2026-05-30.md (analytics chat / Aryan).

Embeds a stratified ~3.5K sample in 5 INPUT-recipe variants into an ISOLATED
eval table (analytics.embed_ab). It NEVER touches articles.labse_embedding.
Pinned model rev 836121a only — we are testing the INPUT recipe, not the model.

Variants (window = BODY char window; title, when used, is prepended in full):
  V0 control : lead_text_translated[:512]                 (translated, no title, 512)  == today
  V1         : title + "\n" + lead_text_original[:512]    (original,  title,    512)
  V2         : title + "\n" + lead_text_original[:1024]   (original,  title,   1024)
  V3         : title + "\n" + lead_text_original[:2000]   (original,  title,   full lead)
  V4 langchk : title + "\n" + lead_text_translated[:1024] (translated, title,  1024)

  V1..V3 isolate the char-window effect; V0<->V1 isolates title+language;
  V2<->V4 share the (original-language) title and differ ONLY in body language
  => clean language isolation.  [NOTE for analytics: window is applied to the
  BODY; the title is always prepended in full. Flag if you meant a total-window.]

Idempotent + resumable: skips (article_id, variant) pairs already in embed_ab.
Memory-bounded: one model instance, batch-encode, commit per batch.

Env:
  AB_DSN / DATABASE_URL / POSTGRES_* — DB connection (tried in that order)
  RECALL_JSON      default /tmp/cluster-recall-set.json
  AB_TARGET_TOTAL  default 3500   (recall set is included regardless of this)
  AB_BATCH         default 64
  AB_LIMIT_PENDING default 0 (=no cap; set small for a smoke test)
  AB_SMOKE         "1" => cap pending at 40 and skip strata top-up
"""
from __future__ import annotations
import os
import sys
import json
import logging

import psycopg2
import psycopg2.extras

LABSE_MODEL_ID = "sentence-transformers/LaBSE"
LABSE_REVISION = "836121a0533e5664b21c7aacc5d22951f2b8b25b"

RECALL_JSON = os.environ.get("RECALL_JSON", "/tmp/cluster-recall-set.json")
TARGET_TOTAL = int(os.environ.get("AB_TARGET_TOTAL", "3500"))
BATCH = int(os.environ.get("AB_BATCH", "64"))
LIMIT_PENDING = int(os.environ.get("AB_LIMIT_PENDING", "0"))
SMOKE = os.environ.get("AB_SMOKE", "") in ("1", "true", "yes")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("embed_ab")

VARIANTS = ("V0", "V1", "V2", "V3", "V4")
VARIANT_META = [
    ("V0", "translated", False, 512),
    ("V1", "original", True, 512),
    ("V2", "original", True, 1024),
    ("V3", "original", True, 2000),
    ("V4", "translated", True, 1024),
]


def build_text(variant: str, title: str | None, lead_o: str | None, lead_t: str | None) -> str:
    t = (title or "").strip()
    lo = lead_o or ""
    lt = lead_t or ""
    if variant == "V0":
        return lt[:512]
    if variant == "V1":
        body = lo[:512]
        return (t + "\n" + body) if t else body
    if variant == "V2":
        body = lo[:1024]
        return (t + "\n" + body) if t else body
    if variant == "V3":
        body = lo[:2000]
        return (t + "\n" + body) if t else body
    if variant == "V4":
        body = lt[:1024]
        return (t + "\n" + body) if t else body
    raise ValueError(variant)


def connect():
    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL")
    if dsn:
        log.info("connecting via DSN env (%s...)", dsn.split("@")[-1][:24] if "@" in dsn else "dsn")
        return psycopg2.connect(dsn)
    host = os.environ.get("POSTGRES_HOST") or os.environ.get("PGHOST") or "rig-postgres"
    port = os.environ.get("POSTGRES_PORT") or os.environ.get("PGPORT") or "5432"
    db = os.environ.get("POSTGRES_DB") or os.environ.get("PGDATABASE") or "rig"
    user = os.environ.get("POSTGRES_USER") or os.environ.get("PGUSER") or "rig"
    pw = os.environ.get("POSTGRES_PASSWORD") or os.environ.get("PGPASSWORD") or ""
    log.info("connecting host=%s db=%s user=%s", host, db, user)
    return psycopg2.connect(host=host, port=port, dbname=db, user=user, password=pw)


def ensure_tables(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics.embed_ab (
            article_id uuid        NOT NULL,
            variant    text        NOT NULL,
            vector     vector(768) NOT NULL,
            char_len   int         NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (article_id, variant)
        );
        CREATE TABLE IF NOT EXISTS analytics.embed_ab_sample (
            article_id uuid PRIMARY KEY,
            stratum    text NOT NULL,
            added_at   timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS analytics.embed_ab_variants (
            variant      text PRIMARY KEY,
            language     text NOT NULL,
            title_prepend boolean NOT NULL,
            char_window  int  NOT NULL,
            model_rev    text NOT NULL
        );
        """
    )
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO analytics.embed_ab_variants(variant,language,title_prepend,char_window,model_rev) "
        "VALUES %s ON CONFLICT (variant) DO NOTHING",
        [(v, lang, tp, win, LABSE_REVISION) for (v, lang, tp, win) in VARIANT_META],
    )


def build_sample(cur, recall_ids: set[str]) -> None:
    cur.execute("SELECT count(*) FROM analytics.embed_ab_sample")
    if cur.fetchone()[0] > 0:
        log.info("sample already built — reusing")
        return

    # 1. recall set (the recall denominator) — keep only ids that exist with text
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO analytics.embed_ab_sample(article_id,stratum) VALUES %s "
        "ON CONFLICT (article_id) DO NOTHING",
        [(rid, "recall") for rid in recall_ids],
        page_size=500,
    )
    cur.execute(
        """
        DELETE FROM analytics.embed_ab_sample s
        WHERE stratum='recall'
          AND NOT EXISTS (
            SELECT 1 FROM articles a
            WHERE a.id = s.article_id
              AND coalesce(a.lead_text_original, a.lead_text_translated) IS NOT NULL
          )
        """
    )
    if SMOKE:
        cur.execute("SELECT count(*) FROM analytics.embed_ab_sample")
        log.info("SMOKE: sample = recall-only (%d)", cur.fetchone()[0])
        return

    # 2. multilingual slice (Indic languages — the cross-lingual recall reason)
    cur.execute(
        """
        INSERT INTO analytics.embed_ab_sample(article_id,stratum)
        SELECT a.id,'multilingual' FROM articles a
        WHERE a.language_iso IN ('te','hi','kn','bn','or','ta','ml','mr','gu','pa')
          AND a.lead_text_original IS NOT NULL AND length(a.lead_text_original) > 120
          AND NOT EXISTS (SELECT 1 FROM analytics.embed_ab_sample s WHERE s.article_id=a.id)
        ORDER BY random() LIMIT 600
        ON CONFLICT DO NOTHING
        """
    )
    # 3. same-source-heavy slice (top sources by volume, multiple events)
    cur.execute(
        """
        INSERT INTO analytics.embed_ab_sample(article_id,stratum)
        SELECT a.id,'same_source' FROM articles a
        WHERE a.source_id IN (
            SELECT source_id FROM articles
            WHERE lead_text_original IS NOT NULL
            GROUP BY source_id ORDER BY count(*) DESC LIMIT 8
        )
          AND a.lead_text_original IS NOT NULL AND length(a.lead_text_original) > 120
          AND NOT EXISTS (SELECT 1 FROM analytics.embed_ab_sample s WHERE s.article_id=a.id)
        ORDER BY random() LIMIT 600
        ON CONFLICT DO NOTHING
        """
    )
    # 4. random remainder to fill TARGET_TOTAL
    cur.execute("SELECT count(*) FROM analytics.embed_ab_sample")
    need = max(0, TARGET_TOTAL - cur.fetchone()[0])
    if need:
        cur.execute(
            """
            INSERT INTO analytics.embed_ab_sample(article_id,stratum)
            SELECT a.id,'random' FROM articles a
            WHERE a.lead_text_original IS NOT NULL AND length(a.lead_text_original) > 120
              AND NOT EXISTS (SELECT 1 FROM analytics.embed_ab_sample s WHERE s.article_id=a.id)
            ORDER BY random() LIMIT %s
            ON CONFLICT DO NOTHING
            """,
            (need,),
        )
    cur.execute("SELECT stratum,count(*) FROM analytics.embed_ab_sample GROUP BY stratum ORDER BY 2 DESC")
    for stratum, n in cur.fetchall():
        log.info("  stratum %-12s = %d", stratum, n)


def main() -> int:
    log.info("loading recall set from %s", RECALL_JSON)
    with open(RECALL_JSON, encoding="utf-8") as fh:
        rj = json.load(fh)
    recall_ids: set[str] = set()
    for ev in rj["events"]:
        for k in ("article_ids_recalled", "article_ids_isolated"):
            for i in ev.get(k) or []:
                recall_ids.add(i)
    log.info("recall member ids: %d (across %d events)", len(recall_ids), len(rj["events"]))

    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()
    ensure_tables(cur)
    conn.commit()
    build_sample(cur, recall_ids)
    conn.commit()

    from sentence_transformers import SentenceTransformer
    log.info("loading LaBSE pinned @ %s (~1.8 GB) ...", LABSE_REVISION[:12])
    model = SentenceTransformer(LABSE_MODEL_ID, revision=LABSE_REVISION)
    log.info("model loaded")
    # CRITICAL for the window A/B: LaBSE defaults to 256 tokens, which would
    # silently truncate V2 (1024c) / V3 (2000c) to ~the same content as V1 and
    # make the char-window axis inert. Raise to LaBSE's 512-token ceiling so the
    # window variants are genuinely different. NOTE: max_seq_length=512 is now
    # PART OF THE RECIPE — 0c and 0a must use the same value. (Prod generate_embedding
    # currently uses the default 256; V0's text is < 256 tokens so V0 is unaffected.)
    try:
        prev = model.max_seq_length
        model.max_seq_length = 512
        log.info("max_seq_length %s -> 512 (window variants meaningful up to 512 tokens)", prev)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not set max_seq_length: %s", exc)

    cur.execute(
        """
        SELECT s.article_id, a.title, a.lead_text_original, a.lead_text_translated
        FROM analytics.embed_ab_sample s
        JOIN articles a ON a.id = s.article_id
        ORDER BY s.article_id
        """
    )
    rows = cur.fetchall()
    log.info("sample articles with text: %d", len(rows))

    cur.execute("SELECT article_id, variant FROM analytics.embed_ab")
    done = {(str(a), v) for a, v in cur.fetchall()}
    log.info("already-embedded pairs: %d", len(done))

    pending = []
    for aid, title, lo, lt in rows:
        for v in VARIANTS:
            if (str(aid), v) in done:
                continue
            txt = build_text(v, title, lo, lt)
            if not txt or len(txt) < 20:
                continue
            pending.append((aid, v, txt))

    cap = 40 if SMOKE else LIMIT_PENDING
    if cap and len(pending) > cap:
        log.info("capping pending %d -> %d (smoke/limit)", len(pending), cap)
        pending = pending[:cap]
    log.info("pending embeds: %d", len(pending))

    ins = conn.cursor()
    total = 0
    for i in range(0, len(pending), BATCH):
        chunk = pending[i : i + BATCH]
        vecs = model.encode([c[2] for c in chunk])
        payload = [
            (c[0], c[1], "[" + ",".join(f"{x:.6f}" for x in vec.tolist()) + "]", len(c[2]))
            for c, vec in zip(chunk, vecs)
        ]
        psycopg2.extras.execute_values(
            ins,
            "INSERT INTO analytics.embed_ab(article_id,variant,vector,char_len) VALUES %s "
            "ON CONFLICT (article_id,variant) DO NOTHING",
            payload,
            template="(%s,%s,%s::vector,%s)",
            page_size=BATCH,
        )
        conn.commit()
        total += len(chunk)
        if (i // BATCH) % 10 == 0:
            log.info("  embedded %d / %d", total, len(pending))

    log.info("DONE — inserted %d new vectors", total)
    cur.execute("SELECT variant, count(*) FROM analytics.embed_ab GROUP BY variant ORDER BY variant")
    for variant, n in cur.fetchall():
        log.info("FINAL embed_ab[%s] = %d", variant, n)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
