"""
Smoke test the clipping substrate enrichment end-to-end.

Inserts a synthetic clipping (English + Telugu), runs enrich_clipping inline,
then verifies: enrichment fields, child tables, entity matview, content_items.
Cleans up the synthetic rows afterward.
"""
from __future__ import annotations

import asyncio
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text
from backend.database import get_db
from backend.tasks.clipping_enrich import _enrich_one_by_id

SAMPLES = [
    {
        "lang": "en",
        "headline": "Cabinet clears Rs 12,400-crore highway project for Andhra Pradesh",
        "body": (
            "The Union Cabinet on Thursday approved a Rs 12,400-crore national highway "
            "project connecting Vijayawada to Amaravati, expected to be completed by 2028. "
            "Road Transport Minister Nitin Gadkari said the project would generate 45,000 "
            "direct jobs. The National Highways Authority of India will float tenders by Q3. "
            "Opposition TDP lawmakers welcomed the move while YSRCP termed it a pre-election "
            "gimmick. The AP government has already acquired 78 per cent of the land."
        ),
    },
    {
        "lang": "te",
        "headline": "తెలంగాణలో వరుణుడి కరుణ - రైతులకు ఊరట",
        "body": (
            "తెలంగాణ రాష్ట్రంలో ఈ సీజన్‌లో సాధారణం కంటే 15 శాతం అధిక వర్షపాతం నమోదైంది. "
            "రాష్ట్ర వ్యవసాయ శాఖ మంత్రి తుమ్మల నాగేశ్వరరావు మాట్లాడుతూ 2,000 కోట్ల పంట నష్ట "
            "పరిహారం ఇవ్వనున్నట్లు తెలిపారు. ఖమ్మం, వరంగల్ జిల్లాల్లో వరి సాగు 20 శాతం పెరిగింది."
        ),
    },
]


async def _get_any_source_id(db) -> str:
    row = (await db.execute(text("SELECT id FROM newspaper_sources LIMIT 1"))).fetchone()
    return str(row.id)


async def main() -> None:
    inserted_ids: list[str] = []
    async with get_db() as db:
        src_id = await _get_any_source_id(db)
        for i, s in enumerate(SAMPLES):
            row = await db.execute(
                text(
                    """
                    INSERT INTO clippings
                      (newspaper_source_id, headline, body_text, language,
                       detected_language, page_number, edition_date, collected_at,
                       substrate_status, text_source)
                    VALUES (:src, :hl, :body, :lang, :lang, 1, CURRENT_DATE, NOW(),
                            'pending', 'ocr')
                    RETURNING id
                    """
                ),
                {"src": src_id, "hl": f"[SMOKE] {s['headline']}", "body": s["body"], "lang": s["lang"]},
            )
            inserted_ids.append(str(row.fetchone().id))
        await db.commit()
    print(f"Inserted {len(inserted_ids)} synthetic clippings: {inserted_ids}")

    # Run enrichment inline
    for cid in inserted_ids:
        result = await _enrich_one_by_id(cid)
        print(f"  enrich {cid}: {result}")

    # Verify
    async with get_db() as db:
        for cid in inserted_ids:
            r = (await db.execute(
                text(
                    "SELECT substrate_status, article_type, topic_fine, topic_category, "
                    "primary_subject, summary_snippet, body_text_translated, "
                    "geo_primary, geo_district, register_emotion, "
                    "jsonb_array_length(entities_extracted) AS n_ents, "
                    "(labse_embedding IS NOT NULL) AS has_embed "
                    "FROM clippings WHERE id = :id"
                ),
                {"id": cid},
            )).fetchone()
            cl = (await db.execute(text("SELECT count(*) c FROM clipping_claims WHERE clipping_id=:id"), {"id": cid})).fetchone().c
            qu = (await db.execute(text("SELECT count(*) c FROM clipping_quotes WHERE clipping_id=:id"), {"id": cid})).fetchone().c
            st = (await db.execute(text("SELECT count(*) c FROM clipping_stances WHERE clipping_id=:id"), {"id": cid})).fetchone().c
            lo = (await db.execute(text("SELECT count(*) c FROM clipping_locations WHERE clipping_id=:id"), {"id": cid})).fetchone().c
            nu = (await db.execute(text("SELECT count(*) c FROM clipping_numbers WHERE clipping_id=:id"), {"id": cid})).fetchone().c
            print("\n" + "=" * 60)
            print(f"CLIPPING {cid}")
            print(f"  status={r.substrate_status}  type={r.article_type}  "
                  f"topic={r.topic_fine}/{r.topic_category}  emotion={r.register_emotion}")
            print(f"  primary_subject: {r.primary_subject}")
            print(f"  snippet: {r.summary_snippet}")
            if r.body_text_translated:
                print(f"  translation[:120]: {r.body_text_translated[:120]}")
            print(f"  geo: {r.geo_primary} / {r.geo_district}")
            print(f"  entities={r.n_ents}  embed={r.has_embed}")
            print(f"  child rows -> claims={cl} quotes={qu} stances={st} locations={lo} numbers={nu}")

        # Refresh matview + check entity resolution
        await db.execute(text("REFRESH MATERIALIZED VIEW clipping_entity_mentions"))
        ment = (await db.execute(
            text(
                "SELECT count(*) c, count(DISTINCT entity_id) e FROM clipping_entity_mentions "
                "WHERE clipping_id = ANY(:ids)"
            ),
            {"ids": inserted_ids},
        )).fetchone()
        print("\n" + "=" * 60)
        print(f"clipping_entity_mentions: {ment.c} mention rows, {ment.e} distinct entities resolved")
        sample = (await db.execute(
            text(
                "SELECT canonical_name, entity_type, country FROM clipping_entity_mentions "
                "WHERE clipping_id = ANY(:ids) LIMIT 10"
            ),
            {"ids": inserted_ids},
        )).fetchall()
        for m in sample:
            print(f"   - {m.canonical_name} ({m.entity_type}, {m.country})")

        # content_items shows clippings
        ci = (await db.execute(
            text("SELECT src, count(*) c FROM content_items WHERE id = ANY(:ids) GROUP BY src"),
            {"ids": inserted_ids},
        )).fetchall()
        print(f"\ncontent_items: {[(c.src, c.c) for c in ci]}")

    # Cleanup
    async with get_db() as db:
        await db.execute(
            text("DELETE FROM clippings WHERE id = ANY(:ids)"), {"ids": inserted_ids}
        )
        await db.commit()
        await db.execute(text("REFRESH MATERIALIZED VIEW clipping_entity_mentions"))
    print("\nCleaned up synthetic clippings.")


if __name__ == "__main__":
    asyncio.run(main())
