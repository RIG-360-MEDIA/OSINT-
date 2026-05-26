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
        # Daily LLM-generated summaries for the /coverage hub panels
        "backend.tasks.coverage_summary_task",
        # /coverage/articles rebuild — RAG-integrated analyst surface tasks
        "backend.tasks.coverage",
        "backend.tasks.coverage.user_cards_task",
        # Note: breaking_task is on a different branch and not deployed here.
        "backend.tasks.coverage.contradictions_task",
        "backend.tasks.coverage.top_stories_task",
        "backend.tasks.coverage.coverage_gaps_task",
        "backend.tasks.coverage.notifications_task",
        "backend.tasks.coverage.claims_quotes_task",
        # Periodic byline backfill — runs every 6h, HTML-only, no LLM cost
        "backend.tasks.substrate.byline_periodic_task",
        # Periodic tweet enrichment — catches v1→v2 upgrades + retries
        "backend.tasks.substrate.tweet_periodic_task",
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
            "tasks.quality.postfix": {"queue": "nlp"},
            "tasks.quality.compare": {"queue": "nlp"},
            "tasks.quality.cluster_importance": {"queue": "nlp"},
            "tasks.quality.entity_mentions": {"queue": "nlp"},
            "tasks.quality.v3_upgrade": {"queue": "nlp"},
            "tasks.fetch_og_images_batch": {"queue": "collectors"},
            "tasks.process_nlp_batch": {"queue": "nlp"},
            "tasks.score_relevance_batch": {"queue": "relevance"},
            "tasks.score_unscored_articles": {"queue": "relevance"},
            "tasks.backfill_user_relevance": {"queue": "relevance"},
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
            # /coverage/articles rebuild
            "tasks.refresh_user_cards": {"queue": "nlp"},
            "tasks.retry_unrefreshed_cards": {"queue": "nlp"},
            "tasks.spawn_sub_cards": {"queue": "nlp"},
            "tasks.detect_breaking_events": {"queue": "nlp"},
            "tasks.classify_pending_breaking_clusters": {"queue": "nlp"},
            "tasks.refresh_contradictions": {"queue": "nlp"},
            "tasks.refresh_top_stories": {"queue": "nlp"},
            "tasks.refresh_coverage_gaps": {"queue": "nlp"},
            "tasks.evaluate_notification_rules": {"queue": "nlp"},
            "tasks.extract_claims_quotes_for_article": {"queue": "nlp"},
            "tasks.extract_pending_claims_quotes": {"queue": "nlp"},
            "tasks.translate_pending_quotes": {"queue": "nlp"},
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
            # Byline backfill — pure HTTP fetching, light parsing, no LLM.
            # Routes to collectors so it shares I/O with HTML scraping.
            "tasks.backfill_bylines_periodic": {"queue": "collectors"},
            "tasks.backfill_tweets_periodic": {"queue": "collectors"},
            "tasks.cm.refresh_voice_share": {"queue": "social"},
            "tasks.cm.refresh_issue_hourly": {"queue": "social"},
            "tasks.cm.refresh_constituency_heatmap": {"queue": "social"},
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
            # ── /coverage/articles rebuild — analytics tasks ──
            # All gated by per-task FEATURE_* env flags so disabling
            # is a config flip, no beat reload needed.
            "refresh-user-cards-daily-0130-utc": {
                "task": "tasks.refresh_user_cards",
                "schedule": crontab(hour=1, minute=30),
                "options": {"queue": "nlp"},
            },
            # Fast-retry driver — picks up cards that were created
            # during a Groq-quota dip and never got their summary
            # generated. Runs every 5 min, capped at 5 cards/fire.
            "retry-unrefreshed-user-cards-every-5-min": {
                "task": "tasks.retry_unrefreshed_cards",
                "schedule": timedelta(minutes=5),
                "options": {"queue": "nlp"},
            },
            "detect-breaking-events-every-15-min": {
                "task": "tasks.detect_breaking_events",
                "schedule": timedelta(minutes=15),
                "options": {"queue": "nlp"},
            },
            # Backfill classification on clusters whose Stage-1 Groq call
            # failed at detection time (quota contention with extraction).
            # Without this, real Telangana / India clusters silently
            # disappear whenever Groq is throttled.
            "classify-pending-breaking-every-5-min": {
                "task": "tasks.classify_pending_breaking_clusters",
                "schedule": timedelta(minutes=5),
                "options": {"queue": "nlp"},
            },
            # Translates pre-existing non-English quotes to English so
            # the Recent Quotes panel renders readable text. Quotes
            # extracted post-migration-049 already include translations
            # at extract time; this driver only catches the legacy backlog.
            "translate-pending-quotes-every-5-min": {
                "task": "tasks.translate_pending_quotes",
                "schedule": timedelta(minutes=5),
                "options": {"queue": "nlp"},
            },
            "refresh-contradictions-daily-0430-utc": {
                "task": "tasks.refresh_contradictions",
                "schedule": crontab(hour=4, minute=30),
                "options": {"queue": "nlp"},
            },
            "refresh-top-stories-every-2h": {
                "task": "tasks.refresh_top_stories",
                "schedule": timedelta(hours=2),
                "options": {"queue": "nlp"},
            },
            "refresh-coverage-gaps-daily-0500-utc": {
                "task": "tasks.refresh_coverage_gaps",
                "schedule": crontab(hour=5, minute=0),
                "options": {"queue": "nlp"},
            },
            "evaluate-notification-rules-every-15-min": {
                "task": "tasks.evaluate_notification_rules",
                "schedule": timedelta(minutes=15),
                "options": {"queue": "nlp"},
            },
            "extract-pending-claims-quotes-every-5-min": {
                # Foundational extraction driver. process_nlp_batch never
                # fires per-article extraction itself, so without this the
                # claims_extracted=FALSE backlog grows forever. Scans the
                # unextracted pile, queues 50 articles per fire. Always on.
                "task": "tasks.extract_pending_claims_quotes",
                "schedule": timedelta(minutes=5),
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
            # 15-min postfix keeps NEW articles auto-clean
            "quality-postfix-every-15-min": {
                "task": "tasks.quality.postfix",
                "schedule": timedelta(minutes=15),
                "kwargs": {"lookback_hours": 1},
                "options": {"queue": "nlp"},
            },
            # Daily new-vs-baseline comparison — 22:00 UTC = 03:30 IST
            "quality-compare-daily": {
                "task": "tasks.quality.compare",
                "schedule": crontab(hour=22, minute=0),
                "options": {"queue": "nlp"},
            },
            # Event-cluster importance refresh every 30 min
            "cluster-importance-every-30-min": {
                "task": "tasks.quality.cluster_importance",
                "schedule": timedelta(minutes=30),
                "options": {"queue": "nlp"},
            },
            # Entity-mention aggregator every 60 min
            "entity-mentions-every-60-min": {
                "task": "tasks.quality.entity_mentions",
                "schedule": timedelta(minutes=60),
                "options": {"queue": "nlp"},
            },
            # Nightly v3 upgrade — 22:30 UTC = 04:00 IST (heavy batch)
            "v3-upgrade-nightly": {
                "task": "tasks.quality.v3_upgrade",
                "schedule": crontab(hour=22, minute=30, day_of_week=0),  # weekly Sun — backfill only
                "options": {"queue": "nlp"},
            },
            # Fast-loop v3 upgrade every 2h — catches new articles within
            # 2h of substrate completion instead of waiting for nightly.
            # B-fix 2026-05-26: nightly run hit SoftTimeLimitExceeded so
            # new articles sat at v2 for up to 24h before being upgraded.
            "v3-upgrade-fast-loop": {
                "task": "tasks.quality.v3_upgrade",
                "schedule": timedelta(hours=2),
                "options": {"queue": "nlp"},
            },
            # Daily contradiction detection — 23:00 UTC = 04:30 IST
            "contradictions-daily": {
                "task": "tasks.refresh_contradictions",
                "schedule": crontab(hour=23, minute=0),
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
