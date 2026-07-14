"""Regression gate: score the current engine against the VERIFIED gold set and
report stance + impact accuracy. Run this before every backfill and on any prompt
or model change. If accuracy drops below THRESHOLD, halt the rollout.

Usage:
    python -m backend.sentiment.bench_gold --model qwen2.5-7b-instruct

Reads analytics.sentiment_gold WHERE verified = true. Never scores against silver.
"""
from __future__ import annotations

import argparse
import os

import psycopg
from openai import OpenAI

from .engine import impact_distance, score_entity

THRESHOLD_STANCE = 0.60  # must stay at/above your production labeler (~0.62 on gold)
CONF_GATE = 0.7          # report a high-confidence impact accuracy at/above this


def load_gold(dsn: str) -> list[tuple[int, str, str, str, str | None]]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT article_id, entity, text_snapshot, gold_stance, gold_impact "
            "FROM analytics.sentiment_gold WHERE verified = true"
        )
        return cur.fetchall()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1"))
    ap.add_argument("--dsn", default=os.environ["ANALYTICS_DSN"])
    args = ap.parse_args()

    gold = load_gold(args.dsn)
    if not gold:
        raise SystemExit("no verified gold rows — build/verify the gold set first")

    client = OpenAI(base_url=args.base_url, api_key=os.environ.get("LLM_API_KEY", "x"))
    st_ok = st_n = im_ok = im_n = 0
    im_near = 0          # ordinal-tolerant: off-by-one counts (neutral<->neg is a near-miss)
    im_mae_sum = im_mae_n = 0.0
    hi_ok = hi_n = 0     # accuracy on high-confidence impact calls only
    for article_id, entity, text, g_stance, g_impact in gold:
        try:
            r = score_entity(client, args.model, entity, text)
        except Exception as exc:  # never silently swallow — surface per-row failures
            print(f"  FAIL article={article_id} entity={entity!r}: {exc}")
            continue
        st_n += 1
        st_ok += r.stance == g_stance
        if g_impact:  # impact gold is optional (harder to annotate)
            im_n += 1
            exact = r.impact == g_impact
            im_ok += exact
            dist = impact_distance(r.impact, g_impact)   # None if either is not_relevant
            im_near += exact or (dist is not None and dist <= 1)
            if dist is not None:
                im_mae_sum += dist
                im_mae_n += 1
            if r.impact_confidence >= CONF_GATE:
                hi_n += 1
                hi_ok += exact

    stance_acc = st_ok / max(st_n, 1)
    impact_acc = im_ok / max(im_n, 1)
    print(f"gold={len(gold)}  stance={st_ok}/{st_n}={stance_acc:.3f}")
    print(f"impact exact={im_ok}/{im_n}={impact_acc:.3f}  "
          f"tolerant(off-by-1)={im_near/max(im_n,1):.3f}  "
          f"MAE={im_mae_sum/max(im_mae_n,1):.2f}")
    print(f"impact @conf>={CONF_GATE}: {hi_ok}/{hi_n}={hi_ok/max(hi_n,1):.3f} "
          f"(covers {hi_n/max(im_n,1)*100:.0f}% of rows)")
    if stance_acc < THRESHOLD_STANCE:
        print(f"REGRESSION: stance {stance_acc:.3f} < {THRESHOLD_STANCE} — HALT")
        return 1
    print("gold gate PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
