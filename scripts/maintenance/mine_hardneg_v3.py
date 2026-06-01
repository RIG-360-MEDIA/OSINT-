#!/usr/bin/env python3
"""
mine_hardneg_v3.py — template-series hard-negative mining (the LAST mine).

v1 (dates differ) and v2 (numbers differ) both yielded only ~10% true negatives:
same-event coverage naturally diverges on dates AND numbers, so neither is a
different-event signal. The genuine false-merge traps are ONE shape:

    same OUTLET · near-identical TEMPLATE title · different INSTANCE-key

e.g. "Today's Front pages: May 12" vs "...May 8"; "Horoscope May 7" vs "May 8";
per-stock tickers; per-match previews. v3 targets exactly that:

    same source_id  AND  trgm_title >= TRGM_TITLE_MIN  AND  (calendar date in the
    two titles DIFFERS)   -> highest purity ("date-keyed" templates)

Pairs with no title date fall to an "entity-keyed" bucket (used only to top up a
sparse stratum; lower purity because same-story live-updates also live there, and
the judge's known over-split bias makes that bucket noisier).

Writes analytics.hard_neg_candidates_v3 (UNLABELED) for the judge + spot-check.

Env: AB_DSN/DATABASE_URL_SYNC · TRGM_TITLE_MIN (0.85) · PER_STRATUM (150)
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
log = logging.getLogger("minev3")

TRGM_TITLE_MIN = float(os.environ.get("TRGM_TITLE_MIN", "0.85"))
PER_STRATUM = int(os.environ.get("PER_STRATUM", "150"))
INDIC = {"te", "hi", "kn", "bn", "ml", "ta", "mr", "gu", "pa", "or", "ne", "as"}
_M = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
DATE_RE = re.compile(
    rf"(?:{_M})[a-z]*\.?\s*\d{{1,2}}|\b\d{{1,2}}[-/]\d{{1,2}}(?:[-/]\d{{2,4}})?\b", re.I)


def dates_of(title: str) -> frozenset[str]:
    out = set()
    for m in DATE_RE.findall(title or ""):
        out.add(re.sub(r"[\s.]+", "", m).lower())
    return frozenset(out)


def stratum_of(lang: str) -> str | None:
    if lang == "en":
        return "en_en"
    return "indic_indic" if lang in INDIC else None


def connect():
    return psycopg2.connect(
        os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
        or os.environ.get("DATABASE_URL"))


def main() -> int:
    conn = connect()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT ps.a_id, ps.b_id, ps.trgm_title, ps.a_language,
               aa.title, bb.title,
               COALESCE(aa.primary_subject,''), COALESCE(bb.primary_subject,'')
        FROM analytics.pair_scores ps
        JOIN articles aa ON aa.id = ps.a_id
        JOIN articles bb ON bb.id = ps.b_id
        WHERE ps.trgm_title >= %s AND ps.a_language = ps.b_language
          AND aa.source_id = bb.source_id AND aa.source_id IS NOT NULL
        """,
        (TRGM_TITLE_MIN,),
    )
    pool = cur.fetchall()
    log.info("same-source near-identical-title pool (trgm_title>=%.2f): %d pairs",
             TRGM_TITLE_MIN, len(pool))

    date_keyed: dict[str, list] = defaultdict(list)
    entity_keyed: dict[str, list] = defaultdict(list)
    for a_id, b_id, trgm_t, alang, at, bt, asu, bsu in pool:
        stratum = stratum_of(alang)
        if stratum is None:
            continue
        da, db = dates_of(at), dates_of(bt)
        row = (stratum, str(a_id), str(b_id), at, bt, asu, bsu, float(trgm_t))
        if da and db and da != db:
            why = f"title dates differ: {sorted(da)} vs {sorted(db)}"
            date_keyed[stratum].append(row + (why,))
        elif at.strip().lower() != bt.strip().lower():   # not an exact title dup
            entity_keyed[stratum].append(row + ("same-source template, no date key",))

    selected = []
    for stratum in set(list(date_keyed) + list(entity_keyed)):
        dk = sorted(date_keyed[stratum], key=lambda r: -r[7])
        ek = sorted(entity_keyed[stratum], key=lambda r: -r[7])
        take = dk[:PER_STRATUM]
        if len(take) < PER_STRATUM:
            take += ek[:PER_STRATUM - len(take)]
        selected.extend(take)
        log.info("  %s: date-keyed=%d entity-keyed=%d -> take %d (date-keyed first)",
                 stratum, len(dk), len(ek), len(take))

    cur.execute("""
        CREATE TABLE IF NOT EXISTS analytics.hard_neg_candidates_v3 (
            stratum text, a_id uuid, b_id uuid,
            a_title text, b_title text, a_subject text, b_subject text,
            trgm_title real, key_reason text,
            label text, label_reason text,
            PRIMARY KEY (a_id, b_id))""")
    cur.execute("TRUNCATE analytics.hard_neg_candidates_v3")
    out_rows = [(s, a, b, at, bt, asu, bsu, t, why)
                for (s, a, b, at, bt, asu, bsu, t, why) in selected]
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO analytics.hard_neg_candidates_v3 (stratum,a_id,b_id,a_title,b_title,"
        "a_subject,b_subject,trgm_title,key_reason) VALUES %s ON CONFLICT (a_id,b_id) DO NOTHING",
        out_rows,
    )
    cur.execute("GRANT SELECT ON analytics.hard_neg_candidates_v3 TO rigwire_app")
    cur.execute("GRANT SELECT, UPDATE ON analytics.hard_neg_candidates_v3 TO analytics_user")
    conn.commit()

    cur.execute("SELECT stratum, count(*) FILTER (WHERE key_reason LIKE 'title dates%%'), count(*) "
                "FROM analytics.hard_neg_candidates_v3 GROUP BY stratum ORDER BY stratum")
    for s, dk, tot in cur.fetchall():
        log.info("FINAL %s = %d  (date-keyed=%d)", s, tot, dk)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
