#!/usr/bin/env python3
"""time_v4_embed.py — measure v4 LaBSE re-embed throughput on a 1,000-article sample.

Mirrors production: same get_labse_model() loader, same batch size (250), the v4
INPUT recipe inlined (title + translated_lead[:1024]) so it does not depend on which
branch is checked out on disk. Encode-only timing (no DB write) + a small write probe,
then projects a whole-corpus ETA from the live article count.

Run INSIDE rig-backend:  docker exec rig-backend python /app/_time_v4_embed.py
"""
from __future__ import annotations

import os
import time

import psycopg2

BATCH = 250          # production embed batch
SAMPLE = 1000        # timing sample size
CHAR_WINDOW = 1024   # v4 body window


def _dsn() -> str:
    for k in ("AB_DSN", "DATABASE_URL_SYNC", "DATABASE_URL"):
        v = os.environ.get(k)
        if v:
            # psycopg2 wants postgresql:// not postgresql+asyncpg://
            return v.replace("+asyncpg", "").replace("+psycopg2", "")
    raise SystemExit("no DSN in env (AB_DSN/DATABASE_URL_SYNC/DATABASE_URL)")


def _v4_text(title, lead_tr, lead_orig) -> str:
    body = (lead_tr or lead_orig or "")[:CHAR_WINDOW]
    t = (title or "").strip()
    return (t + "\n" + body) if t else body


def main() -> int:
    conn = psycopg2.connect(_dsn())
    cur = conn.cursor()

    # corpus size that would need a v4 re-embed (any article with usable lead/body text)
    cur.execute(
        "SELECT count(*) FROM articles WHERE "
        "length(COALESCE(NULLIF(lead_text_translated,''), NULLIF(lead_text_original,''), "
        "NULLIF(full_text_translated,''), NULLIF(full_text_scraped,''),'')) >= 100"
    )
    corpus = cur.fetchone()[0]

    # pull the timing sample (newest first; representative of real text lengths)
    cur.execute(
        "SELECT COALESCE(title,''), COALESCE(lead_text_translated,''), COALESCE(lead_text_original,'') "
        "FROM articles WHERE "
        "length(COALESCE(NULLIF(lead_text_translated,''), NULLIF(lead_text_original,''), "
        "NULLIF(full_text_translated,''), NULLIF(full_text_scraped,''),'')) >= 100 "
        "ORDER BY collected_at DESC LIMIT %s",
        (SAMPLE,),
    )
    rows = cur.fetchall()
    texts = [_v4_text(*r) for r in rows]
    n = len(texts)
    avg_chars = sum(len(t) for t in texts) / max(n, 1)

    # cold model load (mirror prod loader)
    t0 = time.perf_counter()
    from backend.nlp.nlp_embedding import get_labse_model
    model = get_labse_model()
    load_s = time.perf_counter() - t0

    # device introspection
    try:
        import torch
        cuda = torch.cuda.is_available()
        dev = str(next(model._first_module().parameters()).device)
    except Exception:
        cuda, dev = None, "?"

    # warm-up (trigger any lazy init so the timed loop is steady-state)
    model.encode(texts[:8])

    # timed encode, production batch size
    t1 = time.perf_counter()
    done = 0
    for i in range(0, n, BATCH):
        model.encode(texts[i:i + BATCH])
        done += len(texts[i:i + BATCH])
    enc_s = time.perf_counter() - t1
    rate = done / enc_s if enc_s else 0.0

    # tiny write probe: how long to UPDATE one row's vector (cast + index maintenance)
    vec = model.encode(texts[:1])[0]
    cur.execute("SELECT id FROM articles WHERE labse_embedding IS NOT NULL LIMIT 1")
    probe = cur.fetchone()
    write_ms = None
    if probe:
        emb = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
        t2 = time.perf_counter()
        cur.execute("SELECT CAST(%s AS vector)", (emb,))  # parse-only, no mutation
        cur.fetchone()
        write_ms = (time.perf_counter() - t2) * 1000.0

    full_s = corpus / rate if rate else 0.0
    print("=== v4 re-embed timing ===")
    print(f"device                : {dev}  (cuda={cuda})")
    print(f"model load (cold)     : {load_s:.1f}s")
    print(f"sample                : {n} articles, avg {avg_chars:.0f} chars/text")
    print(f"encode (batch={BATCH}) : {enc_s:.1f}s  ->  {rate:.1f} articles/sec  ({1000.0/rate:.1f} ms/article)")
    if write_ms is not None:
        print(f"vector parse probe    : {write_ms:.2f} ms/row (cast only; real UPDATE adds HNSW insert)")
    print(f"corpus to re-embed    : {corpus:,} articles")
    print(f"PROJECTED encode time : {full_s/60:.1f} min  ({full_s/3600:.2f} h) at this rate, single process")
    print(f"  (×0.5 if 2 procs, etc.; add DB write/HNSW overhead on top)")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
