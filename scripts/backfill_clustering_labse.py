"""Backfill labse_embedding using rich v3 LLM-distilled fields.

Replaces the broken labse_embedding values (computed from raw scraped HTML, often
collapsed to identical vectors across unrelated articles) with fresh LaBSE
fingerprints built from the dense LLM-distilled fields.

Input tier per article (whichever's available, best first):
    1. title + " | " + primary_subject + " | " + summary_executive[:1500]
    2. title + " | " + lead_text_translated[:1500]
    3. (skip — no usable text)

Scope:
    - substrate_status='ok'
    - extraction_version IN (2, 3)
    - labse_embedding IS NOT NULL (only overwrite existing — preserves the
      contract that null = embed-eligible-but-not-done)

Runs INSIDE rig-backend container (uses backend.nlp.nlp_embedding.get_labse_model
which is already loaded at FastAPI startup).

Idempotent: writes a `labse_embedding_v2` flag (column added via small migration
OR via comment-only convention) by stamping `labse_embedding_text_hash` so re-runs
skip already-done rows. For MVP, we just batch-update in a single pass and trust
the run to complete; if it crashes, restart and it'll do duplicate work but
final state is the same.

Usage (inside container):
    python3 /app/scripts/backfill_clustering_labse.py --batch-size 64 --limit 100  # smoke
    python3 /app/scripts/backfill_clustering_labse.py --all                          # full run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from typing import Any

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402
from backend.nlp.nlp_embedding import get_labse_model  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backfill_labse")


def build_input_text(row: dict[str, Any]) -> str | None:
    """Pick the highest-quality input text available for this article."""
    title = (row.get("title") or "").strip()
    subject = (row.get("primary_subject") or "").strip()
    summ = (row.get("summary_executive") or "").strip()
    lead = (row.get("lead_text_translated") or "").strip()

    if not title:
        return None

    # Tier 1 — rich v3 path
    if subject and summ and len(summ) > 80:
        return f"{title} | {subject} | {summ[:1500]}"

    # Tier 1b — rich subject but short summary
    if subject and len(subject) > 30:
        body = summ if summ else lead
        if body:
            return f"{title} | {subject} | {body[:1500]}"
        return f"{title} | {subject}"

    # Tier 2 — fallback to lead_text_translated
    if lead and len(lead) > 200:
        return f"{title} | {lead[:1500]}"

    # Tier 3 — skip; title-only would just reintroduce the same bug
    return None


def format_vec(embedding: list[float]) -> str:
    """Serialize float list to pgvector literal."""
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


async def _count_eligible(db, since_days: int | None) -> int:
    base = (
        "SELECT COUNT(*) AS n FROM articles "
        "WHERE substrate_status = 'ok' "
        "AND extraction_version IN (2, 3) "
        "AND labse_embedding IS NOT NULL"
    )
    if since_days:
        q = text(base + " AND collected_at > NOW() - make_interval(days => :d)")
        r = await db.execute(q, {"d": since_days})
    else:
        r = await db.execute(text(base))
    return int(r.fetchone().n or 0)


async def _fetch_batch(
    db, last_id: str | None, batch_size: int, since_days: int | None
) -> list[dict]:
    """Fetch the next batch ordered by id (stable, deterministic, restartable)."""
    base_select = (
        "SELECT id::text AS id, title, primary_subject, summary_executive, "
        "lead_text_translated FROM articles "
        "WHERE substrate_status = 'ok' "
        "AND extraction_version IN (2, 3) "
        "AND labse_embedding IS NOT NULL"
    )
    where_extra = ""
    params: dict[str, Any] = {"n": batch_size}
    if since_days:
        where_extra += " AND collected_at > NOW() - make_interval(days => :d)"
        params["d"] = since_days
    if last_id is not None:
        where_extra += " AND id > CAST(:last AS uuid)"
        params["last"] = last_id
    q = text(base_select + where_extra + " ORDER BY id LIMIT :n")
    rows = await db.execute(q, params)
    return [dict(r._mapping) for r in rows.fetchall()]


async def _update_batch(db, updates: list[tuple[str, str]]) -> None:
    """Bulk update labse_embedding for a batch.
    updates: list of (article_id, pgvector_literal) pairs."""
    if not updates:
        return
    # Single transaction per batch; cheap with small N
    for aid, vec_str in updates:
        await db.execute(
            text(
                "UPDATE articles SET labse_embedding = CAST(:v AS vector) "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"v": vec_str, "id": aid},
        )


async def run(args: argparse.Namespace) -> int:
    model = get_labse_model()
    logger.info("LaBSE loaded; warming with one encode...")
    _ = model.encode(["warmup sentence"])

    async with get_db() as db:
        total = await _count_eligible(db, args.since_days)
    scope_msg = f" (since {args.since_days} days)" if args.since_days else ""
    logger.info("Eligible articles to backfill%s: %d", scope_msg, total)
    if args.limit:
        total = min(total, args.limit)
        logger.info("--limit applied: capping at %d", total)

    processed = 0
    skipped = 0
    last_id: str | None = None
    t0 = time.time()
    last_report = t0

    while True:
        async with get_db() as db:
            rows = await _fetch_batch(db, last_id, args.batch_size, args.since_days)
        if not rows:
            break

        # Build inputs in one pass; record which rows to skip
        texts: list[str] = []
        keep_ids: list[str] = []
        for r in rows:
            inp = build_input_text(r)
            if inp is None:
                skipped += 1
                continue
            texts.append(inp)
            keep_ids.append(r["id"])

        if texts:
            embeddings = model.encode(
                texts,
                batch_size=args.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=False,
            )
            updates = [
                (aid, format_vec(emb.tolist()))
                for aid, emb in zip(keep_ids, embeddings)
            ]
            async with get_db() as db:
                await _update_batch(db, updates)
                await db.commit()

        processed += len(rows)
        last_id = rows[-1]["id"]

        now = time.time()
        if now - last_report >= 10 or processed >= total:
            rate = processed / max(now - t0, 1)
            eta_min = (total - processed) / max(rate, 0.1) / 60
            logger.info(
                "PROGRESS %d/%d (%.1f%%) · %.1f art/sec · ETA %.1f min · skipped=%d",
                processed, total, 100 * processed / max(total, 1),
                rate, eta_min, skipped,
            )
            last_report = now

        if args.limit and processed >= args.limit:
            logger.info("Hit --limit %d, stopping.", args.limit)
            break

    elapsed = time.time() - t0
    logger.info(
        "DONE in %.1f min · processed=%d · skipped=%d · rate=%.1f art/sec",
        elapsed / 60, processed, skipped, processed / max(elapsed, 1),
    )
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="backfill every eligible row")
    g.add_argument("--limit", type=int, help="smoke-test on N rows")
    p.add_argument("--since-days", type=int, default=None,
                   help="restrict to articles collected in the last N days")
    p.add_argument("--batch-size", type=int, default=64)
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
