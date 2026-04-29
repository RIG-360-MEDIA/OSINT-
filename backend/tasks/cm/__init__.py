"""
CM Page Celery tasks.

All tasks are routed in backend/celery_app.py. They:
  * Pull recent un-processed items from articles/social_posts/clippings.
  * Call the appropriate backend/nlp/cm helper.
  * UPSERT results into cm_* tables.
  * Are idempotent and watermark-driven.
"""
