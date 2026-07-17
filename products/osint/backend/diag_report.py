import asyncio
import json
import traceback

from db import get_db
from brief_prefs import load_prefs
import report_builder
import report_render

UID = "db4b9207-51aa-4d39-a7bf-e6fab34c3465"  # teleganarig360 (Telangana client)


def line(k, v):
    if v is None:
        return f"{k:16} NONE                <-- EMPTY"
    if isinstance(v, (list, tuple)):
        return f"{k:16} list[{len(v)}]" + ("            <-- EMPTY" if not v else "")
    if isinstance(v, dict):
        ke = ",".join(sorted(v.keys())[:6])
        return f"{k:16} dict{{{len(v)}}} [{ke}]" + ("   <-- EMPTY" if not v else "")
    if isinstance(v, str):
        s = v.strip()
        return f"{k:16} str[{len(v)}] {s[:48]!r}" + ("   <-- EMPTY" if not s else "")
    return f"{k:16} {type(v).__name__}={v}"


async def go():
    async with get_db() as db:
        prefs = await load_prefs(db, UID)
        if not prefs:
            print("PERSONA MISSING -> would 403")
            return
        try:
            r = await report_builder.build_report(db, prefs)
        except Exception:
            print("BUILD FAILED:")
            traceback.print_exc()
            return

        print("=== TOP-LEVEL STRUCTURE (", len(r), "keys) ===")
        empties = []
        for k in sorted(r.keys()):
            print(line(k, r[k]))
            if r[k] is None or (hasattr(r[k], "__len__") and len(r[k]) == 0):
                empties.append(k)

        print("\n=== HEADER FACTS (should match UI) ===")
        print("state / state_code :", r.get("state"), "/", r.get("state_code"))
        print("principal          :", r.get("principal"))
        print("window_hours       :", r.get("window_hours"))
        print("confidence         :", r.get("confidence"))
        print("kpis               :", json.dumps(r.get("kpis"), default=str)[:500])
        print("sentiment          :", json.dumps(r.get("sentiment"), default=str)[:300])

        print("\n=== CONTENT DEPTH ===")
        for k in ("top_stories", "themes", "quotes", "figures", "districts",
                  "stakeholders", "early_warning", "source_intel", "domains"):
            v = r.get(k) or []
            n = len(v) if hasattr(v, "__len__") else v
            print(f"  {k:14} count={n}")
        print("  narrative sample :", str(r.get("narrative"))[:200])
        ts = r.get("top_stories") or []
        if ts:
            print("  top_story[0]     :", json.dumps(ts[0], default=str)[:260])

        print("\n=== PDF RENDER ===")
        try:
            pdf = report_render.render_pdf(r)
            print("  bytes =", len(pdf), " valid_pdf =", pdf[:5] == b"%PDF-")
        except Exception:
            print("  PDF FAILED:")
            traceback.print_exc()

        print("\n=== VERDICT ===")
        print("  empty/missing sections:", empties or "NONE")


asyncio.run(go())
