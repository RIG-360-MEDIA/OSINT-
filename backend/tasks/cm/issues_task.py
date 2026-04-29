"""
Cluster recent articles into political flashpoints.

Daily at 03:00 + every 2h incremental. On the `nlp` queue.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np
from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.cm.issues import (
    cluster_items,
    find_existing_match,
)
from backend.nlp.nlp_embedding import get_labse_model

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 48
MAX_ITEMS = 600

# D-26 fix — restrict clustering input to TG/AP-relevant articles. Without
# this filter the cluster_issues task was producing world-news clusters
# ("Indonesia train accident scene", "Iran Russia Diplomatic Talks") with
# NULL state and intensity=0, surfacing on the CM page top-issues panel.
# These needles match the canonical names used in articles.geo_primary
# (capitalised state names, capital cities, codes).
_TG_AP_GEO_NEEDLES: tuple[str, ...] = (
    "telangana", "hyderabad", "tg",
    "andhra pradesh", "andhra", "vijayawada", "visakhapatnam",
    "amaravati", "ap",
)


async def _fetch_items() -> list[dict[str, Any]]:
    # Build LIKE clause once; SQL parameters bound by name to avoid injection.
    needle_clauses = " OR ".join(
        f"LOWER(a.geo_primary) LIKE :_geo{i}" for i in range(len(_TG_AP_GEO_NEEDLES))
    )
    geo_params = {f"_geo{i}": f"%{n}%" for i, n in enumerate(_TG_AP_GEO_NEEDLES)}

    sql = f"""
        SELECT a.id,
               a.title,
               COALESCE(a.lead_text_translated, a.lead_text_original, '') AS lead,
               a.geo_primary,
               a.published_at
        FROM articles a
        WHERE a.published_at > now() - (:hrs || ' hours')::interval
          AND COALESCE(a.source_tier, 9) <= 2
          AND ({needle_clauses})
        ORDER BY a.published_at DESC
        LIMIT :lim
    """
    params: dict[str, Any] = {
        "hrs": str(LOOKBACK_HOURS),
        "lim": MAX_ITEMS,
        **geo_params,
    }
    async with get_db() as db:
        rows = (await db.execute(text(sql), params)).all()
    return [
        {
            "id": r.id,
            "kind": "article",
            "title": r.title or "",
            "lead": r.lead or "",
            "geo": (r.geo_primary or "").lower(),
        }
        for r in rows
    ]


async def _existing_centroids(state: str | None) -> list[tuple[int, np.ndarray]]:
    sql = """
        SELECT id, embedding
        FROM cm_issues
        WHERE last_seen > now() - interval '21 days'
          AND embedding IS NOT NULL
          AND (CAST(:state AS text) IS NULL OR state = :state)
    """
    out: list[tuple[int, np.ndarray]] = []
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"state": state})).all()
    for r in rows:
        try:
            vec = np.asarray(list(r.embedding), dtype=np.float32)
            if vec.size:
                out.append((r.id, vec))
        except Exception:
            continue
    return out


def _state_for(geo: str) -> str | None:
    if "telangana" in geo or "hyderabad" in geo:
        return "TG"
    if "andhra" in geo or "vijayawada" in geo or "visakhapatnam" in geo or "vizag" in geo:
        return "AP"
    return None


async def _persist(items, embeddings, clusters) -> int:
    upsert_issue = """
        INSERT INTO cm_issues (label, slug, state, embedding, first_seen, last_seen, volume_24h)
        VALUES (:label, :slug, :state, CAST(:emb AS vector), now(), now(), :vol)
        ON CONFLICT (slug) DO UPDATE
            SET last_seen = EXCLUDED.last_seen,
                volume_24h = cm_issues.volume_24h + EXCLUDED.volume_24h,
                embedding = EXCLUDED.embedding,
                updated_at = now()
        RETURNING id
    """
    update_existing = """
        UPDATE cm_issues SET last_seen = now(), volume_24h = volume_24h + :vol,
                             updated_at = now()
        WHERE id = :id
    """
    insert_evidence = """
        INSERT INTO cm_issue_evidence (issue_id, source_kind, source_id, side, weight)
        VALUES (:iid, 'article', :sid, NULL, 1.0)
        ON CONFLICT DO NOTHING
    """
    n_attached = 0
    async with get_db() as db:
        existing_by_state: dict[str | None, list[tuple[int, np.ndarray]]] = {}
        for st in {None, "TG", "AP"}:
            existing_by_state[st] = await _existing_centroids(st)
        for cluster in clusters:
            sample_idx = cluster.member_indices[:5]
            geos = [items[i]["geo"] for i in sample_idx]
            state = next((_state_for(g) for g in geos if _state_for(g)), None)
            existing = existing_by_state.get(state, [])
            match_id = find_existing_match(cluster.centroid, existing)
            if match_id is not None:
                await db.execute(
                    text(update_existing),
                    {"id": match_id, "vol": len(cluster.member_indices)},
                )
                issue_id = match_id
            else:
                emb_str = "[" + ",".join(f"{x:.6f}" for x in cluster.centroid.tolist()) + "]"
                row = (
                    await db.execute(
                        text(upsert_issue),
                        {
                            "label": cluster.label,
                            "slug": cluster.slug,
                            "state": state,
                            "emb": emb_str,
                            "vol": len(cluster.member_indices),
                        },
                    )
                ).first()
                issue_id = row.id if row else None
            if issue_id is None:
                continue
            for idx in cluster.member_indices:
                await db.execute(
                    text(insert_evidence),
                    {"iid": issue_id, "sid": items[idx]["id"]},
                )
                n_attached += 1
        await db.commit()
    return n_attached


async def _run() -> dict[str, int]:
    items = await _fetch_items()
    if len(items) < 5:
        return {"items": len(items), "clusters": 0, "attached": 0}
    model = get_labse_model()
    texts = [(it["title"] + " " + it["lead"][:300])[:512] for it in items]
    embeddings = np.asarray(model.encode(texts, show_progress_bar=False), dtype=np.float32)
    clusters = await cluster_items(items=items, embeddings=embeddings)
    n_attached = await _persist(items, embeddings, clusters)
    return {"items": len(items), "clusters": len(clusters), "attached": n_attached}


@app.task(name="tasks.cm.cluster_issues", bind=True, max_retries=1)
def cluster_issues(self) -> dict[str, int]:
    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("cluster_issues failed")
        raise self.retry(exc=exc, countdown=600)
