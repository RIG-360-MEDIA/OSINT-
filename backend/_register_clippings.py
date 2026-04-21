# ═══════════════════════════════════════════════════════════════
# P16 Cutting Room — manual registration additions.
#
# Four parallel Claude Code sessions edited separate files but
# share three registration points. To avoid merge conflicts,
# this session DOES NOT touch those three files directly.
# Apply the snippets below once all four sessions complete.
# ═══════════════════════════════════════════════════════════════

# ─── ADD TO backend/main.py ────────────────────────────────────
# from backend.routers.clippings_router import clippings_router
# app.include_router(clippings_router)

# ─── ADD TO backend/tasks/__init__.py ──────────────────────────
# from backend.tasks.newspaper_task import collect_newspapers

# ─── ADD TO backend/celery_app.py (inside beat_schedule) ───────
# 'collect-newspapers-daily': {
#     'task': 'tasks.collect_newspapers',
#     'schedule': crontab(hour=7, minute=30),
#     'options': {'queue': 'collectors'},
# },
