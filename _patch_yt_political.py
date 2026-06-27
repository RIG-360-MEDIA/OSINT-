"""One-shot patcher: make the YouTube fetch pipeline political-only.

Idempotent — re-running is a no-op once applied. Run on Hetzner against the
bind-mounted /root/rig copy.
"""
import sys

PATH = "/root/rig/backend/tasks/youtube_task.py"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()
orig = src

# 1) Fetch selection: only ever claim political rows.
src = src.replace(
    "ORDER BY is_political DESC,",
    "AND is_political\n                             ORDER BY is_political DESC,",
    1,
)

# 2) Discovery insert: non-political videos are recorded but never queued.
src = src.replace(
    "video_published_at, is_political)",
    "video_published_at, is_political, status)",
    1,
)
src = src.replace(
    "VALUES (:vid, :title, :cid, :cname, :pub, :pol)",
    "VALUES (:vid, :title, :cid, :cname, :pub, :pol,\n"
    "                                CASE WHEN :pol THEN 'pending' ELSE 'skipped' END)",
    1,
)

if "AND is_political" not in src or "ELSE 'skipped' END)" not in src:
    print("PATCH FAILED: expected anchors not found", file=sys.stderr)
    sys.exit(1)
if src == orig:
    print("NO CHANGE (already patched?)")
    sys.exit(0)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)
print("PATCHED OK")
