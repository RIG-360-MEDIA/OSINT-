"""
Helpers for govt_collection_runs audit + govt_document_sources health updates.

These are imported by:
- backend/tasks/govt_task.py — start/finish each per-source run
- backend/tasks/govt_doctor_task.py — daily stale-source check

THIS MODULE OWNS: backend/observability/govt_runs.py
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text


async def start_collection_run(db, *, source_id: str, source_name: str) -> str:
    """Insert a 'running' row and return its UUID."""
    row = (await db.execute(text("""
        INSERT INTO govt_collection_runs (source_id, source_name, status)
        VALUES (CAST(:sid AS uuid), :sname, 'running')
        RETURNING id::text AS id
    """), {"sid": source_id, "sname": source_name})).fetchone()
    return row.id


async def finish_collection_run(
    db,
    *,
    run_id: str,
    status: str = "completed",
    urls_discovered: int = 0,
    urls_filtered_junk: int = 0,
    pdfs_downloaded: int = 0,
    pdfs_extracted: int = 0,
    docs_inserted: int = 0,
    docs_failed: int = 0,
    error_summary: Optional[str] = None,
) -> None:
    """Update a run row with final counts and finish timestamp."""
    await db.execute(text("""
        UPDATE govt_collection_runs
        SET finished_at = NOW(),
            status = :st,
            urls_discovered = :ud, urls_filtered_junk = :uj,
            pdfs_downloaded = :pd, pdfs_extracted = :pe,
            docs_inserted = :di, docs_failed = :df,
            error_summary = :err
        WHERE id = CAST(:rid AS uuid)
    """), {
        "rid": run_id,
        "st": status,
        "ud": urls_discovered,
        "uj": urls_filtered_junk,
        "pd": pdfs_downloaded,
        "pe": pdfs_extracted,
        "di": docs_inserted,
        "df": docs_failed,
        "err": error_summary,
    })


async def update_source_health(db, *, source_id: str, success: bool) -> None:
    """Mirror the RSS pattern: bump health on success, decrement on error,
    auto-disable after 25 consecutive failures (2026-05-27: raised from 10,
    and health floor raised 0.0 → 0.1 so circuit breaker doesn't lock a
    source out permanently after a transient outage)."""
    if success:
        await db.execute(text("""
            UPDATE govt_document_sources
            SET health_score = LEAST(health_score + 0.1, 1.0),
                consecutive_failures = 0,
                last_scraped_at = NOW()
            WHERE id = CAST(:sid AS uuid)
        """), {"sid": source_id})
    else:
        row = (await db.execute(text("""
            UPDATE govt_document_sources
            SET health_score = GREATEST(health_score - 0.2, 0.1),
                consecutive_failures = consecutive_failures + 1,
                last_scraped_at = NOW()
            WHERE id = CAST(:sid AS uuid)
            RETURNING name, consecutive_failures
        """), {"sid": source_id})).fetchone()
        if row and row.consecutive_failures >= 25:
            await db.execute(text("""
                UPDATE govt_document_sources
                SET is_active = FALSE
                WHERE id = CAST(:sid AS uuid)
            """), {"sid": source_id})
