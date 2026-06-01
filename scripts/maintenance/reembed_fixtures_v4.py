#!/usr/bin/env python3
"""
reembed_fixtures_v4.py — V4-embed the handful of GATE-FIXTURE articles that are V0
stragglers, so the re-baseline is neither coverage-short nor cross-recipe-contaminated.

Why: §1 verify found 5 of the 1,994 golden+recall fixture articles still on V0
(English articles with no `lead_text_translated`, so never 0c-eligible). 4 of them are
the lone V0 member of a size-2 `true_cluster` must-merge pair — excluding them would
delete 4 merge-tests from the gate; comparing them cross-recipe is the contamination
0c exists to kill. They are English, so their English lead IS the recipe's text.

Embeds from COALESCE(lead_text_translated, lead_text_original) via the LOCKED V4 recipe
(byte-identical to 0c/0a), writes labse_embedding + labse_embedding_v4, stamps
embedding_revision. Old V0 vectors are already preserved in labse_embedding_v0_backup
by the swap. Targets ONLY fixture stragglers (join analytics._fixture_ids).

Env: AB_DSN/DATABASE_URL_SYNC · RECIPE_PATH (/tmp/embedding_recipe.py)
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("refix")

RECIPE_PATH = os.environ.get("RECIPE_PATH", "/tmp/embedding_recipe.py")
_spec = importlib.util.spec_from_file_location("embedding_recipe", RECIPE_PATH)
_er = importlib.util.module_from_spec(_spec)
sys.modules["embedding_recipe"] = _er
_spec.loader.exec_module(_er)
RECIPE = _er.RECIPE
build_embedding_text = _er.build_embedding_text


def main() -> int:
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(
        "SELECT a.id, a.title, a.lead_text_original, a.lead_text_translated "
        "FROM articles a JOIN analytics._fixture_ids f ON f.id = a.id "
        "WHERE a.embedding_revision IS DISTINCT FROM %s",
        (RECIPE.recipe_version,),
    )
    rows = cur.fetchall()
    log.info("fixture stragglers to re-embed: %d (recipe=%s)", len(rows), RECIPE.recipe_version)
    if not rows:
        log.info("nothing to do — all fixtures already V4")
        return 0

    from sentence_transformers import SentenceTransformer
    log.info("loading LaBSE pinned @ %s ...", RECIPE.model_rev[:12])
    model = SentenceTransformer(RECIPE.model_id, revision=RECIPE.model_rev)
    try:
        model.max_seq_length = RECIPE.max_seq_length
    except Exception:  # noqa: BLE001
        pass

    done = 0
    for aid, title, lead_o, lead_t in rows:
        text = build_embedding_text(RECIPE, title=title, lead_original=lead_o,
                                    lead_translated=(lead_t or lead_o))
        if not text or len(text) < 20:
            log.warning("skip %s — empty embedding text", aid)
            continue
        vec = model.encode([text])[0]
        lit = "[" + ",".join(f"{x:.6f}" for x in vec.tolist()) + "]"
        cur.execute(
            "UPDATE articles SET labse_embedding = CAST(%s AS vector), "
            "labse_embedding_v4 = CAST(%s AS vector), embedding_model = %s, "
            "embedding_revision = %s WHERE id = %s",
            (lit, lit, "sentence-transformers/LaBSE", RECIPE.recipe_version, str(aid)),
        )
        conn.commit()
        done += 1
        log.info("  re-embedded %s", aid)

    cur.execute(
        "SELECT count(*) FILTER (WHERE embedding_revision = %s), count(*) "
        "FROM articles WHERE id IN (SELECT id FROM analytics._fixture_ids)",
        (RECIPE.recipe_version,),
    )
    v4, tot = cur.fetchone()
    log.info("DONE: re-embedded %d ; fixtures V4 now %d / %d", done, v4, tot)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
