"""T4_status.py — quick read of T4 progress without quoting nightmares."""
import json
import os
import time
import sys
sys.path.insert(0, "/app")

p = "/docs/quality/backfill_state.json"
s = json.load(open(p))
mtime = os.path.getmtime(p)
print(f"Completed: {len(s['completed'])}")
print(f"Failed   : {len(s.get('failed', {}))}")
print(f"State last write: {time.strftime('%H:%M:%S UTC', time.gmtime(mtime))}")
print(f"Started at      : {s.get('started_at')}")
print(f"Articles still to refill: ~{64755 - len(s['completed'])}")
