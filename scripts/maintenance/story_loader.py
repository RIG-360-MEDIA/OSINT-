#!/usr/bin/env python3
"""
story_loader.py — CORE loader: persist a clustering run into analytics.story_* (shadow mode).

Per loader-enrichment-spec-2026-06-02 §2 (CORE ONLY — no enrichment; that is gated on the
§7.1 round-trip going green). Consumes the clustering run's two CSVs:
  * MEMBERS = cluster_job_7 OUT (article_id, cluster_id, source_id)  — the partition
  * EDGES   = cluster_job_7 EDGES_OUT (a_id, b_id, score)            — scorer-high edges
computes per-story rollups from SOURCE ROWS (no LLM, no invented numbers), assigns STABLE
story_ids (greedy Jaccard vs the prior run), and UPSERTs:
  analytics.story_clusters  ->  story_cluster_members (FK, ON DELETE CASCADE)  ->  story_edges

§2b + RESCUE (build-launch STEP 0): before ID-stability the loader flags template-family blobs
(src>=FLAG_MIN_SRC AND core<CORE_T AND tcoh<TCOH_T) and runs the sub-cluster rescue
(story_rescue.rescue) — re-splitting ONLY flagged blobs and surfacing buried real stories as
first-class clusters. Because the split happens BEFORE ID-assignment, rescued sub-stories ride
the SAME greedy-Jaccard stable-id path (dominant successor inherits the prior id, others get new
stable ids). Rescue is core-only by default (the tcoh-only path re-admits template-blobs — see
the 2026-06-02 15-tcoh spot-check); src floor locked at 12.

Shadow semantics: writes provisional=TRUE, stamps run_id + algo_version, touches NOTHING the
product reads (event_clusters / story_threads untouched — this is purely additive).
Idempotent on an unchanged window: same partition -> Jaccard 1.0 -> same story_ids.
STORY_TBL_SUFFIX writes/reads suffixed throwaway tables (safe testing — never the live partition).

Env: MEMBERS, EDGES, ALGO_VERSION, PROVISIONAL(=1), JACCARD_MIN(=0.5), TOPK_ENT(=6),
     STORY_TBL_SUFFIX(=''), RESCUE_ON(=1), RESCUE_PATH(=/tmp/story_rescue.py),
     RESCUE_MIN_SRC(=12), RESCUE_MIN_SZ(=10), RESCUE_RES(=4.0), RESCUE_ALLOW_TCOH(=0),
     FLAG_MIN_SRC(=25), CORE_T(=0.45), TCOH_T(=0.35), AB_DSN/DATABASE_URL_SYNC.
NOT populated here (enrichment, §3): event_type, subject_locations, stance_distribution,
sentiment, representative_quote — left NULL until the core is validated.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import time
import uuid
from collections import Counter, defaultdict

import psycopg2
from psycopg2.extras import Json, execute_values

MEMBERS = os.environ["MEMBERS"]
EDGES = os.environ["EDGES"]
ALGO_VERSION = os.environ.get("ALGO_VERSION", "cluster_job_7/pf-v1/tg-v3/leiden-res1.0/rescue-v1")
PROVISIONAL = os.environ.get("PROVISIONAL", "1") == "1"
JACCARD_MIN = float(os.environ.get("JACCARD_MIN", "0.5"))
TOPK_ENT = int(os.environ.get("TOPK_ENT", "6"))
TBL = os.environ.get("STORY_TBL_SUFFIX", "")            # safe-test: suffixed throwaway tables
RESCUE_ON = os.environ.get("RESCUE_ON", "1") == "1"      # §2b sub-cluster rescue (STEP 0)
RESCUE_PATH = os.environ.get("RESCUE_PATH", "/tmp/story_rescue.py")
RESCUE_MIN_SRC = int(os.environ.get("RESCUE_MIN_SRC", "12"))   # LOCKED floor (core-only, src>=12)
RESCUE_MIN_SZ = int(os.environ.get("RESCUE_MIN_SZ", "10"))
RESCUE_RES = float(os.environ.get("RESCUE_RES", "4.0"))
RESCUE_ALLOW_TCOH = os.environ.get("RESCUE_ALLOW_TCOH", "0") == "1"  # LOCKED off (re-admits template-blobs)
FLAG_MIN_SRC = int(os.environ.get("FLAG_MIN_SRC", "25"))      # §2b flag floor (locked 2026-06-02 contract)
CORE_T = float(os.environ.get("CORE_T", "0.45"))
TCOH_T = float(os.environ.get("TCOH_T", "0.35"))
TCOH_CAP = int(os.environ.get("TCOH_CAP", "1000"))  # tcoh-spare void above this size (broad topic -> flag + unpack)


def reprint_key(title, lead):  # wire-dedup key (same as the digest): same body => one report
    lead = (lead or "").strip()
    base = lead if len(lead) >= 60 else (title or "")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", base.lower()).split())[:120]


def rep_pick(arts):  # representative = median-length clean English title (avoids clickbait/stubs)
    en = sorted([a for a in arts if a["lang"] == "en" and a["title"] and 25 <= len(a["title"]) <= 95],
                key=lambda a: len(a["title"]))
    if not en:
        en = sorted([a for a in arts if a["title"]], key=lambda a: len(a["title"] or ""))
    if not en:
        return None, None
    pick = en[len(en) // 2]
    return pick["id"], pick["title"][:300]


def _require_igraph() -> bool:
    """Fail loud if igraph is absent — the §2b rescue's community split would otherwise fall back
    to networkx Louvain (the OOM-prone path AND a different clustering than validated). Refuse to
    run, don't silently degrade."""
    try:
        import igraph  # noqa: F401
        return True
    except ImportError:
        sys.stderr.write("FATAL: python-igraph not importable — refusing to run. The §2b rescue "
                         "would fall back to networkx Louvain (OOM-prone + a different clustering "
                         "than validated). Install igraph+leidenalg (baked into the image). Aborting.\n")
        return False


def main() -> int:
    if not _require_igraph():  # rescue() always re-clusters flagged blobs (igraph) regardless of RESCUE_ON
        return 2
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    run_id = int(time.time())
    cur.execute("SELECT now()")
    now_ts = cur.fetchone()[0]

    # ---- load the run's two CSVs into temp tables ----
    cur.execute("CREATE TEMP TABLE _m(article_id uuid, cluster_id uuid, source_id uuid)")
    with open(MEMBERS) as f:
        cur.copy_expert("COPY _m FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    cur.execute("CREATE TEMP TABLE _e(a_id uuid, b_id uuid, score numeric)")
    with open(EDGES) as f:
        cur.copy_expert("COPY _e FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    cur.execute("SELECT count(*) FROM _m")
    n_members = cur.fetchone()[0]

    # ---- per-article rollup fields (collected flat; clusters built AFTER the rescue) ----
    cur.execute("""
        SELECT m.cluster_id, m.article_id, m.source_id, a.title,
               coalesce(a.language_detected,'?'), a.geo_primary, rtrim(a.source_country),
               a.topic_category, a.collected_at, left(a.lead_text_original, 200),
               (SELECT array_agg(n) FROM (
                  SELECT lower(e->>'name') n FROM jsonb_array_elements(coalesce(a.entities_extracted,'[]'::jsonb)) e
                  WHERE e->>'name' IS NOT NULL
                  ORDER BY (e->>'prominence')::float DESC NULLS LAST LIMIT 3) t) AS ents
        FROM _m m JOIN articles a ON a.id = m.article_id
    """)
    rows = []
    art_ents: dict[str, list] = {}
    art_titles: dict[str, str] = {}
    src_of: dict[str, str | None] = {}
    init_members: dict[str, list] = defaultdict(list)
    for cid, aid, sid, title, lang, geo, country, topic, coll, lead, ents in cur:
        cid, aid = str(cid), str(aid)
        sids = str(sid) if sid else None
        rows.append((cid, aid, sids, title, lang, geo, country, topic, coll, lead, ents or []))
        art_ents[aid] = ents or []
        art_titles[aid] = title or ""
        src_of[aid] = sids
        init_members[cid].append(aid)

    # ---- edges: order a<b, dedup keep max, per-article attach_score = best incident edge ----
    cur.execute("SELECT a_id, b_id, score FROM _e")
    edge_best: dict[tuple, float] = {}
    attach: dict[str, float] = defaultdict(float)
    for a, b, s in cur.fetchall():
        a, b, s = str(a), str(b), float(s)
        if a == b:
            continue
        key = (a, b) if a < b else (b, a)
        if s > edge_best.get(key, -1.0):
            edge_best[key] = s
        attach[a] = max(attach[a], s)
        attach[b] = max(attach[b], s)

    # ---- §2b flag + sub-cluster rescue (STEP 0); BEFORE id-stability so rescued sub-stories
    #      are first-class clusters that ride the greedy-Jaccard stable-id path ----
    _spec = importlib.util.spec_from_file_location("story_rescue", RESCUE_PATH)
    story_rescue = importlib.util.module_from_spec(_spec)
    sys.modules["story_rescue"] = story_rescue
    _spec.loader.exec_module(story_rescue)
    final_of, s2b_of, rstats = story_rescue.rescue(
        init_members, edge_best, art_ents, art_titles, src_of,
        res=RESCUE_RES, min_sz_sub=RESCUE_MIN_SZ,
        min_src_sub=(RESCUE_MIN_SRC if RESCUE_ON else 10 ** 9),
        core_t=CORE_T, tcoh_t=TCOH_T, allow_tcoh=RESCUE_ALLOW_TCOH, flag_min_src=FLAG_MIN_SRC,
        tcoh_cap=TCOH_CAP)

    # ---- build clusters keyed by FINAL cluster id (rescued subs split out as 'cid::rN') ----
    cl: dict[str, dict] = defaultdict(lambda: {
        "arts": [], "src": set(), "langs": Counter(), "geos": Counter(),
        "countries": Counter(), "topics": Counter(), "ents": Counter(),
        "first": None, "last": None, "by_key": defaultdict(list)})
    as_of = None
    for cid0, aid, sids, title, lang, geo, country, topic, coll, lead, ents in rows:
        d = cl[final_of.get(aid, cid0)]
        d["arts"].append({"id": aid, "title": title, "lang": lang, "src": sids})
        if sids:
            d["src"].add(sids)
        d["langs"][lang] += 1
        if geo:
            d["geos"][geo] += 1
        if country:
            d["countries"][country] += 1
        if topic:
            d["topics"][topic] += 1
        for e in ents:
            if e:
                d["ents"][e] += 1
        if coll:
            d["first"] = coll if d["first"] is None else min(d["first"], coll)
            d["last"] = coll if d["last"] is None else max(d["last"], coll)
            as_of = coll if as_of is None else max(as_of, coll)
        d["by_key"][reprint_key(title, lead)].append(aid)
    as_of = as_of or now_ts

    # ---- ID stability: greedy best-Jaccard to the prior run; each prior id reused once ----
    cur.execute(f"SELECT article_id, story_id FROM analytics.story_cluster_members{TBL}")
    prior_of = {str(a): str(s) for a, s in cur.fetchall()}
    prior_size = Counter(prior_of.values())
    cand = []  # (jaccard, cluster_id, prior_story_id)
    for cid, d in cl.items():
        ids = [a["id"] for a in d["arts"]]
        for psid, o in Counter(prior_of[a] for a in ids if a in prior_of).items():
            cand.append((o / (len(ids) + prior_size[psid] - o), cid, psid))
    cand.sort(reverse=True)
    assigned, used = {}, set()
    for j, cid, psid in cand:
        if j >= JACCARD_MIN and cid not in assigned and psid not in used:
            assigned[cid], _ = psid, used.add(psid)
    story_id_of = {cid: assigned.get(cid) or str(uuid.uuid4()) for cid in cl}
    reused = len(used)

    # ---- build rows ----
    cluster_rows, member_rows = [], []
    for cid, d in cl.items():
        sid_story = story_id_of[cid]
        n, srcn = len(d["arts"]), len(d["src"])
        uniq_bodies = len(d["by_key"])
        indep = min(srcn, uniq_bodies) if srcn else uniq_bodies
        rep_id, rep_title = rep_pick(d["arts"])
        region = d["geos"].most_common(1)[0][0] if d["geos"] else None
        country = d["countries"].most_common(1)[0][0] if d["countries"] else None
        topic = d["topics"].most_common(1)[0][0] if d["topics"] else None
        s2 = s2b_of.get(cid, {})
        rescued_from_sid = story_id_of.get(s2["rescued_from"]) if s2.get("rescued_from") else None
        cluster_rows.append((
            sid_story, run_id, ALGO_VERSION, PROVISIONAL,
            d["first"] or as_of, d["last"] or as_of, as_of, n, srcn, indep,
            region, country, topic, Json(dict(d["ents"].most_common(TOPK_ENT))),
            Json(dict(d["langs"])), indep, rep_id, rep_title,
            s2.get("core"), s2.get("tcoh"), bool(s2.get("is_tf")), rescued_from_sid))
        canon = {sorted(ids)[0] for ids in d["by_key"].values()}  # one canonical per wire-copy set
        for a in d["arts"]:
            aid = a["id"]
            member_rows.append((aid, sid_story, a["src"], aid == rep_id, aid in canon,
                                attach.get(aid), PROVISIONAL, run_id))

    # ---- write: clusters -> members -> edges (FK order), one transaction ----
    execute_values(cur, f"""
        INSERT INTO analytics.story_clusters{TBL}
          (story_id, run_id, algo_version, provisional, first_seen_at, last_seen_at, as_of,
           article_count, source_count, independent_source_count, subject_region, subject_country,
           topic, primary_entities, languages, importance_score, representative_article_id,
           representative_title, entity_core_cov, title_cohesion, is_template_family,
           rescued_from_story_id)
        VALUES %s
        ON CONFLICT (story_id) DO UPDATE SET
          run_id=EXCLUDED.run_id, algo_version=EXCLUDED.algo_version, provisional=EXCLUDED.provisional,
          first_seen_at=LEAST(analytics.story_clusters{TBL}.first_seen_at, EXCLUDED.first_seen_at),
          last_seen_at=GREATEST(analytics.story_clusters{TBL}.last_seen_at, EXCLUDED.last_seen_at),
          as_of=EXCLUDED.as_of, article_count=EXCLUDED.article_count, source_count=EXCLUDED.source_count,
          independent_source_count=EXCLUDED.independent_source_count, subject_region=EXCLUDED.subject_region,
          subject_country=EXCLUDED.subject_country, topic=EXCLUDED.topic,
          primary_entities=EXCLUDED.primary_entities, languages=EXCLUDED.languages,
          importance_score=EXCLUDED.importance_score,
          representative_article_id=EXCLUDED.representative_article_id,
          representative_title=EXCLUDED.representative_title,
          entity_core_cov=EXCLUDED.entity_core_cov, title_cohesion=EXCLUDED.title_cohesion,
          is_template_family=EXCLUDED.is_template_family,
          rescued_from_story_id=EXCLUDED.rescued_from_story_id, updated_at=now()
    """, cluster_rows, page_size=2000)

    execute_values(cur, f"""
        INSERT INTO analytics.story_cluster_members{TBL}
          (article_id, story_id, source_id, is_representative, is_canonical, attach_score, provisional, run_id)
        VALUES %s
        ON CONFLICT (article_id) DO UPDATE SET
          story_id=EXCLUDED.story_id, source_id=EXCLUDED.source_id,
          is_representative=EXCLUDED.is_representative, is_canonical=EXCLUDED.is_canonical,
          attach_score=EXCLUDED.attach_score, provisional=EXCLUDED.provisional,
          run_id=EXCLUDED.run_id, added_at=now()
    """, member_rows, page_size=5000)

    edge_rows = [(a, b, s, "scorer-high", run_id) for (a, b), s in edge_best.items()]
    if edge_rows:
        execute_values(cur, f"""
            INSERT INTO analytics.story_edges{TBL} (article_a, article_b, score, decided_by, run_id)
            VALUES %s
            ON CONFLICT (article_a, article_b) DO UPDATE SET
              score=EXCLUDED.score, decided_by=EXCLUDED.decided_by, run_id=EXCLUDED.run_id, created_at=now()
        """, edge_rows, page_size=5000)

    # ---- orphan cleanup: provisional stories left member-less by a changed re-run ----
    cur.execute(f"""DELETE FROM analytics.story_clusters{TBL} c WHERE c.provisional AND NOT EXISTS
                   (SELECT 1 FROM analytics.story_cluster_members{TBL} m WHERE m.story_id=c.story_id)""")
    orphans = cur.rowcount
    conn.commit()

    cur.execute(f"""SELECT count(*), count(*) FILTER (WHERE article_count>1),
                          count(*) FILTER (WHERE independent_source_count>=3),
                          count(*) FILTER (WHERE is_template_family),
                          count(*) FILTER (WHERE rescued_from_story_id IS NOT NULL)
                   FROM analytics.story_clusters{TBL}""")
    tot, multi, surfaced, flagged, rescued = cur.fetchone()
    cur.execute(f"SELECT count(*) FROM analytics.story_cluster_members{TBL}")
    mem = cur.fetchone()[0]
    cur.execute(f"SELECT count(*) FROM analytics.story_edges{TBL}")
    eg = cur.fetchone()[0]
    conn.close()
    sys.stderr.write(
        f"LOADED run_id={run_id} algo={ALGO_VERSION} provisional={PROVISIONAL} tbl=story_*{TBL}\n"
        f"  partition: {n_members} member-rows in CSV -> {len(cl)} clusters "
        f"(rescue: flagged={rstats['flagged']} rescued={rstats['rescued']} dry={rstats['dry']})\n"
        f"  story_ids: {reused} reused (Jaccard>={JACCARD_MIN}) + {len(cl)-reused} new; orphans removed={orphans}\n"
        f"  story_clusters={tot} (multi-article={multi}, surfaced>=3indep={surfaced}, "
        f"template-family={flagged}, rescued={rescued})  members={mem}  edges={eg}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
