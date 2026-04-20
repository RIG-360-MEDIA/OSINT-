"""
Celery application with Beat schedule.

Broker: PostgreSQL via sqla+postgresql (no Redis dependency).
Queues: collectors, nlp, relevance, brief
"""
from __future__ import annotations

import os
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab

DATABASE_URL_SYNC: str = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://rig:rigpassword@rig-postgres:5432/rig",
)

_broker_url = DATABASE_URL_SYNC.replace("postgresql", "sqla+postgresql", 1)
_result_url = DATABASE_URL_SYNC.replace("postgresql", "db+postgresql", 1)

app = Celery(
    "rig_surveillance",
    include=[
        "backend.tasks",
        "backend.tasks.collector_tasks",
        "backend.tasks.nlp_processor",
        "backend.tasks.relevance_task",
        "backend.tasks.backfill_task",
        "backend.tasks.dict_reload_task",
        "backend.tasks.thread_task",
    ],
)

app.config_from_object(
    {
        "broker_url": _broker_url,
        "result_backend": _result_url,
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "timezone": "UTC",
        "enable_utc": True,
        "task_routes": {
            "tasks.collect_rss": {"queue": "collectors"},
            "tasks.collect_html": {"queue": "collectors"},
            "tasks.process_nlp_batch": {"queue": "nlp"},
            "tasks.score_relevance_batch": {"queue": "relevance"},
            "tasks.score_unscored_articles": {"queue": "relevance"},
            "tasks.generate_all_briefs": {"queue": "brief"},
        },
        "beat_schedule": {
            "collect-rss-every-15-min": {
                "task": "tasks.collect_rss",
                "schedule": timedelta(minutes=15),
                "options": {"queue": "collectors"},
            },
            "collect-html-every-6-hours": {
                "task": "tasks.collect_html",
                "schedule": timedelta(hours=6),
                "options": {"queue": "collectors"},
            },
            "process-nlp-every-30-seconds": {
                "task": "tasks.process_nlp_batch",
                "schedule": timedelta(seconds=30),
                "options": {"queue": "nlp"},
            },
            "generate-briefs-daily": {
                "task": "tasks.generate_all_briefs",
                "schedule": crontab(hour=0, minute=30),
                "options": {"queue": "brief"},
            },
            "reset-groq-keys-daily": {
                "task": "tasks.reset_groq_keys",
                "schedule": crontab(hour=0, minute=5),
                "options": {"queue": "default"},
            },
            "score-unscored-every-30-min": {
                "task": "tasks.score_unscored_articles",
                "schedule": timedelta(minutes=30),
                "options": {"queue": "relevance"},
            },
            "check-entity-dict-every-5-min": {
                "task": "tasks.check_entity_dict_version",
                "schedule": timedelta(minutes=5),
                "options": {"queue": "nlp"},
            },
            "assign-threads-every-5-min": {
                "task": "tasks.assign_new_article_threads",
                "schedule": timedelta(minutes=5),
                "options": {"queue": "nlp"},
            },
            "nightly-thread-recluster": {
                "task": "tasks.nightly_thread_recluster",
                "schedule": crontab(hour=2, minute=0),
                "options": {"queue": "nlp"},
            },
        },
    }
)
