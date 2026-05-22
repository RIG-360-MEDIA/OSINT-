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
        "backend.tasks.dict_reload_task",
        # SearXNG-fallback thumbnail finder (fix for post-deploy og:image gap)
        "backend.tasks.thumbnail_task",
        # External-source collectors (atlas layers) — kept per cleanup spec
        "backend.tasks.collectors.mandi_agmarknet_task",
        "backend.tasks.collectors.cpcb_aqi_task",
        "backend.tasks.collectors.imd_weather_task",
        "backend.tasks.collectors.tgspdcl_power_task",
        "backend.tasks.collectors.welfare_coverage_task",
        "backend.tasks.collectors.acled_sink_task",
        # Periodic byline backfill — runs every 6h, HTML-only, no LLM cost
        "backend.tasks.substrate.byline_periodic_task",
        # Periodic tweet enrichment — catches v1→v2 upgrades + retries
        "backend.tasks.substrate.tweet_periodic_task",
        # Nightly gold-set regression for the data-quality observability stack
        "backend.tasks.quality_regression_task",
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
            "tasks.collect_rss_direct": {"queue": "collectors"},
            "tasks.collect_html": {"queue": "collectors"},
            "tasks.quality.gold_regression": {"queue": "nlp"},
            "tasks.fetch_og_images_batch": {"queue": "collectors"},
            "tasks.process_nlp_batch": {"queue": "nlp"},
            # Byline / tweet substrate backfill — pure HTTP fetching, light
            # parsing, no LLM. Shares the collectors queue with HTML scraping.
            "tasks.backfill_bylines_periodic": {"queue": "collectors"},
            "tasks.backfill_tweets_periodic": {"queue": "collectors"},
            # External-source collectors (atlas layers) — kept per cleanup spec.
            "tasks.collectors.mandi_agmarknet": {"queue": "collectors"},
            "tasks.collectors.cpcb_aqi":        {"queue": "collectors"},
            "tasks.collectors.imd_weather":     {"queue": "collectors"},
            "tasks.collectors.tgspdcl_power":   {"queue": "collectors"},
            "tasks.collectors.welfare_coverage":{"queue": "collectors"},
            "tasks.collectors.acled_sink":      {"queue": "collectors"},
        },
        "beat_schedule": {
            "collect-rss-every-15-min": {
                "task": "tasks.collect_rss",
                "schedule": timedelta(minutes=15),
                "options": {"queue": "collectors"},
            },
            "collect-rss-direct-every-30-min": {
                "task": "tasks.collect_rss_direct",
                "schedule": timedelta(minutes=30),
                "options": {"queue": "collectors"},
            },
            "collect-html-every-6-hours": {
                "task": "tasks.collect_html",
                "schedule": timedelta(hours=6),
                "options": {"queue": "collectors"},
            },
            # Periodic byline backfill — every 6h, processes up to 1500
            # extraction_version=2 articles missing byline per tick.
            # HTML-only extraction (JSON-LD → meta → CSS selectors),
            # zero LLM cost. Naturally drains as articles get filled in.
            "backfill-bylines-every-6h": {
                "task": "tasks.backfill_bylines_periodic",
                "schedule": timedelta(hours=6),
                "options": {"queue": "collectors"},
            },
            # Periodic tweet content enrichment — every 6h, free oEmbed,
            # catches v1→v2 upgrades and any transient failures.
            "backfill-tweets-every-6h": {
                "task": "tasks.backfill_tweets_periodic",
                "schedule": timedelta(hours=6),
                "options": {"queue": "collectors"},
            },
            # Backfill missing og:image thumbnails using Playwright (real
            # browser bypasses anti-bot rejection of httpx from data-center
            # IPs). Single batch task per fire — opens 1 Chromium, processes
            # up to 30 articles, closes. See backend/tasks/thumbnail_task.py.
            "fetch-og-images-every-10-min": {
                "task": "tasks.fetch_og_images_batch",
                "schedule": timedelta(minutes=10),
                "options": {"queue": "collectors"},
            },
            "process-nlp-every-30-seconds": {
                "task": "tasks.process_nlp_batch",
                "schedule": timedelta(seconds=30),
                "options": {"queue": "nlp"},
            },
            "reset-groq-keys-daily": {
                "task": "tasks.reset_groq_keys",
                "schedule": crontab(hour=0, minute=5),
                "options": {"queue": "default"},
            },
            "check-entity-dict-every-5-min": {
                "task": "tasks.check_entity_dict_version",
                "schedule": timedelta(minutes=5),
                "options": {"queue": "nlp"},
            },
            # ── External scrapers (atlas layers) — kept per cleanup spec ──
            "collectors-mandi-agmarknet-every-4h": {
                "task": "tasks.collectors.mandi_agmarknet",
                "schedule": timedelta(hours=4),
                "options": {"queue": "collectors"},
            },
            "collectors-cpcb-aqi-every-30-min": {
                "task": "tasks.collectors.cpcb_aqi",
                "schedule": timedelta(minutes=30),
                "options": {"queue": "collectors"},
            },
            "collectors-imd-weather-every-1h": {
                "task": "tasks.collectors.imd_weather",
                "schedule": timedelta(hours=1),
                "options": {"queue": "collectors"},
            },
            "collectors-tgspdcl-power-every-30-min": {
                "task": "tasks.collectors.tgspdcl_power",
                "schedule": timedelta(minutes=30),
                "options": {"queue": "collectors"},
            },
            "collectors-welfare-coverage-daily": {
                "task": "tasks.collectors.welfare_coverage",
                "schedule": crontab(hour=4, minute=15),
                "options": {"queue": "collectors"},
            },
            "collectors-acled-sink-every-6h": {
                "task": "tasks.collectors.acled_sink",
                "schedule": timedelta(hours=6),
                "options": {"queue": "collectors"},
            },
            # Nightly gold-set regression — 21:30 UTC = 03:00 IST
            "quality-gold-regression-nightly": {
                "task": "tasks.quality.gold_regression",
                "schedule": crontab(hour=21, minute=30),
                "options": {"queue": "nlp"},
            },
        },
    }
)


# ── Worker boot self-checks ─────────────────────────────────────
#
# Verify Playwright is usable so the 9 JS-rendered govt adapters
# (SEBI, SCI, NGT, MCA, ADB, IMF, UN, CERC, PNGRB) do not silently
# return zero rows on every collection. Logs CRITICAL on failure but
# does not abort the worker — httpx-direct adapters still need to run.
from celery.signals import worker_ready


@worker_ready.connect
def _govt_collector_self_check(**_kw) -> None:
    try:
        from backend.collectors.playwright_helper import assert_available_sync
        assert_available_sync()
    except Exception as exc:  # noqa: BLE001 — self-check must never crash worker
        import logging
        logging.getLogger(__name__).warning(
            "Playwright self-check skipped: %s", exc,
        )


# ── Catch-up: kick stale collectors on worker boot ─────────────────────
#
# Govt-doc and newspaper collections used to be once-daily crontabs, so a
# single missed window (worker restart, broker hiccup, source 5xx) left
# the pillar silent for 24h. The schedule is now every-12h, but as belt-
# and-braces this `worker_ready` handler queries the most recent
# `collected_at` per pillar and fires the collector immediately if the
# last successful run is more than 24 hours ago. The collector itself
# dedupes by URL so it's safe to fire — no-op if nothing new.
#
# Only the `documents` worker runs this; running it from every queue
# would re-fire the tasks several times on each restart.

@worker_ready.connect
def _collector_catch_up(sender=None, **_kw) -> None:  # noqa: D401, ANN001
    # Only the documents worker triggers catch-ups (both targets route
    # there now). Filter on hostname so the other workers stay quiet.
    hostname: str = getattr(sender, "hostname", "") or ""
    if "worker-documents" not in hostname:
        return

    import logging
    import psycopg2
    import os
    from datetime import datetime, timedelta as _td, timezone

    log = logging.getLogger(__name__)
    pg_url = os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://rig:rigpassword@rig-postgres:5432/rig",
    )

    # Tables to inspect → task to fire if stale.
    targets = [
        ("govt_documents", "tasks.collect_govt_documents"),
        ("newspaper_clippings", "tasks.collect_newspapers"),
    ]
    threshold = datetime.now(tz=timezone.utc) - _td(hours=24)

    try:
        with psycopg2.connect(pg_url) as conn, conn.cursor() as cur:
            for table, task_name in targets:
                cur.execute(f"SELECT MAX(collected_at) FROM {table};")
                last = cur.fetchone()[0]
                if last is None or last < threshold:
                    age = "never" if last is None else str(
                        datetime.now(tz=timezone.utc) - last
                    )
                    log.warning(
                        "Catch-up firing %s — last collected %s ago",
                        task_name, age,
                    )
                    app.send_task(task_name)
                else:
                    log.info(
                        "Catch-up skipped %s — last collected %s",
                        task_name, last.isoformat(),
                    )
    except Exception as exc:  # noqa: BLE001 — never crash the worker on boot
        log.warning("Collector catch-up skipped: %s", exc)
