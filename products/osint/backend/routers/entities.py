"""GET /api/brief/entities — 4 Watched Entity cards.

Ported from backend/observability/brief_entities.py (parallel session).
Same hybrid FK-then-ILIKE matching strategy. Same 4 hardcoded entities.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from llm_synth import synthesize_dossier

router = APIRouter(prefix="/api/brief", tags=["brief"])


ENTITIES_CONFIG: list[dict[str, Any]] = [
    {
        "rank": "01", "tone": "rose", "classification": "High Influence",
        "name": "N. Chandrababu Naidu", "init": "CN",
        "image": "images/entity-naidu.png",
        "party": "TDP", "region": "Andhra Pradesh",
        "regional_label": "South India", "region_key": "south",
        "tag": "Opposition Leader",
        "entity_uuid": "ca35f636-000e-40f5-8a16-69d3f0b14621",
        "patterns": ["%chandrababu%naidu%", "%n. chandrababu%", "chandrababu naidu"],
    },
    {
        "rank": "02", "tone": "cyan", "classification": "High Influence",
        "name": "Rahul Gandhi", "init": "RG",
        "image": "images/entity-rahul-gandhi.png",
        "party": "INC", "region": "National",
        "regional_label": "North & West India", "region_key": "north",
        "tag": "National Figure",
        "entity_uuid": "13676001-3789-495e-9b7a-a6ffa2d7d0bc",
        "patterns": ["%rahul gandhi%", "%rahul%gandhi%"],
    },
    {
        "rank": "03", "tone": "amber", "classification": "Rising",
        "name": "Akhilesh Yadav", "init": "AY",
        "image": "images/entity-akhilesh-yadav.png",
        "party": "SP", "region": "Uttar Pradesh",
        "regional_label": "Uttar Pradesh", "region_key": "up",
        "tag": "Regional Leader",
        "entity_uuid": "8b49e04c-65aa-4b8e-8d90-e7b250c98df7",
        "patterns": ["%akhilesh%yadav%", "akhilesh yadav"],
    },
    {
        "rank": "04", "tone": "violet", "classification": "High Influence",
        "name": "Asaduddin Owaisi", "init": "AO",
        "image": "images/entity-owaisi.png",
        "party": "AIMIM", "region": "Telangana",
        "regional_label": "Telangana", "region_key": "telangana",
        "tag": "Regional Voice",
        "entity_uuid": "92a84982-18e1-4fcd-ac69-e2965794f789",
        "patterns": ["%asaduddin%owaisi%", "%asaduddin%", "asad owaisi"],
    },
]


def _classify_velocity(change_pct: float | None) -> tuple[str, str]:
    if change_pct is None:
        return ("Stable", "Neutral")
    if change_pct >= 100:
        return ("Very High", "")
    if change_pct >= 30:
        return ("High", "")
    if change_pct >= 5:
        return ("Rising", "")
    if change_pct <= -20:
        return ("Cooling", "")
    return ("Stable", "")


def _sentiment_label(value: float | None) -> str:
    if value is None:
        return "Neutral"
    if value >= 0.15:
        return "Positive"
    if value <= -0.15:
        return "Negative"
    return "Neutral"


async def _one_entity(db, cfg: dict[str, Any]) -> dict[str, Any]:
    patterns = cfg["patterns"]
    uuid = cfg.get("entity_uuid")
    ilike_claims  = " OR ".join([f"LOWER(ac.subject_text) LIKE :p{i}" for i, _ in enumerate(patterns)])
    ilike_quotes  = " OR ".join([f"LOWER(aq.speaker_name) LIKE :p{i}" for i, _ in enumerate(patterns)])
    ilike_stances = " OR ".join([f"LOWER(asn.actor) LIKE :p{i}"        for i, _ in enumerate(patterns)])
    if uuid:
        or_claims  = f"ac.subject_entity_id = CAST(:euid AS uuid) OR (ac.subject_entity_id IS NULL AND ({ilike_claims}))"
        or_quotes  = f"aq.speaker_entity_id = CAST(:euid AS uuid) OR (aq.speaker_entity_id IS NULL AND ({ilike_quotes}))"
        or_stances = f"asn.actor_entity_id  = CAST(:euid AS uuid) OR (asn.actor_entity_id  IS NULL AND ({ilike_stances}))"
    else:
        or_claims, or_quotes, or_stances = ilike_claims, ilike_quotes, ilike_stances
    params: dict[str, Any] = {f"p{i}": p for i, p in enumerate(patterns)}
    if uuid:
        params["euid"] = uuid

    metrics = (await db.execute(text(f"""
        WITH today_claims AS (
          SELECT COUNT(*) AS n FROM article_claims ac
            JOIN articles a ON a.id = ac.article_id
           WHERE a.collected_at >= analytics.now_sim() - INTERVAL '24 hours'
             AND ({or_claims})
        ),
        today_quotes AS (
          SELECT COUNT(*) AS n FROM article_quotes aq
            JOIN articles a ON a.id = aq.article_id
           WHERE a.collected_at >= analytics.now_sim() - INTERVAL '24 hours'
             AND ({or_quotes})
        ),
        baseline AS (
          SELECT COALESCE(SUM(n_mentions_total)::float /
                          NULLIF(COUNT(DISTINCT date), 0), 0) AS avg_n
            FROM entity_mention_daily
           WHERE date BETWEEN analytics.now_sim_date() - 8 AND analytics.now_sim_date() - 1
             AND ({" OR ".join([f"entity_text LIKE :p{i}" for i, _ in enumerate(patterns)])})
        ),
        sentiment_today AS (
          SELECT AVG(intensity) AS s FROM article_stances asn
            JOIN articles a ON a.id = asn.article_id
           WHERE a.collected_at >= analytics.now_sim() - INTERVAL '24 hours'
             AND asn.intensity IS NOT NULL
             AND ({or_stances})
        )
        SELECT (SELECT n FROM today_claims) + (SELECT n FROM today_quotes) AS today_n,
               (SELECT avg_n FROM baseline) AS baseline_avg,
               (SELECT s FROM sentiment_today) AS sentiment
    """), params)).fetchone()

    today_n = int(metrics.today_n or 0)
    baseline = float(metrics.baseline_avg or 0)
    change_pct = ((today_n - baseline) / baseline * 100) if baseline > 0 else None

    quote_row = (await db.execute(text(f"""
        SELECT aq.quote_text, a.collected_at, s.name AS source
          FROM article_quotes aq
          JOIN articles a ON a.id = aq.article_id
          JOIN sources s ON s.id = a.source_id
         WHERE ({or_quotes})
           AND LENGTH(aq.quote_text) >= 30
           AND aq.quote_text !~ '^[A-Z][a-z]+,\s+[A-Z][a-z]+\s*$'
           AND a.collected_at >= analytics.now_sim() - INTERVAL '7 days'
         ORDER BY LEAST(LENGTH(aq.quote_text), 240) DESC,
                  a.collected_at DESC
         LIMIT 1
    """), params)).fetchone()

    sparkrows = (await db.execute(text(f"""
        SELECT date_trunc('hour', a.collected_at) AS hour, COUNT(*) AS n
          FROM article_claims ac
          JOIN articles a ON a.id = ac.article_id
         WHERE a.collected_at >= analytics.now_sim() - INTERVAL '15 hours'
           AND ({or_claims})
         GROUP BY 1 ORDER BY 1
    """), params)).fetchall()
    velocity_bars = [int(r.n) for r in sparkrows]
    while len(velocity_bars) < 15:
        velocity_bars.insert(0, 0)
    velocity_bars = velocity_bars[-15:]

    sentiment_val = float(metrics.sentiment) if metrics.sentiment is not None else None
    velocity_label, _ = _classify_velocity(change_pct)
    sentiment_label = _sentiment_label(sentiment_val)
    influence = min(100, max(0, today_n * 2))
    change_str = (f"{'+' if change_pct >= 0 else ''}{change_pct:.0f}%"
                  if change_pct is not None else "—")

    return {
        "rank": cfg["rank"],
        "tone": cfg["tone"],
        "classification": cfg["classification"],
        "name": cfg["name"],
        "init": cfg["init"],
        "image": cfg["image"],
        "party": cfg["party"],
        "region": cfg["region"],
        "influence": int(influence),
        "change": change_str,
        "spark": "articles",
        "sentiment": {
            "label": sentiment_label,
            "value": (f"{'+' if (sentiment_val or 0) >= 0 else ''}"
                      f"{sentiment_val:.2f}" if sentiment_val is not None else "0.00"),
            "spark": "sentiment",
        },
        "velocity": velocity_label,
        "velocityBars": velocity_bars,
        "regionalLabel": cfg["regional_label"],
        "regionKey": cfg["region_key"],
        "quote": (quote_row.quote_text[:280] if quote_row and quote_row.quote_text
                  else f"No recent quote captured for {cfg['name']}."),
        "quoteCtx": ((quote_row.source + " · "
                      + quote_row.collected_at.strftime("%d %b · %H:%M IST"))
                     if quote_row else "—"),
        "tag": cfg["tag"],
        "mentions_today": today_n,
    }


_CAMP_ROLE = {"opposition": "Opposition", "rival": "Rival", "govt": "Your side",
              "centre": "Centre", "high_command": "High command",
              "constitutional": "Constitutional", "agency": "Agency", "party": "Party"}


def _verdict(camp: str | None, surge_pct: float | None, crit_pct: int | None) -> tuple[str, str]:
    """Deterministic actionable badge from camp + momentum + posture.

    `article_stances.stance` is the actor's OWN posture, so a high critical share
    means they're on the offensive. Leads the card with what to DO: an opposition
    figure who is attacking AND whose coverage is surging is ESCALATING.
    """
    opp = camp in ("opposition", "rival")
    rising = surge_pct is not None and surge_pct >= 25
    cooling = surge_pct is not None and surge_pct <= -40
    attacking = crit_pct is not None and crit_pct >= 50
    if opp and rising and attacking:
        return ("Escalating", "rose")
    if opp and attacking:
        return ("On the attack", "rose")
    if opp and rising:
        return ("Rising", "amber")
    if opp and cooling:
        return ("Quieter", "cyan")
    if opp:
        return ("Active", "amber")
    if camp == "centre":
        return ("Centre signal", "violet")
    if camp == "govt":
        return ("On message", "amber")
    return ("Watching", "amber")


async def _watched_entities(db, prefs: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    """Actionable threat/opportunity board over the user's watchlist (minus the
    principal — they're covered in CM Perspective). 100% real data: prominence
    from entity_mention_daily, entity-specific sentiment + stance split from
    article_stances, the figure's own latest real quote from article_quotes.
    """
    meta = (prefs.get("watchlist") or {}).get("entity_meta") or []
    psid = prefs.get("primary_subject_id")
    psname = ((prefs.get("primary_subject_meta") or {}).get("name") or "").lower()
    watched = [m for m in meta if m.get("name") and m.get("id") != psid
               and (m.get("name") or "").lower() != psname]
    if not watched:
        return []

    # 1) Prominence — one pass over entity_mention_daily (15k rows; LIKE ANY is fast).
    pats = [f"%{m['name'].lower()}%" for m in watched]
    emd = (await db.execute(text("""
        SELECT lower(entity_text) et, SUM(n_mentions_total) men, MAX(n_sources) src,
               SUM(CASE WHEN date = analytics.now_sim_date() THEN n_mentions_total ELSE 0 END) today,
               COALESCE(SUM(CASE WHEN date BETWEEN analytics.now_sim_date()-6 AND analytics.now_sim_date()-1
                                 THEN n_mentions_total ELSE 0 END) / 6.0, 0) baseline
          FROM entity_mention_daily
         WHERE date BETWEEN analytics.now_sim_date()-6 AND analytics.now_sim_date()
           AND lower(entity_text) LIKE ANY(:pats)
         GROUP BY lower(entity_text)
    """), {"pats": pats})).fetchall()
    prom: dict[str, dict[str, float]] = {}
    for r in emd:
        for m in watched:
            nm = m["name"].lower()
            if nm in r.et or r.et in nm:
                p = prom.setdefault(nm, {"men": 0, "src": 0, "today": 0, "baseline": 0.0})
                p["men"] += int(r.men or 0)
                p["src"] = max(p["src"], int(r.src or 0))
                p["today"] += int(r.today or 0)
                p["baseline"] += float(r.baseline or 0)
                break

    total_men = sum(prom.get(m["name"].lower(), {}).get("men", 0) for m in watched) or 1
    ranked = sorted(watched, key=lambda m: -prom.get(m["name"].lower(), {}).get("men", 0))
    top = [m for m in ranked if prom.get(m["name"].lower(), {}).get("men", 0) > 0][:limit]
    if not top:
        return []
    ids = [m["id"] for m in top]

    # 2) Entity-specific sentiment + critical/supportive split (batched).
    # 2) Posture split from the stance LABEL (critical/supportive = the actor's
    #    own posture). intensity is magnitude only, so we do NOT use it here.
    sent_by = {r.id: r for r in (await db.execute(text("""
        SELECT actor_entity_id::text id, COUNT(*) n,
               COUNT(*) FILTER (WHERE stance = 'critical')   crit,
               COUNT(*) FILTER (WHERE stance = 'supportive') supp
          FROM article_stances asn JOIN articles a ON a.id = asn.article_id
         WHERE asn.actor_entity_id = ANY(CAST(:ids AS uuid[]))
           AND a.collected_at BETWEEN analytics.now_sim() - INTERVAL '7 days' AND analytics.now_sim()
         GROUP BY actor_entity_id
    """), {"ids": ids})).fetchall()}

    # 3) Each figure's own latest substantial quote (batched). Homonym guard:
    #    require a stance row for this actor in the SAME article, so a beauty-
    #    industry "Kapil Mishra" can't masquerade as the politician.
    q_by = {r.id: r for r in (await db.execute(text("""
        SELECT DISTINCT ON (aq.speaker_entity_id) aq.speaker_entity_id::text id,
               COALESCE(aq.quote_text_en, aq.quote_text) q, s.name outlet, a.url, a.collected_at
          FROM article_quotes aq JOIN articles a ON a.id = aq.article_id JOIN sources s ON s.id = a.source_id
         WHERE aq.speaker_entity_id = ANY(CAST(:ids AS uuid[])) AND aq.is_direct = TRUE
           AND LENGTH(aq.quote_text) BETWEEN 40 AND 280
           AND a.collected_at BETWEEN analytics.now_sim() - INTERVAL '7 days' AND analytics.now_sim()
           AND EXISTS (SELECT 1 FROM article_stances st
                        WHERE st.article_id = a.id AND st.actor_entity_id = aq.speaker_entity_id)
         ORDER BY aq.speaker_entity_id, LENGTH(aq.quote_text) DESC, a.collected_at DESC
    """), {"ids": ids})).fetchall()}

    out: list[dict[str, Any]] = []
    for i, m in enumerate(top):
        p = prom.get(m["name"].lower(), {})
        men, today, base = p.get("men", 0), p.get("today", 0), p.get("baseline", 0.0)
        surge = ((today - base) / base * 100) if base > 0 else None
        # Suppress surge for low-volume entities (a 2->9 jump = +350% noise).
        if base < 1.5:
            surge = None
        sr = sent_by.get(m["id"])
        n_st = int(sr.n) if sr else 0
        crit_pct = round(100 * int(sr.crit) / n_st) if n_st else None
        supp_pct = round(100 * int(sr.supp) / n_st) if n_st else None
        posture = (None if not n_st else
                   "critical" if (crit_pct or 0) >= (supp_pct or 0) else "supportive")
        camp = m.get("camp")
        vlabel, vtone = _verdict(camp, surge, crit_pct)
        q = q_by.get(m["id"])
        out.append({
            "rank": f"{i + 1:02d}", "name": m["name"], "party": m.get("party"),
            "role": m.get("role"), "camp": camp, "campRole": _CAMP_ROLE.get(camp or "", "Watched"),
            "tone": vtone, "verdict": vlabel,
            "init": "".join(w[0] for w in m["name"].split()[:2]).upper(),
            "mentions": men, "sov": round(100 * men / total_men, 1),
            "outlets": p.get("src", 0),
            "surge": (f"{'+' if surge >= 0 else ''}{surge:.0f}%" if surge is not None else None),
            "surgeLabel": _classify_velocity(surge)[0] if surge is not None else None,
            "posture": posture, "critPct": crit_pct, "suppPct": supp_pct, "stanceN": n_st,
            "quote": (q.q[:240] if q else None),
            "quoteOutlet": (q.outlet if q else None),
            "quoteUrl": (q.url if q else None),
            "quoteTs": (q.collected_at.strftime("%d %b") if q and q.collected_at else None),
        })
    return out


@router.get("/entities")
async def get_entities(
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        if prefs:
            watched = await _watched_entities(db, prefs)
            if watched:
                return {"entities": watched, "personalized": True,
                        "generated_at": datetime.utcnow().isoformat() + "Z"}
        # Anonymous / no-prefs → global 4-card fallback.
        items = [await _one_entity(db, cfg) for cfg in ENTITIES_CONFIG]
    return {
        "entities": items, "personalized": False,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/entity_read")
async def entity_read(
    name: str = Query(..., min_length=2, max_length=80),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """On-demand analyst dossier for ONE watched figure: a grounded LLM "read"
    + recommended actions over their real facts (prominence, posture, quotes).
    Fired only when a card is expanded, so the grid stays LLM-free."""
    empty = {"name": name, "read": None, "actions": [], "quotes": [], "source": "none"}
    if not user:
        return empty
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"])
        if not prefs:
            return empty
        meta = (prefs.get("watchlist") or {}).get("entity_meta") or []
        m = next((x for x in meta if (x.get("name") or "").lower() == name.lower()), None)
        if not m or not m.get("id"):
            return empty
        subj = (prefs.get("primary_subject_meta") or {}).get("name") or "the principal"
        eid = m["id"]
        pr = (await db.execute(text("""
            SELECT COALESCE(SUM(n_mentions_total),0) men, COALESCE(MAX(n_sources),0) src,
                   COALESCE(SUM(CASE WHEN date = analytics.now_sim_date() THEN n_mentions_total ELSE 0 END),0) today,
                   COALESCE(SUM(CASE WHEN date BETWEEN analytics.now_sim_date()-6 AND analytics.now_sim_date()-1
                                     THEN n_mentions_total ELSE 0 END)/6.0, 0) baseline
              FROM entity_mention_daily
             WHERE date BETWEEN analytics.now_sim_date()-6 AND analytics.now_sim_date()
               AND lower(entity_text) LIKE :p
        """), {"p": f"%{name.lower()}%"})).fetchone()
        st = (await db.execute(text("""
            SELECT COUNT(*) n, COUNT(*) FILTER (WHERE stance='critical') crit,
                   COUNT(*) FILTER (WHERE stance='supportive') supp
              FROM article_stances asn JOIN articles a ON a.id = asn.article_id
             WHERE asn.actor_entity_id = CAST(:e AS uuid)
               AND a.collected_at BETWEEN analytics.now_sim() - INTERVAL '7 days' AND analytics.now_sim()
        """), {"e": eid})).fetchone()
        qrows = (await db.execute(text("""
            SELECT COALESCE(aq.quote_text_en, aq.quote_text) q, s.name outlet, a.url, a.collected_at
              FROM article_quotes aq JOIN articles a ON a.id = aq.article_id JOIN sources s ON s.id = a.source_id
             WHERE aq.speaker_entity_id = CAST(:e AS uuid) AND aq.is_direct = TRUE
               AND LENGTH(aq.quote_text) BETWEEN 40 AND 280
               AND a.collected_at BETWEEN analytics.now_sim() - INTERVAL '7 days' AND analytics.now_sim()
               AND EXISTS (SELECT 1 FROM article_stances stx
                            WHERE stx.article_id = a.id AND stx.actor_entity_id = aq.speaker_entity_id)
             ORDER BY LENGTH(aq.quote_text) DESC, a.collected_at DESC LIMIT 3
        """), {"e": eid})).fetchall()

    men = int(pr.men or 0)
    base = float(pr.baseline or 0)
    surge = ((int(pr.today or 0) - base) / base * 100) if base >= 1.5 else None
    n_st = int(st.n or 0) if st else 0
    quotes = [{"text": r.q[:240], "outlet": r.outlet, "url": r.url,
               "ts": r.collected_at.strftime("%d %b") if r.collected_at else None} for r in qrows]
    camp, role, party = m.get("camp"), m.get("role"), m.get("party")

    fl = [f"PRINCIPAL (your office): {subj}",
          f"WATCHED FIGURE: {name}" + (f" — {party}" if party else "") + (f", {role}" if role else ""),
          f"CAMP: {camp or 'unknown'}",
          f"PROMINENCE: {men} mentions in 7 days across {int(pr.src or 0)} outlets"
          + (f"; momentum {surge:+.0f}% vs the prior week" if surge is not None else "")]
    if n_st:
        fl.append(f"POSTURE: of {n_st} stance-coded items, "
                  f"{round(100*int(st.crit)/n_st)}% critical / {round(100*int(st.supp)/n_st)}% supportive")
    if quotes:
        fl.append("THEIR RECENT WORDS:")
        fl += [f"  - \"{q['text']}\" ({q['outlet']})" for q in quotes]
    facts = "\n".join(fl)

    frame = {"opposition": "a threat / pressure source — flag what they are attacking and whether it warrants a response",
             "rival": "a rival whose moves may affect your turf",
             "centre": "the central government — read it as a signal for your state",
             "high_command": "your own party's high command",
             "govt": "one of your own — flag exposure to defend"}.get(camp or "", "a watched figure")
    system = (
        "/no_think\n"
        f"You are an intelligence analyst briefing the office of {subj}. The figure below is {frame}. "
        "Write a SHORT assessment (2-3 sentences) of what is happening with them right now relative to "
        f"{subj}, then 1-3 concrete recommended actions for the principal's office. Use ONLY the facts "
        "given; do NOT invent names, dates, or outcomes. Describe momentum and posture QUALITATIVELY "
        "(e.g. 'rising', 'mostly critical', 'escalating') and do NOT cite specific numbers or "
        "percentages — those are already shown on the card. Be direct and decision-useful.\n"
        "Format EXACTLY:\nASSESSMENT: <2-3 sentences>\nACTIONS:\n- <action>\n- <action>"
    )
    dossier = await synthesize_dossier(system=system, facts=facts, source_check=facts)
    return {
        "name": name, "camp": camp,
        "read": (dossier or {}).get("read"),
        "actions": (dossier or {}).get("actions", []),
        "quotes": quotes,
        "source": "llm" if dossier else "none",
    }
