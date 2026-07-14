"""LLM-judge audit: sample recent production rows and re-score them with a STRONGER
model as an independent judge. Tracks stance/impact agreement over time so quality
drift is caught between full gold runs (the gold set is fixed; this watches the tail).

Usage:
    python -m backend.sentiment.judge_audit --worker qwen2.5-7b-instruct \
        --judge qwen2.5-32b-instruct --sample 500

Writes each comparison to analytics.sentiment_audit and prints the agreement rate.
Low agreement => investigate the worker/prompt; it does NOT auto-correct rows.
"""
from __future__ import annotations

import argparse
import os

import psycopg
from openai import OpenAI

from .engine import score_entity

ALERT_AGREEMENT = 0.75  # judge should agree with the worker on stance at least this often


def sample_rows(dsn: str, n: int) -> list[tuple[int, str, str, str]]:
    """Pull n random recent production rows joined to their frozen text."""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.article_id, s.entity, s.stance, s.impact
            FROM analytics.article_entity_sentiment s
            WHERE s.created_at > now() - interval '7 days'
            ORDER BY random()
            LIMIT %s
            """,
            (n,),
        )
        return cur.fetchall()


def fetch_text(cur, article_id: int) -> str | None:
    cur.execute(
        "SELECT coalesce(title,'') || ' — ' || left(coalesce(body,''), 1500) "
        "FROM public.articles WHERE id = %s",
        (article_id,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", required=True, help="model that produced the rows (for label)")
    ap.add_argument("--judge", required=True, help="stronger model to re-score with")
    ap.add_argument("--sample", type=int, default=500)
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1"))
    ap.add_argument("--dsn", default=os.environ["ANALYTICS_DSN"])
    args = ap.parse_args()

    rows = sample_rows(args.dsn, args.sample)
    client = OpenAI(base_url=args.base_url, api_key=os.environ.get("LLM_API_KEY", "x"))
    st_agree = im_agree = n = 0

    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        for article_id, entity, prod_stance, prod_impact in rows:
            text = fetch_text(cur, article_id)
            if not text:
                continue
            try:
                j = score_entity(client, args.judge, entity, text)
            except Exception as exc:
                print(f"  judge FAIL article={article_id} entity={entity!r}: {exc}")
                continue
            sa = j.stance == prod_stance
            ia = j.impact == prod_impact
            st_agree += sa
            im_agree += ia
            n += 1
            cur.execute(
                """
                INSERT INTO analytics.sentiment_audit
                  (article_id, entity, prod_stance, prod_impact,
                   judge_stance, judge_impact, judge_model, stance_agree, impact_agree)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (article_id, entity, prod_stance, prod_impact,
                 j.stance, j.impact, args.judge, sa, ia),
            )
        conn.commit()

    rate = st_agree / max(n, 1)
    print(f"audited={n}  stance_agree={rate:.3f}  impact_agree={im_agree/max(n,1):.3f}")
    if rate < ALERT_AGREEMENT:
        print(f"ALERT: judge/worker stance agreement {rate:.3f} < {ALERT_AGREEMENT}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
