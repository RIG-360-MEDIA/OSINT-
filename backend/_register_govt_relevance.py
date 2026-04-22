"""
P15.cm-grade Phase 2 - wiring instructions for B1's relevance pipeline.
Coordinator merges these into shared infra files at the phase boundary.

DO NOT import this module from anywhere. It exists only as a manifest.
"""

# === ADD TO backend/celery_app.py ===
# In the include=[...] list:
#   "backend.tasks.govt_relevance_task",
# In task_routes dict:
#   "tasks.score_govt_doc_relevance":     {"queue": "relevance"},
#   "tasks.score_govt_doc_for_all_users": {"queue": "relevance"},

# === ADD TO backend/tasks/__init__.py ===
# from backend.tasks.govt_relevance_task import (  # noqa: F401
#     score_govt_doc_relevance,
#     score_govt_doc_for_all_users,
# )
