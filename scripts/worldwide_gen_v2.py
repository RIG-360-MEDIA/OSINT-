"""Worldwide generation v2 (2026-07-06) — the shippable recipe from the investigation.

  run-scoped article-native brief  ->  braided-Atlantic writer (gpt-oss-120b)
  ->  strong verifier (token-fixed)  ->  repair-or-hold gate  ->  story_generated_v8 UPSERT

KEY FIXES vs the old worldwide_gen_live.py path:
  * brief members are scoped to the cluster's run_id (kills cross-run pollution)
  * brief built from the LIVE per-article layer, not the stale STEP-3 rollups
  * verifier gets enough tokens to emit its JSON (was token-starved -> verdict=None)
  * repair-or-hold gate: fail -> repair once -> re-verify -> HELD if still failing

DRY-RUN by default (prints what it WOULD write). Pass --write to UPSERT.
Usage: python worldwide_gen_v2.py [--write] [--limit N]
"""
import asyncio, json, os, re, sys, hashlib
import httpx
from sqlalchemy import text
from backend.database import get_db
import backend.nlp.groq_client as gc

WRITE = "--write" in sys.argv
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 3

_CKEYS = list(gc._CEREBRAS_KEYS)
_CK = {"i": 0}
URL = "https://api.cerebras.ai/v1/chat/completions"
MODEL = "gpt-oss-120b"

# ---------- prompts (the winning braided-Atlantic recipe) ----------
PROMPT_D = ("You are an explainer journalist for Rig Wire, writing in The Atlantic's long-form voice: narrative, "
 "confident, builds understanding as it goes, treats the reader as smart but new to the subject. Write ONE "
 "long-read a total newcomer can follow and enjoy.\n\n"
 "FACTS ARE FROZEN. Every number, date, quote, name, market/company, and specific event MUST come from the BRIEF. "
 "If it is not in the brief, it does not exist. Your freedom is ONLY to EXPLAIN what the brief's facts mean - "
 "define a term, say in general what a named entity does, explain in general why a fact matters - woven in as you "
 "go, never adding new information. FORBIDDEN even as context: any market/company/person/number/date/quote not in "
 "the brief; any 'meanwhile X also...' aside; any invented scene detail or dialogue. DATE DISCIPLINE: use dates "
 "exactly as the brief gives them; if only a year or partial date is given, keep it vague ('later that year') and "
 "NEVER invent or CALCULATE a specific day/month (do not add a duration to a start date to guess an end date).\n\n"
 "VOICE & STRUCTURE - braided, not boxed: the spine is the chronology; move through the brief's events roughly in "
 "order, but BRAID in who's involved and why each moment mattered AT the moment it matters - never a separate "
 "'who'/'why' section. Open on a human newcomer hook; close on where things stand now (general framing only). Use "
 "DYNAMIC, story-specific ## subheads - a turn of phrase or a beat in the narrative - NEVER generic or numbered "
 "labels ('What Happened', 'Timeline', '1.', '2.'). Vary how you introduce quotes; avoid press-release cadence.\n\n"
 "LENGTH: aim for about 900 words when the brief has the material to support it (most multi-source stories do) - "
 "write 6-8 sections, each a developed narrative passage (never bullets), and develop each beat fully rather than "
 "summarizing it. This is a SOFT target: never pad, repeat, or invent a single fact to reach it - if the material "
 "is genuinely thin, a shorter complete article is correct. A faithful 600-word story beats a padded 900-word "
 "one.\n\n"
 'OUTPUT strict JSON only, body as ONE markdown string with ## subheads as the ONLY structural breaks - NO horizontal rules (---, ***, ___) and NO separator lines: '
 '{"headline":"","dek":"","body":"","key_facts":[],"pull_quote":{"text":"","speaker":"","source":""}}')

VERIFY = ("You are a fact-faithfulness checker for Rig Wire explainer articles. REPORTED facts (numbers, dates, "
 "quotes, names, events) MUST be supported by the BRIEF - flag any that are not, and flag any date the brief does "
 "not state (including dates computed by adding a duration to a start date). General background/explanation is "
 "allowed unless it smuggles in an unbrief'd specific. OUTPUT strict JSON only: "
 '{"verdict":"pass"|"fail","violations":[{"span":"","why":""}]}. '
 "FAIL only on a real fact/date not in the brief, or a misattributed quote.")

REPAIR = ("You are editing a Rig Wire article to remove UNSUPPORTED content while keeping the voice and length. You "
 "get the BRIEF, the DRAFT, and VIOLATIONS. Remove or rewrite each violation so nothing outside the brief remains "
 "(for an invented date, make it vague using only the brief's ordering). Replace removed material by developing a "
 "fact that IS in the brief. Use ONLY brief content. OUTPUT strict JSON, same schema as the draft.")

# ---------- model call ----------
async def gen(system, user, mx=6000, temp=0.4):
    last = None
    for _ in range(30):
        key = _CKEYS[_CK["i"] % len(_CKEYS)]; _CK["i"] += 1
        try:
            async with httpx.AsyncClient(timeout=180) as c:
                r = await c.post(URL, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                    json={"model": MODEL, "max_tokens": mx, "temperature": temp,
                          "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
            if r.status_code == 200:
                m = r.json()["choices"][0]["message"]
                return (m.get("content") or m.get("reasoning") or "")
            last = "HTTP " + str(r.status_code) + ": " + r.text[:80]
        except Exception as e:
            last = str(e)[:80]
        await asyncio.sleep(0.3)
    raise RuntimeError("model unavailable: " + str(last))

def parse(raw):
    t = re.sub(r"^```(json)?", "", raw.strip()); t = re.sub(r"```$", "", t.strip())
    t = re.sub(r'\*\*("?\w[\w\s]*"?)\*\*(\s*:)', r'\1\2', t)
    m = re.search(r"\{.*\}", t, re.S)
    if not m: return {"headline": "(parse-fail)", "dek": "", "body": raw}
    try: return json.loads(m.group(0))
    except Exception:
        try: return json.loads(re.sub(r"\*\*", "", m.group(0)))
        except Exception: return {"headline": "(parse-fail)", "dek": "", "body": raw}

def extract_body(art):
    b = art.get("body", ""); guard = 0
    while isinstance(b, dict) and "body" in b and guard < 3:  # unwrap nested body.body
        b = b["body"]; guard += 1
    if isinstance(b, dict): return "\n\n".join("## " + k.replace("_", " ").title() + "\n" + str(v) for k, v in b.items())
    if isinstance(b, list): return "\n\n".join(str(x) for x in b)
    return b or ""

def wc(s): return len((s or "").split())
def norm(s): return re.sub(r"\s+", " ", (s or "").strip().lower())[:120]
def dedup(rows, kf):
    seen = set(); out = []
    for r in rows:
        k = kf(r)
        if k and k not in seen: seen.add(k); out.append(r)
    return out

# ---------- topic classification (A1 fix: label the story, don't inherit cluster OTHER) ----------
CANON_TOPICS = {"POLITICS", "GOVERNANCE", "SECURITY", "INTERNATIONAL", "BUSINESS", "FINANCE", "TECHNOLOGY",
                "SCIENCE", "ENVIRONMENT", "HEALTH", "SPORTS", "SOCIETY", "CULTURE", "LEGAL", "INFRASTRUCTURE",
                "AGRICULTURE", "OTHER"}
TOPIC_ALIAS = {"SOCIAL": "SOCIETY", "ECONOMY": "FINANCE", "TECH": "TECHNOLOGY", "WORLD": "INTERNATIONAL",
               "ENV": "ENVIRONMENT", "BUSINESS/FINANCE": "BUSINESS", "INFRA": "INFRASTRUCTURE", "AGRI": "AGRICULTURE"}
TOPIC_SYS = ('Classify this news story from its fact-ledger. Return STRICT JSON: {"topic":"<ONE of: '
             + ", ".join(sorted(CANON_TOPICS)) + '>","tags":["3-6 short lowercase topical tags"]}')

async def classify_topic(brief):
    try:
        d = parse(await gen(TOPIC_SYS, brief[:6000], 400, 0.0))
        t = (d.get("topic") or "OTHER").strip().upper()
        t = TOPIC_ALIAS.get(t, t)
        if t not in CANON_TOPICS:
            t = "OTHER"
        tags = [str(x).strip().lower() for x in (d.get("tags") or []) if str(x).strip()][:6]
        return {"topic": t, "tags": tags}
    except Exception:
        return {"topic": "OTHER", "tags": []}

# ---------- run-scoped article-native brief (THE fix) ----------
async def q(db, sql, **p):
    r = await db.execute(text(sql), p); return [dict(m) for m in r.mappings().all()]

async def build_brief(db, sid, rid):
    a = (await q(db, """SELECT representative_title, topic, subject_country, primary_entities, article_count
         FROM analytics.story_clusters_v8 WHERE story_id=:sid""", sid=sid))[0]
    ids = [r["id"] for r in await q(db, """SELECT a.id FROM analytics.story_cluster_members_v8 m
        JOIN public.articles a ON a.id=m.article_id
        WHERE m.story_id=:sid AND m.run_id=:rid AND a.substrate_status='ok'""", sid=sid, rid=rid)]
    if not ids: return None
    P = {"ids": ids}
    summaries = await q(db, "SELECT summary_executive AS s FROM public.articles WHERE id=ANY(:ids) AND summary_executive IS NOT NULL AND length(summary_executive)>120 ORDER BY length(summary_executive) DESC LIMIT 3", **P)
    claims = dedup(await q(db, "SELECT claim_text FROM public.article_claims WHERE article_id=ANY(:ids) AND claim_text IS NOT NULL ORDER BY confidence DESC NULLS LAST", **P), lambda r: norm(r["claim_text"]))[:40]
    nums = dedup(await q(db, "SELECT value, unit, context FROM public.article_numbers WHERE article_id=ANY(:ids) AND context IS NOT NULL", **P), lambda r: norm(str(r["value"]) + str(r["context"])))[:25]
    events = dedup(await q(db, "SELECT event_description, effective_event_date AS d FROM public.article_events WHERE article_id=ANY(:ids) AND COALESCE(is_future,false)=false AND event_description IS NOT NULL ORDER BY effective_event_date", **P), lambda r: norm(r["event_description"]))[:25]
    quotes = dedup(await q(db, "SELECT COALESCE(quote_text_en,quote_text) AS qt, speaker_name_en, speaker_name FROM public.article_quotes WHERE article_id=ANY(:ids) AND COALESCE(quote_text_en,quote_text) IS NOT NULL AND length(COALESCE(quote_text_en,quote_text))>15", **P), lambda r: norm(r["qt"]))[:12]
    stances = await q(db, "SELECT actor AS target, stance, count(*) AS n FROM public.article_stances WHERE article_id=ANY(:ids) AND actor IS NOT NULL GROUP BY 1,2 ORDER BY n DESC LIMIT 20", **P)
    o = ["=== STORY ANCHOR ===", "Working title: " + str(a["representative_title"]),
         "Topic: " + str(a["topic"]) + "   Country: " + str(a["subject_country"]) + "   Coverage: " + str(len(ids)) + " clean sources (run " + str(rid) + ")"]
    if a.get("primary_entities"): o.append("Key entities: " + json.dumps(a["primary_entities"])[:280])
    if summaries:
        o.append("\n=== SOURCE SUMMARIES ===")
        for i, s in enumerate(summaries, 1): o.append(str(i) + ". " + s["s"].strip())
    o.append("\n=== CLAIMS ===")
    for i, c in enumerate(claims, 1): o.append(str(i) + ". " + c["claim_text"].strip())
    o.append("\n=== NUMBERS ===")
    for i, n in enumerate(nums, 1):
        u = (" " + str(n["unit"])) if n.get("unit") else ""
        o.append(str(i) + ". " + str(n["value"]) + u + " -- " + (str(n["context"]) or "").strip()[:130])
    if events:
        o.append("\n=== CHRONOLOGY ===")
        for e in events:
            d = str(e["d"])[:10] if e.get("d") else "n/d"
            o.append("- " + d + ": " + e["event_description"].strip())
    o.append("\n=== FRAMING / STANCES (target: stance x count) ===")
    for s in stances: o.append("- " + str(s["target"]) + ": " + str(s["stance"]) + " x" + str(s["n"]))
    o.append("\n=== QUOTES ===")
    for i, qq in enumerate(quotes, 1):
        sp = qq.get("speaker_name_en") or qq.get("speaker_name") or "unknown"
        o.append(str(i) + '. ' + sp + ': "' + qq["qt"].strip() + '"')
    distinct = len(claims) + len(nums) + len(events)
    # stable content signature for skip-unchanged: the actual material, NOT the run-id/anchor line
    sig = " | ".join([c["claim_text"] for c in claims]
                     + [str(n["value"]) + "~" + str(n["context"]) for n in nums]
                     + [e["event_description"] for e in events])
    return {"brief": "\n".join(o), "sig": sig, "distinct": distinct, "title": str(a["representative_title"]),
            "topic": (str(a["topic"]) or "OTHER").upper(), "n_ok": len(ids),
            "tags": [str(k) for k in (a.get("primary_entities") or {})][:6]}

fact_version = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

_MH_SQL = ("(SELECT md5(coalesce(string_agg(article_id::text, ',' ORDER BY article_id),'')) "
           "FROM analytics.story_cluster_members_v8 WHERE story_id = :sid)")
_UPSERT = text(f"""
    INSERT INTO analytics.story_generated_v8
      (story_id, headline, deck, body, topic, tags, strategy, status, tier,
       guard_c, verify, claim_provenance, fact_version, member_hash, word_count, run_id, updated_at)
    VALUES (:sid,:h,:d,:b,:topic,:tags,:strat,:status,:tier,
       CAST(:gc AS jsonb), CAST(:vf AS jsonb), CAST(:cp AS jsonb), :fv, {_MH_SQL}, :wc,:rid, now())
    ON CONFLICT (story_id) DO UPDATE SET
      headline=EXCLUDED.headline, deck=EXCLUDED.deck, body=EXCLUDED.body, topic=EXCLUDED.topic,
      tags=EXCLUDED.tags, strategy=EXCLUDED.strategy, status=EXCLUDED.status, tier=EXCLUDED.tier,
      guard_c=EXCLUDED.guard_c, verify=EXCLUDED.verify, claim_provenance=EXCLUDED.claim_provenance,
      fact_version=EXCLUDED.fact_version, member_hash=EXCLUDED.member_hash,
      word_count=EXCLUDED.word_count, run_id=EXCLUDED.run_id, updated_at=now()
""")

def vuser(brief, art, body):
    return "BRIEF:\n" + brief + "\n\nHEADLINE: " + str(art.get("headline", "")) + "\n\nBODY:\n" + body

async def generate_one(db, sid, rid, title):
    B = await build_brief(db, sid, rid)
    if not B or B["distinct"] < 3:
        return {"sid": sid, "status": "SKIP (thin/no ok members)"}
    fv = fact_version(B["sig"])  # A3: skip-unchanged — content signature, stable across runs
    prev = await q(db, "SELECT fact_version, status FROM analytics.story_generated_v8 WHERE story_id=:sid", sid=sid)
    if prev and prev[0].get("fact_version") == fv and str(prev[0].get("status", "")).startswith("PUBLISHABLE"):
        return {"sid": sid, "title": title[:44], "status": "SKIP-unchanged"}
    user = ("Write the long-read now. Aim for ~900 words if the material supports it. Material: " + str(B["distinct"]) + " distinct beats - develop each one fully.\n\nBRIEF:\n" + B["brief"])
    art = parse(await gen(PROMPT_D, user))
    body = extract_body(art)
    v = parse(await gen(VERIFY, vuser(B["brief"], art, body), 8000, 0.0))
    rounds = 0
    _MAX_REPAIR = int(os.environ.get("GEN_MAX_REPAIR", "2"))  # was a single round; loop up to N to reclaim single-unresolved holds
    while rounds < _MAX_REPAIR and v.get("verdict") != "pass" and v.get("violations"):
        rounds += 1
        ruser = "BRIEF:\n" + B["brief"] + "\n\nDRAFT JSON:\n" + json.dumps(art)[:6000] + "\n\nVIOLATIONS:\n" + json.dumps(v.get("violations"))[:1800]
        art = parse(await gen(REPAIR, ruser))
        body = extract_body(art)
        v = parse(await gen(VERIFY, vuser(B["brief"], art, body), 8000, 0.0))
    # a parse-fail draft must never ship as PUBLISHABLE (the verifier can pass on the raw body)
    passed = v.get("verdict") == "pass" and str(art.get("headline", "")) != "(parse-fail)"
    status = "PUBLISHABLE" if passed else "HELD (verify: %d unresolved)" % len(v.get("violations", []))
    cls = await classify_topic(B["brief"])  # A1: real topic label, not the cluster's OTHER
    rec = dict(sid=sid, h=str(art.get("headline", ""))[:300], d=str(art.get("dek", "") or art.get("standfirst", "")),
               b=body, topic=cls["topic"], tags=cls["tags"], strat="source-grounded-v2", status=status,
               tier=(1 if passed else 0), gc=None, vf=json.dumps(v), cp=None,
               fv=fv, wc=wc(body), rid=rid)
    if WRITE:
        await db.execute(_UPSERT, rec); await db.commit()
    return {"sid": sid, "title": title[:44], "topic": cls["topic"], "ok_members": B["n_ok"], "distinct": B["distinct"],
            "words": wc(body), "status": status, "repair_rounds": rounds,
            "violations": len(v.get("violations", [])), "headline": rec["h"]}

_CONC = int(os.environ.get("GEN_CONC", "6"))  # parallel stories in flight; 37 Cerebras keys support this easily
_SEM = asyncio.Semaphore(_CONC)


async def _run_one(sid, rid, title):
    async with _SEM:
        try:
            async with get_db() as db:  # each concurrent story gets its OWN connection (asyncpg conns are not concurrency-safe)
                res = await generate_one(db, sid, rid, title)
        except Exception as e:
            res = {"sid": sid, "error": str(e)[:160]}
    print(json.dumps(res, ensure_ascii=False), flush=True)


async def main():
    async with get_db() as db:
        # A3 frontier: prefer surfaceable stories not yet generated OR re-clustered since last gen
        # (new run_id). fact_version skip-unchanged (in generate_one) is the fine-grained guard on top.
        rows = await q(db, """SELECT sc.story_id::text AS sid, sc.run_id AS rid, sc.representative_title AS title
            FROM analytics.story_clusters_v8 sc
            LEFT JOIN analytics.story_generated_v8 g ON g.story_id = sc.story_id
            LEFT JOIN rigwire.editorial_overrides eo ON eo.story_id = sc.story_id
            WHERE sc.last_seen_at > now() - interval '24 hours'
              AND sc.redirected_to IS NULL AND sc.suppression_reason IS NULL
              AND sc.representative_title IS NOT NULL
              AND sc.independent_source_count >= 2 AND sc.article_count >= 4
              AND (g.story_id IS NULL OR g.run_id IS DISTINCT FROM sc.run_id)
              -- editorial layer (epic 002): never regenerate a human-locked story, never touch a killed one
              AND COALESCE(eo.human_locked, false) = false
              AND COALESCE(eo.action, 'live') <> 'killed'
            ORDER BY sc.importance_score DESC NULLS LAST LIMIT :n""", n=LIMIT)
    print(("WRITE" if WRITE else "DRY-RUN") + " mode | " + str(len(rows)) + " surfaceable clusters selected | conc=" + str(_CONC) + "\n", flush=True)
    await asyncio.gather(*[_run_one(r["sid"], r["rid"], r["title"]) for r in rows])

asyncio.run(main())
