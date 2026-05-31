"""Generic per-user relevance core.

Given a user's saved prefs, score recent articles for how relevant they are to
THAT user. Persona-agnostic: the SQL has ZERO hardcoded names — all persona
specifics come from prefs. Proven in scripts/eval/relevance_eval.py
(3 personas → 10/10 about-precision, 0 cross-overlap, 8/9 hand-labeled golden).

DESIGN NOTE — why the heavy lifting is split:
  The candidate SQL is kept simple + plan-stable (a clever salience-first
  WHERE flipped Postgres into a 15-minute plan). The SQL returns the signals
  (entity tier, title-hit, geo-hit) cheaply; the *salience-first* re-rank — a
  watchlist entity in the HEADLINE is "about" them, a bare body mention isn't —
  is applied in Python on the top candidates (instant, plan-safe).

Signals (freshness-decayed, 48h half-life):
  subject ×6 / core ×3 / context(ext) ×1.5-if-on-turf · title-salience +2 ·
  keyword +1.5 · geo +1.5/-0.7 · topic ±0.5/-2 · admin headline -4.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

HALF_LIFE_H = 48.0
NOISE = [
    "%answer key%", "%bank holiday%", "%full list%", "%horoscope%", "%admit card%",
    "%exam date%", "%recruitment%", "%result 2026%", "%how to download%", "%rashifal%",
    "%schedule today%", "%live streaming%",
]


# Generic political words that must NEVER become a standalone match pattern.
# A bare alias like "Party" or "Government" would otherwise match every
# "… Party" / "… Government" entity in the corpus (e.g. the Mexican
# "Institutional Revolutionary Party"), poisoning relevance with cross-persona
# junk. Real identifiers are multi-word ("aam aadmi party") or specific acronyms
# ("aap", "bjp") and are unaffected — only the bare generic token is dropped.
_GENERIC_TERMS = frozenset({
    "party", "government", "govt", "govt.", "minister", "ministry", "cabinet",
    "leader", "leaders", "opposition", "ruling", "coalition", "alliance", "front",
    "assembly", "parliament", "lok sabha", "rajya sabha", "house", "council",
    "state", "states", "national", "central", "centre", "union", "federal",
    "president", "vice president", "secretary", "spokesperson", "spokesman",
    "chief", "deputy", "office", "the party", "mla", "mlas", "mp", "mps",
    "candidate", "leadership", "high command",
})


def _pats(names: list[str | None]) -> list[str]:
    out: set[str] = set()
    for n in names:
        if not n:
            continue
        t = n.strip().lower()
        if len(t) >= 3 and t not in _GENERIC_TERMS:
            out.add(f"%{t}%")
    return sorted(out) or ["__nomatch__"]


async def build_terms(db, prefs: dict[str, Any]) -> dict[str, Any]:
    """Turn a user's prefs into match-term arrays (alias-expanded, tiered)."""
    wl = prefs.get("watchlist") or {}
    meta = wl.get("entity_meta") or []
    ids = [m["id"] for m in meta if m.get("id")]

    alias: dict[str, tuple[str, list[str]]] = {}
    if ids:
        rows = (await db.execute(text("""
            SELECT id::text AS id, canonical_name, aliases
              FROM public.entity_dictionary WHERE id = ANY(CAST(:ids AS uuid[]))
        """), {"ids": ids})).fetchall()
        alias = {r.id: (r.canonical_name, list(r.aliases) if r.aliases else []) for r in rows}

    psid = prefs.get("primary_subject_id")
    psname = (prefs.get("primary_subject_meta") or {}).get("name")

    subj: list[str] = []
    core: list[str] = []
    ext: list[str] = []
    for m in meta:
        terms = [m.get("name")]
        cn, al = alias.get(m.get("id"), (None, []))
        if cn:
            terms.append(cn)
        terms += [a for a in al if a and len(a) >= 4]
        ps = _pats(terms)
        is_subj = (m.get("id") and m.get("id") == psid) or (psname and m.get("name") == psname)
        if is_subj:
            subj += ps
        elif m.get("tier") == "extended":
            ext += ps
        else:
            core += ps
    if psname and (not subj or subj == ["__nomatch__"]):
        subj = _pats([psname])

    regions = prefs.get("regions") or {}
    geo = _pats((regions.get("states") or []) + (regions.get("districts") or []))
    kw = _pats(wl.get("keywords") or [])
    topics = prefs.get("topics") or {}

    return {
        "subj": sorted(set(subj)) or ["__nomatch__"],
        "wlc": sorted(set(core)) or ["__nomatch__"],
        "wle": sorted(set(ext)) or ["__nomatch__"],
        "geo": geo,
        "kw": kw,
        "noise": NOISE,
        "inc": topics.get("include") or [],
        "exc": topics.get("exclude") or [],
    }


# Plan-stable candidate query (the proven ~2.5s shape). Salience-first
# re-ranking happens in Python below — do NOT fold it into this WHERE.
_SQL = """
WITH win AS (
  SELECT a.id, a.title, a.summary_executive, a.topic_category, a.geo_primary,
         a.collected_at, s.name AS src, a.entities_extracted, lower(a.title) AS lt
    FROM public.articles a
    JOIN public.sources s ON s.id = a.source_id
   WHERE a.collected_at >= analytics.now_sim() - INTERVAL '{wh} hours'
     AND a.collected_at <= analytics.now_sim()
     AND a.entities_extracted IS NOT NULL AND jsonb_typeof(a.entities_extracted) = 'array'
     AND a.title IS NOT NULL AND length(a.title) >= 16
),
ent AS (
  SELECT w.id, lower(e->>'name') AS en, COALESCE((e->>'confidence')::float, 0) AS conf
    FROM win w CROSS JOIN LATERAL jsonb_array_elements(w.entities_extracted) e
),
em AS (
  SELECT id,
    max(CASE WHEN en LIKE ANY(CAST(:subj AS text[])) THEN 3
             WHEN en LIKE ANY(CAST(:wlc AS text[])) THEN 2
             WHEN en LIKE ANY(CAST(:wle AS text[])) THEN 1 ELSE 0 END) AS ent_tier,
    (array_agg(en ORDER BY conf DESC) FILTER (
        WHERE en LIKE ANY(CAST(:subj AS text[])) OR en LIKE ANY(CAST(:wlc AS text[]))
           OR en LIKE ANY(CAST(:wle AS text[]))))[1] AS matched
  FROM ent GROUP BY id
),
sc AS (
  SELECT w.id, w.title, w.summary_executive, w.topic_category, w.geo_primary, w.src, w.collected_at,
    COALESCE(em.ent_tier, 0) AS ent_tier, em.matched,
    (CASE WHEN w.lt LIKE ANY(CAST(:subj AS text[])) OR w.lt LIKE ANY(CAST(:wlc AS text[])) THEN 1 ELSE 0 END) AS tc,
    (CASE WHEN w.geo_primary ILIKE ANY(CAST(:geo AS text[])) THEN 1 ELSE 0 END) AS geo_hit,
    (CASE WHEN w.lt LIKE ANY(CAST(:kw AS text[])) THEN 1 ELSE 0 END) AS kw_hit,
    (CASE WHEN w.lt LIKE ANY(CAST(:noise AS text[])) THEN 1 ELSE 0 END) AS noise
  FROM win w LEFT JOIN em ON em.id = w.id
)
SELECT id, title, summary_executive, topic_category, geo_primary, src, collected_at,
       ent_tier, matched, tc, geo_hit,
  ROUND((
     (CASE WHEN ent_tier=3 THEN 6.0 WHEN ent_tier=2 THEN 3.0
           WHEN ent_tier=1 AND geo_hit=1 THEN 1.5 ELSE 0 END)
   + tc*2.0 + kw_hit*1.5
   + (CASE WHEN geo_hit=1 AND (ent_tier>=2 OR kw_hit=1 OR tc=1) THEN 1.5
           WHEN geo_hit=1 THEN 0.7 ELSE 0 END)
   + (CASE WHEN topic_category = ANY(CAST(:exc AS text[])) THEN -2.0 ELSE 0 END)
   + (CASE WHEN topic_category = ANY(CAST(:inc AS text[])) THEN 0.5 ELSE 0 END)
   + noise * -4.0
  ) * EXP(-EXTRACT(EPOCH FROM (analytics.now_sim() - collected_at)) / 3600.0 / {hl})
  ::numeric, 2) AS score
FROM sc
WHERE ent_tier >= 2 OR tc = 1 OR kw_hit = 1
   OR (ent_tier = 1 AND geo_hit = 1)
   OR geo_hit = 1
ORDER BY score DESC
LIMIT :lim
"""


async def score_relevant(db, prefs: dict[str, Any], window_hours: int = 48, limit: int = 60) -> list[dict[str, Any]]:
    terms = await build_terms(db, prefs)
    sql = _SQL.format(wh=int(window_hours), hl=HALF_LIFE_H)
    rows = (await db.execute(text(sql), {**terms, "lim": int(limit)})).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        score = float(r.score or 0)
        tc = int(r.tc or 0)
        geo = int(r.geo_hit or 0)
        tier = int(r.ent_tier or 0)
        # SALIENCE-FIRST re-rank: a core/subject entity that is only PRESENT in
        # the body (passing mention) and off-turf is not really "about" the user
        # → demote hard so it can never headline (kills the "TN-CM-meets-Modi
        # tagged with a passing Telangana figure" leak).
        if tier >= 2 and not tc and not geo:
            score = round(score * 0.15, 2)
        out.append({
            "id": str(r.id), "title": r.title, "summary": r.summary_executive,
            "topic": r.topic_category, "geo": r.geo_primary, "source": r.src,
            "matched": r.matched, "ent_tier": tier, "tc": tc, "geo_hit": geo,
            "score": score,
        })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out
