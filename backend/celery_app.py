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

def _resolve_sync_url() -> str:
    explicit = os.environ.get("DATABASE_URL_SYNC", "")
    if explicit:
        return explicit
    # Derive from DATABASE_URL so the password is never lost when
    # DATABASE_URL_SYNC is missing from .env (e.g. recreate without --env-file).
    async_url = os.environ.get("DATABASE_URL", "")
    if async_url:
        return async_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return "postgresql://rig:rigpassword@rig-postgres:5432/rig"

DATABASE_URL_SYNC: str = _resolve_sync_url()

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
        # 5-min journalist-name extractor — parses byline → author_name, no LLM
        "backend.tasks.enrich_journalist",
        # Weekly circuit-breaker reset — revives sources that hit health=0
        "backend.tasks.source_health_reset_task",
        # 6-hourly RSS URL refresher — follows 30x redirects, updates rss_url
        "backend.tasks.rss_url_refresh_task",
        # Periodic tweet enrichment — catches v1→v2 upgrades + retries
        "backend.tasks.substrate.tweet_periodic_task",
        # Nightly gold-set regression for the data-quality observability stack
        "backend.tasks.quality_regression_task",
        # 15-min postfix that keeps NEW articles clean (lang + is_future)
        "backend.tasks.quality_postfix_task",
        # Daily quality comparator — new articles vs backfilled baseline
        "backend.tasks.quality_compare_task",
        # 30-min event-cluster importance refresh (T5)
        "backend.tasks.cluster_importance_task",
        # Hourly entity-mention aggregator (T6)
        "backend.tasks.entity_mention_task",
        # Nightly v2→v3 upgrade pass (translation + register fields)
        "backend.tasks.v3_upgrade_task",
        # Newspaper clippings: daily collection fan-out + substrate enrichment
        "backend.tasks.newspaper_task",
        "backend.tasks.clipping_enrich",
        # YouTube clips: discovery + extraction + substrate enrichment drain
        "backend.tasks.youtube_task",
        "backend.tasks.youtube_clip_enrich",
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
            # Byline / tweet substrate backfill — pure HTTP fetching, light
            # parsing, no LLM. Shares the collectors queue with HTML scraping.
            "tasks.backfill_bylines_periodic": {"queue": "collectors"},
            "tasks.backfill_tweets_periodic": {"queue": "collectors"},
            # Journalist-name parser — reads byline, writes author_name. No LLM.
            "tasks.enrich_journalist_batch": {"queue": "nlp"},
            # Weekly source-health reset (revive circuit-breaker-locked sources)
            "tasks.reset_source_circuit_breakers": {"queue": "collectors"},
            # 6-hourly RSS URL refresher
            "tasks.refresh_rss_urls": {"queue": "collectors"},
            # External-source collectors (atlas layers) — kept per cleanup spec.
            "tasks.collectors.mandi_agmarknet": {"queue": "collectors"},
            "tasks.collectors.cpcb_aqi":        {"queue": "collectors"},
            "tasks.collectors.imd_weather":     {"queue": "collectors"},
            "tasks.collectors.tgspdcl_power":   {"queue": "collectors"},
            "tasks.collectors.welfare_coverage":{"queue": "collectors"},
            "tasks.collectors.acled_sink":      {"queue": "collectors"},
            # Brief generation — dedicated brief queue (worker-relevance)
            "tasks.generate_all_briefs":        {"queue": "brief"},
            "tasks.generate_brief_for_user":    {"queue": "brief"},
            # Newspaper clippings — collection + substrate enrichment both on
            # the documents queue (design §6.2: NEVER nlp — that's article NLP).
            "tasks.collect_newspapers":          {"queue": "documents"},
            "tasks.collect_newspapers_fallback": {"queue": "documents"},
            "tasks.collect_one_newspaper":       {"queue": "documents"},
            "tasks.enrich_clipping":             {"queue": "documents"},
            "tasks.drain_pending_clippings":     {"queue": "documents"},
            # YouTube: discovery on collectors (RSS safe from Hetzner),
            # transcript fetch via relay + extraction + enrichment on youtube.
            "tasks.discover_youtube_channels":    {"queue": "collectors"},
            "tasks.fetch_youtube_transcripts":    {"queue": "youtube"},
            "tasks.run_youtube_extraction":       {"queue": "youtube"},
            "tasks.enrich_clip":                  {"queue": "youtube"},
            "tasks.drain_pending_clips":          {"queue": "youtube"},
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
            "enrich-journalist-every-5-minutes": {
                "task": "tasks.enrich_journalist_batch",
                "schedule": timedelta(minutes=5),
                "options": {"queue": "nlp"},
                "kwargs": {"batch_size": 200},
            },
            # Weekly Monday 00:00 UTC — revive sources whose health hit the floor
            "reset-source-circuit-breakers-weekly": {
                "task": "tasks.reset_source_circuit_breakers",
                "schedule": crontab(hour=0, minute=0, day_of_week=1),
                "options": {"queue": "collectors"},
            },
            # Every 6 hours — follow 30x redirects on low-health sources, save new URL
            "refresh-rss-urls-every-6h": {
                "task": "tasks.refresh_rss_urls",
                "schedule": crontab(hour="*/6", minute=20),
                "options": {"queue": "collectors"},
                "kwargs": {"limit": 80},
            },
            "reset-groq-keys-daily": {
                "task": "tasks.reset_groq_keys",
                "schedule": crontab(hour=0, minute=5),
                "options": {"queue": "default"},
            },
            # Newspaper clippings — two idempotent passes (design §3).
            # PRIMARY 02:00 UTC = 07:30 IST: fan out every active paper.
            "collect-newspapers-primary": {
                "task": "tasks.collect_newspapers",
                "schedule": crontab(hour=2, minute=0),
                "options": {"queue": "documents"},
            },
            # FALLBACK 03:00 UTC = 08:30 IST: only papers with NO clipping
            # row for today (covers late CareersWave uploads + failures).
            "collect-newspapers-fallback": {
                "task": "tasks.collect_newspapers_fallback",
                "schedule": crontab(hour=3, minute=0),
                "options": {"queue": "documents"},
            },
            # Catch-up drain for any clipping left in substrate_status=pending
            # (e.g. enrich enqueue lost on a restart). Cheap no-op when empty.
            "drain-pending-clippings-every-10-min": {
                "task": "tasks.drain_pending_clippings",
                "schedule": timedelta(minutes=10),
                "kwargs": {"limit": 50},
                "options": {"queue": "documents"},
            },
            # YouTube discovery — RSS Atom feed per active channel, every 30 min.
            # Safe from Hetzner (RSS not IP-blocked).
            "discover-youtube-channels-every-30-min": {
                "task": "tasks.discover_youtube_channels",
                "schedule": timedelta(minutes=30),
                "options": {"queue": "collectors"},
            },
            # YouTube transcript fetch via relay — Hetzner calls the Tailscale
            # relay pool — hard-won rate calibration. EMPIRICAL: a single residential
            # IP gets YouTube-blocked above ~40/hr (desktop died at ~60/hr; Trijya was
            # clean at 40/hr in the pool but blocked after 37 fetches when pushed to
            # 60/hr solo). So the SAFE sustained per-IP rate is ~20/hr. Beat sets the
            # TOTAL attempt rate, round-robined across the pool, so:
            #   total_rate = ~20/hr  x  (number of healthy IPs).
            # limit 1 / 3 min = ~20/hr — safe for one IP, lets a blocked IP recover.
            # When the desktop heals and rejoins the pool, raise to limit 2 (40/hr,
            # ~20 each). Political/newest first so the important content drains first.
            # TEMPORARY COOL-DOWN (2026-06-12): both residential IPs got throttled
            # on YouTube's caption endpoint from a day of debugging fetches. Paused
            # to ~2/hr so they rest and recover; the occasional probe auto-resumes
            # flow once an IP clears. Restore to limit 1 / 3 min (~20/hr) once a
            # live fetch through Trijya succeeds again.
            "fetch-youtube-transcripts-every-3-min": {
                "task": "tasks.fetch_youtube_transcripts",
                "schedule": timedelta(minutes=360),
                "kwargs": {"limit": 1},
                "options": {"queue": "youtube"},
            },
            # YouTube extraction — drain transcribed rows into clips, every 5 min.
            "run-youtube-extraction-every-5-min": {
                "task": "tasks.run_youtube_extraction",
                "schedule": timedelta(minutes=5),
                "kwargs": {"limit": 10},
                "options": {"queue": "youtube"},
            },
            # YouTube clip substrate drain — catch-up for any clip left pending
            # after extraction (e.g. worker restart during batch). Bounded at 20
            # per tick so the youtube worker (concurrency=1) isn't overwhelmed.
            "drain-pending-clips-every-10-min": {
                "task": "tasks.drain_pending_clips",
                "schedule": timedelta(minutes=10),
                "kwargs": {"limit": 20},
                "options": {"queue": "youtube"},
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
            # DISABLED 2026-05-29: the v1→v2 nightly repass (register +
            # translation only) is now redundant — new articles go straight
            # to v3 via the drain-tick task below, and v3 already produces
            # register_style + english_translation + the full fact layer.
            # Removing the "v2 step" so articles aren't diverted to a partial
            # version. (The 23,971 legacy v1 articles are an accepted blind
            # spot; re-extracting them would need a one-off claim-filter run.)
            # "v3-upgrade-nightly": {
            #     "task": "tasks.quality.v3_upgrade",
            #     "schedule": crontab(hour=22, minute=30),
            #     "options": {"queue": "nlp"},
            # },
            # Daily contradiction detection — 23:00 UTC = 04:30 IST
            "contradictions-daily": {
                "task": "tasks.refresh_contradictions",
                "schedule": crontab(hour=23, minute=0),
                "options": {"queue": "nlp"},
            },
            # Daily brief generation fan-out — 00:30 UTC = 06:00 IST
            # Iterates every user with brief page access and enqueues a
            # per-user generate_brief_for_user task on the brief queue.
            "generate-briefs-daily": {
                "task": "tasks.generate_all_briefs",
                "schedule": crontab(hour=0, minute=30),
                "options": {"queue": "brief"},
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
        ("clippings", "tasks.collect_newspapers"),
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
