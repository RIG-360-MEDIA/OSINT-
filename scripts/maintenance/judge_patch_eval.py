#!/usr/bin/env python3
"""
judge_patch_eval.py — §4 before/after for the gray-band judge over-split patch.

Runs the PATCHED same-event judge on two labeled sets and reports BOTH directions:
  * MISSES (truth=SAME): the judge over-split pairs (label='not_same_event' AND NOT
    human_clean) — the patch should RECOVER these to SAME. Before = 0% agreement
    (the original judge called them DIFFERENT — that's why they're labeled not_same_event).
  * CLEAN (truth=DIFFERENT): the verified-clean template negatives (human_clean) — the
    patch must NOT over-correct; they should STAY DIFFERENT. Before = 100% agreement.

"Materially better" = high recovery on MISSES AND high retention on CLEAN (no swing to
merging genuinely-different events). Read-only: writes nothing. Gentle concurrency.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from collections import Counter

import psycopg2

sys.path.insert(0, "/app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("jp")

from backend.nlp.groq_client import classify  # noqa: E402

SYS_PATCHED = (
    "You are a strict news same-event judge. Two articles either report the SAME "
    "real-world event or DIFFERENT events that merely look alike. The SAME event "
    "reported at a different time, from a different angle, as a live-update vs recap, or "
    "as announcement -> reactions -> swearing-in, is SAME. Answer DIFFERENT only when the "
    "underlying incident / match / day / subject genuinely differs (a different sports "
    "match, a different day's update, a different city's case, a template reused for "
    "another subject). Reply with EXACTLY one token on line 1: SAME or DIFFERENT. "
    "Line 2: one short reason. /no_think"
)
CONC = int(os.environ.get("ADJ_CONCURRENCY", "3"))


def fmt(p) -> str:
    return (
        "Article A:\n  title: %s\n  subject: %s\n\nArticle B:\n  title: %s\n  subject: %s\n\n"
        "Same real-world event?"
        % (p["a_title"] or "", (p["a_subject"] or "")[:300],
           p["b_title"] or "", (p["b_subject"] or "")[:300])
    )


def parse(out):
    if not out:
        return None
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S | re.I).strip()
    head = out[:40].upper()
    if "DIFFERENT" in head:
        return "DIFFERENT"
    if "SAME" in head:
        return "SAME"
    return None


async def _judge(sem, p):
    async with sem:
        try:
            out = await classify(SYS_PATCHED, fmt(p))
        except Exception:  # noqa: BLE001
            return p, None
    return p, parse(out)


async def _run(pairs):
    sem = asyncio.Semaphore(CONC)
    return await asyncio.gather(*(_judge(sem, p) for p in pairs))


def main() -> int:
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("""
        SELECT setname,a_id,b_id,a_title,b_title,a_subject,b_subject FROM (
          SELECT 'miss' setname,a_id,b_id,a_title,b_title,a_subject,b_subject
            FROM analytics.hard_neg_candidates    WHERE label='not_same_event' AND NOT human_clean
          UNION SELECT 'miss',a_id,b_id,a_title,b_title,a_subject,b_subject
            FROM analytics.hard_neg_candidates_v2 WHERE label='not_same_event' AND NOT human_clean
          UNION SELECT 'clean',a_id,b_id,a_title,b_title,a_subject,b_subject
            FROM analytics.hard_neg_candidates    WHERE human_clean
          UNION SELECT 'clean',a_id,b_id,a_title,b_title,a_subject,b_subject
            FROM analytics.hard_neg_candidates_v2 WHERE human_clean
        ) u
    """)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    seen, pairs = set(), []
    for r in rows:
        k = (r["setname"], *sorted([str(r["a_id"]), str(r["b_id"])]))
        if k in seen:
            continue
        seen.add(k)
        pairs.append(r)
    n_miss = sum(1 for p in pairs if p["setname"] == "miss")
    n_clean = sum(1 for p in pairs if p["setname"] == "clean")
    log.info("misses(truth=SAME)=%d  clean(truth=DIFFERENT)=%d", n_miss, n_clean)

    try:
        asyncio.run(classify(SYS_PATCHED, "Article A:\n title:x\n\nArticle B:\n title:y\n\nSame?"))
        log.info("warm-up ok")
    except Exception as exc:  # noqa: BLE001
        log.warning("warm-up: %s", exc)

    res = asyncio.run(_run(pairs))
    miss_same = miss_n = clean_diff = clean_n = unparsed = 0
    for p, v in res:
        if v is None:
            unparsed += 1
            continue
        if p["setname"] == "miss":
            miss_n += 1
            miss_same += (v == "SAME")
        else:
            clean_n += 1
            clean_diff += (v == "DIFFERENT")
    log.info("=== §4 PATCHED-JUDGE before/after ===")
    log.info("MISSES truth=SAME: BEFORE 0%% (all called DIFFERENT) -> AFTER %d/%d = %.1f%% SAME (recovery)",
             miss_same, miss_n, 100.0 * miss_same / max(miss_n, 1))
    log.info("CLEAN  truth=DIFF: BEFORE 100%% -> AFTER %d/%d = %.1f%% still DIFFERENT (retention; low=over-correction)",
             clean_diff, clean_n, 100.0 * clean_diff / max(clean_n, 1))
    log.info("unparsed=%d", unparsed)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
