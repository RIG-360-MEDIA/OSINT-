"""
Time-bounded govt doc ingest. Re-uses the existing pipeline pieces from
backend/tasks/govt_task.py and backend/collectors/govt_collector.py but adds:

  - per-PDF hard timeout (default 90s)
  - global wall-clock ceiling (default 25 min)
  - max_new_docs ceiling (default 60)
  - per-source candidate cap (default 4)
  - line-buffered logging so you can tail it live

Skips dedup'd docs without spending any compute.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
import traceback

import spacy
from sqlalchemy import text

from backend.collectors.govt_collector import (
    download_pdf,
    extract_text_from_pdf,
    fetch_document_urls,
)
from backend.database import get_db
from backend.nlp.govt_chunker import chunk_document_smart
from backend.nlp.govt_intel import compute_intrinsic_importance, extract_intel
from backend.nlp.nlp_embedding import generate_embedding
from backend.nlp.nlp_entities import extract_entities
from backend.nlp.nlp_geo import tag_geography
from backend.nlp.nlp_language import detect_and_translate
from backend.nlp.nlp_topic import classify_topic
from backend.observability.govt_runs import (
    finish_collection_run,
    start_collection_run,
    update_source_health,
)


def _now() -> str:
    return time.strftime("%H:%M:%S")


async def _ingest_one(db, source, doc_info, nlp_model, per_doc_timeout: int) -> str:
    """Process a single candidate doc end-to-end with a hard timeout. Returns status string."""
    url = doc_info["url"]
    title = doc_info["title"]

    try:
        async def _pipeline():
            existing = await db.execute(
                text("SELECT id FROM govt_documents WHERE document_url = :url"),
                {"url": url},
            )
            if existing.fetchone():
                return "DEDUP"

            with tempfile.TemporaryDirectory() as tmpdir:
                pdf_path = await download_pdf(url, tmpdir)
                if not pdf_path:
                    return "NO_PDF"

                full_text = await extract_text_from_pdf(pdf_path)
                if not full_text or len(full_text) < 100:
                    return "TOO_SHORT"

                lang, translated = await detect_and_translate(full_text[:2000], title)
                text_for_nlp = (translated or full_text)[:3000]

                intel = await extract_intel(translated or full_text, title)
                intrinsic = compute_intrinsic_importance(intel)
                entities = extract_entities(title, text_for_nlp, nlp_model)
                topic = await classify_topic(title, text_for_nlp)
                geo, _ = await tag_geography(title, text_for_nlp, entities)
                embedding = generate_embedding(text_for_nlp[:512])

                dump = intel.model_dump(mode="json")

                inserted = await db.execute(
                    text(
                        """
                        INSERT INTO govt_documents (
                          source_id, source_name, source_geography, document_type,
                          title, document_url, full_text, full_text_translated,
                          language_detected, topic_category, geo_primary,
                          entities_extracted, labse_embedding, nlp_processed,
                          intel_json, intrinsic_importance, document_nature,
                          action_posture, geography_affected,
                          financial_magnitude_inr, effective_date,
                          winners, losers, enforcement_strength
                        ) VALUES (
                          :source_id, :source_name, :source_geo, :doc_type,
                          :title, :url, :full_text, :translated,
                          :lang, :topic, :geo,
                          CAST(:entities AS JSONB), CAST(:embedding AS vector), TRUE,
                          CAST(:intel_json AS JSONB), :intrinsic, :doc_nature,
                          :action_posture, CAST(:geo_affected AS JSONB),
                          :fin_magnitude, CAST(:eff_date AS DATE),
                          CAST(:winners AS JSONB), CAST(:losers AS JSONB),
                          :enforcement
                        )
                        ON CONFLICT (document_url) DO NOTHING
                        RETURNING id
                        """
                    ),
                    {
                        "source_id": str(source.id),
                        "source_name": source.name,
                        "source_geo": source.source_geography,
                        "doc_type": source.document_type,
                        "title": title[:1000],
                        "url": url,
                        "full_text": full_text[:50000],
                        "translated": (translated or "")[:50000] or None,
                        "lang": lang,
                        "topic": topic,
                        "geo": geo,
                        "entities": json.dumps(entities),
                        "embedding": str(embedding) if embedding else None,
                        "intel_json": intel.model_dump_json(),
                        "intrinsic": float(intrinsic),
                        "doc_nature": intel.document_nature,
                        "action_posture": intel.action_posture,
                        "geo_affected": json.dumps(dump.get("geography_affected") or []),
                        "fin_magnitude": intel.financial_magnitude_inr,
                        "eff_date": dump.get("effective_date"),
                        "winners": json.dumps(dump.get("winners") or []),
                        "losers": json.dumps(dump.get("losers") or []),
                        "enforcement": intel.enforcement_strength,
                    },
                )
                doc_row = inserted.fetchone()
                if not doc_row:
                    return "DEDUP"

                doc_id = doc_row.id
                chunks = chunk_document_smart(translated or full_text)
                for chunk in chunks[:50]:  # cap per-doc chunk count for speed
                    chunk_emb = generate_embedding(chunk["text"][:512])
                    await db.execute(
                        text(
                            """
                            INSERT INTO govt_document_chunks
                              (document_id, chunk_index, chunk_text, labse_embedding,
                               section_heading, start_char, end_char)
                            VALUES (CAST(:doc_id AS uuid), :idx, :text, CAST(:emb AS vector),
                                    :section_heading, :start_char, :end_char)
                            ON CONFLICT (document_id, chunk_index) DO NOTHING
                            """
                        ),
                        {
                            "doc_id": str(doc_id),
                            "idx": chunk["index"],
                            "text": chunk["text"],
                            "emb": str(chunk_emb) if chunk_emb else None,
                            "section_heading": chunk.get("section_heading"),
                            "start_char": chunk.get("start_char"),
                            "end_char": chunk.get("end_char"),
                        },
                    )

                await db.commit()
                return f"INSERTED ({intel.document_nature}/{intel.action_posture} imp={intrinsic})"

        return await asyncio.wait_for(_pipeline(), timeout=per_doc_timeout)
    except asyncio.TimeoutError:
        await db.rollback()
        return f"TIMEOUT({per_doc_timeout}s)"
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        return f"ERROR: {type(exc).__name__}: {str(exc)[:80]}"


async def main(args) -> None:
    print(f"[{_now()}] loading spaCy", flush=True)
    nlp_model = spacy.load("en_core_web_sm")
    started = time.time()
    deadline = started + args.wall_seconds
    inserted_total = 0

    async with get_db() as db:
        sources = (
            await db.execute(
                text(
                    """
                    SELECT id, name, portal_url, source_geography, document_type
                    FROM govt_document_sources
                    WHERE is_active = TRUE
                    ORDER BY name
                    """
                )
            )
        ).fetchall()
        print(f"[{_now()}] {len(sources)} active sources", flush=True)

        for source in sources:
            if time.time() > deadline:
                print(f"[{_now()}] WALL DEADLINE — stopping", flush=True)
                break
            if inserted_total >= args.max_new_docs:
                print(f"[{_now()}] MAX_NEW_DOCS ({args.max_new_docs}) — stopping", flush=True)
                break

            print(f"[{_now()}] === {source.name} ===", flush=True)

            run_id = await start_collection_run(db, source_id=str(source.id), source_name=source.name)
            urls_discovered = pdfs_downloaded = source_inserted = docs_failed = 0
            error_summary = None

            try:
                doc_urls = await asyncio.wait_for(
                    fetch_document_urls(source.portal_url, source.document_type, since_days=2),
                    timeout=30,
                )
            except Exception as exc:
                doc_urls = []
                error_summary = f"discovery: {exc}"
            urls_discovered = len(doc_urls)
            print(f"[{_now()}]   discovered {urls_discovered}", flush=True)

            for doc_info in doc_urls[: args.per_source_cap]:
                if time.time() > deadline or inserted_total >= args.max_new_docs:
                    break
                status = await _ingest_one(db, source, doc_info, nlp_model, args.per_doc_timeout)
                print(f"[{_now()}]     · {doc_info['title'][:40]:<40} → {status}", flush=True)
                if status == "DEDUP":
                    pass
                elif status.startswith("INSERTED"):
                    inserted_total += 1
                    source_inserted += 1
                    pdfs_downloaded += 1
                elif status in ("NO_PDF", "TOO_SHORT") or status.startswith("TIMEOUT") or status.startswith("ERROR"):
                    docs_failed += 1

            success = error_summary is None
            await finish_collection_run(
                db, run_id=run_id,
                status="completed" if success else "failed",
                urls_discovered=urls_discovered, pdfs_downloaded=pdfs_downloaded,
                docs_inserted=source_inserted, docs_failed=docs_failed,
                error_summary=error_summary,
            )
            await update_source_health(db, source_id=str(source.id), success=success)
            await db.commit()

    print(f"\n[{_now()}] DONE — {inserted_total} new docs in {int(time.time()-started)}s", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--wall-seconds", type=int, default=1500)
    p.add_argument("--max-new-docs", type=int, default=60)
    p.add_argument("--per-source-cap", type=int, default=4)
    p.add_argument("--per-doc-timeout", type=int, default=90)
    args = p.parse_args()
    try:
        asyncio.run(main(args))
    except Exception:
        traceback.print_exc()
