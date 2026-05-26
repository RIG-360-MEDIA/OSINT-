"""Verification suite for pick_breaking_per_user. Run inside rig-backend."""
import asyncio
import sys
from sqlalchemy import text
from backend.database import get_db
from backend.tasks.coverage.pick_breaking_per_user_task import (
    _is_junk_title,
    _fetch_candidates,
    _collapse_near_duplicates,
    _select_pool,
    _pick_for_user,
    _run_async,
)

USER = "db4b9207-51aa-4d39-a7bf-e6fab34c3465"


async def main() -> None:
    results: list[tuple[str, bool, str]] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        mark = "PASS" if cond else "FAIL"
        results.append((name, cond, detail))
        print(f"[{mark}] {name}: {detail}")

    junk_titles = [
        "Daily Horoscope: 10 May 2026",
        "Top 10 best mutual funds of 2026",
        "5 Tips to lose weight fast",
        "Aaj ka rashifal: Saturday predictions",
        "Easy chicken biryani recipe",
        "Vastu tips for prosperity",
        "Weather forecast Hyderabad today",
    ]
    real_titles = [
        "Iran-Israel conflict deepens; oil prices spike",
        "Supreme Court rules on Telangana case",
        "Revanth Reddy meets PM Modi today",
    ]
    junk_caught = all(_is_junk_title(t) for t in junk_titles)
    real_kept = all(not _is_junk_title(t) for t in real_titles)
    ok(
        "T1 junk filter",
        junk_caught and real_kept,
        f"junk_caught={junk_caught} real_kept={real_kept}",
    )

    async with get_db() as db:
        zero_q = text(
            "SELECT COUNT(*) FROM user_article_relevance uar "
            "JOIN articles a ON a.id=uar.article_id "
            "WHERE uar.user_id=:u "
            "AND a.collected_at > now() - make_interval(secs=>1) "
            "AND a.source_tier IN (1,2) "
            "AND uar.relevance_tier IN (1,2)"
        )
        c = (await db.execute(zero_q, {"u": USER})).scalar()
        ok(
            "T2 0-article 1-second window",
            c == 0,
            f"candidates_in_1sec_window={c} (expected 0)",
        )

        cands = await _fetch_candidates(db, USER)
        n = len(cands)
        n_t1 = sum(1 for c in cands if c["source_tier"] == 1)
        n_t2 = sum(1 for c in cands if c["source_tier"] == 2)
        ok(
            "T3 candidates fetched",
            n > 0,
            f"total={n} tier1={n_t1} tier2={n_t2}",
        )

        before = len(cands)
        deduped = _collapse_near_duplicates(cands)
        max_dup = max(
            (c.get("near_dup_sources", 1) for c in deduped),
            default=1,
        )
        ok(
            "T4 dedup runs without error",
            True,
            f"before={before} after={len(deduped)} max_near_dup={max_dup}",
        )

        pool, label = _select_pool(deduped)
        if n_t1 > 0:
            cond = label == "tier1_only" and all(
                c["source_tier"] == 1 for c in pool
            )
        else:
            cond = label == "tier2_only" and all(
                c["source_tier"] == 2 for c in pool
            )
        ok(
            "T5 tier-1-beats-tier-2 rule",
            cond,
            f"label={label} pool_size={len(pool)} (n_t1={n_t1})",
        )

        result = await _pick_for_user(
            db,
            USER,
            {
                "role_type": "government",
                "geo_primary": "Hyderabad",
                "signal_priorities": {},
            },
        )
        ok(
            "T6 stickiness on second run",
            result.get("action") == "noop_sticky",
            f"action={result.get('action')}",
        )

        row = (
            await db.execute(
                text(
                    "SELECT article_id::text AS id, source_tier, "
                    "near_dup_sources, candidates_count, decision_path, "
                    "reason, picker_model "
                    "FROM user_breaking_now WHERE user_id=:u"
                ),
                {"u": USER},
            )
        ).mappings().first()
        cond_row = (
            row is not None
            and row["source_tier"] in (1, 2)
            and row["candidates_count"] >= 1
            and isinstance(row["reason"], str)
            and len(row["reason"]) > 10
        )
        ok(
            "T7 row populated correctly",
            cond_row,
            (
                f"tier={row['source_tier']} "
                f"cands={row['candidates_count']} "
                f"path={row['decision_path']}"
                if row
                else "no row"
            ),
        )

    summary = await _run_async()
    cond_idem = summary.get("upserts", 0) == 0 and summary.get("sticky", 0) == 1
    ok("T8 orchestrator idempotent on sticky run", cond_idem, str(summary))

    fails = [n for n, c, _ in results if not c]
    print()
    print(
        f"{len(results) - len(fails)}/{len(results)} PASSED"
        + ("" if not fails else f"  FAILED: {fails}")
    )
    sys.exit(0 if not fails else 1)


asyncio.run(main())
