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
# Loosened from 0.18 → 0.32. At 0.18 only near-duplicate republished
# wires clustered (e.g. an AP wire on a German bank standoff fed by
# 5 syndicated outlets). Real "different reporters on the same event"
# vary on phrasing and language enough to require ~0.30. Tested on a
# 24h window of 6106 articles — produces dozens of natural clusters
# vs the 2 we got before.
_DBSCAN_EPS = 0.32


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


async def _generate_headline(article_titles: list[str]) -> str:
    sample = "\n".join(f"- {t}" for t in article_titles[:8])
    try:
        out = await call_groq(
            system=(
                "You write a single short news-wire headline (max 12 words) "
                "summarizing what is unfolding. No quotes, no fluff. Plain text."
            ),
            user=f"Articles in this burst:\n{sample}\n\nHeadline:",
            task_type="classification",
            model=FAST_MODEL,
        )
    except (GroqQuotaExhausted, GroqCallFailed):
        # Fallback: use the first article title
        return article_titles[0][:120] if article_titles else "Breaking development"
    return out.strip().replace('"', "")[:200]


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

    headline = await _generate_headline(titles)
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
                   headline, sources_count, score)
                VALUES (:ws, :we, CAST(:ids AS uuid[]),
                        :h, :sc, :score)
                """
            ),
            {
                "ws": window_start,
                "we": window_end,
                "ids": article_ids,
                "h": headline,
                "sc": len(distinct_sources),
                "score": float(len(indices)) / max(len(distinct_sources), 1),
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
