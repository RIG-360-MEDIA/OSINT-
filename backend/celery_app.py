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
        "backend.tasks.youtube_task",
        "backend.tasks.govt_task",
        "backend.tasks.govt_relevance_task",
        "backend.tasks.govt_doctor_task",
        "backend.tasks.social_task",
        "backend.tasks.social_briefing_task",
        "backend.tasks.social_intel_task",
        "backend.tasks.newspaper_task",
        # Playwright-based og:image backfill (post-deploy thumbnail gap)
        "backend.tasks.thumbnail_task",
        # Playwright Telugu-daily scraper (Eenadu / Sakshi / AJ — no public RSS)
        "backend.collectors.telugu_scraper",
        # Daily brief auto-generation (P10 / fix-brief-prod-readiness P1.5)
        "backend.tasks.brief_task",
        # Brief quality scorecard cron (fix-brief-prod-readiness P2.10)
        "backend.tasks.brief_quality_task",
        # CM Page political-intelligence tasks
        "backend.tasks.cm.stance_task",
        "backend.tasks.cm.speakers_task",
        "backend.tasks.cm.issues_task",
        "backend.tasks.cm.dissent_task",
        "backend.tasks.cm.counter_narrative_task",
        "backend.tasks.cm.refresh_views_task",
        "backend.tasks.cm.risk_window_task",
        "backend.tasks.cm.promise_task",
        "backend.tasks.cm.backfill_newspaper_sentiment_task",
        "backend.tasks.cm.exploitation_index_task",
        # CM Page v2 — district resolution + LLM auto-publish stack
        "backend.tasks.cm.backfill_district_geo",
        "backend.tasks.cm.lead_headline_task",
        "backend.tasks.cm.analysis_column_task",
        "backend.tasks.cm.action_queue_task",
        # CM Page v2 — external-source collectors (atlas layers)
        "backend.tasks.collectors.mandi_agmarknet_task",
        "backend.tasks.collectors.cpcb_aqi_task",
        "backend.tasks.collectors.imd_weather_task",
        "backend.tasks.collectors.tgspdcl_power_task",
        "backend.tasks.collectors.welfare_coverage_task",
        "backend.tasks.collectors.acled_sink_task",
        # Daily LLM-generated summaries for the /coverage hub panels
        "backend.tasks.coverage_summary_task",
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
            "tasks.fetch_og_images_batch": {"queue": "collectors"},
            "tasks.scrape_telugu_dailies": {"queue": "collectors"},
            "tasks.collect_youtube": {"queue": "youtube"},
            "tasks.collect_govt_documents": {"queue": "documents"},
            "tasks.govt_collection_doctor": {"queue": "documents"},
            # Newspaper collection moved off the busy `collectors` queue
            # (which has concurrency=1 and is regularly blocked by
            # 30-60 minute RSS scrapes). Lives on `documents` queue
            # alongside govt-doc collection — both are heavy I/O and
            # benefit from the dedicated 2-worker pool there.
            "tasks.score_govt_doc_relevance": {"queue": "relevance"},
            "tasks.score_govt_doc_for_all_users": {"queue": "relevance"},
            "tasks.process_nlp_batch": {"queue": "nlp"},
            "tasks.score_relevance_batch": {"queue": "relevance"},
            "tasks.score_unscored_articles": {"queue": "relevance"},
            "tasks.generate_all_briefs": {"queue": "brief"},
            "tasks.generate_brief_for_user": {"queue": "brief"},
            "tasks.score_brief_quality": {"queue": "brief"},
            "tasks.collect_reddit": {"queue": "social"},
            "tasks.collect_telegram": {"queue": "social"},
            "tasks.backfill_social_entity_matches": {"queue": "social"},
            "tasks.translate_pending_social_posts": {"queue": "social"},
            "tasks.cluster_recent_social_posts": {"queue": "social"},
            "tasks.recompute_social_baselines": {"queue": "social"},
            "tasks.detect_social_events": {"queue": "social"},
            "tasks.compose_social_summary": {"queue": "social"},
            "tasks.auto_promote_subjects": {"queue": "social"},
            "tasks.aggregate_social_sentiment_daily": {"queue": "nlp"},
            "tasks.collect_newspapers": {"queue": "documents"},
            "tasks.refresh_coverage_summaries": {"queue": "nlp"},
            # CM Page tasks. Heavy LLM work routes to `nlp`; cheap
            # aggregation/refresh work routes to `social` to avoid
            # competing with article NLP for the nlp pool.
            "tasks.cm.tag_stance": {"queue": "nlp"},
            "tasks.cm.extract_speakers": {"queue": "nlp"},
            "tasks.cm.cluster_issues": {"queue": "nlp"},
            "tasks.cm.score_dissent": {"queue": "nlp"},
            "tasks.cm.generate_counter_narratives": {"queue": "nlp"},
            "tasks.cm.score_promise_status": {"queue": "nlp"},
            "tasks.cm.refresh_risk_window": {"queue": "nlp"},
            "tasks.cm.backfill_newspaper_sentiment": {"queue": "nlp"},
            "tasks.cm.compute_exploitation_index": {"queue": "social"},
            "tasks.cm.refresh_voice_share": {"queue": "social"},
            "tasks.cm.refresh_issue_hourly": {"queue": "social"},
            "tasks.cm.refresh_constituency_heatmap": {"queue": "social"},
            # CM Page v2 — district resolution backfill on `nlp` (gazetteer
            # match against entities_extracted; no re-NER, low cost).
            "tasks.cm.backfill_district_geo": {"queue": "nlp"},
            # CM Page v2 — LLM auto-publish stack on `nlp`.
            "tasks.cm.lead_headline": {"queue": "nlp"},
            "tasks.cm.analysis_column": {"queue": "nlp"},
            "tasks.cm.action_queue": {"queue": "nlp"},
            # CM Page v2 — external-source collectors. Routed to the
            # dedicated `collectors` queue so heavy LLM/article NLP work
            # never blocks them and they never block article ingest.
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
            # Playwright og:image batch — opens one Chromium, processes
            # up to 30 articles, closes. See backend/tasks/thumbnail_task.py.
            "fetch-og-images-every-10-min": {
                "task": "tasks.fetch_og_images_batch",
                "schedule": timedelta(minutes=10),
                "options": {"queue": "collectors"},
            },
            # Telugu-daily scraper: hits Eenadu (×33 districts), Sakshi/AJ
            # are config-stubbed in the module pending bot bypass work.
            "scrape-telugu-dailies-every-30-min": {
                "task": "tasks.scrape_telugu_dailies",
                "schedule": timedelta(minutes=30),
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
            # Brief quality rubric scorecard — runs once a day, ~30 min
            # after the daily fan-out so yesterday's briefs are already
            # in the table. fix/brief-prod-readiness P2.10.
            "score-brief-quality-daily": {
                "task": "tasks.score_brief_quality",
                "schedule": crontab(hour=1, minute=0),
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
            "collect-youtube-every-2h": {
                # Bumped from 6h → 2h: at the old cadence the wires were
                # showing day-old clips even when fresh content existed
                # on monitored channels. The YouTube transcript fetch is
                # the slow step (~30-60s per video) but happens on the
                # dedicated `youtube` queue, so it never blocks anything.
                "task": "tasks.collect_youtube",
                "schedule": timedelta(hours=2),
                "options": {"queue": "youtube"},
            },
            # Govt docs and newspapers historically fired once a day on a
            # crontab. When that single window missed (worker busy / blip)
            # the pillar went silent for 24h. Both now fire every 12 hours
            # so a missed window self-heals on the next tick. The collector
            # itself dedupes by URL so re-running is a no-op when there's
            # nothing new — cheap.
            "collect-govt-docs-every-12h": {
                "task": "tasks.collect_govt_documents",
                "schedule": timedelta(hours=12),
                "options": {"queue": "documents"},
            },
            "govt-doctor-every-12h": {
                "task": "tasks.govt_collection_doctor",
                "schedule": timedelta(hours=12),
                "options": {"queue": "documents"},
            },
            # ── Tiered cadence per platform ──
            "collect-reddit-hot-every-15-min": {
                "task": "tasks.collect_reddit",
                "schedule": timedelta(minutes=15),
                "kwargs": {"tier": "hot"},
                "options": {"queue": "social"},
            },
            "collect-reddit-warm-every-1-hour": {
                "task": "tasks.collect_reddit",
                "schedule": timedelta(hours=1),
                "kwargs": {"tier": "warm"},
                "options": {"queue": "social"},
            },
            "collect-reddit-cold-every-6-hours": {
                "task": "tasks.collect_reddit",
                "schedule": timedelta(hours=6),
                "kwargs": {"tier": "cold"},
                "options": {"queue": "social"},
            },
            "collect-telegram-hot-every-15-min": {
                "task": "tasks.collect_telegram",
                "schedule": timedelta(minutes=15),
                "kwargs": {"tier": "hot"},
                "options": {"queue": "social"},
            },
            "collect-telegram-warm-every-1-hour": {
                "task": "tasks.collect_telegram",
                "schedule": timedelta(hours=1),
                "kwargs": {"tier": "warm"},
                "options": {"queue": "social"},
            },
            "collect-telegram-cold-every-6-hours": {
                "task": "tasks.collect_telegram",
                "schedule": timedelta(hours=6),
                "kwargs": {"tier": "cold"},
                "options": {"queue": "social"},
            },
            "translate-social-posts-every-10-min": {
                "task": "tasks.translate_pending_social_posts",
                "schedule": timedelta(minutes=10),
                "options": {"queue": "social"},
            },
            "cluster-social-posts-every-15-min": {
                "task": "tasks.cluster_recent_social_posts",
                "schedule": timedelta(minutes=15),
                "options": {"queue": "social"},
            },
            "auto-promote-social-subjects-nightly": {
                "task": "tasks.auto_promote_subjects",
                "schedule": crontab(hour=2, minute=0),
                "options": {"queue": "social"},
            },
            "recompute-social-baselines-nightly": {
                "task": "tasks.recompute_social_baselines",
                "schedule": crontab(hour=2, minute=30),
                "options": {"queue": "social"},
            },
            "detect-social-events-every-30-min": {
                "task": "tasks.detect_social_events",
                "schedule": timedelta(minutes=30),
                "options": {"queue": "social"},
            },
            "compose-social-summary-every-6-hours": {
                "task": "tasks.compose_social_summary",
                "schedule": timedelta(hours=6),
                "options": {"queue": "social"},
            },
            "aggregate-social-sentiment-hourly": {
                "task": "tasks.aggregate_social_sentiment_daily",
                "schedule": crontab(minute=15),
                "options": {"queue": "nlp"},
            },
            "collect-newspapers-daily-0430-utc": {
                "task": "tasks.collect_newspapers",
                # 04:30 UTC = 10:00 IST — most Indian dailies publish their
                # e-paper editions by mid-morning. Daily crontab (not 12h
                # timedelta) so a missed fire isn't repeated within the
                # same calendar day, and the next fire time isn't reset
                # by container restarts.
                "schedule": crontab(hour=4, minute=30),
                # Moved off `collectors` queue (concurrency=1, blocked by
                # long RSS scrapes) onto `documents` queue (2 workers,
                # dedicated for heavy I/O like newspapers + govt PDFs).
                "options": {"queue": "documents"},
            },
            "refresh-coverage-summaries-daily-0415-utc": {
                # Regenerates the 2-3 line summary shown beneath each
                # panel on the /coverage hub. Five small Groq calls
                # (FAST_MODEL, ~150 tokens each), all under 30 s.
                # Slotted at 04:15 UTC so it runs after the night's
                # collection is settled but before the 04:30 newspaper
                # window. See backend/tasks/coverage_summary_task.py.
                "task": "tasks.refresh_coverage_summaries",
                "schedule": crontab(hour=4, minute=15),
                "options": {"queue": "nlp"},
            },
            # ── CM Page political-intelligence schedule ──
            #
            # Heavy LLM work runs on `nlp`; cheap aggregations on `social`.
            # Frequencies match the per-section TTLs in
            # backend/nlp/cm/cache.py so the cache is rarely warmer than
            # the underlying data.
            "cm-tag-stance-every-5-min": {
                "task": "tasks.cm.tag_stance",
                "schedule": timedelta(minutes=5),
                "options": {"queue": "nlp"},
            },
            "cm-extract-speakers-every-10-min": {
                "task": "tasks.cm.extract_speakers",
                "schedule": timedelta(minutes=10),
                "options": {"queue": "nlp"},
            },
            "cm-cluster-issues-incremental-2h": {
                "task": "tasks.cm.cluster_issues",
                "schedule": timedelta(hours=2),
                "options": {"queue": "nlp"},
            },
            "cm-cluster-issues-daily": {
                "task": "tasks.cm.cluster_issues",
                "schedule": crontab(hour=3, minute=0),
                "options": {"queue": "nlp"},
            },
            "cm-score-dissent-daily": {
                "task": "tasks.cm.score_dissent",
                "schedule": crontab(hour=4, minute=0),
                "options": {"queue": "nlp"},
            },
            "cm-generate-counter-narratives-daily": {
                "task": "tasks.cm.generate_counter_narratives",
                "schedule": crontab(hour=5, minute=0),
                "options": {"queue": "nlp"},
            },
            "cm-score-promise-status-daily": {
                "task": "tasks.cm.score_promise_status",
                "schedule": crontab(hour=6, minute=0),
                "options": {"queue": "nlp"},
            },
            "cm-refresh-risk-window-every-6h": {
                "task": "tasks.cm.refresh_risk_window",
                "schedule": timedelta(hours=6),
                "options": {"queue": "nlp"},
            },
            "cm-backfill-newspaper-sentiment-daily": {
                "task": "tasks.cm.backfill_newspaper_sentiment",
                "schedule": crontab(hour=1, minute=30),
                "options": {"queue": "nlp"},
            },
            "cm-refresh-issue-hourly-every-30-min": {
                "task": "tasks.cm.refresh_issue_hourly",
                "schedule": timedelta(minutes=30),
                "options": {"queue": "social"},
            },
            "cm-refresh-voice-share-every-6h": {
                "task": "tasks.cm.refresh_voice_share",
                "schedule": timedelta(hours=6),
                "options": {"queue": "social"},
            },
            "cm-compute-exploitation-index-every-2h": {
                "task": "tasks.cm.compute_exploitation_index",
                "schedule": timedelta(hours=2),
                "options": {"queue": "social"},
            },
            "cm-refresh-constituency-heatmap-daily": {
                "task": "tasks.cm.refresh_constituency_heatmap",
                "schedule": crontab(hour=2, minute=15),
                "options": {"queue": "social"},
            },
            # ── CM Page v2 — district backfill (resilience) ──
            #
            # Nightly catch-up for any articles processed before the
            # district-resolution NLP step shipped, plus any rows that
            # got an entities update later. Idempotent ON CONFLICT.
            "cm-backfill-district-geo-nightly": {
                "task": "tasks.cm.backfill_district_geo",
                "schedule": crontab(hour=3, minute=30),
                "options": {"queue": "nlp"},
            },
            # ── CM Page v2 — LLM auto-publish stack ──
            "cm-lead-headlines-every-5-min": {
                "task": "tasks.cm.lead_headline",
                "schedule": timedelta(minutes=5),
                "options": {"queue": "nlp"},
            },
            "cm-analysis-column-hourly": {
                # Bumped from 3x/day to hourly per user request — gives
                # the LLM more chances to land a valid draft if a single
                # call hits a Groq rate-limit wall. The cite-id gate
                # still rejects unsubstantiated drafts.
                "task": "tasks.cm.analysis_column",
                "schedule": timedelta(hours=1),
                "options": {"queue": "nlp"},
            },
            "cm-action-queue-every-15-min": {
                "task": "tasks.cm.action_queue",
                "schedule": timedelta(minutes=15),
                "options": {"queue": "nlp"},
            },
            # ── CM Page v2 — external scrapers ──
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
