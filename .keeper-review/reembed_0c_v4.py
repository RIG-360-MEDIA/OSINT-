#!/usr/bin/env python3
"""
reembed_0c_v4.py — Phase 0c FULL re-embed onto the LOCKED V4 recipe.

Strategy (a) — shadow column:
  * Writes ONLY to articles.labse_embedding_v4 (production articles.labse_embedding
    is untouched until a separate atomic swap, so the live index never goes
    mixed-state and the old vectors stay recoverable).
  * Idempotent / resumable: skips rows whose shadow vector is already set.
  * Memory-bounded: one model instance, batch-encode, commit per batch, and a
    host-availability pause so it never crosses the reaper line.

Eligibility = lead_text_translated present (V4 is TRANSLATED + title; the small
non-translated remainder keeps its existing vector and is picked up by 0a once
translated). The eventual swap is COALESCE(labse_embedding_v4, labse_embedding)
so non-shadow rows are preserved.

Recipe is loaded BY FILE from embedding_recipe.py (no backend-package side effects)
so 0c and 0a are provably byte-identical. Provenance stamping happens on the SWAP,
not here (this only fills shadow vectors).

Env: AB_DSN/DATABASE_URL_SYNC · RECIPE_PATH (default /tmp/embedding_recipe.py)
     C_BATCH (128) · C_MIN_AVAIL_MB (800) · C_LIMIT (0=all; small for smoke)
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
import time

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("0c")

RECIPE_PATH = os.environ.get("RECIPE_PATH", "/tmp/embedding_recipe.py")
BATCH = int(os.environ.get("C_BATCH", "128"))
MIN_AVAIL_MB = int(os.environ.get("C_MIN_AVAIL_MB", "800"))
LIMIT = int(os.environ.get("C_LIMIT", "0"))

# Load the locked recipe as a standalone leaf module (no backend.__init__ imports).
_spec = importlib.util.spec_from_file_location("embedding_recipe", RECIPE_PATH)
_er = importlib.util.module_from_spec(_spec)
sys.modules["embedding_recipe"] = _er
_spec.loader.exec_module(_er)
RECIPE = _er.RECIPE
build_embedding_text = _er.build_embedding_text

ELIGIBLE = (
    "lead_text_translated IS NOT NULL AND length(lead_text_translated) > 50"
)


def connect():
    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    return psycopg2.connect(dsn)


def avail_mb() -> int:
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:  # noqa: BLE001
        return 99999
    return 99999


def main() -> int:
    log.info(
        "0c recipe: lang=%s title=%s window=%s max_seq=%s rev=%s",
        RECIPE.language, RECIPE.title_prepend, RECIPE.char_window,
        RECIPE.max_seq_length, RECIPE.recipe_version,
    )
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(f"SELECT count(*) FROM articles WHERE labse_embedding_v4 IS NULL AND {ELIGIBLE}")
    log.info("remaining to embed: %d  (limit=%s)", cur.fetchone()[0], LIMIT or "all")

    from sentence_transformers import SentenceTransformer
    log.info("loading LaBSE pinned @ %s ...", RECIPE.model_rev[:12])
    model = SentenceTransformer(RECIPE.model_id, revision=RECIPE.model_rev)
    try:
        model.max_seq_length = RECIPE.max_seq_length
    except Exception:  # noqa: BLE001
        pass
    log.info("model loaded, max_seq_length=%s", getattr(model, "max_seq_length", "?"))

    done = 0
    while True:
        if LIMIT and done >= LIMIT:
            log.info("reached C_LIMIT=%d — stopping", LIMIT)
            break
        if avail_mb() < MIN_AVAIL_MB:
            log.warning("host avail %dMB < %dMB floor — pausing 120s", avail_mb(), MIN_AVAIL_MB)
            time.sleep(120)
            continue
        cur.execute(
            f"""
            SELECT id, title, lead_text_original, lead_text_translated
            FROM articles
            WHERE labse_embedding_v4 IS NULL AND {ELIGIBLE}
            ORDER BY collected_at DESC
            LIMIT %s
            """,
            (BATCH,),
        )
        rows = cur.fetchall()
        if not rows:
            break

        texts, ids = [], []
        for aid, title, lo, lt in rows:
            txt = build_embedding_text(RECIPE, title=title, lead_original=lo, lead_translated=lt)
            if txt and len(txt) >= 20:
                texts.append(txt)
                ids.append(str(aid))

        if ids:
            vecs = model.encode(texts)
            payload = [
                (aid, "[" + ",".join(f"{x:.6f}" for x in vec.tolist()) + "]")
                for aid, vec in zip(ids, vecs)
            ]
            psycopg2.extras.execute_values(
                cur,
                "UPDATE articles AS a SET labse_embedding_v4 = CAST(d.vec AS vector) "
                "FROM (VALUES %s) AS d(id, vec) WHERE a.id = d.id::uuid",
                payload, template="(%s,%s)", page_size=BATCH,
            )
            conn.commit()

        done += len(rows)
        if not ids and len(rows) == BATCH:
            log.warning("batch produced no embeddable text — stopping to avoid a loop")
            break
        if (done // BATCH) % 20 == 0:
            log.info("progress: %d processed (avail=%dMB)", done, avail_mb())

    cur.execute(f"SELECT count(labse_embedding_v4), count(*) FROM articles WHERE {ELIGIBLE}")
    filled, eligible = cur.fetchone()
    log.info("0c DONE: shadow filled %s / %s eligible", filled, eligible)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
