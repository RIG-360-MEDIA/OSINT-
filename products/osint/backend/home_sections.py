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

from posture import POL, _BODY_PRESENT, compute_posture, current_mood, principal_of
from relevance import score_relevant
import i18n as _i18n

# Strip URL-slug junk some sources store as the title (trailing ids, ?utm=, .html).
# Also catches slug codes before the id, e.g. "vvnp 1530822.html", "nnm_1234567".
_TITLE_JUNK = re.compile(
    r"\s*((?:[a-z]{2,8}[ _])?(?:\d{5,}\S*|\.html?))\s*$", re.I)


def _clean_title(t):
    if not t:
        return t
    c = _TITLE_JUNK.sub("", str(t).strip()).strip()
    return c or t

_MIN = "−"  # unicode minus, matches the design's typography
_LQ = "“"  # left double quotation mark
_RQ = "”"  # right double quotation mark

# Parties/fronts are frequently mistyped as `person` in the entity dictionary.
# PEOPLE TO WATCH is about individuals, so we exclude org/party-shaped names.
_PARTY_RE = re.compile(
    r"(?i)(\bparty\b|congress|desam|samithi|samiti|janata|sena|morcha|majlis|"
    r"aadmi|sangh|front|ministry|court|commission|aayog|reserve bank)")


def _is_person(m: dict[str, Any]) -> bool:
    t = (m.get("type") or "").lower()
    k = (m.get("kind") or "").lower()
    if t not in ("person", "politician") and k not in ("person", "politician"):
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


async def _sentiment_series(db, pid: str, wh: int, overall: float | None,
                            bucket_s: int = 21600) -> dict[str, Any]:
    """Coverage-sentiment waveform for the principal.

    Mean stance polarity (POL × intensity, ×100, range −100…+100) per
    `bucket_s`-second bucket, over body-present articles that mention the
    principal — the same anti-hallucination idiom posture.py uses. The
    headline number reuses the masthead favourability (`overall`) so the
    figure shown on the landing page matches the masthead exactly; the
    buckets carry the trajectory shape.
    """
    rows = (await db.execute(text(f"""
        SELECT to_timestamp(floor(extract(epoch FROM a.collected_at) / :bs) * :bs) AS b,
               round(100 * avg(({POL}) * st.intensity)::numeric, 1) AS v,
               count(DISTINCT a.id) AS n
          FROM article_entity_mentions m
          JOIN articles a ON a.id = m.article_id
          JOIN article_stances st ON st.article_id = a.id
         WHERE m.entity_id = CAST(:pid AS uuid)
           AND st.actor_entity_id = CAST(:pid AS uuid)
           AND st.intensity IS NOT NULL
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
           AND a.collected_at <= analytics.now_sim()
           AND {_BODY_PRESENT}
         GROUP BY 1
         ORDER BY 1
    """), {"pid": pid, "wh": wh, "bs": bucket_s})).fetchall()

    points = [{"t": r.b.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "v": float(r.v) if r.v is not None else 0.0,
               "n": int(r.n)} for r in rows]
    label = ("Favourable" if (overall or 0) >= 10 else
             "Adverse" if (overall or 0) <= -10 else "Mixed")
    return {"now": overall, "label": label, "points": points,
            "n": sum(p["n"] for p in points)}


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


async def _latest_co_story_for(db, ids: list[str], pid: str | None, wh: int) -> dict[str, dict[str, str]]:
    """Latest co-appearing story (with the principal) per entity, in ONE query.

    Returns {entity_id: {title, source, when}}. When pid is None or no co-story
    exists in the window, falls back to the entity's own latest in-window story.
    The latest headline changes as new articles ingest -> the card visibly differs
    each refresh even when the underlying counts move slowly.
    """
    if not ids:
        return {}
    out: dict[str, dict[str, str]] = {}
    # Reject URL-slug "titles" (some sources store the slug instead of the real
    # headline). A real title doesn't end in .html/.htm/.aspx/.php and doesn't
    # contain a multi-digit numeric id surrounded by underscores or hyphens.
    title_ok = (
        " AND a.title IS NOT NULL "
        " AND a.title !~* '\\.(html?|aspx|php)$' "
        " AND a.title !~* '[/\\\\]' "
        " AND a.title !~* '(^|[ _-])[0-9]{4,}[ _-]?[a-z]{0,4}(\\.html?)?$' "
        " AND length(a.title) BETWEEN 18 AND 220 "
    )
    if pid:
        rows = (await db.execute(text(f"""
            SELECT DISTINCT ON (m.entity_id) m.entity_id::text id, a.title, s.name src, a.collected_at
              FROM article_entity_mentions m
              JOIN article_entity_mentions mp ON mp.article_id=m.article_id AND mp.entity_id=CAST(:pid AS uuid)
              JOIN articles a ON a.id=m.article_id
              JOIN sources s ON s.id=a.source_id
             WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
               AND a.collected_at>=analytics.now_sim()-make_interval(hours=>:wh)
               AND a.collected_at<=analytics.now_sim()
               AND {_BODY_PRESENT}
               {title_ok}
             ORDER BY m.entity_id, a.collected_at DESC
        """), {"ids": ids, "pid": pid, "wh": wh})).fetchall()
        for r in rows:
            out[r.id] = {"title": r.title, "source": r.src, "when": str(r.collected_at) if r.collected_at else ""}
    missing = [i for i in ids if i not in out]
    if missing:
        rows = (await db.execute(text(f"""
            SELECT DISTINCT ON (m.entity_id) m.entity_id::text id, a.title, s.name src, a.collected_at
              FROM article_entity_mentions m
              JOIN articles a ON a.id=m.article_id
              JOIN sources s ON s.id=a.source_id
             WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
               AND a.collected_at>=analytics.now_sim()-make_interval(hours=>:wh)
               AND a.collected_at<=analytics.now_sim()
               AND {_BODY_PRESENT}
               {title_ok}
             ORDER BY m.entity_id, a.collected_at DESC
        """), {"ids": missing, "wh": wh})).fetchall()
        for r in rows:
            out[r.id] = {"title": r.title, "source": r.src, "when": str(r.collected_at) if r.collected_at else ""}
    return out


async def _fetch_entity_images(db, ids: list[str]) -> dict[str, str]:
    """Fetch confirmed image URLs from analytics.entity_image. {entity_id: url}."""
    if not ids:
        return {}
    rows = (await db.execute(text("""
        SELECT entity_id::text, image_url
          FROM analytics.entity_image
         WHERE entity_id = ANY(CAST(:ids AS uuid[]))
           AND ok = true AND image_url IS NOT NULL
    """), {"ids": ids})).fetchall()
    return {r.entity_id: r.image_url for r in rows}


def _region_label(m: dict[str, Any]) -> str:
    return m.get("state") or ("national" if m.get("type") == "person" else "")


async def _top_pos_neg_stories_for(
    db, ids: list[str], pid: str, wh: int
) -> dict[str, dict]:
    """Best (most positive lean) and worst (most negative lean) co-story per entity."""
    if not ids:
        return {}
    title_ok = (
        " AND a.title IS NOT NULL "
        " AND a.title !~* '\\.(html?|aspx|php)$' "
        " AND a.title !~* '[/\\\\]' "
        " AND a.title !~* '(^|[ _-])[0-9]{4,}[ _-]?[a-z]{0,4}(\\.html?)?$' "
        " AND length(a.title) BETWEEN 18 AND 220 "
    )
    rows = (await db.execute(text(f"""
        WITH scored AS (
            SELECT m.entity_id::text AS eid,
                   a.title, s.name AS outlet, a.url,
                   round(100 * avg(({POL}) * st.intensity)::numeric, 1) AS lean
              FROM article_entity_mentions m
              JOIN article_entity_mentions mp ON mp.article_id = m.article_id
                                             AND mp.entity_id = CAST(:pid AS uuid)
              JOIN articles a ON a.id = m.article_id
              JOIN sources s ON s.id = a.source_id
              JOIN article_stances st ON st.article_id = a.id
             WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
               AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
               AND a.collected_at <= analytics.now_sim()
               AND {_BODY_PRESENT}
               {title_ok}
             GROUP BY m.entity_id, a.id, a.title, s.name, a.url
        ),
        ranked AS (
            SELECT eid, title, outlet, url, lean,
                   rank() OVER (PARTITION BY eid ORDER BY lean DESC) AS pos_rank,
                   rank() OVER (PARTITION BY eid ORDER BY lean ASC)  AS neg_rank
              FROM scored
        )
        SELECT eid, title, outlet, url, lean, pos_rank, neg_rank
          FROM ranked
         WHERE pos_rank = 1 OR neg_rank = 1
    """), {"ids": ids, "pid": pid, "wh": wh})).fetchall()

    out: dict[str, dict] = {}
    for r in rows:
        if r.eid not in out:
            out[r.eid] = {}
        entry = {
            "title": _clean_title(r.title),
            "outlet": r.outlet,
            "url": r.url or "",
            "lean": float(r.lean) if r.lean is not None else 0.0,
        }
        if r.pos_rank == 1:
            out[r.eid]["top_pos"] = entry
        if r.neg_rank == 1:
            out[r.eid]["top_neg"] = entry
    return out


def _read_word(fav: float | None) -> str:
    """The shared-coverage tone as a plain WORD instead of a bare number."""
    if fav is None:
        return "—"
    if fav <= -25:
        return "Very negative"
    if fav <= -10:
        return "Negative"
    if fav < 10:
        return "Mixed"
    if fav < 25:
        return "Positive"
    return "Very positive"


async def build_players(db, prefs: dict[str, Any], wh: int, limit: int = 8) -> dict[str, Any]:
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
        pinned = bool(m.get("pinned"))
        c = cov.get(m["id"])
        coverage = int(c.coverage) if c else 0
        if coverage == 0 and not pinned:
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
        sigs.append({"m": m, "pinned": pinned, "coverage": coverage, "co_p": co_p, "in_reg": in_reg,
                     "adverse_co": adverse_co, "in_reg_neg": in_reg_neg,
                     "lean": lean_fav, "lean_n": lean_n,
                     "pressure": pressure, "entangle": entangle})

    # PEOPLE TO WATCH is a manually-curated list, not an auto-curated feed: it
    # shows ONLY the individuals the user explicitly added (newest first), capped
    # at `limit`. We deliberately do NOT backfill a freed slot with a relevance-
    # ranked name — removing someone leaves the panel smaller. `limit` is a ceiling,
    # not a target. Each surviving card still renders its genuine coverage read
    # (pressure / entangled / thin), and a freshly-added name with no coverage yet
    # gets the "just added" treatment below.
    def _rk(s: dict[str, Any]) -> str:
        return "pressure" if s["pressure"] > 0 else "entangled"
    pinned_cards = [s for s in sigs if s["pinned"]][::-1][:limit]
    ordered = [(_rk(s), s) for s in pinned_cards]
    chosen_ids_list = [s["m"]["id"] for _, s in ordered]
    outlets = await _top_outlets_for(db, chosen_ids_list, wh)
    latest_stories = await _latest_co_story_for(db, chosen_ids_list, pid, wh)
    img_map = await _fetch_entity_images(db, chosen_ids_list)
    # Batch-translate non-English headlines so every card gets a bilingual gloss.
    non_en_titles = {ls["title"] for ls in latest_stories.values()
                     if ls.get("title") and not _i18n.is_english(ls["title"])}
    en_map = await _i18n.ensure_en(db, non_en_titles) if non_en_titles else {}

    players = []
    for kind, s in ordered:
        m = s["m"]
        party = (m.get("party") or "").strip()
        region = _region_label(m)
        rel_bits = [b for b in [party or m.get("type"), region] if b]
        rel = " · ".join(rel_bits) if rel_bits else (m.get("tier") or "watch")
        outlet = outlets.get(m["id"])
        lean_fav, lean_n = s["lean"], s["lean_n"]

        if s.get("pinned") and s["coverage"] == 0:
            tone = "neutral"
            verdict = "Just added"
            score = "—"
            why = f"No coverage in {_window_label(wh)} yet — newly added to your watch list."
            watch = "Freshly added; the card fills in as stories mention them."
            summary = (f"{m['name']} is on your watch list but hasn't appeared in coverage "
                       f"this window yet. {rel} — the read builds as articles come in.")
        elif kind == "pressure":
            neg_lean = lean_fav is not None and lean_fav <= -15
            tone = "hostile" if (neg_lean or s["adverse_co"] >= 2) else "neutral"
            verdict = "Pressure point"
            score = _read_word(lean_fav) if (lean_fav is not None and lean_n >= 3) else "—"
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
                score = _read_word(lean_fav)
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

        # Drop in the actual latest co-appearing headline so the card visibly
        # changes when new stories ingest (without it the prose looks frozen).
        ls = latest_stories.get(m["id"])
        latest_title = (ls or {}).get("title")
        latest_title_en = None
        if ls and latest_title:
            t = latest_title.strip()
            if len(t) > 140:
                t = t[:137].rstrip() + "…"
            summary = f"{summary} Latest: {_LQ}{t}{_RQ} ({ls.get('source') or '—'})."
            if not _i18n.is_english(latest_title):
                latest_title_en = en_map.get(latest_title)

        players.append({
            "id": m["id"],
            "img": img_map.get(m["id"]),
            "name": m["name"], "rel": rel, "kind": kind, "stance": tone, "verdict": verdict,
            "score": score, "trend": "",
            "summary": summary, "why": why, "watch": watch,
            "latest_headline": latest_title,
            "latest_headline_en": latest_title_en,
            "latest_source": (ls or {}).get("source"),
            "latest_at": (ls or {}).get("when"),
            "_meta": {"coverage": s["coverage"], "co_principal": s["co_p"], "in_region": s["in_reg"],
                      "adverse_co": s["adverse_co"], "in_region_neg": s["in_reg_neg"],
                      "lean": lean_fav, "lean_n": lean_n,
                      "pressure": s["pressure"], "entangle": round(s["entangle"], 1)},
        })
    return {"players": players}


# ───────────────────────── THE SIX (evidence feeds) ─────────────────────────
def _ago(h: Any) -> str:
    """Human 'time ago' from an age in hours."""
    if h is None:
        return ""
    h = float(h)
    if h < 1:
        return f"{max(1, int(h * 60))}m ago"
    if h < 24:
        return f"{int(h)}h ago"
    return f"{int(h / 24)}d ago"


def _pol_tone(pol: Any) -> str:
    """Sum of (polarity x intensity) → a simple pos/neg/neutral dot class."""
    if pol is None:
        return "neu"
    p = float(pol)
    return "neg" if p < 0 else "pos" if p > 0 else "neu"


def _trim(s: str | None, n: int = 160) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


async def build_six_feeds(db, prefs: dict[str, Any], pid: str, pname: str,
                          wh: int) -> dict[str, Any]:
    """THE SIX rebuilt as six plain evidence feeds — each a 'latest X about you'
    list, sourced and linkable, ordered newest-first so it refreshes as articles
    ingest. No derived abstractions: every row is a real quote or headline."""
    win = _window_label(wh)
    if not pid:
        return {"six": []}
    p = {"pid": pid, "wh": wh}
    # Coverage tone DIRECTED AT THE PRINCIPAL (not the whole article): only
    # stances whose target is the principal count, so "Congress criticised" in a
    # story doesn't read as support for a Congress CM. Matches the sentiment feed.
    pol_sum = (f"(SELECT COALESCE(sum(({POL})*st.intensity),0) "
               f"FROM article_stances st WHERE st.article_id=a.id "
               f"AND st.actor_entity_id=CAST(:pid AS uuid))")
    to_en: set[str] = set()   # non-English strings to translate in one batch

    # ── 1. Latest quotes about you ──────────────────────────────────────────
    qrows = (await db.execute(text(f"""
        SELECT q.quote_text AS txt, q.speaker_name AS who, src.name AS source,
               a.url AS url,
               EXTRACT(EPOCH FROM (analytics.now_sim()-a.collected_at))/3600.0 AS age_h
          FROM article_quotes q
          JOIN articles a ON a.id=q.article_id
          JOIN sources src ON src.id=a.source_id
          JOIN article_entity_mentions m ON m.article_id=a.id AND m.entity_id=CAST(:pid AS uuid)
         WHERE a.collected_at >= analytics.now_sim()-make_interval(hours=>:wh)
           AND a.collected_at <= analytics.now_sim()
           AND q.is_direct AND q.quote_text IS NOT NULL
           AND char_length(btrim(q.quote_text)) >= 15
           AND {_BODY_PRESENT}
         ORDER BY a.collected_at DESC
         LIMIT 14
    """), p)).fetchall()
    quote_items, seen_q = [], set()
    for r in qrows:
        t = _trim(r.txt, 220)
        key = t.lower()[:60]
        if key in seen_q:
            continue
        seen_q.add(key)
        if not _i18n.is_english(t):
            to_en.add(t)
        who = (r.who or "").strip()
        sub = " · ".join(x for x in [who, r.source] if x)
        quote_items.append({"kind": "quote", "text": t, "sub": sub,
                            "when": _ago(r.age_h), "tone": "neu", "url": r.url or ""})
        if len(quote_items) >= 5:
            break

    async def _articles(extra: str, limit: int = 5):
        rows = (await db.execute(text(f"""
            SELECT COALESCE(NULLIF(a.title,''), a.lead_text_translated, '') AS title,
                   src.name AS source, a.url AS url, {pol_sum} AS pol,
                   EXTRACT(EPOCH FROM (analytics.now_sim()-a.collected_at))/3600.0 AS age_h
              FROM article_entity_mentions m
              JOIN articles a ON a.id=m.article_id
              JOIN sources src ON src.id=a.source_id
             WHERE m.entity_id=CAST(:pid AS uuid)
               AND a.collected_at >= analytics.now_sim()-make_interval(hours=>:wh)
               AND a.collected_at <= analytics.now_sim()
               AND {_BODY_PRESENT}
               {extra}
             ORDER BY a.collected_at DESC
             LIMIT {int(limit)}
        """), p)).fetchall()
        out = []
        for r in rows:
            t = _trim(r.title, 150)
            if not t:
                continue
            if not _i18n.is_english(t):
                to_en.add(t)
            out.append({"kind": "link", "text": t, "sub": r.source,
                        "when": _ago(r.age_h), "tone": _pol_tone(r.pol),
                        "url": r.url or ""})
        return out

    # ── 2/3/4. Latest articles · criticism · support ───────────────────────
    art_items = await _articles("")
    crit_items = await _articles(f"AND {pol_sum} < 0")
    supp_items = await _articles(f"AND {pol_sum} > 0")

    # ── 5. Latest from people you watch ────────────────────────────────────
    wmeta = (prefs.get("watchlist") or {}).get("entity_meta") or []
    wids = [m["id"] for m in wmeta if _is_person(m) and m.get("id") != pid]
    watch_items = []
    if wids:
        wrows = (await db.execute(text(f"""
            SELECT COALESCE(NULLIF(a.title,''), a.lead_text_translated, '') AS title,
                   src.name AS source, a.url AS url,
                   (SELECT canonical_name FROM entity_dictionary ed WHERE ed.id=m.entity_id) AS person,
                   EXTRACT(EPOCH FROM (analytics.now_sim()-a.collected_at))/3600.0 AS age_h,
                   a.collected_at AS ts
              FROM article_entity_mentions m
              JOIN articles a ON a.id=m.article_id
              JOIN sources src ON src.id=a.source_id
             WHERE m.entity_id = ANY(CAST(:wids AS uuid[]))
               AND a.collected_at >= analytics.now_sim()-make_interval(hours=>:wh)
               AND a.collected_at <= analytics.now_sim()
               AND {_BODY_PRESENT}
             ORDER BY a.collected_at DESC
             LIMIT 30
        """), {"wids": wids, "wh": wh})).fetchall()
        seen_w = set()
        for r in wrows:
            t = _trim(r.title, 140)
            if not t or t.lower()[:50] in seen_w:
                continue
            seen_w.add(t.lower()[:50])
            if not _i18n.is_english(t):
                to_en.add(t)
            sub = " · ".join(x for x in [(r.person or "").strip(), r.source] if x)
            watch_items.append({"kind": "link", "text": t, "sub": sub,
                                "when": _ago(r.age_h), "tone": "neu", "url": r.url or ""})
            if len(watch_items) >= 5:
                break

    # ── 6. What you're being tied to ───────────────────────────────────────
    # Exclude noise that isn't a meaningful "tie": the principal himself, his OWN
    # state and party (derived from prefs), and pure locations — so the feed shows
    # the PEOPLE and RIVAL PARTIES he's being linked to, not 'Telangana'/'Hyderabad'.
    psmeta = prefs.get("primary_subject_meta") or {}
    own_state = (psmeta.get("state") or "").strip()
    states = (prefs.get("regions") or {}).get("states") or []
    own_party = (psmeta.get("party") or "").strip()
    # Block the principal's own party under every label it travels under so a
    # Congress CM isn't shown as "tied to" his own party.
    _party_aliases = {"inc", "congress", "indian national congress"}
    excl_names = {n.lower() for n in (
        [pname, own_state, own_party] + list(states)) if n and n.strip()}
    excl_names |= _party_aliases if (own_party.lower() in _party_aliases
                                     or "congress" in own_party.lower()) else set()
    tied_rows = (await db.execute(text("""
        SELECT ed.canonical_name AS name, count(DISTINCT a.id) AS n
          FROM article_entity_mentions m
          JOIN articles a ON a.id=m.article_id
          JOIN article_entity_mentions co ON co.article_id=a.id AND co.entity_id <> CAST(:pid AS uuid)
          JOIN entity_dictionary ed ON ed.id=co.entity_id
         WHERE m.entity_id=CAST(:pid AS uuid)
           AND a.collected_at >= analytics.now_sim()-make_interval(hours=>:wh)
           AND a.collected_at <= analytics.now_sim()
           AND ed.redirected_to IS NULL
           AND char_length(ed.canonical_name) >= 3
           AND COALESCE(ed.entity_type,'') <> 'location'
           AND lower(btrim(ed.canonical_name)) <> ALL(CAST(:excl AS text[]))
           AND {body}
         GROUP BY ed.canonical_name
         ORDER BY n DESC
         LIMIT 7
    """.format(body=_BODY_PRESENT)),
        {**p, "excl": list(excl_names) or [""]})).fetchall()
    tied_items = [{"kind": "tag", "text": r.name,
                   "sub": f"in {r.n} stories" if r.n != 1 else "in 1 story",
                   "tone": "neu"} for r in tied_rows
                  if (r.name or "").strip().lower() not in excl_names]

    # One batched translation pass for every non-English line we'll show.
    en_map = await _i18n.ensure_en(db, to_en) if to_en else {}
    for grp in (quote_items, art_items, crit_items, supp_items, watch_items):
        for it in grp:
            if it["text"] in en_map and en_map[it["text"]]:
                it["en"] = _trim(en_map[it["text"]], 220 if it["kind"] == "quote" else 150)

    feeds = [
        {"key": "quotes",  "title": "Latest quotes in your coverage",
         "blurb": "What people are saying — word for word.",
         "items": quote_items, "empty": f"No quotes in the last {win}."},
        {"key": "articles", "title": "Latest articles about you",
         "blurb": "Fresh coverage, newest first.",
         "items": art_items, "empty": f"No new articles in the last {win}."},
        {"key": "criticism", "title": "Latest criticism of you",
         "blurb": "The newest coverage that runs against you.",
         "items": crit_items, "empty": "No clearly negative coverage right now."},
        {"key": "support", "title": "Latest support for you",
         "blurb": "The newest coverage that runs with you.",
         "items": supp_items, "empty": "No clearly positive coverage right now."},
        {"key": "watchlist", "title": "Latest from people you watch",
         "blurb": "New stories featuring your watch list.",
         "items": watch_items,
         "empty": "Nothing new from your watch list yet." if wids
                  else "Add people to your watch list to see this."},
        {"key": "tied", "title": "What you're being tied to",
         "blurb": "Names and topics showing up alongside you.",
         "items": tied_items, "empty": "Not enough coverage to tell yet."},
    ]
    return {"six": feeds}


# ───────────────────────── THE SIX (legacy analytical, unused) ──────────────
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
            ht += (f"{_LQ}{origin['title']}{_RQ} ({origin.get('outlet', '')}) is the seed of the "
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
            ht += f"The adverse line originates with {_LQ}{origin['title']}{_RQ} ({origin.get('outlet','')}). "
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
                          "text": f"{_LQ}{origin['title']}{_RQ} — carried by {spread} outlets "
                                  f"({neg} adverse signals in {win}). It has spread past its origin; "
                                  f"answer it before it sets."})
        else:
            items.append({"verdict": "HOLD", "vtone": "neu",
                          "text": f"{_LQ}{origin['title']}{_RQ} — still {('one outlet' if spread<=1 else f'{spread} outlets')} "
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
                       "text": f"For the {_LQ}{origin['title'][:60]}{_RQ} line — a one-paragraph rebuttal to get ahead of it honestly."})
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
        SELECT id::text id, collected_at d, language_iso lang, url FROM articles WHERE id = ANY(CAST(:ids AS uuid[]))
    """), {"ids": ids})).fetchall()}
    out = []
    for r in ranked[:k]:
        m = meta.get(r["id"])
        out.append({"id": r["id"], "date": _fmt_day(m.d if m else None),
                    "text": _clean_title(r["title"]), "src": r.get("source") or "",
                    "lang": (m.lang if m else None), "url": (m.url if m else None) or ""})
    await _i18n.attach_en(db, out, "text")
    return out



async def _fetch_article_urls(db, ids: list[str]) -> dict[str, str]:
    """Fetch published URLs for a list of article IDs. Returns {id: url}."""
    if not ids:
        return {}
    rows = (await db.execute(text("""
        SELECT id::text, url FROM articles WHERE id = ANY(CAST(:ids AS uuid[]))
    """), {"ids": ids})).fetchall()
    return {r.id: (r.url or "") for r in rows}

def build_briefing(prefs: dict[str, Any], posture: dict[str, Any],
                   ranked: list[dict[str, Any]], what_happened: list[dict[str, Any]],
                   wh: int, ao_en: str | None = None, ao_url: str = "") -> dict[str, Any]:
    M = posture.get("metrics", {})
    overall, ov_n = _overall_fav(posture)
    traj = M.get("stance_trajectory", {})
    direction = traj.get("direction")
    ao = M.get("attack_origination", {}).get("origin") or {}
    ao_title = _clean_title(ao_en or ao.get("title"))
    qsb = M.get("quote_selection_bias", {}).get("items", [])
    you_q = sum(i["quotes_principal"] for i in qsb)
    opp_q = sum(i["quotes_opposition"] for i in qsb)
    iss_meta = M.get("issue_ownership", {})
    iss = iss_meta.get("items", []) if iss_meta.get("confidence") in ("high", "medium") else []
    contested = [i for i in iss if i.get("verdict") == "contested"]
    owns = [i for i in iss if i.get("verdict") == "owns"]
    fff = M.get("friend_foe_fence", {})
    neg_signals = M.get("weighted_pressure", {}).get("negative_signals", 0)
    amps = M.get("attack_origination", {}).get("amplifiers", [])
    amp_count = len({a.get("outlet") for a in amps if a.get("outlet")})

    stance_word = ("favourable" if (overall or 0) >= 10 else
                   "mixed" if (overall or 0) > -10 else "adverse")
    top_r = ranked[0] if ranked else None
    top_title = _clean_title((top_r or {}).get("title_en") or (top_r or {}).get("title", "—"))

    # ── BOTTOM-LINE CARDS ─────────────────────────────────────────────────────
    ally_all = fff.get("ally", [])
    ally = [a for a in ally_all if a.get("n", 0) >= 2]
    if ally:
        a0 = ally[0]
        fav = a0['favourability']
        warmth = "strongly" if fav >= 20 else "consistently"
        support_v = f"{a0['outlet']} is running {warmth} positive for you — the clean place to land a win this week."
        support_id, support_url = None, ""
    elif top_r and (overall or 0) >= 0:
        support_v = f"{_LQ}{top_title}{_RQ} is your strongest story this window."
        support_id, support_url = top_r.get("id"), top_r.get("url", "")
    else:
        support_v = "No strong positive signal detected in coverage this window."
        support_id, support_url = None, ""

    if ao.get("title"):
        attack_v = f"{_LQ}{ao_title}{_RQ} — {ao.get('outlet', '')}."
        attack_id, attack_url = ao.get("article_id"), ao_url
    else:
        attack_v = "No concentrated attack line in the current window."
        attack_id, attack_url = None, ""

    steam_r = ranked[1] if len(ranked) > 1 else top_r
    if steam_r:
        steam_title = _clean_title(steam_r.get("title_en") or steam_r.get("title", ""))
        steam_v = f"{_LQ}{steam_title}{_RQ} is gathering traction — track it before it frames the narrative."
        steam_id, steam_url = steam_r.get("id"), steam_r.get("url", "")
    else:
        steam_v = "Not enough coverage to identify a gaining story."
        steam_id, steam_url = None, ""

    if contested:
        pressure_v = (f"You are contested on {contested[0]['topic'].title()} "
                      f"and the coverage there is not firmly yours. "
                      f"Resolve it before it becomes the week's dominant frame.")
        pressure_id, pressure_url = None, ""
    elif ao.get("title"):
        pressure_v = (f"The adverse thread from {ao.get('outlet', 'a hostile outlet')} is your live "
                      f"pressure point — one more outlet picking it up changes the week.")
        pressure_id, pressure_url = attack_id, attack_url
    else:
        pressure_v = "No live pressure point detected — stay on the front foot."
        pressure_id, pressure_url = None, ""

    bottom_line = [
        {"k": "Supporting You", "v": support_v, "article_id": support_id, "url": support_url},
        {"k": "Attacking You",  "v": attack_v,  "article_id": attack_id,  "url": attack_url},
        {"k": "Gaining Steam",  "v": steam_v,   "article_id": steam_id,   "url": steam_url},
        {"k": "Pressure Point", "v": pressure_v, "article_id": pressure_id, "url": pressure_url},
    ]

    src_pool = ranked[:6]

    def _src(r: dict[str, Any]) -> dict[str, Any]:
        return {"id": r["id"], "title": _clean_title(r.get("title_en") or r["title"]),
                "source": r.get("source", ""), "url": r.get("url", "")}

    # ── HIGHLIGHTS OF THE DAY ───────────────────────────────────────────────
    coverage_strength = ("clearly" if abs(overall or 0) >= 15 else
                         "broadly" if abs(overall or 0) >= 5 else "marginally")
    h: list[str] = [
        f"Your coverage over the {_window_label(wh)} reads {coverage_strength} {stance_word}.",
    ]
    if top_title and top_title != "—":
        h.append(f"The story drawing the most attention in your window is {_LQ}{top_title}{_RQ} — "
                 f"it is setting the tone for how your work is being read.")
    if you_q or opp_q:
        if you_q >= max(1, opp_q):
            h.append("You are being quoted more than the opposition, "
                     "which means your voice is carrying the coverage — "
                     "not someone else speaking for you.")
        else:
            h.append("The opposition is getting more quote space than you — "
                     "the outlets are letting them shape the narrative.")
    if ao.get("title"):
        spread_note = (f"spread to {amp_count} outlets" if amp_count > 1
                       else "not yet spread beyond its origin")
        spread_desc = ("and has already spread to multiple outlets" if amp_count > 1
                       else "but has not yet spread beyond its origin")
        h.append(f"There is one adverse thread to watch: {_LQ}{ao_title}{_RQ} from "
                 f"{ao.get('outlet', 'an outlet')} — it is the live hostile line, "
                 f"{spread_desc}.")
    if owns:
        h.append(f"You have a clear ownership advantage on {owns[0]['topic'].title()}, "
                 f"which is a genuine asset to protect and amplify this week.")
    if contested:
        h.append(f"The front that needs your attention is {contested[0]['topic'].title()} — "
                 f"the coverage there is genuinely split, "
                 f"and silence will cost you ground.")
    elif direction:
        dir_note = ("that is the signal to press harder" if direction == "rising"
                    else "monitor it through the week")
        h.append(f"The trajectory of your coverage is currently {direction} — {dir_note}.")
    highlights = " ".join(h[:6])

    # ── WHY IT MATTERS ──────────────────────────────────────────────────────────
    wim: list[str] = []
    if contested:
        wim.append(f"The {contested[0]['topic'].title()} front is the one that will define whether "
                   f"this week holds or slips — it is contested territory, not firmly yours, "
                   f"and contested narratives move fast once they settle.")
    else:
        wim.append("With no open contested front, your position this week is about protecting "
                   "ground already held, not recovering lost territory.")
    if ao.get("title"):
        wim.append(f"The adverse thread from {ao.get('outlet', 'the hostile outlet')} matters less "
                   f"right now for its volume and more for its potential to spread — a single "
                   f"second-tier pickup changes the calculus entirely.")
    if direction in ("rising", "cooling"):
        dir_msg = ("momentum is building on your side" if direction == "rising"
                   else "the window's energy is softening — manage it before it "
                        "becomes a story in itself")
        wim.append(f"The trajectory signal says {dir_msg}.")
    if overall is not None and overall >= 10:
        wim.append("A favourable overall lean is not a reason to stop pushing — "
                   "it is the best time to land a win, when the press is already running with you.")
    elif overall is not None and overall <= -10:
        wim.append("An adverse lean means you are playing defence, but defence has a game plan: "
                   "dominate the quotes, control the contested front, and make the hostile outlet "
                   "the story rather than letting it write yours.")
    why_it_matters = " ".join(wim[:4])

    # ── THE OTHER SIDE ───────────────────────────────────────────────────────────
    concentration = ("concentrated around one outlet" if ao.get("outlet")
                     else "scattered across sources")
    volume_word = "heavy" if neg_signals >= 10 else "moderate" if neg_signals >= 4 else "limited"
    os_: list[str] = [
        f"The case for not over-reading this: the adverse signal volume is {volume_word}, "
        f"and it is {concentration} rather than a coordinated press movement.",
    ]
    if ao.get("outlet"):
        os_.append(f"Strip {ao.get('outlet')} out of the calculation and the week's picture "
                   f"looks significantly cleaner — "
                   f"one hostile outlet does not make a hostile press.")
    os_.append("What would actually flip the call from manageable to serious: a second independent "
               "outlet picking up the adverse line and running with it as its own story — "
               "that has not happened yet.")
    if ov_n < 8:
        os_.append("The signal pool is still thin, which means this read could "
                   "shift materially with even one new piece of coverage — "
                   "treat it as directional, not final.")
    else:
        os_.append("The signal pool is broad enough to trust the direction, "
                   "even if the exact numbers will move.")
    other_side = " ".join(os_[:4])

    # ── WHAT'S NEXT ─────────────────────────────────────────────────────────────
    conf = traj.get("confidence", "low")
    wn: list[str] = []
    if ao.get("title"):
        wn.append(f"The most important thing to watch is whether {_LQ}{ao_title}{_RQ} gets "
                  f"picked up by a second major outlet — that is the single event that moves "
                  f"it from a contained thread to a story requiring a public response.")
    else:
        wn.append("With no dominant adverse line in play, the watch this window is for any new "
                  "story that gets outsized amplification — the first outlet to run a new "
                  "frame often sets it.")
    if contested:
        wn.append(f"On the {contested[0]['topic'].title()} front, expect the contest to continue "
                  f"— the next development there will pull the overall lean one way or the other.")
    conf_note = ("enough signals are moving consistently to trust the direction"
                 if conf in ("high", "medium")
                 else "thin signal, so check it again at the next refresh before acting on it")
    wn.append(f"The trajectory is currently {direction or 'flat'}, with {conf} confidence "
              f"— {conf_note}.")
    if direction == "cooling":
        wn.append("A cooling trajectory typically stabilises before it reverses; "
                  "the key is to not chase it with reactive statements that extend the news cycle.")
    elif direction == "rising":
        wn.append("A rising trajectory is the time to go long — pitch stories, push the "
                  "owned fronts, and move the conversation while the press is receptive.")
    whats_next = {
        "text": " ".join(wn[:4]),
        "confidence": conf,
        "sources": [_src(r) for r in src_pool[:3]],
    }

    return {"briefing": {
        "bottomLine": bottom_line,
        "whatHappened": what_happened,
        "highlights": highlights,
        "highlightsSources": [_src(r) for r in src_pool],
        "whyItMatters": why_it_matters,
        "whyItMattersSources": [_src(r) for r in src_pool[:4]],
        "otherSide": other_side,
        "otherSideSources": [_src(r) for r in src_pool[:4]],
        "whatsNext": whats_next,
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
                     posture_wh: int = 72, relevance_wh: int = 48) -> dict[str, Any]:
    """Assemble the full Night Desk Home payload for the authenticated persona.

    Computes the posture bundle + relevance ONCE and reshapes into the three
    sections, so numbers are consistent across THE BRIEFING / PEOPLE TO WATCH /
    THE SIX. Honest + source-grounded throughout.
    """
    pid, pname = principal_of(prefs)
    posture = await compute_posture(db, prefs, window_hours=posture_wh, only=_HOME_METRICS)
    ranked = await score_relevant(db, prefs, window_hours=relevance_wh, limit=40)

    # Patch article URLs into ranked list and resolve the attack-origin URL.
    ao_o = posture.get("metrics", {}).get("attack_origination", {}).get("origin") or {}
    ao_id = ao_o.get("article_id")
    url_ids = [r["id"] for r in ranked[:10]] + ([ao_id] if ao_id else [])
    url_map = await _fetch_article_urls(db, list(dict.fromkeys(url_ids)))
    ranked = [{**r, "url": url_map.get(r["id"], "")} for r in ranked]
    ao_url = url_map.get(ao_id or "", "")

    wh_events = await _what_happened(db, ranked, k=4)
    await _i18n.attach_en(db, ranked[:5], "title")
    ao_t = ao_o.get("title")
    ao_en = (await _i18n.ensure_en(db, {ao_t})).get(ao_t) if (ao_t and not _i18n.is_english(ao_t)) else None
    briefing = build_briefing(prefs, posture, ranked, wh_events, relevance_wh, ao_en=ao_en, ao_url=ao_url)
    players_out = await build_players(db, prefs, posture_wh)
    six = await build_six_feeds(db, prefs, pid, pname, posture_wh)

    now = (await db.execute(text("SELECT analytics.now_sim() AS n"))).scalar()
    # SHARED CANONICAL MOOD — the ONE directed, intensity-weighted 3-day headline
    # mood Home / War Room / Report must all show identically. Its `fav` drives the
    # masthead headline number AND the Coverage Sentiment "now" figure so the two
    # never contradict; the waveform trajectory points stay as computed below.
    mood = await current_mood(db, pid)
    sentiment = await _sentiment_series(db, pid, posture_wh, mood["fav"])
    sentiment["label"] = mood["label"]

    parts = (pname or "").split()
    states = (prefs.get("regions") or {}).get("states") or []
    masthead = {
        "state": states[0] if states else None,
        "principal": pname,
        "first": parts[0] if parts else "",
        "last": " ".join(parts[1:]) if len(parts) > 1 else "",
        "displayName": display_name,
        "asOf": _fmt_asof(now),
        # Window, headline number, adverse/favourable label + confidence all come
        # from the shared current_mood so the masthead agrees with War Room / Report.
        "window": mood["window_label"],
        "overall": mood["fav"],
        "label": mood["label"],
        "confidence": mood["confidence"],
    }

    return {
        "personalized": True,
        "as_of": str(now),
        "masthead": masthead,
        "sentiment": sentiment,
        **briefing,        # -> "briefing"
        **players_out,     # -> "players" (+ optional "caveats")
        **six,             # -> "six"
        "caveats": _caveats(prefs, players_out.get("players", [])),
    }



_HTML_TAG_RE = re.compile(r"<[^>]+>")
# Leading breadcrumb nav some scrapers leave on the lead text: "Home |Telangana |…"
_BREADCRUMB_RE = re.compile(r"^(?:[\w&'.\-]+ *\| *)+")


def _clean_head(s: str | None) -> str:
    """Strip raw HTML and breadcrumb nav a scraper may have left in the text."""
    if not s:
        return ""
    s = _HTML_TAG_RE.sub(" ", s)
    s = _BREADCRUMB_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


async def sentiment_explain(db, pid: str, wh: int, limit: int = 5) -> dict[str, Any]:
    """Top +/- stories driving the sentiment number, each with a one-line why.
    Same population as the score (stances ABOUT the principal) ordered by
    contribution = POL x intensity, so it can never disagree with the headline.

    The English gloss is a clean *title* translation (never the breadcrumb-/HTML-
    polluted lead text), attached only to non-English headlines — an English
    headline already reads in the 'why' line, so a gloss would be redundant."""
    rows = (await db.execute(text(f"""
        SELECT a.id::text AS id, src.name AS source, st.stance,
               round((({POL}) * st.intensity)::numeric, 2) AS contrib,
               COALESCE(NULLIF(a.title, ''), NULLIF(a.lead_text_translated, ''), '') AS headline,
               a.language_detected AS lang,
               a.url AS url
          FROM article_entity_mentions m
          JOIN articles a ON a.id = m.article_id
          JOIN sources src ON src.id = a.source_id
          JOIN article_stances st ON st.article_id = a.id
         WHERE m.entity_id = CAST(:pid AS uuid)
           AND st.actor_entity_id = CAST(:pid AS uuid)
           AND st.intensity IS NOT NULL
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
           AND a.collected_at <= analytics.now_sim()
           AND {_BODY_PRESENT}
    """), {"pid": pid, "wh": wh})).fetchall()

    # Pick the strongest movers first so we only pay to translate the few shown.
    pos_rows = sorted((r for r in rows if float(r.contrib) > 0),
                      key=lambda r: -float(r.contrib))[:limit]
    neg_rows = sorted((r for r in rows if float(r.contrib) < 0),
                      key=lambda r: float(r.contrib))[:limit]

    # Translate only the non-English titles among the rows we'll actually show.
    heads = {r.id: _clean_head(r.headline) for r in (pos_rows + neg_rows)}
    non_en = {h for h in heads.values() if h and not _i18n.is_english(h)}
    en_map = await _i18n.ensure_en(db, non_en) if non_en else {}

    def _item(r):
        positive = float(r.contrib) > 0
        verb = "praised" if positive else "criticised"
        head = heads.get(r.id, "")
        head_en = "" if (not head or _i18n.is_english(head)) else (en_map.get(head) or "")
        return {"article_id": r.id, "source": r.source, "stance": r.stance,
                "contribution": float(r.contrib), "headline": head[:140],
                "headline_en": head_en[:140], "lang": (r.lang or ""),
                "url": (r.url or ""),
                "why": f"{r.source} {verb} you — {head[:90]}"}

    return {"top_positive": [_item(r) for r in pos_rows],
            "top_negative": [_item(r) for r in neg_rows]}
