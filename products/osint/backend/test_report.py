import asyncio
import traceback

from db import get_db
from brief_prefs import load_prefs
import report_builder

TELANGANA_UID = "db4b9207-51aa-4d39-a7bf-e6fab34c3465"


async def go():
    async with get_db() as db:
        prefs = await load_prefs(db, TELANGANA_UID)
        print("prefs_loaded:", prefs is not None)
        if not prefs:
            print("=> would 403 (no persona)")
            return
        print("prefs_keys:", sorted(prefs.keys()))
        try:
            r = await report_builder.build_report(db, prefs)
            print("REPORT_OK state_code:", r.get("state_code"))
            print("sections:", sorted(r.keys()))
            # spot-check that content blocks aren't empty (LLM-dependent)
            for k in ("executive", "cm_perspective", "stories"):
                v = r.get(k)
                n = len(v) if hasattr(v, "__len__") else v
                print(f"  block {k}: {'EMPTY' if not v else ('len=' + str(n))}")
        except Exception:
            print("REPORT_FAILED:")
            traceback.print_exc()


asyncio.run(go())
