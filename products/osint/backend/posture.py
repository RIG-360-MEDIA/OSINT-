"""Generic posture-scoring engine (Category-1 numerical intelligence).

Every metric here is a PURE FUNCTION of the user's prefs + the corpus — there
are ZERO hardcoded entity names. The principal is `prefs['primary_subject_id']`
and the targets/opposition are the watchlist (`watchlist.entity_meta`). A brand
new user just needs a prefs row; every score then works for them automatically.

Scoring backbone (shared by the favourability family):
  `article_stances` gives each *actor's* posture (18 labels x intensity) but no
  directional target, so "how favourable is outlet/journalist X toward person Y"
  is a SALIENCE PROXY — the stance polarity in articles where Y is mentioned,
  EXCLUDING Y's own self-stance, attributed to the outlet/byline. Every score
  ships with `n` (sample size) + a `confidence` band; thin samples degrade
  gracefully rather than lying (cold-start safety).
"""
from __future__ import annotations

import statistics
from typing import Any

from sqlalchemy import text

# stance label -> polarity, from the real 18-label distribution in the corpus.
POL = """CASE st.stance
 WHEN 'supportive' THEN 1 WHEN 'sympathetic' THEN 1 WHEN 'promotional' THEN 1 WHEN 'defensive' THEN 1
 WHEN 'admiration' THEN 1 WHEN 'admiring' THEN 1 WHEN 'honored' THEN 1 WHEN 'grateful' THEN 1 WHEN 'optimistic' THEN 1
 WHEN 'critical' THEN -1 WHEN 'mocking' THEN -1 WHEN 'concerned' THEN -1 WHEN 'lament' THEN -1 WHEN 'skeptical' THEN -1
 ELSE 0 END"""

# Articles where the principal entity is mentioned, inside the window.
_PSAL = """article_entity_mentions m JOIN articles a ON a.id=m.article_id JOIN sources s ON s.id=a.source_id
 WHERE m.entity_id=CAST(:pid AS uuid)
   AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
   AND a.collected_at <= analytics.now_sim()"""

_HIGH, _MED, _LOW = 20, 8, 3  # sample-size thresholds


def confidence(n: int) -> str:
    """Sample-size -> honest confidence band (used by every score + the UI)."""
    if n >= _HIGH:
        return "high"
    if n >= _MED:
        return "medium"
    if n >= _LOW:
        return "low"
    return "insufficient"


def principal_of(prefs: dict[str, Any]) -> tuple[str | None, str | None]:
    pid = prefs.get("primary_subject_id")
    name = (prefs.get("primary_subject_meta") or {}).get("name")
    return pid, name


def opposition_of(prefs: dict[str, Any]) -> list[tuple[str, str]]:
    pid = prefs.get("primary_subject_id")
    meta = (prefs.get("watchlist") or {}).get("entity_meta") or []
    return [(m["id"], m.get("name") or "?") for m in meta if m.get("id") and m["id"] != pid]


async def _q(db, sql: str, **p) -> list:
    return (await db.execute(text(sql), p)).fetchall()


# ───────────────────────── metrics ─────────────────────────

async def outlet_favourability(db, pid: str, wh: int) -> dict[str, Any]:
    """Per-outlet posture toward the principal, -100..+100, n>=3."""
    rows = await _q(db, f"""
      WITH p AS (SELECT DISTINCT a.id, a.source_id FROM {_PSAL})
      SELECT s.name src, count(DISTINCT p.id) n,
             round(100*avg(({POL})*st.intensity)::numeric,1) fav
      FROM p JOIN article_stances st ON st.article_id=p.id AND st.actor_entity_id<>CAST(:pid AS uuid)
      JOIN sources s ON s.id=p.source_id
      GROUP BY s.name HAVING count(DISTINCT p.id)>=3 ORDER BY fav ASC""", pid=pid, wh=wh)
    items = [{"outlet": r.src, "n": int(r.n), "favourability": float(r.fav)} for r in rows]
    return {"items": items, "n": len(items),
            "confidence": confidence(sum(i["n"] for i in items))}


async def share_of_voice(db, pid: str, opp: list[tuple[str, str]], wh: int) -> dict[str, Any]:
    ids = [pid] + [o[0] for o in opp]
    nm = {pid: "principal", **dict(opp)}
    rows = await _q(db, """
      SELECT m.entity_id::text id, count(DISTINCT a.id) n
      FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id
      WHERE m.entity_id=ANY(CAST(:ids AS uuid[]))
        AND a.collected_at>=analytics.now_sim()-make_interval(hours => :wh)
        AND a.collected_at<=analytics.now_sim()
      GROUP BY 1""", ids=ids, wh=wh)
    tot = sum(int(r.n) for r in rows) or 1
    items = sorted(({"entity_id": r.id, "name": nm.get(r.id, "?"), "articles": int(r.n),
                     "sov_pct": round(100 * int(r.n) / tot, 1)} for r in rows),
                   key=lambda x: -x["articles"])
    p_sov = next((i["sov_pct"] for i in items if i["entity_id"] == pid), 0.0)
    return {"items": items, "principal_sov_pct": p_sov, "n": tot, "confidence": confidence(tot)}


async def stance_mix(db, pid: str, wh: int) -> dict[str, Any]:
    rows = await _q(db, f"""
      WITH p AS (SELECT DISTINCT a.id, date_trunc('week',a.collected_at)::date wk FROM {_PSAL})
      SELECT p.wk::text wk,
        count(*) FILTER (WHERE ({POL})<0) critical,
        count(*) FILTER (WHERE ({POL})=0) neutral,
        count(*) FILTER (WHERE ({POL})>0) supportive
      FROM p JOIN article_stances st ON st.article_id=p.id AND st.actor_entity_id<>CAST(:pid AS uuid)
      GROUP BY p.wk ORDER BY p.wk""", pid=pid, wh=wh)
    items = [{"week": r.wk, "critical": int(r.critical), "neutral": int(r.neutral),
              "supportive": int(r.supportive)} for r in rows]
    return {"items": items, "n": len(items), "confidence": confidence(len(items) * _MED)}


async def weighted_pressure(db, pid: str, wh: int) -> dict[str, Any]:
    r = (await _q(db, f"""
      WITH p AS (SELECT DISTINCT a.id, COALESCE(s.source_tier,3) tier FROM {_PSAL})
      SELECT round(sum(CASE WHEN ({POL})<0 THEN st.intensity*(4-LEAST(p.tier,3)) ELSE 0 END)::numeric,1) pressure,
             count(*) FILTER (WHERE ({POL})<0) neg_n
      FROM p JOIN article_stances st ON st.article_id=p.id AND st.actor_entity_id<>CAST(:pid AS uuid)
    """, pid=pid, wh=wh))[0]
    neg = int(r.neg_n or 0)
    return {"pressure": float(r.pressure or 0), "negative_signals": neg, "n": neg, "confidence": confidence(neg)}


async def friend_foe_fence(db, pid: str, wh: int) -> dict[str, Any]:
    rows = await _q(db, f"""
      WITH p AS (SELECT DISTINCT a.id, s.name src FROM {_PSAL})
      SELECT p.src, count(DISTINCT p.id) n, round(100*avg(({POL})*st.intensity)::numeric,1) fav
      FROM p JOIN article_stances st ON st.article_id=p.id AND st.actor_entity_id<>CAST(:pid AS uuid)
      GROUP BY p.src HAVING count(DISTINCT p.id)>=3""", pid=pid, wh=wh)
    ally = [{"outlet": r.src, "favourability": float(r.fav), "n": int(r.n)} for r in rows if r.fav >= 15]
    foe = [{"outlet": r.src, "favourability": float(r.fav), "n": int(r.n)} for r in rows if r.fav <= -15]
    fence = [{"outlet": r.src, "favourability": float(r.fav), "n": int(r.n)} for r in rows if -15 < r.fav < 15]
    return {"ally": sorted(ally, key=lambda x: -x["favourability"]),
            "hostile": sorted(foe, key=lambda x: x["favourability"]),
            "fence": fence, "n": len(rows), "confidence": confidence(len(rows) * _LOW)}


async def allegiance_divergence(db, pid: str, opp: list[tuple[str, str]], wh: int) -> dict[str, Any]:
    if not opp:
        return {"items": [], "rival": None, "n": 0, "confidence": "insufficient"}
    rivals = await _q(db, """SELECT m.entity_id::text id, count(DISTINCT a.id) n
        FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id
        WHERE m.entity_id=ANY(CAST(:ids AS uuid[]))
          AND a.collected_at>=analytics.now_sim()-make_interval(hours => :wh)
        GROUP BY 1 ORDER BY 2 DESC LIMIT 1""", ids=[o[0] for o in opp], wh=wh)
    if not rivals:
        return {"items": [], "rival": None, "n": 0, "confidence": "insufficient"}
    rid = rivals[0].id
    rname = dict(opp).get(rid, "rival")
    rows = await _q(db, f"""
      WITH pp AS (SELECT DISTINCT a.id, s.name src FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id JOIN sources s ON s.id=a.source_id
                  WHERE m.entity_id=CAST(:pid AS uuid) AND a.collected_at>=analytics.now_sim()-make_interval(hours => :wh)),
           rp AS (SELECT DISTINCT a.id, s.name src FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id JOIN sources s ON s.id=a.source_id
                  WHERE m.entity_id=CAST(:rid AS uuid) AND a.collected_at>=analytics.now_sim()-make_interval(hours => :wh)),
           pf AS (SELECT pp.src, round(100*avg(({POL})*st.intensity)::numeric,1) fp, count(DISTINCT pp.id) n
                  FROM pp JOIN article_stances st ON st.article_id=pp.id AND st.actor_entity_id<>CAST(:pid AS uuid) GROUP BY pp.src),
           rf AS (SELECT rp.src, round(100*avg(({POL})*st.intensity)::numeric,1) fr
                  FROM rp JOIN article_stances st ON st.article_id=rp.id AND st.actor_entity_id<>CAST(:rid AS uuid) GROUP BY rp.src)
      SELECT pf.src, pf.n, pf.fp, rf.fr, (pf.fp-rf.fr) divergence
      FROM pf JOIN rf ON rf.src=pf.src WHERE pf.n>=3 ORDER BY divergence ASC""", pid=pid, rid=rid, wh=wh)
    items = [{"outlet": r.src, "n": int(r.n), "fav_principal": float(r.fp),
              "fav_rival": float(r.fr), "divergence": float(r.divergence)} for r in rows]
    return {"items": items, "rival": rname, "n": len(items), "confidence": confidence(len(items) * _LOW)}


async def stance_trajectory(db, pid: str, wh: int) -> dict[str, Any]:
    rows = await _q(db, f"""
      WITH p AS (SELECT DISTINCT a.id, EXTRACT(EPOCH FROM (a.collected_at-(analytics.now_sim()-make_interval(hours => :wh))))/86400.0 dnum FROM {_PSAL})
      SELECT p.dnum, ({POL})*st.intensity v
      FROM p JOIN article_stances st ON st.article_id=p.id AND st.actor_entity_id<>CAST(:pid AS uuid)""", pid=pid, wh=wh)
    xs = [float(r.dnum) for r in rows]
    ys = [float(r.v) for r in rows]
    if len(xs) < 4:
        return {"slope_per_day": None, "n": len(xs), "confidence": "insufficient"}
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs) or 1e-9
    slope = 100 * sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    half = (wh / 24) / 2
    early = [y for x, y in zip(xs, ys) if x < half]
    late = [y for x, y in zip(xs, ys) if x >= half]
    e = 100 * statistics.mean(early) if early else 0.0
    lt = 100 * statistics.mean(late) if late else 0.0
    return {"slope_per_day": round(slope, 2), "first_half_avg": round(e, 1),
            "second_half_avg": round(lt, 1),
            "direction": "warming" if slope > 0 else ("cooling" if slope < 0 else "flat"),
            "n": len(xs), "confidence": confidence(len(xs))}


async def quote_selection_bias(db, pid: str, opp: list[tuple[str, str]], wh: int) -> dict[str, Any]:
    rows = await _q(db, """
      WITH p AS (SELECT DISTINCT a.id, s.name src FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id JOIN sources s ON s.id=a.source_id
                 WHERE m.entity_id=CAST(:pid AS uuid) AND a.collected_at>=analytics.now_sim()-make_interval(hours => :wh))
      SELECT p.src,
        count(*) FILTER (WHERE q.speaker_entity_id=CAST(:pid AS uuid)) you,
        count(*) FILTER (WHERE q.speaker_entity_id=ANY(CAST(:opp AS uuid[]))) opp
      FROM p JOIN article_quotes q ON q.article_id=p.id
      GROUP BY p.src HAVING count(*) FILTER (WHERE q.speaker_entity_id=CAST(:pid AS uuid))
                          + count(*) FILTER (WHERE q.speaker_entity_id=ANY(CAST(:opp AS uuid[])))>=2
      ORDER BY opp DESC""", pid=pid, opp=[o[0] for o in opp] or [pid], wh=wh)
    items = [{"outlet": r.src, "quotes_principal": int(r.you), "quotes_opposition": int(r.opp)} for r in rows]
    return {"items": items, "n": len(items), "confidence": confidence(len(items) * _MED)}


async def attack_origination(db, pid: str, wh: int) -> dict[str, Any]:
    rows = await _q(db, f"""
      WITH p AS (SELECT a.id, s.name src, a.collected_at, a.title FROM {_PSAL})
      SELECT p.src, p.collected_at::text ts, left(p.title,90) title
      FROM p JOIN article_stances st ON st.article_id=p.id AND st.actor_entity_id<>CAST(:pid AS uuid)
      WHERE ({POL})<0 ORDER BY p.collected_at ASC LIMIT 8""", pid=pid, wh=wh)
    if not rows:
        return {"origin": None, "amplifiers": [], "n": 0, "confidence": "insufficient"}
    return {"origin": {"outlet": rows[0].src, "ts": rows[0].ts, "title": rows[0].title},
            "amplifiers": [{"outlet": r.src, "ts": r.ts} for r in rows[1:6]],
            "n": len(rows), "confidence": confidence(len(rows))}


async def issue_ownership(db, pid: str, wh: int) -> dict[str, Any]:
    rows = await _q(db, f"""
      WITH p AS (SELECT DISTINCT a.id, a.topic_category t FROM {_PSAL})
      SELECT p.t topic, count(DISTINCT p.id) n, round(100*avg(({POL})*st.intensity)::numeric,1) fav
      FROM p JOIN article_stances st ON st.article_id=p.id AND st.actor_entity_id<>CAST(:pid AS uuid)
      WHERE p.t IS NOT NULL GROUP BY p.t HAVING count(DISTINCT p.id)>=4 ORDER BY n DESC LIMIT 10""", pid=pid, wh=wh)
    items = [{"topic": r.topic, "n": int(r.n), "favourability": float(r.fav),
              "verdict": "owns" if r.fav > 10 else ("cedes" if r.fav < -10 else "contested")} for r in rows]
    return {"items": items, "n": len(items), "confidence": confidence(len(items) * _LOW)}


async def first_to_know(db, pid: str, wh: int) -> dict[str, Any]:
    r = (await _q(db, f"""
      WITH p AS (SELECT a.id, a.collected_at::date d FROM {_PSAL}), daily AS (SELECT d, count(*) c FROM p GROUP BY d)
      SELECT (SELECT min(d) FROM p)::text first_day, (SELECT d FROM daily ORDER BY c DESC LIMIT 1)::text peak_day,
             ((SELECT d FROM daily ORDER BY c DESC LIMIT 1)-(SELECT min(d) FROM p)) lead_days,
             (SELECT sum(c) FROM daily) n""", pid=pid, wh=wh))[0]
    return {"first_day": r.first_day, "peak_day": r.peak_day,
            "lead_days": int(r.lead_days) if r.lead_days is not None else None,
            "n": int(r.n or 0), "confidence": confidence(int(r.n or 0))}


async def counter_speed(db, pid: str, wh: int) -> dict[str, Any]:
    r = (await _q(db, f"""
      WITH p AS (SELECT DISTINCT a.id, a.collected_at FROM {_PSAL}),
           ev AS (SELECT p.collected_at ts, (CASE WHEN ({POL})<0 THEN 'neg' WHEN ({POL})>0 THEN 'pos' ELSE 'neu' END) k
                  FROM p JOIN article_stances st ON st.article_id=p.id AND st.actor_entity_id<>CAST(:pid AS uuid)),
           neg AS (SELECT ts FROM ev WHERE k='neg'), pos AS (SELECT ts FROM ev WHERE k='pos')
      SELECT round(avg(EXTRACT(EPOCH FROM (nextpos-ts))/3600)::numeric,1) hrs, count(*) n FROM (
        SELECT neg.ts, (SELECT min(pos.ts) FROM pos WHERE pos.ts>neg.ts) nextpos FROM neg) x WHERE nextpos IS NOT NULL
    """, pid=pid, wh=wh))[0]
    return {"median_hours": float(r.hrs) if r.hrs is not None else None,
            "pairs": int(r.n or 0), "n": int(r.n or 0), "confidence": confidence(int(r.n or 0))}


async def target_heat(db, opp: list[tuple[str, str]], wh: int) -> dict[str, Any]:
    if not opp:
        return {"items": [], "n": 0, "confidence": "insufficient"}
    nm = dict(opp)
    rows = await _q(db, f"""
      SELECT t.id::text id, count(DISTINCT a.id) vol,
             count(*) FILTER (WHERE ({POL})<0) neg,
             round(sum(CASE WHEN ({POL})<0 THEN st.intensity*(4-LEAST(COALESCE(s.source_tier,3),3)) ELSE 0 END)::numeric,1) heat
      FROM (SELECT unnest(CAST(:ids AS uuid[])) id) t
      JOIN article_entity_mentions m ON m.entity_id=t.id
      JOIN articles a ON a.id=m.article_id JOIN sources s ON s.id=a.source_id
      LEFT JOIN article_stances st ON st.article_id=a.id AND st.actor_entity_id<>t.id
      WHERE a.collected_at>=analytics.now_sim()-make_interval(hours => :wh)
      GROUP BY t.id ORDER BY heat DESC NULLS LAST""", ids=[o[0] for o in opp], wh=wh)
    items = [{"name": nm.get(r.id, "?"), "coverage": int(r.vol), "negative": int(r.neg or 0),
              "heat": float(r.heat or 0)} for r in rows]
    return {"items": items, "n": len(items), "confidence": confidence(len(items) * _LOW)}


async def cross_language_gap(db, pid: str, wh: int) -> dict[str, Any]:
    rows = await _q(db, f"""
      WITH p AS (SELECT DISTINCT a.id, a.language_iso lang FROM {_PSAL})
      SELECT COALESCE(p.lang,'?') lang, count(DISTINCT p.id) n, round(100*avg(({POL})*st.intensity)::numeric,1) fav
      FROM p JOIN article_stances st ON st.article_id=p.id AND st.actor_entity_id<>CAST(:pid AS uuid)
      GROUP BY p.lang HAVING count(DISTINCT p.id)>=3 ORDER BY fav""", pid=pid, wh=wh)
    items = [{"language": r.lang, "n": int(r.n), "favourability": float(r.fav)} for r in rows]
    gap = round(items[-1]["favourability"] - items[0]["favourability"], 1) if len(items) >= 2 else None
    return {"items": items, "gap": gap, "n": len(items), "confidence": confidence(sum(i["n"] for i in items))}


async def narrative_half_life(db, pid: str, wh: int) -> dict[str, Any]:
    rows = await _q(db, f"""WITH p AS (SELECT a.id, a.collected_at::date d FROM {_PSAL})
        SELECT d::text d, count(*) c FROM p GROUP BY d ORDER BY d""", pid=pid, wh=wh)
    series = [(r.d, int(r.c)) for r in rows]
    if not series:
        return {"peak": None, "half_life_days": None, "n": 0, "confidence": "insufficient"}
    pk_i = max(range(len(series)), key=lambda i: series[i][1])
    peak_d, peak_c = series[pk_i]
    half = peak_c / 2
    decay = next((i - pk_i for i in range(pk_i + 1, len(series)) if series[i][1] <= half), None)
    return {"peak_day": peak_d, "peak_count": peak_c, "half_life_days": decay,
            "sticky": decay is None, "n": sum(c for _, c in series), "confidence": confidence(len(series) * _LOW)}


# ───────────────────────── orchestrator ─────────────────────────

async def compute_posture(db, prefs: dict[str, Any], window_hours: int = 504) -> dict[str, Any]:
    """All 15 green-lit posture metrics for a user. Generic; cold-start safe."""
    pid, pname = principal_of(prefs)
    if not pid:
        return {"personalized": False, "reason": "no primary subject set", "metrics": {}}
    opp = opposition_of(prefs)
    wh = int(window_hours)
    return {
        "personalized": True, "subject": pname, "window_hours": wh,
        "metrics": {
            "outlet_favourability": await outlet_favourability(db, pid, wh),
            "share_of_voice": await share_of_voice(db, pid, opp, wh),
            "stance_mix": await stance_mix(db, pid, wh),
            "weighted_pressure": await weighted_pressure(db, pid, wh),
            "friend_foe_fence": await friend_foe_fence(db, pid, wh),
            "allegiance_divergence": await allegiance_divergence(db, pid, opp, wh),
            "stance_trajectory": await stance_trajectory(db, pid, wh),
            "quote_selection_bias": await quote_selection_bias(db, pid, opp, wh),
            "attack_origination": await attack_origination(db, pid, wh),
            "issue_ownership": await issue_ownership(db, pid, wh),
            "first_to_know": await first_to_know(db, pid, wh),
            "counter_speed": await counter_speed(db, pid, wh),
            "target_heat": await target_heat(db, opp, wh),
            "cross_language_gap": await cross_language_gap(db, pid, wh),
            "narrative_half_life": await narrative_half_life(db, pid, wh),
        },
    }
