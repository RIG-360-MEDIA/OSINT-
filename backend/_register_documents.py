"""
P15 — manual wiring instructions.

Four parallel sessions ran on this branch and were instructed NOT to
edit the three shared files below to avoid merge conflicts. After all
four sessions finish, the human applies the additions in this file by
hand.

Three insertion points:
  1. backend/main.py
  2. backend/tasks/__init__.py
  3. backend/celery_app.py
"""

# ════════════════════════════════════════════════════════════════════════
# 1. ADD TO backend/main.py
# ════════════════════════════════════════════════════════════════════════
#
#   from backend.routers.documents_router import documents_router
#   app.include_router(documents_router)
#

# ════════════════════════════════════════════════════════════════════════
# 2. ADD TO backend/tasks/__init__.py
# ════════════════════════════════════════════════════════════════════════
#
#   from backend.tasks.govt_task import collect_govt_documents  # noqa: F401
#

# ════════════════════════════════════════════════════════════════════════
# 3. ADD TO backend/celery_app.py
# ════════════════════════════════════════════════════════════════════════
#
# (a) Ensure these are at the top of the file:
#
#   from celery.schedules import crontab   # already present
#
# (b) Add module to the Celery `include=[...]` list:
#
#   "backend.tasks.govt_task",
#
# (c) Add to `task_routes` dict:
#
#   "tasks.collect_govt_documents": {"queue": "collectors"},
#
# (d) Add to `beat_schedule` dict:
#
#   "collect-govt-docs-daily": {
#       "task":     "tasks.collect_govt_documents",
#       "schedule": crontab(hour=6, minute=30),
#       "options":  {"queue": "collectors"},
#   },
#
