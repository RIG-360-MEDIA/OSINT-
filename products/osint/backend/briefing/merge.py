"""Event-merge: group the day's government items into events, across all 3 media.

Deterministic, rule-based on the structured event fields the judge already
extracted (actors[], action, place) plus lands_on/topic. No LLM cost. This is
what §1 (Daily Brief) and §2 (Big Story) rank over — and it does what the
articles-only v8 clusterer cannot: group a TV clip with a newspaper with a web
article about the same event.

Grouping rule: two items are the same event if they share a significant actor
(roster name / normalised entity) OR a strong action+place overlap. Union-find
over the day's items. Spread = distinct sources per pillar (TV deduped already).
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from db import get_db

_WS = re.compile(r"\s+")
_STOP = {"the", "a", "an", "of", "in", "on", "to", "for", "and", "govt",
         "government", "telangana", "state", "said", "over", "after"}

# Generic government entities that appear across MANY unrelated stories — they
# must NEVER be a merge key, or distinct events (a corruption case, a bill, an
# NHRC notice) collapse into one blob just because each mentions "the government"
# or "ACB". An actor key containing any of these substrings is dropped from
# merge keys. Specific names (ministers, projects like Kaleshwaram, REDCO, a
# named bill) do NOT contain these and stay as keys.
_GENERIC_ENTITY_SUBSTR = (
    "government", "govt", "administration", "the state", "secretariat",
    "acb", "anti-corruption", "nhrc", "human rights commission",
    "election commission", "the centre", "central govt",
    "opposition", "ruling party", "the party", "official", "authorities",
)


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "").lower()).strip()


def _actor_keys(actors: list[str], lands_on: str | None) -> set[str]:
    keys = set()
    for a in (actors or []):
        n = _norm(a)
        if len(n) >= 4 and n not in _STOP:
            keys.add(n)
    if lands_on:
        n = _norm(lands_on)
        if len(n) >= 4:
            keys.add(n)
    return keys


def _action_tokens(action: str) -> set[str]:
    return {w for w in re.sub(r"[^\w\s]", " ", _norm(action)).split()
            if len(w) > 3 and w not in _STOP}


def _same_event(a: dict, b: dict) -> bool:
    # shared SPECIFIC actor (generic party/CM names already stripped) AND the
    # same topic -> same event. The topic guard stops two unrelated stories that
    # happen to name the same second-tier figure from merging.
    shared = a["key_actors"] & b["key_actors"]
    if shared and a["topic"] == b["topic"]:
        return True
    # no specific actor: require strong action overlap AND same place AND topic
    at, bt = a["atok"], b["atok"]
    if at and bt and len(at & bt) >= 2 and a["place"] == b["place"] and a["topic"] == b["topic"]:
        return True
    return False


async def _fetch_titles(db, rows) -> dict[str, str]:
    """Bulk indexed title lookup, one query per pillar."""
    web = [r.item_ref for r in rows if r.pillar == "web"]
    npr = [r.item_ref for r in rows if r.pillar == "newspaper"]
    tv = [r.item_ref for r in rows if r.pillar == "tv"]
    out: dict[str, str] = {}
    if web:
        for a in (await db.execute(text(
            "SELECT id::text ref, title FROM articles WHERE id = ANY(CAST(:ids AS uuid[]))"
        ), {"ids": web})).fetchall():
            out[a.ref] = a.title
    if npr:
        # newspaper item_ref may be a clipping id (scanned cutting) OR an article
        # id (print paper collected via its web edition — scans are paywalled)
        for c in (await db.execute(text(
            "SELECT id::text ref, headline title FROM clippings WHERE id = ANY(CAST(:ids AS uuid[]))"
        ), {"ids": npr})).fetchall():
            out[c.ref] = c.title
        miss = [x for x in npr if x not in out]
        if miss:
            for a in (await db.execute(text(
                "SELECT id::text ref, title FROM articles WHERE id = ANY(CAST(:ids AS uuid[]))"
            ), {"ids": miss})).fetchall():
                out[a.ref] = a.title
    if tv:
        for v in (await db.execute(text(
            "SELECT video_id ref, max(video_title) title FROM youtube_clips_v2 WHERE video_id = ANY(:ids) GROUP BY video_id"
        ), {"ids": tv})).fetchall():
            out[v.ref] = v.title
    return out


async def merge_events(org_id: str, cover_date) -> dict[str, Any]:
    async with get_db() as db:
        run = (await db.execute(text("""
            SELECT id FROM briefing.runs WHERE org_id=CAST(:o AS uuid) AND cover_date=:d
        """), {"o": org_id, "d": cover_date})).fetchone()
        if not run:
            return {"error": "no run"}
        rid = run.id

        rows = (await db.execute(text("""
            SELECT i.id, i.pillar, i.source_ref, i.verdict, i.strength, i.topic,
                   i.department, i.lands_on, i.event_action, i.event_actors,
                   i.event_place, i.evidence, i.item_ref
              FROM briefing.items i
             WHERE i.run_id=:r AND i.about_government AND NOT i.unclear
        """), {"r": rid})).fetchall()

        # Bulk title lookup by pillar, indexed (avoids per-row seq scans / timeout).
        titles = await _fetch_titles(db, rows)

        items = []
        for r in rows:
            items.append({
                "id": r.id, "pillar": r.pillar, "source": r.source_ref,
                "verdict": r.verdict, "strength": r.strength, "topic": r.topic,
                "department": r.department, "lands_on": r.lands_on,
                "action": r.event_action or "", "title": titles.get(r.item_ref, "") or "",
                "evidence": r.evidence or "", "place": _norm(r.event_place) or "telangana",
                "actors": _actor_keys(r.event_actors, r.lands_on),
                "atok": _action_tokens(r.event_action or ""),
            })

        # Strip GENERIC actors (party names, the CM, "government") that appear in
        # a large fraction of items — they merge unrelated stories transitively
        # into one blob. An actor kept as a merge key must be specific enough to
        # distinguish an event: appears in < 8% of items and in < 10 items.
        from collections import Counter
        df = Counter()
        for it in items:
            for a in it["actors"]:
                df[a] += 1
        n = max(len(items), 1)
        # generic = appears in many items (frequency) OR is a government-wide
        # entity by name (substring) — either way it can't distinguish events.
        generic = {a for a, c in df.items() if c > max(6, 0.05 * n)}
        generic |= {a for a in df if any(g in a for g in _GENERIC_ENTITY_SUBSTR)}
        for it in items:
            it["key_actors"] = it["actors"] - generic

        # union-find
        parent = list(range(len(items)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            parent[find(x)] = find(y)

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if _same_event(items[i], items[j]):
                    union(i, j)

        groups: dict[int, list[int]] = {}
        for i in range(len(items)):
            groups.setdefault(find(i), []).append(i)

        # clear prior events for this run
        await db.execute(text("DELETE FROM briefing.events WHERE run_id=:r"), {"r": rid})

        events = []
        for members in groups.values():
            mi = [items[k] for k in members]
            web = {m["source"] for m in mi if m["pillar"] == "web"}
            tv = {m["source"] for m in mi if m["pillar"] == "tv"}
            np = {m["source"] for m in mi if m["pillar"] == "newspaper"}
            fav = sum(1 for m in mi if m["verdict"] == "favourable")
            crit = sum(1 for m in mi if m["verdict"] == "critical")
            dd = (fav + crit) or 1
            net = round(100 * (fav - crit) / dd)
            spread = len(web) + len(tv) + len(np)
            strong = any(m["strength"] == "strong" for m in mi)
            # representative = longest title, prefer web then tv then np
            rep = sorted(mi, key=lambda m: (m["pillar"] != "web", -len(m["title"] or "")))[0]
            importance = spread * 2 + (3 if strong else 0) + crit
            label = rep["title"][:140] or (rep["action"][:140])
            top_web = next((m["id"] for m in mi if m["pillar"] == "web"), None)
            top_tv = next((m["id"] for m in mi if m["pillar"] == "tv"), None)
            top_np = next((m["id"] for m in mi if m["pillar"] == "newspaper"), None)
            events.append({
                "members": [items[k]["id"] for k in members],
                "label": label, "spread_web": len(web), "spread_tv": len(tv),
                "spread_np": len(np), "net": net, "importance": importance,
                "topic": rep["topic"], "department": rep["department"],
                "rep_evidence": rep["evidence"], "rep_verdict": rep["verdict"],
                "top_web": top_web, "top_tv": top_tv, "top_np": top_np,
                "size": len(mi),
            })

        events.sort(key=lambda e: -e["importance"])

        for e in events:
            await db.execute(text("""
                INSERT INTO briefing.events
                  (org_id, run_id, label, member_item_ids, spread_web, spread_tv,
                   spread_np, net_tone, importance, top_web_item, top_tv_item, top_np_item)
                VALUES (CAST(:o AS uuid), :r, :label, CAST(:mem AS uuid[]), :sw, :stv,
                        :snp, :net, :imp, :tw, :ttv, :tnp)
            """), {"o": org_id, "r": rid, "label": e["label"], "mem": e["members"],
                   "sw": e["spread_web"], "stv": e["spread_tv"], "snp": e["spread_np"],
                   "net": e["net"], "imp": e["importance"], "tw": e["top_web"],
                   "ttv": e["top_tv"], "tnp": e["top_np"]})
        await db.execute(text("UPDATE briefing.runs SET status='merged' WHERE id=:r"), {"r": rid})
        await db.commit()

        return {"items": len(items), "events": len(events),
                "top": [{"label": e["label"][:70], "spread": e["spread_web"] + e["spread_tv"] + e["spread_np"],
                         "web": e["spread_web"], "tv": e["spread_tv"], "np": e["spread_np"],
                         "net": e["net"], "size": e["size"]} for e in events[:8]]}
