"""Stage 0 — cluster assembler.

Groups recent articles by LaBSE cosine similarity. Each cluster becomes a
candidate "story" for downstream stages.

Method:
  1. Fetch last `lookback_hours` substrate-ok articles with labse_embedding.
  2. Query pgvector for all pairwise sims above `similarity_threshold` —
     this stays in Postgres so we don't materialise an N×N matrix in
     Python memory.
  3. Run connected-components on the edge list (union-find).
  4. Filter clusters to `min_cluster_size`+ articles.
  5. Persist to `narrative_clusters` + `narrative_cluster_members`.

Why pgvector-side similarity (not in-Python):
  For 2000 articles that is ~4M comparisons. Postgres + pgvector finishes
  in ~3s with an HNSW index; pulling embeddings into Python costs both
  bandwidth (2000 × 768 × 4 bytes ≈ 6MB) and memory for the dense matrix.

No LLM tokens are spent in Stage 0.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterator

from sqlalchemy import text

from backend.database import get_db

logger = logging.getLogger(__name__)

# ── Tunables ─────────────────────────────────────────────────────────
DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_SIMILARITY_THRESHOLD = 0.78  # cosine — empirically separates same-story from same-topic
DEFAULT_MIN_CLUSTER_SIZE = 2          # singletons aren't a "story" worth narrativising
DEFAULT_MAX_LOOKBACK_ARTICLES = 3000  # safety cap

# ── Data types (immutable) ───────────────────────────────────────────


@dataclass(frozen=True)
class ClusterEdge:
    """A single similarity edge between two articles."""
    a: str  # article id (UUID as str)
    b: str
    sim: float


@dataclass(frozen=True)
class AssembledCluster:
    """One cluster from connected-components."""
    article_ids: tuple[str, ...]
    seed_id: str           # representative article (highest collected_at)
    avg_internal_sim: float


# ── Union-Find (immutable interface, mutable internals) ──────────────


class _UnionFind:
    """Standard union-find with path compression."""

    def __init__(self, items: Iterator[str]) -> None:
        self._parent: dict[str, str] = {i: i for i in items}
        self._rank: dict[str, int] = {i: 0 for i in self._parent}

    def find(self, x: str) -> str:
        # iterative path compression
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # compress
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1

    def groups(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for k in list(self._parent.keys()):
            r = self.find(k)
            out.setdefault(r, []).append(k)
        return out


# ── Stage logic ──────────────────────────────────────────────────────


async def fetch_edges(
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    max_articles: int = DEFAULT_MAX_LOOKBACK_ARTICLES,
) -> tuple[list[str], list[ClusterEdge]]:
    """Pull article ids + similarity edges from pgvector.

    Returns (all_article_ids, edges). All edges have sim >= threshold.
    Cosine similarity = 1 - (vec1 <=> vec2) in pgvector.
    """
    async with get_db() as db:
        # 1. Set of candidate article ids
        articles = (await db.execute(text("""
            SELECT id::text AS aid
              FROM articles
             WHERE substrate_status = 'ok'
               AND labse_embedding IS NOT NULL
               AND collected_at > NOW() - (:hours::text || ' hours')::interval
             ORDER BY collected_at DESC
             LIMIT :cap
        """), {"hours": str(lookback_hours), "cap": max_articles})).mappings().all()
        ids = [r["aid"] for r in articles]
        if len(ids) < 2:
            return ids, []
        # 2. Pairwise sims (one side fixed to id-tuple to avoid full cross-join)
        edges_rows = (await db.execute(text("""
            WITH cohort AS (
                SELECT id, labse_embedding, collected_at
                  FROM articles
                 WHERE id::text = ANY(:ids)
            )
            SELECT a.id::text AS a_id,
                   b.id::text AS b_id,
                   1 - (a.labse_embedding <=> b.labse_embedding) AS sim
              FROM cohort a
              JOIN cohort b ON a.id < b.id
             WHERE 1 - (a.labse_embedding <=> b.labse_embedding) >= :thr
        """), {"ids": ids, "thr": similarity_threshold})).mappings().all()
    edges = [ClusterEdge(a=r["a_id"], b=r["b_id"], sim=float(r["sim"])) for r in edges_rows]
    return ids, edges


def assemble_from_edges(
    article_ids: list[str],
    edges: list[ClusterEdge],
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
) -> list[AssembledCluster]:
    """Run connected-components on the edge list, emit clusters."""
    if not article_ids:
        return []
    uf = _UnionFind(iter(article_ids))
    edge_lookup: dict[tuple[str, str], float] = {}
    for e in edges:
        uf.union(e.a, e.b)
        key = (e.a, e.b) if e.a < e.b else (e.b, e.a)
        edge_lookup[key] = e.sim
    groups = uf.groups()
    out: list[AssembledCluster] = []
    for _, members in groups.items():
        if len(members) < min_cluster_size:
            continue
        members_sorted = sorted(members)
        # avg internal sim — only counts edges that exist (others are sub-threshold)
        sims = []
        for i in range(len(members_sorted)):
            for j in range(i + 1, len(members_sorted)):
                k = (members_sorted[i], members_sorted[j])
                if k in edge_lookup:
                    sims.append(edge_lookup[k])
        avg = sum(sims) / len(sims) if sims else 0.0
        out.append(AssembledCluster(
            article_ids=tuple(members_sorted),
            seed_id=members_sorted[0],  # caller can refine to "most recent"
            avg_internal_sim=avg,
        ))
    # Largest first
    out.sort(key=lambda c: (-len(c.article_ids), -c.avg_internal_sim))
    return out


async def persist_clusters(
    clusters: list[AssembledCluster],
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
) -> int:
    """Write clusters + members to DB. Returns number persisted.

    NOTE: requires migration `070_narrative_clusters.sql` (not yet shipped).
    Until then this function logs and returns 0 — callers can still use the
    in-memory clusters returned by `assemble_from_edges`.
    """
    if not clusters:
        return 0
    try:
        async with get_db() as db:
            persisted = 0
            for c in clusters:
                # placeholder — schema will land in migration 070
                result = await db.execute(text("""
                    INSERT INTO narrative_clusters
                       (lookback_hours, avg_internal_sim, member_count)
                    VALUES (:hrs, :sim, :n)
                    RETURNING id::text AS cid
                """), {"hrs": lookback_hours, "sim": c.avg_internal_sim, "n": len(c.article_ids)})
                cid = result.scalar()
                for aid in c.article_ids:
                    await db.execute(text("""
                        INSERT INTO narrative_cluster_members (cluster_id, article_id)
                        VALUES (:cid, :aid)
                    """), {"cid": cid, "aid": aid})
                persisted += 1
            await db.commit()
            return persisted
    except Exception as e:  # noqa: BLE001
        logger.warning("persist_clusters skipped (likely missing migration 070): %s", e)
        return 0


async def run_stage0(
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
) -> list[AssembledCluster]:
    """End-to-end Stage 0 entry point. Returns in-memory clusters.

    Persistence is best-effort — fails silently if migration not applied.
    """
    ids, edges = await fetch_edges(
        lookback_hours=lookback_hours,
        similarity_threshold=similarity_threshold,
    )
    logger.info(
        "stage0: %d articles, %d edges above threshold %.2f",
        len(ids), len(edges), similarity_threshold,
    )
    clusters = assemble_from_edges(ids, edges, min_cluster_size=min_cluster_size)
    logger.info(
        "stage0: %d clusters (covering %d articles)",
        len(clusters), sum(len(c.article_ids) for c in clusters),
    )
    await persist_clusters(clusters, lookback_hours=lookback_hours)
    return clusters
