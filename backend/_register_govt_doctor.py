"""
P15.cm-grade Phase 2 — wiring instructions for B3's observability + dedicated worker.
Coordinator merges these into shared infra files at the phase boundary.
"""

# ═══ ADD TO backend/celery_app.py ═══
# In include=[...]:
#   "backend.tasks.govt_doctor_task",
# In task_routes — CHANGE existing entry:
#   "tasks.collect_govt_documents": {"queue": "documents"}   (was "collectors")
# Plus new entries:
#   "tasks.govt_collection_doctor": {"queue": "documents"},
# In beat_schedule:
#   "govt-doctor-daily": {
#       "task": "tasks.govt_collection_doctor",
#       "schedule": crontab(hour=7, minute=0),
#       "options": {"queue": "documents"},
#   },
# Update existing collect-govt-docs-daily entry queue from "collectors" to "documents":
#   "options": {"queue": "documents"}

# ═══ ADD TO backend/tasks/__init__.py ═══
# from backend.tasks.govt_doctor_task import govt_collection_doctor  # noqa: F401

# ═══ ADD TO backend/start.sh ═══
# Mirror the worker-collectors line. Add a new worker:
#   celery -A backend.celery_app worker -n worker-documents@%h -Q documents \
#     --concurrency=2 --prefetch-multiplier=1 --loglevel=INFO &

# ═══ Coordinator: also add 4 lines to backend/tasks/govt_task.py ═══
# At top of _collect_govt_docs():
#   from backend.observability.govt_runs import start_collection_run, finish_collection_run, update_source_health
# Inside the per-source loop, before fetch_document_urls:
#   run_id = await start_collection_run(db, source_id=str(source.id), source_name=source.name)
# After the per-source loop, success path:
#   await finish_collection_run(db, run_id=run_id, status="completed",
#                                 urls_discovered=len(doc_urls), pdfs_downloaded=pdfs_downloaded,
#                                 docs_inserted=source_inserted)
#   await update_source_health(db, source_id=str(source.id), success=True)
# On exception in the per-source loop:
#   await finish_collection_run(db, run_id=run_id, status="failed", error_summary=str(exc))
#   await update_source_health(db, source_id=str(source.id), success=False)
