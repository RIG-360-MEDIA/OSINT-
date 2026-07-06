#!/usr/bin/env python3
"""On-demand keyword sentiment — Scenario 2.

The keyword is NOT a precomputed entity (not in the dict, not extracted), so
there is nothing in ``analytics.article_entity_sentiment`` to aggregate. Instead:

  1. FTS the corpus for the keyword over a recent window  -> matching articles
  2. Live-score each article with the SAME two-field scorer as the backfill,
     target = the keyword itself (subject perspective)     -> stance + impact
  3. Aggregate + CACHE the (keyword, window) result         -> 2nd call is instant

Prompts + label normalization are imported from ``backfill.py`` so on-demand and
bulk results are produced by identical logic. The default lane is ``cloud``
(low on-demand volume, fast, keys already in rig-backend's env); ``ollama`` is
available for local scoring.

CLI (inside rig-backend, or on a node with the DB tunnel + wenv):
  python3 keyword_sentiment.py --keyword "operation sindoor" --days 30
  python3 keyword_sentiment.py --keyword "xyz corp" --days 14 --lane ollama \
      --endpoint http://127.0.0.1:11434 --model qwen2.5:7b-instruct
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Optional

import psycopg2
from psycopg2.extras import execute_values

from backfill import CLOUD, CLOUD_MODELS, SCHEMA, SYS_ONE, UA, norm, um1

DSN = os.environ.get("DATABASE_URL_SYNC", "postgresql://rig:@rig-postgres:5432/rig")
FTS_CFG = os.environ.get("ASKRIG_FTS_CONFIG", "simple")
CACHE_TTL_MIN = int(os.environ.get("KW_SENT_TTL_MIN", "360"))   # 6h; recompute after this
DEFAULT_CAP = int(os.environ.get("KW_SENT_CAP", "200"))         # max articles scored per call
DEFAULT_CONC = int(os.environ.get("KW_SENT_CONC", "8"))

# ordinal weights for the -1..1 summary scores
STANCE_W = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
IMPACT_W = {"positive": 1.0, "negative": -1.0, "neutral": 0.0, "not_relevant": 0.0}

Scorer = Callable[[str, str], Optional[tuple]]  # (keyword, text) -> (stance, impact, conf, model) | None


@dataclass(frozen=True)
class Hit:
    article_id: str
    stance: str
    impact: str
    impact_confidence: Optional[float]
    published_at: object
    model: str


# --------------------------------------------------------------------------- #
# Discovery — match on title + lead (the exact text the scorer reads, so
# discovery and scoring are consistent) plus the name-weighted `fts` index.
# Windowing/ordering use `collected_at`, which is indexed (published_at is not,
# and carries 1970-epoch junk). A trigram GIN index on title+lead
# (articles_titlelead_trgm_idx) makes the ILIKE arms fast for arbitrary
# keywords; without it, discovery still works but seq-scans the window.
# --------------------------------------------------------------------------- #
# the concatenated title+lead expression the trigram index is built on — MUST be
# kept byte-identical between the index DDL and this query for the index to apply.
_TITLELEAD = ("coalesce(title,'') || ' ' || coalesce(lead_text_original,'') || ' ' "
              "|| coalesce(lead_text_translated,'')")

_SEARCH_SQL = f"""
SELECT id::text,
       coalesce(title,'') || ' — ' || coalesce(lead_text_original, lead_text_translated, '') AS text,
       published_at
FROM articles
WHERE collected_at > now() - make_interval(days => %(days)s)
  AND substrate_status = 'ok' AND NOT is_duplicate
  AND ( ({_TITLELEAD}) ILIKE %(pat)s
        OR fts @@ websearch_to_tsquery(%(cfg)s, %(q)s) )
ORDER BY collected_at DESC
LIMIT %(cap)s
"""


def _like_pattern(keyword: str) -> str:
    # escape LIKE metacharacters so a keyword with % or _ matches literally
    esc = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def search(conn, keyword: str, days: int, cap: int) -> list[tuple]:
    """Return up to ``cap`` recent (id, text, published_at) rows mentioning the keyword."""
    with conn.cursor() as c:
        c.execute(_SEARCH_SQL, {"cfg": FTS_CFG, "q": keyword, "pat": _like_pattern(keyword),
                                "days": days, "cap": cap})
        return c.fetchall()  # [(id, text, published_at), ...]


# --------------------------------------------------------------------------- #
# Scorers (reuse SYS_ONE / um1 / SCHEMA / norm from backfill.py)
# --------------------------------------------------------------------------- #
def _post_json(url: str, key: str, payload: dict) -> str:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=90).read())["choices"][0]["message"]["content"]


def make_cloud_scorer() -> Scorer:
    keys = {p: [k.strip() for k in os.environ.get(v, "").split(",") if k.strip()]
            for p, (_, v) in CLOUD.items()}
    rr = {"i": 0}

    def score(keyword: str, text: str) -> Optional[tuple]:
        for att in range(4):  # rotate (provider, model) + key, back off on rate limits
            prov, model = CLOUD_MODELS[rr["i"] % len(CLOUD_MODELS)]
            rr["i"] += 1
            url, _ = CLOUD[prov]
            kl = keys.get(prov) or []
            if not kl:
                continue
            key = kl[rr["i"] % len(kl)]
            try:
                content = _post_json(url, key, {
                    "model": model, "temperature": 0, "max_tokens": 120,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": SYS_ONE},
                                 {"role": "user", "content": um1(keyword, text)}]})
                m = re.search(r"\{.*\}", content, re.S)
                if not m:
                    return None
                j = json.loads(m.group(0))
                s, im = norm(j.get("stance")), norm(j.get("impact"), True)
                return (s, im, j.get("impact_confidence"), model) if s and im else None
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and att < 3:
                    time.sleep(1.5 * (att + 1))
                    continue
                return None
            except Exception:
                return None
        return None

    return score


def make_ollama_scorer(endpoint: str, model: str) -> Scorer:
    url = endpoint.rstrip("/") + "/api/chat"

    def score(keyword: str, text: str) -> Optional[tuple]:
        try:
            body = json.dumps({
                "model": model, "stream": False, "options": {"temperature": 0}, "format": SCHEMA,
                "messages": [{"role": "system", "content": SYS_ONE},
                             {"role": "user", "content": um1(keyword, text)}]}).encode()
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            content = json.loads(urllib.request.urlopen(req, timeout=90).read())["message"]["content"]
            j = json.loads(content)
            s, im = norm(j.get("stance")), norm(j.get("impact"), True)
            return (s, im, j.get("impact_confidence"), model) if s and im else None
        except Exception:
            return None

    return score


# --------------------------------------------------------------------------- #
# Aggregate
# --------------------------------------------------------------------------- #
def aggregate(hits: list[Hit]) -> dict:
    n = len(hits)
    sc = Counter(h.stance for h in hits)
    ic = Counter(h.impact for h in hits)

    def signed(counter: Counter, weights: dict) -> Optional[float]:
        if not n:
            return None
        return round(sum(weights[k] * v for k, v in counter.items()) / n, 3)

    return {
        "n_scored": n,
        "stance": {"positive": sc["positive"], "negative": sc["negative"], "neutral": sc["neutral"]},
        "impact": {"positive": ic["positive"], "negative": ic["negative"],
                   "neutral": ic["neutral"], "not_relevant": ic["not_relevant"]},
        "stance_score": signed(sc, STANCE_W),
        "impact_score": signed(ic, IMPACT_W),
    }


# --------------------------------------------------------------------------- #
# Cache read / write
# --------------------------------------------------------------------------- #
def _read_cache(conn, kw: str, days: int) -> Optional[dict]:
    with conn.cursor() as c:
        c.execute(
            """SELECT n_matched, n_scored, capped, stance_pos, stance_neg, stance_neu,
                      impact_pos, impact_neg, impact_neu, impact_nr, stance_score, impact_score,
                      model, source, computed_at
               FROM analytics.keyword_sentiment_cache
               WHERE keyword_norm = %s AND window_days = %s
                 AND computed_at > now() - make_interval(mins => %s)""",
            (kw, days, CACHE_TTL_MIN))
        r = c.fetchone()
    if not r:
        return None
    (n_matched, n_scored, capped, spos, sneg, sneu, ipos, ineg, ineu, inr,
     sscore, iscore, model, source, computed_at) = r
    return {
        "keyword": kw, "window_days": days, "cached": True,
        "n_matched": n_matched, "n_scored": n_scored, "capped": capped,
        "stance": {"positive": spos, "negative": sneg, "neutral": sneu},
        "impact": {"positive": ipos, "negative": ineg, "neutral": ineu, "not_relevant": inr},
        "stance_score": sscore, "impact_score": iscore,
        "model": model, "source": source, "computed_at": computed_at.isoformat(),
    }


def _write_cache(conn, kw: str, days: int, n_matched: int, capped: bool,
                 agg: dict, hits: list[Hit], model: str, source: str) -> None:
    st, im = agg["stance"], agg["impact"]
    with conn.cursor() as c:
        c.execute(
            """INSERT INTO analytics.keyword_sentiment_cache
                 (keyword_norm, window_days, n_matched, n_scored, capped,
                  stance_pos, stance_neg, stance_neu,
                  impact_pos, impact_neg, impact_neu, impact_nr,
                  stance_score, impact_score, model, source, computed_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
               ON CONFLICT (keyword_norm, window_days) DO UPDATE SET
                 n_matched=EXCLUDED.n_matched, n_scored=EXCLUDED.n_scored, capped=EXCLUDED.capped,
                 stance_pos=EXCLUDED.stance_pos, stance_neg=EXCLUDED.stance_neg, stance_neu=EXCLUDED.stance_neu,
                 impact_pos=EXCLUDED.impact_pos, impact_neg=EXCLUDED.impact_neg,
                 impact_neu=EXCLUDED.impact_neu, impact_nr=EXCLUDED.impact_nr,
                 stance_score=EXCLUDED.stance_score, impact_score=EXCLUDED.impact_score,
                 model=EXCLUDED.model, source=EXCLUDED.source, computed_at=now()""",
            (kw, days, n_matched, agg["n_scored"], capped,
             st["positive"], st["negative"], st["neutral"],
             im["positive"], im["negative"], im["neutral"], im["not_relevant"],
             agg["stance_score"], agg["impact_score"], model, source))
        # refresh the per-article drill-down for this (keyword, window)
        c.execute("DELETE FROM analytics.keyword_sentiment_hits WHERE keyword_norm=%s AND window_days=%s",
                  (kw, days))
        if hits:
            execute_values(
                c, """INSERT INTO analytics.keyword_sentiment_hits
                        (keyword_norm, window_days, article_id, stance, impact,
                         impact_confidence, published_at, model) VALUES %s""",
                [(kw, days, h.article_id, h.stance, h.impact, h.impact_confidence, h.published_at, h.model)
                 for h in hits])
    conn.commit()


def _empty_result(kw: str, days: int) -> dict:
    return {"keyword": kw, "window_days": days, "cached": False, "n_matched": 0, "n_scored": 0,
            "capped": False, "stance": {"positive": 0, "negative": 0, "neutral": 0},
            "impact": {"positive": 0, "negative": 0, "neutral": 0, "not_relevant": 0},
            "stance_score": None, "impact_score": None, "source": "ondemand",
            "note": "no mentions of this keyword in the window"}


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def get_keyword_sentiment(conn, keyword: str, window_days: int = 30, *, lane: str = "cloud",
                          endpoint: str = "http://127.0.0.1:11434", model: Optional[str] = None,
                          cap: int = DEFAULT_CAP, conc: int = DEFAULT_CONC,
                          force: bool = False) -> dict:
    """Return two-field sentiment for an arbitrary keyword over the last ``window_days``.

    Serves from cache when a fresh (< TTL) entry exists unless ``force``. Otherwise
    FTS-discovers mentions, live-scores them, aggregates, caches, and returns.
    """
    kw = " ".join(keyword.split()).lower()
    if not kw:
        raise ValueError("keyword is empty")

    if not force:
        cached = _read_cache(conn, kw, window_days)
        if cached:
            return cached

    # fetch cap+1 so we can tell whether the window held more than we scored
    rows = search(conn, keyword, window_days, cap + 1)
    capped = len(rows) > cap
    rows = rows[:cap]
    n_matched = len(rows)  # a floor when capped (">= cap"); exact otherwise

    if n_matched == 0:
        _write_cache(conn, kw, window_days, 0, False, aggregate([]), [],
                     model="none", source="ondemand")
        return _empty_result(kw, window_days)

    scorer = (make_cloud_scorer() if lane == "cloud"
              else make_ollama_scorer(endpoint, model or "qwen2.5:7b-instruct"))

    with ThreadPoolExecutor(max_workers=conc) as ex:
        scored = list(ex.map(lambda r: scorer(keyword, r[1]), rows))

    hits = [Hit(aid, r[0], r[1], r[2], pub, r[3])
            for (aid, _text, pub), r in zip(rows, scored) if r]

    agg = aggregate(hits)
    used_model = hits[0].model if hits else (model or lane)
    _write_cache(conn, kw, window_days, n_matched, capped, agg, hits, used_model, "ondemand")

    result = {"keyword": kw, "window_days": window_days, "cached": False,
              "n_matched": n_matched, "capped": capped, "source": "ondemand",
              "model": used_model, **agg,
              "top": [{"article_id": h.article_id, "stance": h.stance, "impact": h.impact}
                      for h in hits[:20]]}
    return result


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="On-demand keyword sentiment (Scenario 2)")
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--lane", choices=["cloud", "ollama"], default="cloud")
    ap.add_argument("--endpoint", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="qwen2.5:7b-instruct")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP)
    ap.add_argument("--conc", type=int, default=DEFAULT_CONC)
    ap.add_argument("--force", action="store_true", help="ignore cache; recompute")
    a = ap.parse_args()

    conn = psycopg2.connect(DSN)
    t0 = time.time()
    out = get_keyword_sentiment(conn, a.keyword, a.days, lane=a.lane, endpoint=a.endpoint,
                                model=a.model, cap=a.cap, conc=a.conc, force=a.force)
    out["elapsed_s"] = round(time.time() - t0, 1)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    conn.close()


if __name__ == "__main__":
    main()
