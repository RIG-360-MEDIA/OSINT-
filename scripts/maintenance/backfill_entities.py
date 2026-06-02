#!/usr/bin/env python3
"""
backfill_entities.py — re-extract articles.entities_extracted with the FIXED nlp_entities
(word-boundary + surface-form prominence) and the CLEANED entity_dictionary.

Standalone (does NOT touch the live worker / no rig-backend restart): loads the fixed
/tmp/nlp_entities.py, populates its _ENTITY_DICT from the current (cleaned) table, loads
en_core_web_sm, streams V4 articles via a server-side cursor, recomputes entities, and
UPDATEs in batches on a SEPARATE write connection.

Env: AB_DSN/DATABASE_URL_SYNC · LIMIT (timing test) · BATCH (default 500) · NE_PATH
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

import psycopg2
from psycopg2.extras import execute_batch

BATCH = int(os.environ.get("BATCH", "500"))
LIMIT = os.environ.get("LIMIT")
NE_PATH = os.environ.get("NE_PATH", "/tmp/nlp_entities.py")


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    ne = _load_module(NE_PATH, "nlp_entities")

    # ---- populate the fixed module's _ENTITY_DICT from the CLEANED table (sync) ----
    setup = psycopg2.connect(dsn)
    scur = setup.cursor()
    scur.execute("SELECT canonical_name, entity_type, aliases, state, party FROM entity_dictionary")
    d: dict[str, dict] = {}
    for canonical_name, entity_type, aliases, state, party in scur.fetchall():
        surfaces = [canonical_name] + [(a or "").strip() for a in (aliases or []) if (a or "").strip()]
        entry = {"canonical_name": canonical_name, "entity_type": entity_type,
                 "state": state, "party": party, "surfaces": surfaces}
        d[canonical_name.lower()] = entry
        for a in (aliases or []):
            s = (a or "").strip()
            if s:
                d[s.lower()] = entry
    ne._ENTITY_DICT = d
    ne._DICT_LOADED = True
    setup.close()
    sys.stderr.write(f"dict loaded: {len(d)} keys (cleaned)\n")

    import spacy
    nlp_model = spacy.load("en_core_web_sm")

    read_conn = psycopg2.connect(dsn)
    write_conn = psycopg2.connect(dsn)
    rcur = read_conn.cursor(name="bf_read")
    rcur.itersize = 2000
    q = ("SELECT id, COALESCE(title,''), left(COALESCE(lead_text_translated, lead_text_original, ''), 6000) "
         "FROM articles WHERE embedding_revision='v4-tr-title-1024' ORDER BY id")
    if LIMIT:
        q += f" LIMIT {int(LIMIT)}"
    rcur.execute(q)
    wcur = write_conn.cursor()

    UP = "UPDATE articles SET entities_extracted = CAST(%s AS jsonb) WHERE id = %s"
    t0 = time.time()
    n = 0
    batch = []
    for aid, title, text in rcur:
        ents = ne.extract_entities(title=title, text=text, nlp_model=nlp_model)
        batch.append((json.dumps(ents), str(aid)))
        n += 1
        if len(batch) >= BATCH:
            execute_batch(wcur, UP, batch)
            write_conn.commit()
            batch = []
            if n % 10000 == 0:
                sys.stderr.write(f"  {n} done  {n/(time.time()-t0):.1f} art/s\n")
                sys.stderr.flush()
    if batch:
        execute_batch(wcur, UP, batch)
        write_conn.commit()
    dt = time.time() - t0
    rate = n / dt if dt else 0
    sys.stderr.write(f"DONE {n} articles in {dt:.0f}s ({rate:.1f} art/s); "
                     f"projected 136581 -> {136581/rate/60:.0f} min\n" if rate else "DONE (0)\n")
    read_conn.close()
    write_conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
