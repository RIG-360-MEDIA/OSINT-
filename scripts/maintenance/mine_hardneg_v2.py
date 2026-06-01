#!/usr/bin/env python3
"""
mine_hardneg_v2.py — better hard-negative mining via the shared_numbers signal.

v1 selected on (trgm_subject gray-band + event_date_match=false) and yielded ~83%
SAME-event pairs: event_date_match is a BROKEN negativity signal (same-event
articles routinely fail/disagree on date extraction). v2 replaces it with the
validated signal:

    look-alike (high trgm_subject)  AND  same template / DIFFERENT specific numbers

i.e. both articles cite numbers, but their number sets mostly DIVERGE (each side has
its own distinct numbers, overlap is a minority). That is the "same template,
different instance" pattern — a different IPL match, a different day's
horoscope/fuel-price, a different toll/score/point-drop — the genuine false-merge
traps a same-event scorer must learn to reject.

Numbers are extracted from title + lead_text_translated (English for every language,
so the signal is comparable across en/indic). Ubiquitous year tokens are dropped so
boilerplate ("...2026") cannot create a fake overlap.

Writes analytics.hard_neg_candidates_v2 (UNLABELED) for the LLM judge + spot-check.

Env: AB_DSN/DATABASE_URL_SYNC · TRGM_MIN (0.6) · JACC_MAX (0.34) · PER_STRATUM (150)
"""
from __future__ import annotations

import logging
import os
import re
import sys
from collections import defaultdict

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("minev2")

TRGM_MIN = float(os.environ.get("TRGM_MIN", "0.6"))
JACC_MAX = float(os.environ.get("JACC_MAX", "0.34"))
PER_STRATUM = int(os.environ.get("PER_STRATUM", "150"))
YEARS = {"2022", "2023", "2024", "2025", "2026", "2027"}
INDIC = {"te", "hi", "kn", "bn", "ml", "ta", "mr", "gu", "pa", "or", "ne", "as"}
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_of(text: str) -> set[str]:
    """Salient number tokens (commas stripped; ubiquitous years + all-zero dropped)."""
    out: set[str] = set()
    for tok in NUM_RE.findall(text or ""):
        norm = tok.replace(",", "")
        if norm in YEARS or norm.strip("0.") == "":
            continue
        out.add(norm)
    return out


def stratum_of(lang: str) -> str | None:
    if lang == "en":
        return "en_en"
    return "indic_indic" if lang in INDIC else None


def connect():
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    return psycopg2.connect(dsn)


def main() -> int:
    conn = connect()
    cur = conn.cursor()

    cur.execute(
        "SELECT a_id, b_id, trgm_subject, COALESCE(shared_actors,0), a_language "
        "FROM analytics.pair_scores "
        "WHERE trgm_subject >= %s AND a_language = b_language",
        (TRGM_MIN,),
    )
    pool = cur.fetchall()
    log.info("look-alike pool (trgm>=%.2f, same-lang): %d pairs", TRGM_MIN, len(pool))

    ids = {str(r[0]) for r in pool} | {str(r[1]) for r in pool}
    log.info("distinct articles to read: %d", len(ids))
    nums: dict[str, set[str]] = {}
    texts: dict[str, tuple[str, str]] = {}
    id_list = list(ids)
    for i in range(0, len(id_list), 1000):
        cur.execute(
            "SELECT id, COALESCE(title,''), COALESCE(lead_text_translated,''), "
            "COALESCE(primary_subject,'') FROM articles WHERE id = ANY(%s::uuid[])",
            (id_list[i:i + 1000],),
        )
        for aid, title, lead, subj in cur.fetchall():
            sid = str(aid)
            nums[sid] = numbers_of(title + " " + lead)
            texts[sid] = (title, subj)

    cand = []
    for a_id, b_id, trgm, sh_act, alang in pool:
        stratum = stratum_of(alang)
        if stratum is None:
            continue
        a, b = str(a_id), str(b_id)
        na, nb = nums.get(a, set()), nums.get(b, set())
        if not na or not nb:
            continue
        a_only, b_only = na - nb, nb - na
        if len(a_only) < 1 or len(b_only) < 1:
            continue
        jac = len(na & nb) / len(na | nb)
        if jac > JACC_MAX:
            continue
        cand.append((stratum, a, b, float(trgm), int(sh_act), jac,
                     sorted(na)[:8], sorted(nb)[:8]))
    log.info("divergent-number candidates: %d", len(cand))

    by = defaultdict(list)
    for c in cand:
        by[c[0]].append(c)
    selected = []
    for stratum, rows in sorted(by.items()):
        rows.sort(key=lambda r: (-r[3], r[5]))   # trickiest: high trgm, low jaccard
        selected.extend(rows[:PER_STRATUM])
        log.info("  %s: %d found -> take %d", stratum, len(rows), min(len(rows), PER_STRATUM))

    cur.execute("""
        CREATE TABLE IF NOT EXISTS analytics.hard_neg_candidates_v2 (
            stratum text, a_id uuid, b_id uuid,
            a_title text, b_title text, a_subject text, b_subject text,
            trgm_subject real, shared_actors int, num_jaccard real,
            a_numbers text, b_numbers text,
            label text, label_reason text,
            PRIMARY KEY (a_id, b_id))""")
    cur.execute("TRUNCATE analytics.hard_neg_candidates_v2")
    out_rows = []
    for stratum, a, b, trgm, sh_act, jac, na, nb in selected:
        at, asu = texts.get(a, ("", ""))
        bt, bsu = texts.get(b, ("", ""))
        out_rows.append((stratum, a, b, at, bt, asu, bsu, trgm, sh_act, round(jac, 3),
                         ",".join(na), ",".join(nb)))
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO analytics.hard_neg_candidates_v2 (stratum,a_id,b_id,a_title,b_title,"
        "a_subject,b_subject,trgm_subject,shared_actors,num_jaccard,a_numbers,b_numbers) "
        "VALUES %s ON CONFLICT (a_id,b_id) DO NOTHING",
        out_rows,
    )
    cur.execute("GRANT SELECT ON analytics.hard_neg_candidates_v2 TO rigwire_app")
    cur.execute("GRANT SELECT, UPDATE ON analytics.hard_neg_candidates_v2 TO analytics_user")
    conn.commit()

    cur.execute("SELECT stratum, count(*) FROM analytics.hard_neg_candidates_v2 "
                "GROUP BY stratum ORDER BY stratum")
    for s, c in cur.fetchall():
        log.info("FINAL %s = %d", s, c)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
