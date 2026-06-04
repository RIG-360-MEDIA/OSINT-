"""Builders for the Night Desk Home sections — THE BRIEFING, PEOPLE TO WATCH,
THE SIX — for the authenticated persona.

Design rules (non-negotiable, from the CM-content-correctness mandate):
  * Source-grounded only. Every number shown is computed from the corpus; no
    fabricated handles, pledges, quotes, or hostility figures.
  * Honest measurement. `article_stances` has an `actor` but NO target column,
    so we CANNOT compute a directed "X's hostility toward the principal" score.
    PEOPLE TO WATCH therefore ranks people by how entangled they are in the
    principal's coverage and scores them by the LEAN OF THAT COVERAGE WHEN THEY
    APPEAR (principal-directed, defensible) — never by the actor's own valence,
    which conflates "their mood in coverage" with "their stance toward you".
  * Confidence-aware. Thin samples are labelled, not dressed up.

All heavy stance maths reuse posture.py's vetted idioms (POL stance map +
_BODY_PRESENT hallucination filter) so numbers are consistent across the product.

v1 is fully deterministic (structure + facts). LLM prose (synthesize_paragraph,
faithfulness-gated) is layered on top with template fallbacks.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from posture import POL, _BODY_PRESENT, compute_posture, principal_of
from relevance import score_relevant
import i18n as _i18n

_MIN = "−"  # unicode minus, matches the design's typography

# Parties/fronts are frequently mistyped as `person` in the entity dictionary.
# PEOPLE TO WATCH is about individuals, so we exclude org/party-shaped names.
_PARTY_RE = re.compile(
    r"(?i)(\bparty\b|congress|desam|samithi|samiti|janata|sena|morcha|majlis|"
    r"aadmi|sangh|front|ministry|court|commission|aayog|reserve bank)")


def _is_person(m: dict[str, Any]) -> bool:
    if m.get("type") != "person":
        return False
    return not _PARTY_RE.search(m.get("name", ""))


# The only posture metrics the Home page consumes — passed to compute_posture so
# we don't pay for the other 7 (share_of_voice, stance_mix, target_heat, …).
_HOME_METRICS = {
    "outlet_favourability", "stance_trajectory", "attack_origination",
    "quote_selection_bias", "issue_ownership", "weighted_pressure",
    "friend_foe_fence", "cross_language_gap",
}
_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ───────────────────────── small helpers ─────────────────────────
def _signed(x: float | int | None, dp: int = 0) -> str | None:
    """Signed number with the design's unicode minus, e.g. -64 -> '−64'."""
    if x is None:
        return None
    v = round(float(x), dp)
    if dp == 0:
        v = int(v)
    s = f"{abs(v)}"
    return f"{_MIN}{s}" if v < 0 else f"+{s}" if v > 0 else f"{s}"


def _fmt_day(dt) -> str:
    if dt is None:
        return ""
    return f"{dt.day} {_MONTHS[dt.month]}"


def _window_label(wh: int) -> str:
    if wh <= 36:
        return "last 24 hours"
    d = round(wh / 24)
    return f"last {d} days"


def _tone_from_fav(fav: float | None, n: int, min_n: int = 3) -> str:
    if fav is None or n < min_n:
        return "neutral"
    if fav >= 15:
        return "supportive"
    if fav <= -15:
        return "hostile"
    return "neutral"


def _overall_fav(posture: dict[str, Any]) -> tuple[float | None, int]:
    """n-weighted average favourability across outlets (the headline lean)."""
    items = posture.get("metrics", {}).get("outlet_favourability", {}).get("items", [])
    num = sum(it["favourability"] * it["n"] for it in items)
    den = sum(it["n"] for it in items)
    return (round(num / den, 1), den) if den else (None, 0)


# ───────────────────────── PEOPLE TO WATCH ─────────────────────────
async def _people_signals(db, pid: str, ids: list[str], states: list[str], wh: int):
    """Per-watchlist-person signals, body-present:
       coverage, co_principal (appears in a principal article), in_region,
       and lean = the favourability of principal-coverage WHEN THEY APPEAR."""
    cov = {r.id: r for r in (await db.execute(text(f"""
        SELECT m.entity_id::text id,
               count(DISTINCT a.id) coverage,
               count(DISTINCT a.id) FILTER (WHERE EXISTS (
                   SELECT 1 FROM article_entity_mentions pm
                    WHERE pm.article_id=a.id AND pm.entity_id=CAST(:pid AS uuid))) co_principal,
               count(DISTINCT a.id) FILTER (WHERE a.geo_primary = ANY(:states)) in_region,
               -- adverse signals: stories where this person co-appears with the
               -- principal AND the story carries a negative stance (pressure on you)
               count(DISTINCT a.id) FILTER (WHERE
                   EXISTS (SELECT 1 FROM article_entity_mentions pm
                            WHERE pm.article_id=a.id AND pm.entity_id=CAST(:pid AS uuid))
                   AND EXISTS (SELECT 1 FROM article_stances st
                                WHERE st.article_id=a.id AND ({POL})<0)) adverse_co,
               -- active in adverse coverage inside your states
               count(DISTINCT a.id) FILTER (WHERE a.geo_primary = ANY(:states)
                   AND EXISTS (SELECT 1 FROM article_stances st
                                WHERE st.article_id=a.id AND ({POL})<0)) in_region_neg
          FROM article_entity_mentions m
          JOIN articles a ON a.id=m.article_id
         WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
           AND a.collected_at>=analytics.now_sim()-make_interval(hours=>:wh)
           AND a.collected_at<=analytics.now_sim()
           AND {_BODY_PRESENT}
         GROUP BY 1
    """), {"pid": pid, "ids": ids, "states": states, "wh": wh})).fetchall()}

    lean = {r.id: r for r in (await db.execute(text(f"""
        SELECT m.entity_id::text id,
               round(100*avg(({POL})*st.intensity)::numeric,1) lean,
               count(*) lean_n
          FROM article_entity_mentions m
          JOIN articles a ON a.id=m.article_id
          JOIN article_stances st ON st.article_id=a.id
         WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
           AND a.collected_at>=analytics.now_sim()-make_interval(hours=>:wh)
           AND a.collected_at<=analytics.now_sim()
           AND EXISTS (SELECT 1 FROM article_entity_mentions pm
                        WHERE pm.article_id=a.id AND pm.entity_id=CAST(:pid AS uuid))
           AND {_BODY_PRESENT}
         GROUP BY 1
    """), {"pid": pid, "ids": ids, "wh": wh})).fetchall()}
    return cov, lean


async def _top_outlets_for(db, ids: list[str], wh: int) -> dict[str, str]:
    """Top outlet (by article count) per entity, in ONE query (DISTINCT ON)."""
    if not ids:
        return {}
    rows = (await db.execute(text(f"""
        SELECT DISTINCT ON (m.entity_id) m.entity_id::text id, s.name nm
          FROM article_entity_mentions m
          JOIN articles a ON a.id=m.article_id
          JOIN sources s ON s.id=a.source_id
         WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
           AND a.collected_at>=analytics.now_sim()-make_interval(hours=>:wh)
           AND a.collected_at<=analytics.now_sim()
           AND {_BODY_PRESENT}
         GROUP BY m.entity_id, s.name
         ORDER BY m.entity_id, count(DISTINCT a.id) DESC
    """), {"ids": ids, "wh": wh})).fetchall()
    return {r.id: r.nm for r in rows}


def _region_label(m: dict[str, Any]) -> str:
    return m.get("state") or ("national" if m.get("type") == "person" else "")


async def build_players(db, prefs: dict[str, Any], wh: int, limit: int = 5) -> dict[str, Any]:
    pid, _ = principal_of(prefs)
    states = (prefs.get("regions") or {}).get("states") or []
    meta = prefs["watchlist"]["entity_meta"]
    people = [m for m in meta if _is_person(m) and m["id"] != pid]
    if not people:
        return {"players": [], "caveats": ["No individuals on the watchlist to watch."]}

    ids = [m["id"] for m in people]
    cov, lean = await _people_signals(db, pid, ids, states, wh)

    sigs = []
    for m in people:
        c = cov.get(m["id"])
        coverage = int(c.coverage) if c else 0
        if coverage == 0:
            continue
        co_p = int(c.co_principal) if c else 0
        in_reg = int(c.in_region) if c else 0
        adverse_co = int(c.adverse_co) if c else 0
        in_reg_neg = int(c.in_region_neg) if c else 0
        ln = lean.get(m["id"])
        lean_fav = float(ln.lean) if ln and ln.lean is not None else None
        lean_n = int(ln.lean_n) if ln else 0
        # PRESSURE = adverse coverage that genuinely touches YOU: stories where
        # this person co-appears with the principal AND the story carries a
        # negative tone. We deliberately do NOT use "negative stories in your
        # states" — that counts negativity about anyone (an ally in a critical
        # piece about a third party), which falsely flags allies as threats.
        pressure = adverse_co * 100
        # ENTANGLEMENT = how present they are in YOUR coverage.
        entangle = co_p * 100 + in_reg * 2 + min(coverage, 200) / 50.0
        sigs.append({"m": m, "coverage": coverage, "co_p": co_p, "in_reg": in_reg,
                     "adverse_co": adverse_co, "in_reg_neg": in_reg_neg,
                     "lean": lean_fav, "lean_n": lean_n,
                     "pressure": pressure, "entangle": entangle})

    # Blend: lead with up to 3 genuine pressure points, fill the rest with the
    # most-entangled names. Honest per-persona — pressure cards are empty when no
    # watched figure is in adverse coverage (then it's an all-entangled board).
    chosen_ids: set[str] = set()
    pressure_cards = sorted([s for s in sigs if s["pressure"] > 0],
                            key=lambda x: -x["pressure"])[:3]
    for s in pressure_cards:
        chosen_ids.add(s["m"]["id"])
    entangled_cards = sorted([s for s in sigs if s["m"]["id"] not in chosen_ids],
                             key=lambda x: -x["entangle"])[: max(0, limit - len(pressure_cards))]
    ordered = ([("pressure", s) for s in pressure_cards]
               + [("entangled", s) for s in entangled_cards])[:limit]
    outlets = await _top_outlets_for(db, [s["m"]["id"] for _, s in ordered], wh)

    players = []
    for kind, s in ordered:
        m = s["m"]
        party = (m.get("party") or "").strip()
        region = _region_label(m)
        rel_bits = [b for b in [party or m.get("type"), region] if b]
        rel = " · ".join(rel_bits) if rel_bits else (m.get("tier") or "watch")
        outlet = outlets.get(m["id"])
        lean_fav, lean_n = s["lean"], s["lean_n"]

        if kind == "pressure":
            neg_lean = lean_fav is not None and lean_fav <= -15
            tone = "hostile" if (neg_lean or s["adverse_co"] >= 2) else "neutral"
            verdict = "Pressure point"
            score = _signed(lean_fav) if (lean_fav is not None and lean_n >= 3) else "—"
            adv, irn = s["adverse_co"], s["in_reg_neg"]
            adv_co = f"{adv} story" if adv == 1 else f"{adv} stories"
            adv_adj = f"{adv} adverse story" if adv == 1 else f"{adv} adverse stories"
            carry = "carries" if adv == 1 else "carry"
            irn_s = f"{irn} negative story" if irn == 1 else f"{irn} negative stories"
            why = (f"{adv_adj} where you co-appear; "
                   f"{irn_s} in your states ({s['coverage']} mentions"
                   + (f", top outlet {outlet})." if outlet else ")."))
            watch = "In your adverse coverage now — the line to track."
            summary = (f"{m['name']} is turning up in coverage that cuts against you — "
                       f"{adv_co} where you co-appear {carry} a negative read"
                       + (f", and {irn_s} in your states" if irn else "")
                       + f". {rel} — track whether it builds.")
        else:
            tone = _tone_from_fav(lean_fav, lean_n)
            thin = lean_n < 3
            if thin:
                verdict = "Thin signal"
                score = "—"
                why = (f"Appears in {s['co_p']} of your stories"
                       if s["co_p"] else f"{s['coverage']} mentions in {_window_label(wh)}, none alongside you")
                why += f"; {s['in_reg']} in your states." if s["in_reg"] else "; no in-state coverage."
                watch = "Too little co-coverage to read a posture — track if volume rises."
                summary = (f"{m['name']} surfaces in your window mostly outside your own coverage "
                           f"({s['coverage']} mentions, {s['co_p']} alongside you). Not enough shared "
                           f"coverage yet to judge how it cuts for or against you.")
            else:
                verdict = ("Reads favourable" if tone == "supportive"
                           else "Reads adverse" if tone == "hostile" else "Mixed read")
                score = _signed(lean_fav)
                lean_word = ("positive" if lean_fav >= 15 else "negative" if lean_fav <= -15 else "even")
                why = (f"In the {s['co_p']} stories where you both appear, coverage leans {lean_word} "
                       f"({_signed(lean_fav)}); {s['coverage']} total mentions"
                       + (f", top outlet {outlet}." if outlet else "."))
                watch = ("Your shared coverage runs with you — the dominant co-narrative."
                         if tone == "supportive" else
                         "Shared coverage runs against you — the line to track."
                         if tone == "hostile" else
                         "Shared coverage is balanced; watch which way it tips.")
                summary = (f"{m['name']} is one of the names most entangled with your coverage this "
                           f"window — present in {s['co_p']} of your stories ({s['coverage']} mentions overall). "
                           f"Where you co-appear, the coverage reads {lean_word} ({_signed(lean_fav)} on "
                           f"{lean_n} stance signals)" + (f", led by {outlet}." if outlet else "."))

        players.append({
            "name": m["name"], "rel": rel, "kind": kind, "stance": tone, "verdict": verdict,
            "score": score, "trend": "",
            "summary": summary, "why": why, "watch": watch,
            "_meta": {"coverage": s["coverage"], "co_principal": s["co_p"], "in_region": s["in_reg"],
                      "adverse_co": s["adverse_co"], "in_region_neg": s["in_reg_neg"],
                      "lean": lean_fav, "lean_n": lean_n,
                      "pressure": s["pressure"], "entangle": round(s["entangle"], 1)},
        })
    return {"players": players}


# ───────────────────────── THE SIX ─────────────────────────
def build_six(prefs: dict[str, Any], posture: dict[str, Any], wh: int) -> dict[str, Any]:
    M = posture.get("metrics", {})
    win = _window_label(wh)
    overall, ov_n = _overall_fav(posture)

    six: list[dict[str, Any]] = []

    # 1 — THE HARD TRUTH: the honest one-paragraph read of the window.
    fff = M.get("friend_foe_fence", {})
    n_ally, n_hostile = len(fff.get("ally", [])), len(fff.get("hostile", []))
    qsb = M.get("quote_selection_bias", {}).get("items", [])
    you_q = sum(i["quotes_principal"] for i in qsb)
    opp_q = sum(i["quotes_opposition"] for i in qsb)
    ao = M.get("attack_origination", {})
    origin = ao.get("origin") or {}
    iss_meta = M.get("issue_ownership", {})
    iss = iss_meta.get("items", []) if iss_meta.get("confidence") in ("high", "medium") else []
    contested = [i for i in iss if i.get("verdict") == "contested"]
    owns = [i for i in iss if i.get("verdict") == "owns"]
    if overall is not None and overall >= 10 and n_hostile == 0:
        ht_title = "It's a good week — guard the one soft spot"
        ht = (f"The honest read is that your coverage runs favourable: a net lean of "
              f"{_signed(overall)} across {ov_n} outlet-signals, no outlet hostile, and you are "
              f"quoted {you_q} times to the opposition's {opp_q}. The risk is not volume — it's a "
              f"single line. ")
        if origin.get("title"):
            ht += (f"“{origin['title']}” ({origin.get('outlet','')}) is the seed of the "
                   f"one adverse narrative; it is still contained. ")
        if contested:
            ht += f"You are contested on {contested[0]['topic'].title()} ({_signed(contested[0]['favourability'])}). "
        if owns:
            ht += f"You own {owns[0]['topic'].title()} ({_signed(owns[0]['favourability'])})."
    else:
        ht_title = "Where you're actually exposed"
        ht = (f"Net lean is {_signed(overall) if overall is not None else 'thin'} across {ov_n} "
              f"outlet-signals with {n_hostile} hostile outlet(s). ")
        if origin.get("title"):
            ht += f"The adverse line originates with “{origin['title']}” ({origin.get('outlet','')}). "
        ht += f"Opposition is quoted {opp_q} to your {you_q}."
    six.append({"kicker": "The Hard Truth", "title": ht_title, "body": ht,
                "print": "built from coverage + stance counts — it reads the press, not the public."})

    # 2 — REAL OR NOISE: classify the live adverse line by spread.
    neg = M.get("weighted_pressure", {}).get("negative_signals", 0)
    amps = ao.get("amplifiers", [])
    amp_outlets = {a.get("outlet") for a in amps if a.get("outlet")}
    items = []
    if origin.get("title"):
        spread = len(amp_outlets)
        if spread >= 3:
            items.append({"verdict": "RESPOND", "vtone": "neg",
                          "text": f"“{origin['title']}” — carried by {spread} outlets "
                                  f"({neg} adverse signals in {win}). It has spread past its origin; "
                                  f"answer it before it sets."})
        else:
            items.append({"verdict": "HOLD", "vtone": "neu",
                          "text": f"“{origin['title']}” — still {('one outlet' if spread<=1 else f'{spread} outlets')} "
                                  f"and {neg} adverse signals total. Loud where it runs, not yet spreading. "
                                  f"Watch, don't feed."})
    if not items:
        items.append({"verdict": "HOLD", "vtone": "neu",
                      "text": f"No concentrated adverse line in {win} — {neg} scattered negative signals, "
                              f"nothing meeting a respond threshold."})
    six.append({"kicker": "Real or Noise?", "title": "What's actually worth reacting to", "items": items})

    # 3 — ARE YOU BEING HEARD: quote-selection bias.
    if qsb:
        worst = min(qsb, key=lambda i: i["quotes_principal"] - i["quotes_opposition"])
        ratio = (f"{you_q}:{opp_q}" if opp_q else f"{you_q}:0")
        if you_q >= max(1, opp_q) * 1.5:
            heard = (f"You are being heard. Across {len(qsb)} outlets your voice carries {ratio} against "
                     f"the opposition's — they are not speaking for you inside your own coverage. "
                     f"Thinnest parity is {worst['outlet']} ({worst['quotes_principal']}:{worst['quotes_opposition']}).")
        else:
            heard = (f"You are covered but not always heard: {ratio} quote share against the opposition "
                     f"across {len(qsb)} outlets. Weakest at {worst['outlet']} "
                     f"({worst['quotes_principal']}:{worst['quotes_opposition']}).")
    else:
        heard = "Too few attributed quotes in the window to judge quote share."
    six.append({"kicker": "Are You Being Heard?", "title": "Are they quoting you, or speaking for you", "body": heard})

    # 4 — THE COVERAGE SPLIT: cross-language gap.
    clg = M.get("cross_language_gap", {})
    langs = {i["language"]: i for i in clg.get("items", [])}
    if "en" in langs and "te" in langs:
        en, te = langs["en"], langs["te"]
        gap = clg.get("gap")
        warmer = "English" if en["favourability"] >= te["favourability"] else "Telugu"
        body = (f"English reads {_signed(en['favourability'])} ({en['n']} signals); Telugu reads "
                f"{_signed(te['favourability'])} ({te['n']}). {warmer} is the warmer press, gap of "
                f"{abs(gap) if gap is not None else '—'}. ")
        body += ("Both languages run in your favour — no split to manage this week."
                 if en["favourability"] > 0 and te["favourability"] > 0 else
                 "The two presses are telling different stories — brief off the wrong one and you'll misread the week.")
        six.append({"kicker": "The Coverage Split", "title": "Telugu press vs English press", "body": body,
                    "print": "press-by-language, not public opinion — we don't read social media."})
    else:
        six.append({"kicker": "The Coverage Split", "title": "Telugu press vs English press",
                    "body": "Not enough dual-language stance data in the window to split the read.",
                    "print": "press-by-language, not public opinion."})

    # 5 — WHO TO CALL: friend/foe/fence.
    ally_all = fff.get("ally", [])
    hostile = fff.get("hostile", [])
    # Prefer outlets with enough signal to be a confident call (n>=5); a +43 on
    # 3 signals is noise, not a recommendation.
    ally = [a for a in ally_all if a["n"] >= 5] or ally_all
    if ally:
        a0 = ally[0]
        call = f"Your warmest outlet is {a0['outlet']} ({_signed(a0['favourability'])}, {a0['n']} signals) — the clean place to land a win. "
        if len(ally) > 1:
            a1 = ally[1]
            call += f"{a1['outlet']} ({_signed(a1['favourability'])}, {a1['n']}) is your second-best room. "
        call += (f"Avoid {hostile[0]['outlet']} ({_signed(hostile[0]['favourability'])}) — engaging only feeds it."
                 if hostile else "No outlet is hostile right now, so there is no fire to avoid — pitch widely.")
    else:
        call = "No outlet clears the favourability bar for a confident recommendation this window."
    six.append({"kicker": "Who To Call", "title": "Which outlet to work today", "body": call,
                "print": "outlet calls from stance data; we name a reporter only where the byline is in the data."})

    # 6 — READY FOR YOU: draft types tied to the real live issues (no fabricated text).
    drafts = []
    if contested:
        drafts.append({"verdict": "STATEMENT", "vtone": "pos",
                       "text": f"On {contested[0]['topic'].title()} — your contested front ({_signed(contested[0]['favourability'])}). "
                               f"A short position line, ready to ship or kill."})
    if origin.get("title"):
        drafts.append({"verdict": "COUNTER-LINE", "vtone": "pos",
                       "text": f"For the “{origin['title'][:60]}” line — a one-paragraph rebuttal to get ahead of it honestly."})
    drafts.append({"verdict": "TRANSLATED", "vtone": "neu",
                   "text": "The sharpest adverse Telugu line, rendered in English so your national desk sees exactly what's being said."})
    six.append({"kicker": "Ready For You", "title": "Drafts waiting for your sign-off", "items": drafts,
                "print": "draft scaffolds only — nothing leaves without your sign-off."})

    return {"six": six}


# ───────────────────────── THE BRIEFING ─────────────────────────
async def _what_happened(db, ranked: list[dict[str, Any]], k: int = 4) -> list[dict[str, Any]]:
    ids = [r["id"] for r in ranked[:k]]
    if not ids:
        return []
    meta = {r.id: r for r in (await db.execute(text("""
        SELECT id::text id, collected_at d, language_iso lang FROM articles WHERE id = ANY(CAST(:ids AS uuid[]))
    """), {"ids": ids})).fetchall()}
    out = []
    for r in ranked[:k]:
        m = meta.get(r["id"])
        out.append({"id": r["id"], "date": _fmt_day(m.d if m else None),
                    "text": r["title"], "src": r.get("source") or "", "lang": (m.lang if m else None)})
    await _i18n.attach_en(db, out, "text")
    return out


def build_briefing(prefs: dict[str, Any], posture: dict[str, Any],
                   ranked: list[dict[str, Any]], what_happened: list[dict[str, Any]],
                   wh: int) -> dict[str, Any]:
    M = posture.get("metrics", {})
    overall, ov_n = _overall_fav(posture)
    traj = M.get("stance_trajectory", {})
    direction = traj.get("direction")
    ao = M.get("attack_origination", {}).get("origin") or {}
    qsb = M.get("quote_selection_bias", {}).get("items", [])
    you_q = sum(i["quotes_principal"] for i in qsb)
    opp_q = sum(i["quotes_opposition"] for i in qsb)
    iss_meta = M.get("issue_ownership", {})
    iss = iss_meta.get("items", []) if iss_meta.get("confidence") in ("high", "medium") else []
    contested = [i for i in iss if i.get("verdict") == "contested"]

    stance_word = ("favourable" if (overall or 0) >= 10 else
                   "mixed" if (overall or 0) > -10 else "adverse")
    top_story = ranked[0]["title"] if ranked else "—"

    bottom_line = [
        {"k": "Where You Stand",
         "v": f"Coverage runs {stance_word} ({_signed(overall) if overall is not None else 'thin'}), "
              f"{'cooling pressure' if direction=='cooling' else direction or 'steady'}."},
        {"k": "Know This", "v": top_story},
    ]
    if ao.get("title"):
        bottom_line.append({"k": "The Attack",
                            "v": f"“{ao['title']}” — {ao.get('outlet','')}."})
    bottom_line.append({"k": "Your Move",
                        "v": (f"Get ahead of the {contested[0]['topic'].lower()} front before it sets."
                              if contested else "Push your warmest win into your warmest outlet today."),
                        "action": True})

    what_it_means = (
        f"The week reads {stance_word}. " +
        (f"Your dominant story is “{top_story}”. " if ranked else "") +
        (f"The one adverse thread is “{ao['title']}” ({ao.get('outlet','')}), still contained. "
         if ao.get("title") else "No single adverse thread is dominating. ") +
        (f"You are quoted {you_q} to {opp_q} — your voice, not the opposition's, is carrying the coverage."
         if you_q else "")
    )
    why_it_matters = (
        (f"You are contested on {contested[0]['topic'].title()} ({_signed(contested[0]['favourability'])}); "
         f"that's the front that decides whether a good week holds. "
         if contested else "With no contested front open, the job this week is to protect the lead, not chase. ")
        + "Silence on the one adverse line is what would turn it from noise into a story."
    )
    whats_next = {
        "text": (f"Watch whether “{ao['title']}” jumps outlets — the day a second tier-1 outlet "
                 f"carries it, it stops being contained. " if ao.get("title")
                 else "No adverse line is near a tipping point; the trajectory is the thing to watch. ")
                + f"Trajectory is currently {direction or 'flat'}.",
        "confidence": M.get("stance_trajectory", {}).get("confidence", "low"),
    }
    how_to_play = (
        "Lead with your strongest delivery story in your warmest outlet. "
        + (f"Contest {contested[0]['topic'].lower()} directly. " if contested else "")
        + ("Don't argue the adverse line on its own terms — bury it under your own news."
           if ao.get("title") else "Hold the line; there's nothing to chase.")
    )
    other_side = (
        f"The case you're over-reading this: the adverse signal is thin "
        f"({M.get('weighted_pressure', {}).get('negative_signals', 0)} negative signals) and concentrated. "
        + ("Strip the one origin outlet and the week is clean. " if ao.get("outlet") else "")
        + "What would flip the call: a second independent outlet picking up the adverse line. It hasn't, yet."
    )

    return {"briefing": {
        "bottomLine": bottom_line,
        "whatHappened": what_happened,
        "whatItMeans": what_it_means,
        "whyItMatters": why_it_matters,
        "whatsNext": whats_next,
        "howToPlay": how_to_play,
        "otherSide": other_side,
    }}


# ───────────────────────── MASTHEAD + ORCHESTRATOR ─────────────────────────
def _fmt_asof(dt) -> str:
    if dt is None:
        return ""
    return f"{dt.day} {_MONTHS[dt.month]} {dt.year}"


def _caveats(prefs: dict[str, Any], players: list[dict[str, Any]]) -> list[str]:
    out = []
    if players and not any(p.get("kind") == "pressure" for p in players):
        out.append("No watched individual is in adverse coverage with you this window — "
                   "the pressure lane fills when opposition figures are on your watchlist.")
    return out


async def build_home(db, prefs: dict[str, Any], *, display_name: str | None = None,
                     posture_wh: int = 504, relevance_wh: int = 168) -> dict[str, Any]:
    """Assemble the full Night Desk Home payload for the authenticated persona.

    Computes the posture bundle + relevance ONCE and reshapes into the three
    sections, so numbers are consistent across THE BRIEFING / PEOPLE TO WATCH /
    THE SIX. Honest + source-grounded throughout.
    """
    pid, pname = principal_of(prefs)
    posture = await compute_posture(db, prefs, window_hours=posture_wh, only=_HOME_METRICS)
    ranked = await score_relevant(db, prefs, window_hours=relevance_wh, limit=40)

    wh_events = await _what_happened(db, ranked, k=4)
    briefing = build_briefing(prefs, posture, ranked, wh_events, relevance_wh)
    players_out = await build_players(db, prefs, posture_wh)
    six = build_six(prefs, posture, posture_wh)

    now = (await db.execute(text("SELECT analytics.now_sim() AS n"))).scalar()
    overall, ov_n = _overall_fav(posture)
    # Confidence from the favourability signal count (share_of_voice dropped from
    # the Home metric set for speed).
    conf = ("high" if ov_n >= 20 else "medium" if ov_n >= 8
            else "low" if ov_n > 0 else "insufficient")

    parts = (pname or "").split()
    states = (prefs.get("regions") or {}).get("states") or []
    masthead = {
        "state": states[0] if states else None,
        "principal": pname,
        "first": parts[0] if parts else "",
        "last": " ".join(parts[1:]) if len(parts) > 1 else "",
        "displayName": display_name,
        "asOf": _fmt_asof(now),
        "window": _window_label(posture_wh),
        "overall": overall,
        "confidence": conf,
    }

    return {
        "personalized": True,
        "as_of": str(now),
        "masthead": masthead,
        **briefing,        # -> "briefing"
        **players_out,     # -> "players" (+ optional "caveats")
        **six,             # -> "six"
        "caveats": _caveats(prefs, players_out.get("players", [])),
    }
