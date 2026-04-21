"""
P17 — Signal Room registration stub.

Four Claude sessions are editing the repo in parallel; to avoid merge
conflicts, this session does NOT touch `backend/main.py`,
`backend/tasks/__init__.py`, or `backend/celery_app.py`. The exact lines to
append to each file are listed below as comments. A single manual pass after
all sessions commit will apply them.
"""

# ═══ ADD TO backend/main.py ═══════════════════════════════════════════════
# from backend.routers.signals_router import signals_router
# app.include_router(signals_router)


# ═══ ADD TO backend/tasks/__init__.py ═════════════════════════════════════
# from backend.tasks.social_task import (
#     collect_reddit,
#     collect_twitter,
#     collect_telegram,
# )


# ═══ ADD TO backend/celery_app.py ═════════════════════════════════════════
#
# 1. Append to the `include` list passed to Celery(...):
#
#        "backend.tasks.social_task",
#
# 2. Append to the `task_routes` dict:
#
#        "tasks.collect_reddit":   {"queue": "collectors"},
#        "tasks.collect_twitter":  {"queue": "collectors"},
#        "tasks.collect_telegram": {"queue": "collectors"},
#
# 3. Append to the `beat_schedule` dict:
#
#        "collect-reddit-every-30min": {
#            "task": "tasks.collect_reddit",
#            "schedule": timedelta(minutes=30),
#            "options": {"queue": "collectors"},
#        },
#        "collect-twitter-every-6h": {
#            "task": "tasks.collect_twitter",
#            "schedule": timedelta(hours=6),
#            "options": {"queue": "collectors"},
#        },
#        "collect-telegram-every-15min": {
#            "task": "tasks.collect_telegram",
#            "schedule": timedelta(minutes=15),
#            "options": {"queue": "collectors"},
#        },
