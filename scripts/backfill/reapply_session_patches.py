"""Re-apply today's session patches after origin merge wiped them.

Run inside rig-backend container OR directly on host (paths work for both).
Idempotent — checks if patch already applied before re-applying.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path("/root/rig") if Path("/root/rig").exists() else Path("/app")


def patch(file: str, old: str, new: str, label: str) -> bool:
    p = PROJECT_ROOT / file
    src = p.read_text()
    if new in src:
        print(f"  ✓ {label}: already applied, skipping")
        return False
    if old not in src:
        print(f"  ✗ {label}: anchor NOT found in {file}")
        return False
    p.write_text(src.replace(old, new, 1))
    print(f"  ✓ {label}: applied")
    return True


def main() -> int:
    print("=== Patch 1: _LOCAL_FAIL_COOLDOWN 10.0 → 0.0 ===")
    patch(
        "backend/nlp/groq_client.py",
        "_LOCAL_FAIL_COOLDOWN = 10.0",
        "_LOCAL_FAIL_COOLDOWN = 0.0  # 2026-05-26: zero cooldown — network errors retry immediately",
        "groq_client cooldown",
    )

    print("\n=== Patch 2: ::text casts on translator quote insert ===")
    patch(
        "backend/tasks/coverage/claims_quotes_task.py",
        """                    VALUES (:a, :sp, :se, :qt, :d,
                            :qt_en, :sp_en,
                            CASE WHEN :qt_en IS NOT NULL
                                 THEN NOW() ELSE NULL END)""",
        """                    VALUES (:a, :sp, :se, :qt, :d,
                            :qt_en::text, :sp_en::text,
                            CASE WHEN :qt_en::text IS NOT NULL
                                 THEN NOW() ELSE NULL END)""",
        "claims_quotes ::text casts",
    )

    print("\n=== Patch 3: extraction_version 2 → 3 (substrate stamps v3 directly) ===")
    # sed-style: 3 occurrences
    p = PROJECT_ROOT / "backend/tasks/substrate/run_corpus_pass.py"
    src = p.read_text()
    new_src = src
    new_src = new_src.replace("extraction_version=2,", "extraction_version=3,")
    new_src = new_src.replace("extraction_version=2 WHERE", "extraction_version=3 WHERE")
    new_src = new_src.replace("extraction_version: int = 2", "extraction_version: int = 3")
    if new_src != src:
        p.write_text(new_src)
        print(f"  ✓ extraction_version stamps updated to 3")
    else:
        print(f"  ✓ already at 3 OR no anchor")

    print("\n=== Patch 4a: Newsroom celery imports ===")
    patch(
        "backend/celery_app.py",
        '        "backend.tasks.v3_upgrade_task",\n',
        '        "backend.tasks.v3_upgrade_task",\n'
        '        # Newsroom (live monitoring + extract + briefing) — was missing,\n'
        '        # causing "unregistered task" errors after every container restart.\n'
        '        "backend.tasks.newsroom.check_liveness",\n'
        '        "backend.tasks.newsroom.detect_breaking",\n'
        '        "backend.tasks.newsroom.extract_quotes",\n'
        '        "backend.tasks.newsroom.generate_daily_brief",\n'
        '        "backend.tasks.newsroom.live_digest",\n'
        '        "backend.tasks.newsroom.live_monitor",\n'
        '        "backend.tasks.newsroom.process_broadcast",\n',
        "newsroom celery imports",
    )

    print("\n=== Patch 6: canonical_url homepage guard ===")
    patch(
        "backend/tasks/substrate/run_corpus_pass.py",
        """    # ─── canonical url ────────────────────────────────────────────────
    canonical = None
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        canonical = link["href"]""",
        """    # ─── canonical url ────────────────────────────────────────────────
    # 2026-05-26: reject homepage-collapse (some sources serve
    # <link rel=canonical href=https://site/> on every article — corrupted
    # 1,222 rows before we caught it).
    canonical = None
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        cand = (link["href"] or "").strip()
        try:
            from urllib.parse import urlparse
            parsed = urlparse(cand)
            path = (parsed.path or "").rstrip("/")
            if path and len(path) > 1:
                canonical = cand
        except Exception:
            canonical = None""",
        "canonical_url homepage guard",
    )

    print("\n=== Patch 7: entity resolver with aliases ===")
    patch(
        "backend/tasks/coverage/claims_quotes_task.py",
        """async def _resolve_entity_id(name: str) -> str | None:
    async with get_db() as db:
        result = await db.execute(
            text(
                "SELECT id::text FROM entity_dictionary "
                "WHERE LOWER(canonical_name) = LOWER(:n) LIMIT 1"
            ),
            {"n": name},
        )
        row = result.fetchone()
    return row[0] if row else None""",
        '''async def _resolve_entity_id(name: str) -> str | None:
    """Resolve speaker/subject name -> entity_dictionary.id.

    2026-05-26 patch: also matches against the aliases ARRAY column.
    Lifted entity linking from ~2% to ~50-60% on existing rows.
    """
    if not name or len(name.strip()) < 2:
        return None
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT id::text FROM entity_dictionary
                 WHERE LOWER(canonical_name) = LOWER(:n)
                    OR EXISTS (
                       SELECT 1 FROM unnest(aliases) AS a
                        WHERE LOWER(a) = LOWER(:n)
                    )
                 ORDER BY
                   (LOWER(canonical_name) = LOWER(:n)) DESC,
                   (entity_type = \\'person\\') DESC,
                   LENGTH(canonical_name) DESC
                 LIMIT 1
                """
            ),
            {"n": name.strip()},
        )
        row = result.fetchone()
    return row[0] if row else None''',
        "entity alias resolver",
    )

    print("\n=== Patch 8: B2 translator skip English (JOIN articles + filter) ===")
    patch(
        "backend/tasks/coverage/claims_quotes_task.py",
        """                SELECT id::text AS id, speaker_name, quote_text
                FROM article_quotes
                WHERE quote_text_en IS NULL
                  AND extracted_at > NOW() - INTERVAL '60 days'
                ORDER BY extracted_at DESC
                LIMIT :lim""",
        """                SELECT q.id::text AS id, q.speaker_name, q.quote_text
                FROM article_quotes q
                JOIN articles a ON a.id = q.article_id
                WHERE q.quote_text_en IS NULL
                  AND q.extracted_at > NOW() - INTERVAL '60 days'
                  AND a.language_iso IS NOT NULL
                  AND a.language_iso <> 'en'   -- B2: skip English quotes
                ORDER BY q.extracted_at DESC
                LIMIT :lim""",
        "B2 translator skip English",
    )

    print("\n=== Patch 9: substrate prompt — SPO triple per claim (D1) ===")
    patch(
        "backend/tasks/substrate/run_corpus_pass.py",
        "  claims: [{text: str, claimant: article|<name>, type: attributable|asserted|disputed, verifiable: bool}] max 5, can be []",
        "  claims: [{subject: str, predicate: str, object: str, text: str, claimant: article|<name>, type: attributable|asserted|disputed, verifiable: bool}] max 5, can be []",
        "D1 claims schema (SPO)",
    )

    print("\n=== Patch 10: substrate persistence — write predicate + object_text (D1) ===")
    patch(
        "backend/tasks/substrate/run_corpus_pass.py",
        "INSERT INTO article_claims\n                  (article_id, claim_text, subject_text, confidence)\n                VALUES (:aid, :tx, :sub, :cf)",
        "INSERT INTO article_claims\n                  (article_id, claim_text, subject_text, predicate, object_text, confidence)\n                VALUES (:aid, :tx, :sub, :pr, :ob, :cf)",
        "D1 persistence (SPO columns)",
    )

    print("\n=== ALL PATCHES PROCESSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
