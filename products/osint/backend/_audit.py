"""Live cross-surface data capture for the Telangana user (Revanth). Delete after."""
import asyncio
import json
from sqlalchemy import text

from db import get_db
from brief_prefs import load_prefs
from posture import POL, _BODY_PRESENT
from war_room import build_war_room
from analytics_page import build_analytics
from dossier import build_roster, build_entity_file
from map_page import build_map
from report_builder import build_report
import home_sections

PID = "9a70e644-5a04-456e-a569-1a9e68aae1ed"


def jj(x):
    return json.dumps(x, default=str, ensure_ascii=False)[:600]


async def main():
    async with get_db() as db:
        row = (await db.execute(text(
            "SELECT user_id FROM analytics.user_brief_prefs WHERE primary_subject_id=:p LIMIT 1"), {"p": PID})).fetchone()
        prefs = await load_prefs(db, str(row.user_id))

        print("\n##### CANONICAL COUNTS (Revanth) #####")
        for label, sql in [
            ("mentions_all_time_RAW", "SELECT count(DISTINCT article_id) FROM article_entity_mentions WHERE entity_id=CAST(:p AS uuid)"),
            ("mentions_alltime_BODYPRESENT", f"SELECT count(DISTINCT a.id) FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id WHERE m.entity_id=CAST(:p AS uuid) AND {_BODY_PRESENT}"),
            ("quotes_BY_revanth", "SELECT count(*) FROM article_quotes WHERE speaker_entity_id=CAST(:p AS uuid)"),
            ("claims_subject_revanth", "SELECT count(*) FROM article_claims WHERE subject_entity_id=CAST(:p AS uuid)"),
        ]:
            n = (await db.execute(text(sql), {"p": PID})).scalar()
            print(f"  {label} = {n}")

        print("\n  directed favourability by window:")
        for w in ['24 hours', '3 days', '7 days', '21 days', '47 days']:
            r = (await db.execute(text(f"""
                WITH pa AS (SELECT DISTINCT a.id FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id
                            WHERE m.entity_id=CAST(:p AS uuid) AND a.collected_at>=analytics.now_sim()-interval '{w}')
                SELECT round(100*avg(({POL})*st.intensity)::numeric,1) fav,
                       count(*) FILTER (WHERE ({POL})>0) pos, count(*) FILTER (WHERE ({POL})<0) neg
                  FROM pa JOIN article_stances st ON st.article_id=pa.id AND st.actor_entity_id=CAST(:p AS uuid)
            """), {"p": PID})).fetchone()
            print(f"    {w}: fav={r.fav} pos={r.pos} neg={r.neg}")

        print("\n##### HOME #####")
        try:
            home = await home_sections.build_home(db, prefs)
            print("  keys:", list(home.keys()))
            for k in ("masthead", "sentiment", "posture", "net", "favourability"):
                if k in home:
                    print(f"  {k}: {jj(home[k])}")
            six = home.get("six") or home.get("latest") or []
            if isinstance(six, list):
                for feed in six:
                    fid = feed.get("key") or feed.get("id")
                    items = feed.get("items") or []
                    print(f"  feed[{fid}] '{feed.get('title')}' n={len(items)} first={jj((items[0] if items else {}))[:160]}")
        except Exception as e:
            print("  HOME ERR:", repr(e))

        print("\n##### WAR ROOM #####")
        wr = await build_war_room(db, prefs)
        print("  station:", jj(wr.get("station")))
        print("  lead.summary:", (wr.get("lead", {}).get("summary") or "")[:200])
        print("  cables:", [(c.get("id"), c.get("sev"), c.get("src"), c["facets"].get("outlets")) for c in (wr.get("cables") or [])])

        print("\n##### ANALYTICS #####")
        an = await build_analytics(db, prefs)
        print("  base:", an.get("base"), "window:", an.get("window"))
        for m in an.get("modules", []):
            if m["id"] in ("volume", "forvsagainst", "outletlean", "sov", "battlefield"):
                print(f"  [{m['id']}] {m['name']} | sub='{m.get('sub')}' | data={jj(m.get('data'))[:260]}")

        print("\n##### DOSSIER (Revanth) #####")
        ro = await build_roster(db, prefs)
        names = [r["name"] for r in ro.get("roster", [])]
        dups = {n for n in names if names.count(n) > 1}
        print("  roster_n:", len(names), "duplicates:", dups, "first3:", names[:3])
        ef = await build_entity_file(db, PID, prefs)
        print("  tiles:", jj(ef.get("tiles")), "standing:", jj(ef.get("standing")), "window_days:", ef.get("window_days"))
        print("  summary:", (ef.get("summary") or "")[:200])

        print("\n##### MAP #####")
        mp = await build_map(db, prefs)
        dfs = mp.get("districtFeeds") or []
        print("  situation:", (mp.get("situation") or "")[:200])
        print("  districtFeeds_n:", len(dfs), "sum_counts:", sum(d.get("count", 0) for d in dfs),
              "top3:", [(d["name"], d["count"]) for d in sorted(dfs, key=lambda x: -x["count"])[:3]])
        print("  bubbles_n:", len(mp.get("bubbles") or []))

        print("\n##### REPORT #####")
        rep = await build_report(db, prefs)
        print("  at_a_glance:", jj(rep.get("at_a_glance")))
        print("  sentiment:", jj(rep.get("sentiment")), "kpis:", jj(rep.get("kpis")))
        print("  top_stories_n:", len(rep.get("top_stories") or []), "deep_dives_n:", len(rep.get("deep_dives") or []))


asyncio.run(main())
