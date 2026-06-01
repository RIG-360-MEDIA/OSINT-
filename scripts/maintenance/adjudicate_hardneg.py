#!/usr/bin/env python3
"""
adjudicate_hardneg.py — LLM-propose same/different on analytics.hard_neg_candidates.

The production groq/cerebras judge (classify, FAST_MODEL) proposes SAME vs DIFFERENT
per candidate pair; the verdict is written to hard_neg_candidates.label
('same_event' | 'not_same_event' | 'UNPARSED'). A human/DB-chat spot-check on a
stratified sample (done separately) computes per-stratum agreement BEFORE the labels
are treated as final — same independent-verification discipline applied to the judge.

Chunked + resumable (WHERE label IS NULL), bounded concurrency, warm-up call first to
avoid the known groq_manager cold-start Lock. Runs inside rig-backend (has the pool +
keys). NOTE: this writes only to the analytics adjudication table, never production.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys

import psycopg2

sys.path.insert(0, "/app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("adj")

from backend.nlp.groq_client import classify  # noqa: E402

SYS = (
    "You are a strict news same-event judge. Two articles either report the SAME "
    "real-world event (same incident/announcement, same actors, about the same day) or "
    "DIFFERENT events that merely look alike (a different sports match, a different court "
    "case, a different city's version, a different day's update, a template reused for "
    "another subject). Reply with EXACTLY one token on line 1: SAME or DIFFERENT. "
    "Line 2: one short reason. /no_think"
)
CHUNK = 50
CONCURRENCY = int(os.environ.get("ADJ_CONCURRENCY", "3"))  # gentle: Groq daily-exhausted, shares pool with live enrichment
TABLE = os.environ.get("ADJ_TABLE", "analytics.hard_neg_candidates")
assert re.match(r"^analytics\.[a-z0-9_]+$", TABLE), "ADJ_TABLE must be analytics.<name>"


def fmt(p) -> str:
    return (
        "Article A:\n  title: %s\n  subject: %s\n\nArticle B:\n  title: %s\n  subject: %s\n\n"
        "Same real-world event?"
        % (p["a_title"] or "", (p["a_subject"] or "")[:300],
           p["b_title"] or "", (p["b_subject"] or "")[:300])
    )


def parse(out):
    if not out:
        return None, ""
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S | re.I).strip()
    head = out[:40].upper()
    if "DIFFERENT" in head:
        v = "not_same_event"
    elif "SAME" in head:
        v = "same_event"
    else:
        v = None
    return v, out.replace("\n", " ").strip()[:180]


async def _judge(sem, p):
    """Return (pair, status, verdict, reason).

    status in {'ok' (verdict set), 'parse_fail' (got text but no SAME/DIFFERENT
    token -> UNPARSED), 'api_err' (pool/transport error -> row left NULL so a
    later resume retries it instead of poisoning it to a terminal label)}.
    """
    async with sem:
        try:
            out = await classify(SYS, fmt(p))
        except Exception as exc:  # noqa: BLE001
            return p, "api_err", None, "ERR " + str(exc)[:80]
    v, reason = parse(out)
    if v is None:
        return p, "parse_fail", None, reason
    return p, "ok", v, reason


async def _run_chunk(pairs):
    sem = asyncio.Semaphore(CONCURRENCY)
    return await asyncio.gather(*(_judge(sem, p) for p in pairs))


def main() -> int:
    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(dsn)
    conn.autocommit = False

    try:
        asyncio.run(classify(SYS, "Article A:\n  title: x\n\nArticle B:\n  title: y\n\nSame?"))
        log.info("warm-up ok")
    except Exception as exc:  # noqa: BLE001
        log.warning("warm-up failed (continuing): %s", exc)

    total = 0
    errs = 0
    while True:
        cur = conn.cursor()
        cur.execute(
            f"SELECT a_id,b_id,stratum,a_title,b_title,a_subject,b_subject "
            f"FROM {TABLE} WHERE label IS NULL LIMIT %s",
            (CHUNK,),
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        if not rows:
            break
        results = asyncio.run(_run_chunk(rows))
        w = conn.cursor()
        wrote = 0
        api_errs = 0
        for p, status, v, reason in results:
            if status == "api_err":
                api_errs += 1          # leave label NULL -> retried on next resume
                continue
            if status == "parse_fail":
                errs += 1
            label = v if status == "ok" else "UNPARSED"
            w.execute(
                f"UPDATE {TABLE} SET label=%s, label_reason=%s "
                "WHERE a_id=%s AND b_id=%s",
                (label, reason, p["a_id"], p["b_id"]),
            )
            wrote += 1
        conn.commit()
        total += wrote
        log.info("labeled %d (unparsed=%d, api_err_this_chunk=%d)", total, errs, api_errs)
        if wrote == 0 and api_errs == len(results):
            log.warning("whole chunk API-errored -> pool likely exhausted; %d done, "
                        "stopping (resumable, %d left NULL)", total, len(results))
            break

    cur = conn.cursor()
    cur.execute(
        f"SELECT stratum, label, count(*) FROM {TABLE} "
        "GROUP BY stratum, label ORDER BY stratum, label"
    )
    for s, l, c in cur.fetchall():
        log.info("  FINAL %s | %s = %d", s, l, c)
    log.info("DONE total=%d unparsed=%d", total, errs)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
