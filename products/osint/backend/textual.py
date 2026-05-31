"""Generic textual-intelligence engine (Category-2).

Pure function of the user's prefs + corpus — principal = `primary_subject_id`,
opposition = watchlist. Every LLM surface is faithfulness-gated (via llm_synth)
and **pinned to English output** (the corpus is multilingual; without the pin the
model mirrors the source language). Cold-start safe: with no facts we return a
graceful "limited coverage" note rather than hallucinating.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from llm_synth import synthesize_dossier, synthesize_paragraph

POS = "('supportive','sympathetic','promotional','defensive','admiration','admiring','honored','grateful','optimistic')"
NEG = "('critical','mocking','concerned','lament','skeptical')"
EN = "/no_think Respond in English only. Use only facts present below; do not invent names, numbers or quotes.\n"

_WIN = "a.collected_at>=analytics.now_sim()-make_interval(hours => :wh) AND a.collected_at<=analytics.now_sim()"


async def _q(db, sql: str, **p) -> list:
    return (await db.execute(text(sql), p)).fetchall()


def _principal(prefs):
    return prefs.get("primary_subject_id"), (prefs.get("primary_subject_meta") or {}).get("name")


def _opp(prefs):
    pid = prefs.get("primary_subject_id")
    meta = (prefs.get("watchlist") or {}).get("entity_meta") or []
    return [(m["id"], m.get("name") or "?") for m in meta if m.get("id") and m["id"] != pid]


async def _facts(db, pid: str, opp: list, wh: int) -> dict[str, Any]:
    oppids = [o[0] for o in opp] or [pid]
    neg = await _q(db, f"""WITH p AS (SELECT DISTINCT a.id,a.title,s.name src FROM article_entity_mentions m
        JOIN articles a ON a.id=m.article_id JOIN sources s ON s.id=a.source_id WHERE m.entity_id=CAST(:pid AS uuid) AND {_WIN})
        SELECT DISTINCT p.title,p.src FROM p JOIN article_stances st ON st.article_id=p.id
        WHERE st.actor_entity_id<>CAST(:pid AS uuid) AND st.stance IN {NEG} LIMIT 8""", pid=pid, wh=wh)
    pos = await _q(db, f"""WITH p AS (SELECT DISTINCT a.id,a.title,s.name src FROM article_entity_mentions m
        JOIN articles a ON a.id=m.article_id JOIN sources s ON s.id=a.source_id WHERE m.entity_id=CAST(:pid AS uuid) AND {_WIN})
        SELECT DISTINCT p.title,p.src FROM p JOIN article_stances st ON st.article_id=p.id
        WHERE st.actor_entity_id<>CAST(:pid AS uuid) AND st.stance IN {POS} LIMIT 8""", pid=pid, wh=wh)
    pq = await _q(db, f"""SELECT COALESCE(q.quote_text_en,q.quote_text) qt FROM article_quotes q JOIN articles a ON a.id=q.article_id
        WHERE q.speaker_entity_id=CAST(:pid AS uuid) AND {_WIN} AND length(q.quote_text)>30 LIMIT 6""", pid=pid, wh=wh)
    oq = await _q(db, f"""SELECT q.speaker_name spk, COALESCE(q.quote_text_en,q.quote_text) qt FROM article_quotes q
        JOIN articles a ON a.id=q.article_id WHERE q.speaker_entity_id=ANY(CAST(:opp AS uuid[])) AND {_WIN}
        AND length(q.quote_text)>30 LIMIT 6""", opp=oppids, wh=wh)
    return {
        "negf": "\n".join(f"- {r.title} ({r.src})" for r in neg) or "(none)",
        "posf": "\n".join(f"- {r.title} ({r.src})" for r in pos) or "(none)",
        "pqf": "\n".join(f'- "{r.qt[:160]}"' for r in pq) or "(none)",
        "oqf": "\n".join(f'- {r.spk}: "{r.qt[:140]}"' for r in oq) or "(none)",
        "has_coverage": bool(neg or pos),
    }


async def _para(system: str, facts: str) -> dict[str, Any]:
    try:
        r = await synthesize_paragraph(system=EN + system, facts=facts, source_check=facts, min_words=8, min_chars=30)
    except Exception as e:  # noqa: BLE001
        return {"text": None, "method": "llm", "ok": False, "error": str(e)[:80]}
    return {"text": r, "method": "llm", "ok": bool(r)}


# ───────────────────────── features ─────────────────────────

async def executive_bluf(db, pid, pname, f):
    return await _para(f"You brief the office of {pname}. Write a 2-sentence bottom-line-up-front of the coverage.",
                       f"CRITICAL:\n{f['negf']}\nSUPPORTIVE:\n{f['posf']}")

async def entity_dossier(db, pid, pname, f):
    try:
        d = await synthesize_dossier(system=EN + f"Senior analyst dossier on {pname}. Format: ASSESSMENT: <3-4 sentences> ACTIONS:\n- <a>\n- <a>",
                                     facts=f"CRITICAL:\n{f['negf']}\nSUPPORTIVE:\n{f['posf']}\nQUOTES:\n{f['pqf']}",
                                     source_check=f"{f['negf']}\n{f['posf']}\n{f['pqf']}")
        return {"read": (d or {}).get("read"), "actions": (d or {}).get("actions", []), "method": "llm", "ok": bool(d)}
    except Exception as e:  # noqa: BLE001
        return {"read": None, "actions": [], "method": "llm", "ok": False, "error": str(e)[:80]}

async def this_week(db, pid, pname, f):
    return await _para(f"Summarise this week's coverage of {pname} in 2 sentences.", f"{f['negf']}\n{f['posf']}")

async def who_attacking(db, pid, pname, f):
    return await _para(f"Name who is ATTACKING and who is DEFENDING {pname} this week, in 2 sentences.",
                       f"CRITICAL:\n{f['negf']}\nSUPPORTIVE:\n{f['posf']}\nOPPOSITION QUOTES:\n{f['oqf']}")

async def framing_comparison(db, pid, pname, f):
    return await _para(f"Contrast how hostile vs favourable outlets framed {pname} this week, in 2 sentences.",
                       f"HOSTILE HEADLINES:\n{f['negf']}\nFAVOURABLE HEADLINES:\n{f['posf']}")

async def counter_narrative(db, pid, pname, f):
    return await _para(f"You are {pname}'s comms aide. Draft a 2-sentence grounded rebuttal to the strongest attack below.",
                       f"ATTACKS:\n{f['negf']}\nFAVOURABLE FACTS:\n{f['posf']}")

async def narrative_dna(db, pid, pname, f):
    return await _para(f"Identify the 2-3 competing FRAMES in this week's {pname} coverage. One line each.",
                       f"{f['negf']}\n{f['posf']}")

async def opposition_memo(db, pid, pname, f):
    return await _para(f"Write a 2-sentence red-team memo as if from {pname}'s OPPONENTS, listing his weak points this week.", f["negf"])

async def situation_room(db, pid, pname, f):
    return await _para(f"Write a 3-line situation read for {pname}: (1) top narrative (2) who's driving (3) one risk.",
                       f"{f['negf']}\n{f['posf']}\nOPP:\n{f['oqf']}")

async def crisis_brief(db, pid, pname, f):
    return await _para(f"Compile a 2-sentence crisis brief for {pname} on the most negative storyline: what, who, why it matters.", f["negf"])

async def dog_didnt_bark(db, pid, pname, opp, wh):
    oppids = [o[0] for o in opp] or [pid]
    rows = await _q(db, f"""WITH ot AS (SELECT a.topic_category topic,count(*) c FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id
          WHERE m.entity_id=ANY(CAST(:opp AS uuid[])) AND {_WIN} AND a.topic_category IS NOT NULL GROUP BY 1),
          mine AS (SELECT a.topic_category topic,count(*) c FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id
          WHERE m.entity_id=CAST(:pid AS uuid) AND {_WIN} AND a.topic_category IS NOT NULL GROUP BY 1)
          SELECT ot.topic, ot.c opp_c, COALESCE(mine.c,0) my_c FROM ot LEFT JOIN mine ON mine.topic=ot.topic
          ORDER BY (ot.c - COALESCE(mine.c,0)) DESC LIMIT 5""", opp=oppids, pid=pid, wh=wh)
    return {"items": [{"topic": r.topic, "opposition": int(r.opp_c), "principal": int(r.my_c)} for r in rows], "method": "compute"}

async def since_last_looked(db, pid, pname, wh):
    rows = await _q(db, """SELECT DISTINCT a.title, s.name src FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id
        JOIN sources s ON s.id=a.source_id WHERE m.entity_id=CAST(:pid AS uuid)
        AND a.collected_at>=analytics.now_sim()-make_interval(hours=>72) ORDER BY 1 LIMIT 6""", pid=pid)
    return {"items": [{"title": r.title, "outlet": r.src} for r in rows], "method": "retrieval"}

async def instant_oppo_dossier(db, pid, opp, wh):
    if not opp:
        return {"rival": None, "read": None, "method": "llm", "ok": False}
    r = await _q(db, """SELECT m.entity_id::text id, count(DISTINCT a.id) n FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id
        WHERE m.entity_id=ANY(CAST(:ids AS uuid[])) AND a.collected_at>=analytics.now_sim()-make_interval(hours=>:wh)
        GROUP BY 1 ORDER BY 2 DESC LIMIT 1""", ids=[o[0] for o in opp], wh=wh)
    if not r:
        return {"rival": None, "read": None, "method": "llm", "ok": False}
    rid = r[0].id
    rname = dict(opp).get(rid, "rival")
    rn = await _q(db, f"""SELECT DISTINCT a.title, s.name src FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id
        JOIN sources s ON s.id=a.source_id WHERE m.entity_id=CAST(:rid AS uuid) AND {_WIN} LIMIT 8""", rid=rid, wh=wh)
    rf = "\n".join(f"- {x.title} ({x.src})" for x in rn) or "(none)"
    try:
        d = await synthesize_dossier(system=EN + f"Opposition dossier on {rname}. Format: ASSESSMENT: <3 sentences> ACTIONS:\n- <a>",
                                     facts=rf, source_check=rf)
        return {"rival": rname, "read": (d or {}).get("read"), "method": "llm", "ok": bool(d)}
    except Exception as e:  # noqa: BLE001
        return {"rival": rname, "read": None, "method": "llm", "ok": False, "error": str(e)[:80]}

async def quote_translation(db, pid, wh):
    rows = await _q(db, f"""SELECT q.quote_text orig, q.quote_text_en en FROM article_quotes q JOIN articles a ON a.id=q.article_id
        WHERE a.language_iso<>'en' AND q.quote_text_en IS NOT NULL AND length(q.quote_text)>30 AND {_WIN}
        AND q.speaker_entity_id=CAST(:pid AS uuid) LIMIT 1""", pid=pid, wh=wh)
    if not rows:
        rows = await _q(db, f"""SELECT q.quote_text orig, q.quote_text_en en FROM article_quotes q JOIN articles a ON a.id=q.article_id
            WHERE a.language_iso<>'en' AND q.quote_text_en IS NOT NULL AND length(q.quote_text)>30 AND {_WIN} LIMIT 1""", wh=wh)
    if not rows:
        return {"original": None, "english": None, "method": "retrieval"}
    return {"original": rows[0].orig[:160], "english": rows[0].en[:200], "method": "retrieval-backfilled"}

async def source_trail(db, pid, wh):
    rows = await _q(db, f"""WITH p AS (SELECT DISTINCT a.id,a.title,s.name src,a.collected_at FROM article_entity_mentions m
        JOIN articles a ON a.id=m.article_id JOIN sources s ON s.id=a.source_id WHERE m.entity_id=CAST(:pid AS uuid) AND {_WIN})
        SELECT title,src,collected_at::text ts FROM p JOIN article_stances st ON st.article_id=p.id
        WHERE st.actor_entity_id<>CAST(:pid AS uuid) AND st.stance IN {NEG} ORDER BY collected_at ASC LIMIT 6""", pid=pid, wh=wh)
    return {"items": [{"ts": r.ts[:16], "outlet": r.src, "title": r.title[:80]} for r in rows], "method": "retrieval"}


# ───────────────────────── orchestrator ─────────────────────────

# Cheap (no-LLM) features always run; LLM features run on request to bound cost.
_LLM = {"executive_bluf", "entity_dossier", "this_week", "who_attacking", "framing_comparison",
        "counter_narrative", "narrative_dna", "opposition_memo", "situation_room", "crisis_brief", "instant_oppo_dossier"}
_CHEAP = {"dog_didnt_bark", "since_last_looked", "quote_translation", "source_trail"}
ALL = sorted(_LLM | _CHEAP)


async def compute_textual(db, prefs: dict[str, Any], window_hours: int = 504,
                          features: list[str] | None = None) -> dict[str, Any]:
    pid, pname = _principal(prefs)
    if not pid:
        return {"personalized": False, "reason": "no primary subject set", "features": {}}
    opp = _opp(prefs)
    wh = int(window_hours)
    want = set(features) if features else set(ALL)
    f = await _facts(db, pid, opp, wh)
    out: dict[str, Any] = {}
    if not f["has_coverage"]:
        return {"personalized": True, "subject": pname, "window_hours": wh,
                "note": "limited coverage in window — textual synthesis suppressed", "features": {}}
    # LLM features (passed the shared facts bundle)
    fns = {
        "executive_bluf": lambda: executive_bluf(db, pid, pname, f),
        "entity_dossier": lambda: entity_dossier(db, pid, pname, f),
        "this_week": lambda: this_week(db, pid, pname, f),
        "who_attacking": lambda: who_attacking(db, pid, pname, f),
        "framing_comparison": lambda: framing_comparison(db, pid, pname, f),
        "counter_narrative": lambda: counter_narrative(db, pid, pname, f),
        "narrative_dna": lambda: narrative_dna(db, pid, pname, f),
        "opposition_memo": lambda: opposition_memo(db, pid, pname, f),
        "situation_room": lambda: situation_room(db, pid, pname, f),
        "crisis_brief": lambda: crisis_brief(db, pid, pname, f),
        "instant_oppo_dossier": lambda: instant_oppo_dossier(db, pid, opp, wh),
        "dog_didnt_bark": lambda: dog_didnt_bark(db, pid, pname, opp, wh),
        "since_last_looked": lambda: since_last_looked(db, pid, pname, wh),
        "quote_translation": lambda: quote_translation(db, pid, wh),
        "source_trail": lambda: source_trail(db, pid, wh),
    }
    for name in ALL:
        if name in want:
            out[name] = await fns[name]()
    return {"personalized": True, "subject": pname, "window_hours": wh, "features": out}
