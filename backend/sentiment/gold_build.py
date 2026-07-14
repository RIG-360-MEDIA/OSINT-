"""Build / grow the benchmark gold set.

Two sources feed analytics.sentiment_gold:
  1. HUMAN seed (verified=true): the 40 pairs hand-annotated during the engine
     evaluation, loaded from gold_seed_human.csv. These are the trustworthy floor.
  2. SILVER (verified=false): fresh (article, entity) pairs sampled from the corpus
     and PRE-labeled by a strong model. A human then reviews these in the app and
     flips verified=true. Silver is NEVER used by the regression gate until verified.

This separation enforces the project rule: no fabricated eval data. A model-labeled
row is explicitly SILVER until a human signs off; only then does it count as gold.

Usage:
    python -m backend.sentiment.gold_build --load-human            # one-time seed
    python -m backend.sentiment.gold_build --silver 160 \
        --judge qwen2.5-32b-instruct                               # grow to ~200
"""
from __future__ import annotations

import argparse
import csv
import os
import pathlib

import psycopg
from openai import OpenAI

from .engine import score_entity

HERE = pathlib.Path(__file__).parent


def load_human(dsn: str) -> int:
    path = HERE / "gold_seed_human.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO analytics.sentiment_gold
                  (article_id, entity, text_snapshot, gold_stance, gold_impact, verified, source)
                VALUES (NULL, %s, %s, %s, %s, true, 'human')
                ON CONFLICT (article_id, entity) DO NOTHING
                """,
                (r["entity"], r["text_snapshot"], r["gold_stance"], r["gold_impact"]),
            )
        conn.commit()
    return len(rows)


def load_reviewed(dsn: str) -> tuple[int, int]:
    """Load gold_candidates_silver.csv. Rows a human has filled in (human_stance set)
    become VERIFIED gold using the human labels; unreviewed rows stay SILVER.

    This is the step that turns model pre-labels into trustworthy gold — loading silver
    as-is would be circular (scoring the model against its own predictions).
    """
    path = HERE / "gold_candidates_silver.csv"
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    ver = sil = 0
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for r in rows:
            hs = (r.get("human_stance") or "").strip()
            hi = (r.get("human_impact") or "").strip() or None
            if hs:  # human-reviewed -> verified gold
                cur.execute(
                    """
                    INSERT INTO analytics.sentiment_gold
                      (article_id, entity, text_snapshot, gold_stance, gold_impact, verified, source)
                    VALUES (NULL, %s, %s, %s, %s, true, 'human')
                    ON CONFLICT (article_id, entity) DO NOTHING
                    """,
                    (r["entity"], r["text_snapshot"], hs, hi),
                )
                ver += 1
            else:  # not yet reviewed -> silver, excluded from the gate
                cur.execute(
                    """
                    INSERT INTO analytics.sentiment_gold
                      (article_id, entity, text_snapshot, gold_stance, gold_impact, verified, source)
                    VALUES (NULL, %s, %s, %s, %s, false, 'silver')
                    ON CONFLICT (article_id, entity) DO NOTHING
                    """,
                    (r["entity"], r["text_snapshot"], r["silver_stance"], r["silver_impact"]),
                )
                sil += 1
        conn.commit()
    return ver, sil


def sample_pairs(dsn: str, n: int) -> list[tuple[int, str, str]]:
    """Diverse (article_id, entity, text) pairs the model has NOT yet been gold-tested on.

    Pulls entities from the live per-article table so the benchmark reflects real
    inputs. Adjust the source table/columns to match your entity store.
    """
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.id, s.actor,
                   coalesce(a.title,'') || ' — ' || left(coalesce(a.body,''), 1500)
            FROM analytics.article_stances s
            JOIN public.articles a ON a.id = s.article_id
            WHERE a.created_at > now() - interval '30 days'
            ORDER BY random()
            LIMIT %s
            """,
            (n,),
        )
        return cur.fetchall()


def build_silver(dsn: str, base_url: str, judge: str, n: int) -> int:
    client = OpenAI(base_url=base_url, api_key=os.environ.get("LLM_API_KEY", "x"))
    written = 0
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for article_id, entity, text in sample_pairs(dsn, n):
            try:
                r = score_entity(client, judge, entity, text)
            except Exception as exc:
                print(f"  silver FAIL article={article_id} entity={entity!r}: {exc}")
                continue
            cur.execute(
                """
                INSERT INTO analytics.sentiment_gold
                  (article_id, entity, text_snapshot, gold_stance, gold_impact, verified, source)
                VALUES (%s,%s,%s,%s,%s, false, 'silver')
                ON CONFLICT (article_id, entity) DO NOTHING
                """,
                (article_id, entity, text[:1500], r.stance, r.impact),
            )
            written += cur.rowcount
        conn.commit()
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--load-human", action="store_true")
    ap.add_argument("--load-reviewed", action="store_true",
                    help="load gold_candidates_silver.csv: human-filled rows -> verified gold")
    ap.add_argument("--silver", type=int, default=0)
    ap.add_argument("--judge", default="qwen2.5-32b-instruct")
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1"))
    ap.add_argument("--dsn", default=os.environ["ANALYTICS_DSN"])
    args = ap.parse_args()

    if args.load_human:
        print(f"seeded {load_human(args.dsn)} human-verified gold rows")
    if args.load_reviewed:
        ver, sil = load_reviewed(args.dsn)
        print(f"loaded {ver} verified (human-reviewed) + {sil} silver rows")
    if args.silver:
        n = build_silver(args.dsn, args.base_url, args.judge, args.silver)
        print(f"added {n} SILVER rows (verified=false) — review + flip verified in the app")
    if not (args.load_human or args.load_reviewed or args.silver):
        ap.error("nothing to do: pass --load-human, --load-reviewed, and/or --silver N")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
