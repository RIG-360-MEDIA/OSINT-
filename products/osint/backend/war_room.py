"""War Room — the live crisis desk: what's attacking the principal, how bad, and the ammo.

Reuses the vetted posture metric family (weighted_pressure, counter_speed,
attack_origination, target_heat, friend_foe_fence, stance_trajectory) and adds targeted
queries for the threat stack, the field (momentum / attack-map / bloc), and the arsenal.
Source-grounded; POL + _BODY_PRESENT reused so every count is real. Precomputed (30-min cache).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from posture import POL, _BODY_PRESENT, compute_posture, current_mood, principal_of
from llm_synth import synthesize_paragraph
import i18n

WH = 504  # 21-day crisis window
_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_POSTURE = {"weighted_pressure", "counter_speed", "attack_origination", "target_heat",
            "friend_foe_fence", "stance_trajectory", "issue_ownership"}


def _day(dt) -> str:
    return f"{dt.day} {_MONTHS[dt.month]}" if dt else ""


def _lead_summary(cables: list[dict[str, Any]], pname: str, neg_stories: int,
                  trend_label: str, origin: str, days: int) -> str:
    """Plain-language situation read, composed from the real cable list + station
    fields. 3-5 grounded sentences, no invented numbers. `days` is the crisis
    window length (WH//24) so the prose can't lie if WH changes."""
    name = pname or "The principal"
    if not cables:
        return (f"{name} is facing no concentrated adverse storyline in this {days}-day window — "
                f"the board is quiet. Coverage is {neg_stories} negative stories over the period. "
                f"Keep watching; nothing has clustered into a sustained attack yet.")
    top = cables[0]
    n = int(top.get("src") or 0)
    outlets = int(top["facets"].get("outlets") or 0)
    topic = top["facets"].get("what", "an issue")
    trend_word = {"WORSENING": "worsening", "EASING": "easing",
                  "STEADY": "holding steady"}.get(trend_label, "mixed")
    sentences = [
        f"{name} is facing {len(cables)} adverse storyline(s) this window.",
        (f"The sharpest is “{topic}” — {n} critical piece(s)"
         + (f" across {outlets} outlet(s)" if outlets else "")
         + (f", originating with {origin}." if origin else ".")),
        f"Coverage is {trend_word}, with {neg_stories} negative stories over {days} days.",
    ]
    if len(cables) > 1:
        sentences.append(f"Also watch “{cables[1]['facets'].get('what', 'a second line')}”.")
    return " ".join(sentences)


def _sev(n: int, neg: float) -> str:
    # severity needs VOLUME, not just one harsh piece — a single negative article
    # is WATCH, never HIGH (avoids a lone outlet inflating the board).
    if n >= 8 or (n >= 5 and neg >= 0.5):
        return "CRITICAL"
    if n >= 3:
        return "HIGH"
    return "WATCH"


async def _threat_cables(db, pid: str, wh: int) -> list[dict[str, Any]]:
    """Adverse storylines: the principal's negative-stance coverage grouped by topic."""
    rows = (await db.execute(text(f"""
        WITH pa AS (
          SELECT a.id, a.title, a.topic_category, a.collected_at, s.name src, a.language_iso lang,
                 COALESCE(s.source_tier, 3) tier,
                 count(*) FILTER (WHERE ({POL}) < 0) negn,
                 avg(CASE WHEN ({POL}) < 0 THEN abs(st.intensity) END) negint
            FROM article_entity_mentions m
            JOIN articles a ON a.id = m.article_id
            JOIN sources s ON s.id = a.source_id
            JOIN article_stances st ON st.article_id = a.id AND st.actor_entity_id = CAST(:pid AS uuid)
           WHERE m.entity_id = CAST(:pid AS uuid)
             AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
             AND {_BODY_PRESENT}
           GROUP BY a.id, a.title, a.topic_category, a.collected_at, s.name, a.language_iso, s.source_tier
          HAVING count(*) FILTER (WHERE ({POL}) < 0) > 0
        )
        SELECT COALESCE(topic_category, 'OTHER') topic, count(*) n, count(DISTINCT src) outlets,
               round(avg(negint)::numeric, 2) avgneg, min(tier) tier,
               max(collected_at) latest, min(collected_at) first,
               (array_agg(title ORDER BY negint DESC NULLS LAST, collected_at DESC))[1] rep,
               (array_agg(id::text ORDER BY negint DESC NULLS LAST, collected_at DESC))[1] rep_id,
               (array_agg(lang ORDER BY negint DESC NULLS LAST, collected_at DESC))[1] rep_lang,
               (array_agg(src   ORDER BY collected_at ASC))[1] origin,
               (array_agg(DISTINCT src))[1:4] hits
          FROM pa GROUP BY 1 ORDER BY count(*) DESC, avg(negint) DESC NULLS LAST LIMIT 6
    """), {"pid": pid, "wh": wh})).fetchall()
    maxn = max((int(r.n) for r in rows), default=1)
    cables = []
    for r in rows:
        n, neg = int(r.n), float(r.avgneg or 0)
        topic = r.topic or "OTHER"
        cables.append({
            "id": topic, "sev": _sev(n, neg),
            "verdict": f"{topic.title()} — {n} adverse across {int(r.outlets)} outlet(s)",
            "score": f"−{round(neg * 100)}", "src": int(r.n),
            "receipt": {"reach": round(int(r.outlets) / 6, 2), "neg": round(neg, 2),
                        "vel": round(n / maxn, 2), "tier": round((4 - int(r.tier)) / 3, 2)},
            "claim": r.rep, "rep_id": r.rep_id, "rep_lang": r.rep_lang,
            "who": r.origin, "date": _day(r.latest), "origin": r.origin,
            "facets": {"what": topic.title(), "hurts": f"{n} pieces, {int(r.outlets)} outlets",
                       "outlets": int(r.outlets),
                       "acts": "Contest in your warmest outlet" if neg >= 0.4 else "Monitor",
                       "hits": list(r.hits or [])},
        })
    await i18n.attach_en(db, cables, "claim")
    return cables


async def _momentum(db, pid: str, person_ids: list[str], wh: int) -> list[dict[str, Any]]:
    rows = (await db.execute(text(f"""
        SELECT m.entity_id::text id, ed.canonical_name nm,
               count(DISTINCT a.id) vol,
               count(DISTINCT a.id) FILTER (WHERE EXISTS (
                   SELECT 1 FROM article_stances st WHERE st.article_id = a.id AND ({POL}) < 0)) neg,
               count(DISTINCT a.id) FILTER (WHERE a.collected_at >= analytics.now_sim() - make_interval(hours => :half)) recent
          FROM article_entity_mentions m
          JOIN articles a ON a.id = m.article_id
          JOIN entity_dictionary ed ON ed.id = m.entity_id
         WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
         GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 7
    """), {"ids": person_ids, "wh": wh, "half": wh // 2})).fetchall()
    out = []
    for r in rows:
        vol, recent = int(r.vol), int(r.recent)
        older = vol - recent
        dir_ = "up" if recent > older else "down" if recent < older else "flat"
        out.append({"name": r.nm, "vol": vol, "neg": int(r.neg),
                    "trend": "▲ rising" if dir_ == "up" else "▼ cooling" if dir_ == "down" else "steady",
                    "dir": dir_})
    return out


async def _attackmap(db, pid: str, person_ids: list[str], wh: int) -> dict[str, Any]:
    rows = (await db.execute(text(f"""
        SELECT ed.canonical_name rival, COALESCE(a.topic_category, 'OTHER') issue, count(DISTINCT a.id) n
          FROM article_entity_mentions m
          JOIN articles a ON a.id = m.article_id
          JOIN entity_dictionary ed ON ed.id = m.entity_id
         WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
           AND EXISTS (SELECT 1 FROM article_entity_mentions pm WHERE pm.article_id = a.id AND pm.entity_id = CAST(:pid AS uuid))
           AND EXISTS (SELECT 1 FROM article_stances st WHERE st.article_id = a.id AND ({POL}) < 0)
         GROUP BY 1, 2
    """), {"ids": person_ids, "pid": pid, "wh": wh})).fetchall()
    if not rows:
        return {"issues": [], "rivals": [], "grid": {}, "foot": "No co-occurring adverse coverage in window."}
    rivals_n: dict[str, int] = {}
    issues_n: dict[str, int] = {}
    grid: dict[str, dict[str, int]] = {}
    maxn = 1
    for r in rows:
        rivals_n[r.rival] = rivals_n.get(r.rival, 0) + int(r.n)
        issues_n[r.issue] = issues_n.get(r.issue, 0) + int(r.n)
        grid.setdefault(r.rival, {})[r.issue] = int(r.n)
        maxn = max(maxn, int(r.n))
    rivals = [k for k, _ in sorted(rivals_n.items(), key=lambda x: -x[1])][:5]
    issues = [k for k, _ in sorted(issues_n.items(), key=lambda x: -x[1])][:4]
    # Return RAW integer story counts (the frontend renders proportional bars +
    # the exact number). Also hand back per-rival/per-issue totals so the UI can
    # rank and label without recomputing.
    raw = {rv: {i: int(grid.get(rv, {}).get(i, 0)) for i in issues} for rv in rivals}
    return {"issues": [i.title() for i in issues], "issue_keys": issues,
            "rivals": rivals, "grid": {rv: {i.title(): raw[rv][i] for i in issues} for rv in rivals},
            "rival_totals": {rv: rivals_n[rv] for rv in rivals},
            "foot": "Adverse stories where each rival co-appears with you, by topic."}


async def _bloc(db, person_ids: list[str], wh: int) -> dict[str, Any]:
    rows = (await db.execute(text("""
        SELECT a1.nm n1, a2.nm n2, count(DISTINCT a1.article_id) shared FROM (
            SELECT m.article_id, m.entity_id, ed.canonical_name nm
              FROM article_entity_mentions m JOIN entity_dictionary ed ON ed.id = m.entity_id
              JOIN articles a ON a.id = m.article_id
             WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
               AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
        ) a1 JOIN (
            SELECT m.article_id, m.entity_id, ed.canonical_name nm
              FROM article_entity_mentions m JOIN entity_dictionary ed ON ed.id = m.entity_id
             WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
        ) a2 ON a2.article_id = a1.article_id AND a2.entity_id > a1.entity_id
         GROUP BY 1, 2 HAVING count(DISTINCT a1.article_id) >= 3 ORDER BY 3 DESC LIMIT 6
    """), {"ids": person_ids, "wh": wh})).fetchall()
    edges = [{"a": r.n1, "b": r.n2, "n": int(r.shared)} for r in rows]
    paired = {e["a"] for e in edges} | {e["b"] for e in edges}
    return {"edges": edges, "solo": [], "foot": "Watched figures who repeatedly share coverage.",
            "_paired": list(paired)}


async def _ammunition(db, pid: str, wh: int) -> list[dict[str, Any]]:
    rows = (await db.execute(text(f"""
        SELECT a.title, a.url FROM article_entity_mentions m
          JOIN articles a ON a.id = m.article_id JOIN article_stances st ON st.article_id = a.id AND st.actor_entity_id = CAST(:pid AS uuid)
         WHERE m.entity_id = CAST(:pid AS uuid)
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
           AND {_BODY_PRESENT}
         GROUP BY a.id, a.title, a.url HAVING avg(CASE WHEN ({POL}) > 0 THEN 1 WHEN ({POL}) < 0 THEN -1 ELSE 0 END) > 0.3
         ORDER BY max(a.collected_at) DESC LIMIT 8
    """), {"pid": pid, "wh": wh})).fetchall()
    items = [{"text": r.title, "url": r.url} for r in rows]
    await i18n.attach_en(db, items, "text")
    return items


async def _intercepts(db, pid: str, person_ids: list[str], wh: int) -> list[dict[str, Any]]:
    """Watched voices quoted in articles that ALSO cover the principal AND carry a
    negative stance — i.e. opposition on record where it touches you."""
    rows = (await db.execute(text(f"""
        SELECT q.quote_text q, NULLIF(q.quote_text_en,'') qen, ed.canonical_name who,
               s.name src, COALESCE(s.source_tier,3) tier, a.url
          FROM article_quotes q
          JOIN articles a ON a.id = q.article_id
          JOIN sources s ON s.id = a.source_id
          JOIN entity_dictionary ed ON ed.id = q.speaker_entity_id
         WHERE q.speaker_entity_id = ANY(CAST(:ids AS uuid[]))
           AND q.speaker_entity_id <> CAST(:pid AS uuid)
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
           AND length(COALESCE(q.quote_text_en, q.quote_text)) BETWEEN 24 AND 240
           AND EXISTS (SELECT 1 FROM article_entity_mentions pm WHERE pm.article_id = a.id AND pm.entity_id = CAST(:pid AS uuid))
           AND EXISTS (SELECT 1 FROM article_stances st WHERE st.article_id = a.id AND st.actor_entity_id = CAST(:pid AS uuid) AND ({POL}) < 0)
         ORDER BY a.collected_at DESC LIMIT 6
    """), {"ids": person_ids, "pid": pid, "wh": wh})).fetchall()
    out = [{"quote": r.q, "quote_en": (r.qen if (r.qen and r.qen != r.q) else None),
            "who": r.who, "role": "watchlist", "tier": f"T{r.tier}", "src": r.src, "url": r.url} for r in rows]
    await i18n.attach_en(db, out, "quote")
    return out


async def build_war_room(db, prefs: dict[str, Any]) -> dict[str, Any]:
    pid, pname = principal_of(prefs)
    if not pid:
        return {"personalized": False}
    meta = prefs["watchlist"]["entity_meta"]
    person_ids = [m["id"] for m in meta if m.get("type") == "person"]

    posture = await compute_posture(db, prefs, window_hours=WH, only=_POSTURE)
    M = posture.get("metrics", {})
    wp = M.get("weighted_pressure", {})
    ao = M.get("attack_origination", {}).get("origin") or {}
    th = M.get("target_heat", {}).get("items", [])
    cables = await _threat_cables(db, pid, WH)
    ammo = await _ammunition(db, pid, WH)
    intercepts = await _intercepts(db, pid, person_ids, WH)

    # shared canonical 3-day headline mood — the ONE directed, intensity-weighted
    # read that Home, War Room and the Report all show identically. Distinct from
    # the 21-day crisis stats below (different window: 'last 3 days' vs 21-DAY).
    mood = await current_mood(db, pid)

    now = (await db.execute(text("SELECT analytics.now_sim() AS n"))).scalar()
    critical = sum(1 for c in cables if c["sev"] == "CRITICAL")

    # mood trend toward the principal (directed-stance slope) → a plain word for the stat bar
    _dir = M.get("stance_trajectory", {}).get("direction")
    trend_label, trend_tone = {
        "cooling": ("WORSENING", "neg"),
        "warming": ("EASING", "pos"),
        "flat": ("STEADY", None),
    }.get(_dir, ("—", None))

    # crisis lead from the worst cable / attack origin
    lead_cable = cables[0] if cables else None
    lead = {
        "tag": "CRISIS WATCH",
        "slug": (lead_cable["facets"]["what"] if lead_cable else "No active crisis"),
        "windowEst": ("~48h to spread" if lead_cable and lead_cable["sev"] in ("CRITICAL", "HIGH") else "contained"),
        "read": (f"“{lead_cable.get('claim_en') or lead_cable['claim']}” — your sharpest adverse line, {lead_cable['facets']['hurts']}."
                 if lead_cable else "No concentrated adverse storyline in the window."),
        "trigger": (f"origin {ao.get('outlet','')}" if ao.get("outlet") else "—"),
        "basis": f"{wp.get('negative_signals', 0)} negative signals",
        "caveat": "Estimate from coverage spread + velocity, not a forecast.",
        "metric": {"label": "Threat lead", "value": (lead_cable["score"] if lead_cable else "—"),
                   "n": (lead_cable["src"] if lead_cable else 0), "confidence": wp.get("confidence", "low")},
    }
    lead["summary"] = _lead_summary(
        cables, pname, wp.get("negative_signals", 0), trend_label,
        (ao.get("outlet") or lead_cable["origin"]) if lead_cable else "", WH // 24)

    # pre-draft counter (LLM, gated) for the lead cable
    predraft_en = None
    if lead_cable:
        facts = f"Adverse line: {lead_cable['claim']}. Topic: {lead_cable['facets']['what']}. Principal: {pname}."
        predraft_en = await synthesize_paragraph(
            system=("/no_think Respond in English only. You are a government communications aide. Draft ONE "
                    "tight rebuttal paragraph (max 55 words) the principal could issue. Factual, calm, no invented numbers."),
            facts=facts, source_check=facts, min_words=10, min_chars=40)
    arsenal = {
        "forCable": (lead_cable["facets"]["what"] if lead_cable else "—"),
        "ammunition": ammo or [{"text": "No clean supportive lines surfaced this window."}],
        "predraft": {"lang": "EN", "words": len((predraft_en or "").split()),
                     "en": predraft_en or "Draft unavailable — compose from the ammunition above.",
                     "flag": "Draft only — sign-off required."},
        "intercepts": intercepts,
    }

    # counter-attack: opposition under fire (target_heat), exclude the principal
    counterattack = {
        "items": [{"name": t["name"], "issue": "coverage", "heat": f"heat {round(t['heat'])}",
                   "line": f"{t['negative']} negative pieces of {t['coverage']} total."}
                  for t in th if t["name"] not in ("principal", pname)][:4],
        "metric": {"label": "Opposition heat", "value": str(len(th)), "n": sum(t["coverage"] for t in th),
                   "confidence": M.get("target_heat", {}).get("confidence", "low")},
    }

    return {
        "personalized": True,
        "station": {
            "desk": pname,
            "mood": mood,
            "activeAttacks": len(cables),
            "serious": critical,
            "negStories": wp.get("negative_signals", 0),
            "trendLabel": trend_label,
            "trendTone": trend_tone,
            "asOf": f"AS OF {_day(now)} {now.year if now else ''}",
            "window": "21-DAY WINDOW",
        },
        "lead": lead,
        "cables": cables,
        "arsenal": arsenal,
        "counterattack": counterattack,
    }
