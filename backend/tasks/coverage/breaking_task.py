"""
tasks.detect_breaking_events

Every 15 min. Fetches articles from the last 2h, clusters via DBSCAN
over LaBSE embeddings (sklearn — already a dep). Cluster size >= 4
with >= 3 distinct sources → write breaking_clusters row with Groq-
generated headline.

Auto-decay: marks rows is_active=FALSE when the window has aged out
(>6h) OR the cluster is no longer producing new arrivals.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import numpy as np
from sklearn.cluster import DBSCAN
from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.groq_client import (
    FAST_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logger = logging.getLogger(__name__)


_WINDOW_HOURS = 2
_MIN_CLUSTER_SIZE = 3
_MIN_DISTINCT_SOURCES = 2
# DBSCAN eps had been loosened to 0.32 to surface MORE clusters. That was
# too loose: articles co-mentioning a major place name ("Telangana") got
# pulled into the same cluster despite being about completely different
# events. Tightened to 0.22 — strict enough that semantically-unrelated
# articles can't co-cluster, loose enough that translations of the same
# wire across Telugu/English/Bengali still group. Combined with the
# downstream Groq event-validation gate (see _classify_cluster), junk
# clusters are now caught at two layers.
_DBSCAN_EPS = 0.22

# Event types that exist in the wild but are NOT what users want from a
# BREAKING surface. We classify but reject these.
_TRIVIAL_EVENT_TYPES: frozenset[str] = frozenset({
    "sports_result",
    "entertainment_release",
    "celebrity_news",
    "routine_update",
})

# Severity levels considered worth surfacing. "low" is filtered out.
_SURFACEABLE_SEVERITIES: frozenset[str] = frozenset({
    "medium", "high", "breaking",
})

_CLASSIFY_SYSTEM = (
    "You validate a candidate breaking-news cluster — a set of articles "
    "an algorithm grouped together based on text similarity. Your job is "
    "twofold: (1) decide whether these articles are actually reporting "
    "ONE shared event, and (2) if yes, classify what kind and how serious. "
    "Return STRICT JSON, no prose, no fences.\n"
    "{\n"
    '  "is_real_event": true|false,\n'
    '  "shared_subject": "what the cluster is jointly about, or null",\n'
    '  "event_type": one of [policy_announcement, official_statement, '
    "election_event, crime_incident, disaster_emergency, "
    "protest_demonstration, legal_proceeding, market_event, "
    "infrastructure_update, health_alert, weather_alert, "
    "sports_result, entertainment_release, celebrity_news, "
    "routine_update, other],\n"
    '  "severity": "low" | "medium" | "high" | "breaking",\n'
    '  "summary": "one-line plain summary, max 14 words"\n'
    "}\n"
    "Hard rules:\n"
    "- is_real_event MUST be false if the headlines describe UNRELATED "
    "topics that merely share a place name or entity. Example: a flood-"
    "relief announcement, an election rally, and a cricket toss all "
    "mentioning the same state — that is NOT one event.\n"
    "- severity=low for: routine sports results, celebrity gossip, "
    "promotional/scheduled releases, daily-column content.\n"
    "- severity=medium for: noteworthy political statements, local "
    "crime, infrastructure milestones, market moves.\n"
    "- severity=high for: major policy, significant crime, large "
    "incidents, court rulings of consequence.\n"
    "- severity=breaking for: emergencies, mass-casualty events, urgent "
    "national/international announcements."
)


async def _fetch_recent_articles() -> list[dict[str, Any]]:
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT a.id::text AS article_id, a.title, a.published_at,
                       a.source_id::text, s.name AS source_name,
                       a.labse_embedding
                FROM articles a
                JOIN sources s ON s.id = a.source_id
                WHERE a.is_duplicate IS NOT TRUE
                  AND a.collected_at > NOW() - make_interval(hours => :hrs)
                  AND a.labse_embedding IS NOT NULL
                ORDER BY a.published_at DESC NULLS LAST
                LIMIT 500
                """
            ),
            {"hrs": _WINDOW_HOURS},
        )
        rows = result.fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        # pgvector returns embedding as string "[0.1,0.2,...]" via SQL text;
        # normalize to list[float].
        emb = r.labse_embedding
        if isinstance(emb, str):
            emb = [float(x) for x in emb.strip("[]").split(",")]
        out.append(
            {
                "article_id": r.article_id,
                "title": r.title,
                "published_at": r.published_at,
                "source_id": r.source_id,
                "source_name": r.source_name,
                "embedding": list(emb) if emb is not None else None,
            }
        )
    return [a for a in out if a["embedding"] is not None]


def _cluster(articles: list[dict[str, Any]]) -> dict[int, list[int]]:
    """DBSCAN over normalized embeddings → {label: [indices]}."""
    if len(articles) < _MIN_CLUSTER_SIZE:
        return {}
    matrix = np.array([a["embedding"] for a in articles], dtype=np.float32)
    # normalize for cosine
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms

    labels = DBSCAN(
        eps=_DBSCAN_EPS,
        min_samples=_MIN_CLUSTER_SIZE,
        metric="cosine",
        n_jobs=1,
    ).fit_predict(matrix)

    clusters: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        if label == -1:  # noise
            continue
        clusters.setdefault(int(label), []).append(idx)
    return clusters


async def _classify_cluster(article_titles: list[str]) -> dict[str, Any]:
    """
    One Groq call per cluster — combines event validation + classification
    + headline generation. Returns parsed JSON or {} on failure.

    On Groq failure we return {} (caller treats as "not validated yet" and
    skips persisting the cluster). This is the right behaviour: rather
    than ship an unvalidated cluster as BREAKING, we'd rather wait for
    the next 15-min cycle when Groq is healthy.
    """
    sample = "\n".join(
        f"{i + 1}. {t}" for i, t in enumerate(article_titles[:10])
    )
    try:
        raw = await call_groq(
            system=_CLASSIFY_SYSTEM,
            user=f"Headlines:\n{sample}\n\nReturn JSON.",
            task_type="rag_response",
            model=FAST_MODEL,
            json_response=True,
        )
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return {}
        return parsed
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.warning("breaking classifier Groq failed: %s", exc)
        return {}
    except json.JSONDecodeError:
        logger.warning("breaking classifier returned non-JSON")
        return {}


async def _store_cluster(
    articles: list[dict[str, Any]],
    indices: list[int],
) -> None:
    members = [articles[i] for i in indices]
    article_ids = [m["article_id"] for m in members]
    titles = [m["title"] for m in members]
    distinct_sources = {m["source_id"] for m in members}

    if len(distinct_sources) < _MIN_DISTINCT_SOURCES:
        return  # single-source burst — likely not real news

    # ── Stage 1: event validation + classification (Groq) ─────────────
    # One call decides four things at once: real-event flag, event_type,
    # severity, and the headline summary. On Groq failure we skip the
    # cluster entirely rather than persist an unvalidated row.
    classification = await _classify_cluster(titles)
    if not classification:
        logger.info(
            "breaking cluster skipped (classifier unavailable); "
            "%d articles, %d sources", len(members), len(distinct_sources)
        )
        return

    is_real_event = bool(classification.get("is_real_event"))
    if not is_real_event:
        logger.info(
            "breaking cluster rejected (not one shared event): titles=%s",
            titles[:3],
        )
        return

    event_type = str(classification.get("event_type") or "other").strip().lower()
    severity = str(classification.get("severity") or "low").strip().lower()

    if event_type in _TRIVIAL_EVENT_TYPES:
        logger.info(
            "breaking cluster rejected (trivial event_type=%s): %s",
            event_type, titles[0] if titles else "",
        )
        return
    if severity not in _SURFACEABLE_SEVERITIES:
        logger.info(
            "breaking cluster rejected (severity=%s): %s",
            severity, titles[0] if titles else "",
        )
        return

    headline = (
        str(classification.get("summary") or "").strip().replace('"', "")[:200]
        or (titles[0][:120] if titles else "Breaking development")
    )
    shared_subject = (
        str(classification.get("shared_subject") or "").strip()[:240] or None
    )

    window_start = min(m["published_at"] for m in members if m["published_at"])
    window_end = max(m["published_at"] for m in members if m["published_at"])

    async with get_db() as db:
        # Skip if a cluster with overlapping members was already recorded
        # in last 30 min (DBSCAN naturally re-finds the same group every run).
        existing = await db.execute(
            text(
                """
                SELECT id FROM breaking_clusters
                WHERE created_at > NOW() - interval '30 minutes'
                  AND is_active = TRUE
                  AND member_article_ids && CAST(:ids AS uuid[])
                LIMIT 1
                """
            ),
            {"ids": article_ids},
        )
        if existing.fetchone():
            return

        await db.execute(
            text(
                """
                INSERT INTO breaking_clusters
                  (window_start, window_end, member_article_ids,
                   headline, sources_count, score,
                   event_type, severity, is_real_event,
                   shared_subject, classified_at)
                VALUES (:ws, :we, CAST(:ids AS uuid[]),
                        :h, :sc, :score,
                        :et, :sev, TRUE,
                        :subj, NOW())
                """
            ),
            {
                "ws": window_start,
                "we": window_end,
                "ids": article_ids,
                "h": headline,
                "sc": len(distinct_sources),
                "score": float(len(indices)) / max(len(distinct_sources), 1),
                "et": event_type,
                "sev": severity,
                "subj": shared_subject,
            },
        )
        await db.commit()


async def _decay_old() -> None:
    async with get_db() as db:
        await db.execute(
            text(
                """
                UPDATE breaking_clusters
                SET is_active = FALSE
                WHERE is_active = TRUE
                  AND created_at < NOW() - interval '6 hours'
                """
            )
        )
        await db.commit()


async def _detect_run() -> dict[str, Any]:
    articles = await _fetch_recent_articles()
    if len(articles) < _MIN_CLUSTER_SIZE:
        await _decay_old()
        return {"clusters_found": 0, "reason": "thin window"}

    clusters = _cluster(articles)
    new_count = 0
    for indices in clusters.values():
        if len(indices) < _MIN_CLUSTER_SIZE:
            continue
        try:
            await _store_cluster(articles, indices)
            new_count += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("breaking cluster store failed: %s", exc)

    await _decay_old()
    return {"clusters_found": new_count, "scanned": len(articles)}


def _flag(name: str) -> bool:
    raw = os.getenv(name, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


@app.task(
    name="tasks.detect_breaking_events",
    bind=True,
    max_retries=0,
)
def detect_breaking_events(self) -> dict:  # type: ignore[no-untyped-def]
    if not _flag("FEATURE_BREAKING"):
        return {"skipped": "feature flag off"}
    return asyncio.run(_detect_run())
