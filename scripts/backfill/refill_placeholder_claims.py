"""refill_placeholder_claims.py — Surgical backfill for the article_claims
placeholder bug.

Re-extracts claims for every article that has at least one row with
`LOWER(subject_text)='article'` (or other placeholder noun). The current
extraction prompt produces clean named entities (verified on a 30-call
side-by-side test) — so we just need to:

  1. SELECT affected articles in batches of 500
  2. For each article:
       a. DELETE its existing article_claims rows
       b. Call the LLM via the unified pool (Ollama + Cerebras + Groq)
       c. INSERT fresh claims

QUOTES ARE LEFT UNTOUCHED. We only re-extract claims, so existing
`article_quotes` data is preserved.

State file: docs/quality/backfill_state.json
  { "completed": [aid, ...], "failed": {aid: error}, "started_at": iso }

Run inside rig-backend (so it has access to the unified pool):
    docker exec -d rig-backend python /app/scripts/backfill/refill_placeholder_claims.py

Stop with SIGTERM — checkpoint flushes immediately.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("refill_claims")

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402
from backend.nlp.groq_client import call_groq  # noqa: E402

# Persisted state lives under /docs/quality (mounted into the container)
STATE_DIR = Path("/docs/quality") if Path("/docs/quality").exists() else Path("docs/quality")
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = STATE_DIR / "backfill_state.json"

PLACEHOLDERS = {"article", "story", "report", "piece", "news",
                "author", "writer", "we", "they", "someone"}

# Same extraction prompt the production task uses (verified clean on test rerun)
_SYSTEM = (
    "You extract factual claims and attributed quotes from a news article. "
    "Return STRICT JSON: { "
    "claims: [{text: 'short factual claim', subject: 'named entity', "
    "predicate: 'verb-phrase', object: 'short object'}, ...] (max 6) }. "
    "\n"
    "Rules for `subject`:\n"
    "  * Must be a specific named entity (person / org / place / company).\n"
    "  * NEVER use a generic noun like 'article', 'story', 'report', 'piece', "
    "'news', 'author', 'we', 'they', 'someone'.\n"
    "  * If you cannot identify a specific named subject for a claim, OMIT "
    "that claim entirely — do not invent one.\n"
    "\n"
    "Skip opinion / editorial commentary — only verifiable factual claims. "
    "No prose outside JSON. No fences. Only return the `claims` key."
)


# ── State management ─────────────────────────────────────────────────────────

def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            log.warning("Could not parse state file — starting fresh")
    return {
        "completed": [],
        "failed": {},
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def save_state(state: dict[str, Any]) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


# ── DB helpers ───────────────────────────────────────────────────────────────

async def next_batch(skip_ids: set[str], limit: int = 500) -> list[dict[str, Any]]:
    """Pull articles still needing a refill.

    Joins to article_claims to find ones with placeholder subjects, dedupes
    article_id, and excludes anything in skip_ids.
    """
    sql = """
        SELECT DISTINCT a.id::text AS aid,
               a.title,
               COALESCE(a.full_text_scraped,
                        a.lead_text_translated,
                        a.lead_text_original) AS body
          FROM articles a
          JOIN article_claims ac ON ac.article_id = a.id
         WHERE LOWER(ac.subject_text) = ANY(:placeholders)
           AND a.substrate_status = 'ok'
           AND COALESCE(a.full_text_scraped, a.lead_text_translated,
                        a.lead_text_original) IS NOT NULL
           AND LENGTH(COALESCE(a.full_text_scraped, a.lead_text_translated,
                               a.lead_text_original)) > 100
         ORDER BY 1
         LIMIT :lim
    """
    async with get_db() as db:
        rows = (await db.execute(text(sql), {
            "placeholders": list(PLACEHOLDERS),
            "lim": int(limit) + len(skip_ids),
        })).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.aid in skip_ids:
            continue
        out.append({"aid": r.aid, "title": r.title, "body": (r.body or "")[:3500]})
        if len(out) >= limit:
            break
    return out


async def total_remaining(skip_ids: set[str]) -> int:
    """Count distinct affected articles still in the broken state."""
    async with get_db() as db:
        row = (await db.execute(text("""
            SELECT COUNT(DISTINCT ac.article_id) AS n
              FROM article_claims ac
             WHERE LOWER(ac.subject_text) = ANY(:p)
        """), {"p": list(PLACEHOLDERS)})).fetchone()
    return int(row.n) - len(skip_ids)


# ── Per-article work ─────────────────────────────────────────────────────────

async def refill_one(article: dict[str, Any], max_retries: int = 3) -> dict[str, Any]:
    """Delete bad claims, call LLM, insert clean claims. Idempotent per aid.

    Retries up to `max_retries` on transient LLM failures (rate limits, queue
    busy, JSON validation, network blips). The unified pool already rotates
    keys, so each retry tries a fresh slot.
    """
    aid = article["aid"]
    user = f"Title: {article.get('title','')}\n\nBody:\n{article['body']}"

    parsed: dict[str, Any] | None = None
    last_err = ""
    for attempt in range(max_retries):
        try:
            raw = await call_groq(
                system=_SYSTEM, user=user,
                task_type="classification", json_response=True,
                max_tokens_override=600,
            )
            parsed = json.loads(raw)
            break
        except Exception as exc:
            last_err = str(exc)[:200]
            # Brief backoff before retry — pool rotates keys for us
            await asyncio.sleep(0.6 * (attempt + 1))
    if parsed is None:
        return {"aid": aid, "ok": False, "error": last_err}

    claims = parsed.get("claims") or []
    # Filter out any sneaky placeholders the LLM still produces
    clean_claims = [
        c for c in claims
        if isinstance(c, dict)
        and (c.get("subject") or "").strip().lower() not in PLACEHOLDERS
        and (c.get("text") or "").strip()
    ][:6]

    # Persist: delete old + insert new in a single transaction.
    # Match production behaviour by resolving subject → entity_dictionary.id
    # when possible (this restores entity-linking — the whole reason we're
    # doing this backfill).
    async with get_db() as db:
        await db.execute(
            text("DELETE FROM article_claims WHERE article_id = CAST(:a AS uuid)"),
            {"a": aid},
        )
        for c in clean_claims:
            subject = (c.get("subject") or "")[:240]
            entity_row = (await db.execute(text(
                "SELECT id::text FROM entity_dictionary "
                "WHERE LOWER(canonical_name) = LOWER(:n) LIMIT 1"
            ), {"n": subject})).fetchone() if subject else None
            entity_id = entity_row.id if entity_row else None
            # asyncpg doesn't allow reusing the same named param twice in a
            # CASE expression — build the entity-ID fragment in Python instead.
            entity_sql = "CAST(:e AS uuid)" if entity_id else "NULL"
            params: dict[str, Any] = {
                "a": aid,
                "t": str(c.get("text", ""))[:1000],
                "s": subject or None,
                "p": (c.get("predicate") or "")[:120] or None,
                "o": (c.get("object") or "")[:240] or None,
                "c": 0.7,
            }
            if entity_id:
                params["e"] = entity_id
            await db.execute(text(
                "INSERT INTO article_claims "
                "  (article_id, claim_text, subject_entity_id, subject_text, "
                "   predicate, object_text, confidence) "
                "VALUES (CAST(:a AS uuid), :t, " + entity_sql + ", "
                "        :s, :p, :o, :c)"
            ), params)
        await db.commit()

    return {"aid": aid, "ok": True, "n_claims": len(clean_claims)}


# ── Main loop ────────────────────────────────────────────────────────────────

async def main_async(args: argparse.Namespace) -> int:
    state = load_state()
    completed: set[str] = set(state.get("completed", []))
    failed: dict[str, str] = dict(state.get("failed", {}))

    total = await total_remaining(completed)
    log.info("Backfill starting. %d articles still to refill (already done: %d, failed: %d)",
             total, len(completed), len(failed))

    if args.limit and args.limit > 0:
        log.info("Limit set: will process at most %d this run", args.limit)

    sem = asyncio.Semaphore(args.concurrency)
    stop_flag = {"stop": False}

    def _on_signal(*_: Any) -> None:
        log.warning("SIGTERM received — finishing current tasks then exiting")
        stop_flag["stop"] = True
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    processed_this_run = 0
    t0 = time.time()

    async def _worker(article: dict[str, Any]) -> None:
        nonlocal processed_this_run
        async with sem:
            if stop_flag["stop"]:
                return
            # Honor --limit mid-batch (don't wait for the whole 500 to drain)
            if args.limit and processed_this_run >= args.limit:
                return
            r = await refill_one(article)
            processed_this_run += 1
            if r["ok"]:
                completed.add(r["aid"])
                # Drop any prior failure entry
                failed.pop(r["aid"], None)
            else:
                failed[r["aid"]] = r["error"]
            # Checkpoint every 100 articles
            if processed_this_run % 100 == 0:
                state["completed"] = sorted(completed)
                state["failed"] = failed
                save_state(state)
                elapsed = time.time() - t0
                rate = processed_this_run / max(elapsed, 1)
                eta_min = (total - processed_this_run) / max(rate, 1e-6) / 60
                log.info("Progress: %d/%d this run · %d total done · %d failed · "
                         "%.1f/sec · ETA %.0fm",
                         processed_this_run, total, len(completed),
                         len(failed), rate, eta_min)

    while not stop_flag["stop"]:
        batch = await next_batch(completed, limit=args.batch)
        if not batch:
            log.info("No more articles to backfill — done.")
            break

        tasks = [_worker(a) for a in batch]
        await asyncio.gather(*tasks)

        if args.limit and processed_this_run >= args.limit:
            log.info("Hit per-run limit (%d) — stopping. Will resume on next invocation.",
                     args.limit)
            break

    # Final flush
    state["completed"] = sorted(completed)
    state["failed"] = failed
    state["last_run_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_state(state)

    log.info("Final: %d completed, %d failed, %d processed this run",
             len(completed), len(failed), processed_this_run)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, default=500,
                   help="Articles per DB fetch batch (default 500)")
    p.add_argument("--concurrency", type=int, default=8,
                   help="Parallel LLM calls (default 8). Pool has 52 slots.")
    p.add_argument("--limit", type=int, default=0,
                   help="Max articles this run (0 = unlimited)")
    args = p.parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
