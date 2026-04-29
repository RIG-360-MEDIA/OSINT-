"""
Detect intra-coalition contradictions. Daily 04:00 on `nlp` queue.

Pairs same-party speakers on the same issue within a 48h window. Below the
CONFIDENCE_FLOOR in dissent.py the verdict is dropped.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.cm import coalitions
from backend.nlp.cm.dissent import compare

logger = logging.getLogger(__name__)

PAIR_LIMIT_PER_ISSUE = 6
ISSUE_LIMIT = 12


async def _candidates() -> list[dict[str, Any]]:
    sql = """
        SELECT q.issue_id, i.label, i.state, q.party,
               array_agg(DISTINCT q.speaker_canonical) FILTER (
                   WHERE q.speaker_canonical IS NOT NULL
               ) AS speakers
        FROM cm_spokesperson_quotes q
        JOIN cm_issues i ON i.id = q.issue_id
        WHERE q.extracted_at > now() - interval '48 hours'
          AND q.party IS NOT NULL
        GROUP BY q.issue_id, i.label, i.state, q.party
        HAVING COUNT(DISTINCT q.speaker_canonical) >= 2
        ORDER BY MAX(i.intensity) DESC NULLS LAST
        LIMIT :lim
    """
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"lim": ISSUE_LIMIT})).all()
    return [
        {
            "issue_id": r.issue_id,
            "label": r.label,
            "state": r.state,
            "party": r.party,
            "speakers": list(r.speakers or []),
        }
        for r in rows
    ]


async def _quote_for(issue_id: int, party: str, speaker: str) -> dict[str, Any] | None:
    sql = """
        SELECT id, quote, source_url
        FROM cm_spokesperson_quotes
        WHERE issue_id = :iid AND party = :p AND speaker_canonical = :s
          AND extracted_at > now() - interval '48 hours'
        ORDER BY extracted_at DESC
        LIMIT 1
    """
    async with get_db() as db:
        r = (
            await db.execute(text(sql), {"iid": issue_id, "p": party, "s": speaker})
        ).first()
    return {"id": r.id, "quote": r.quote, "url": r.source_url} if r else None


async def _persist(verdict, *, issue_id, state, party, speaker_a, speaker_b, qa, qb) -> None:
    coalition = await coalitions.party_kind(state, party)
    if coalition not in {"ruling", "opposition"}:
        return
    insert = """
        INSERT INTO cm_dissent_signals (
            state, coalition, party, speakers, issue_id, summary, severity,
            confidence, evidence_urls, quote_ids, detected_at
        ) VALUES (
            :state, :coalition, :party, :speakers, :iid, :summary, :sev,
            :conf, :urls, :qids, now()
        )
    """
    async with get_db() as db:
        await db.execute(
            text(insert),
            {
                "state": state,
                "coalition": coalition,
                "party": party,
                "speakers": [speaker_a, speaker_b],
                "iid": issue_id,
                "summary": verdict.summary or "Contradicting statements within party",
                "sev": verdict.severity,
                "conf": verdict.confidence,
                "urls": [u for u in (qa["url"], qb["url"]) if u],
                "qids": [qa["id"], qb["id"]],
            },
        )
        await db.commit()


async def _run() -> int:
    n_signals = 0
    for cand in await _candidates():
        speakers = cand["speakers"][:PAIR_LIMIT_PER_ISSUE]
        for i, sa in enumerate(speakers):
            qa = await _quote_for(cand["issue_id"], cand["party"], sa)
            if not qa:
                continue
            for sb in speakers[i + 1 :]:
                qb = await _quote_for(cand["issue_id"], cand["party"], sb)
                if not qb:
                    continue
                try:
                    verdict = await compare(
                        issue_label=cand["label"],
                        party=cand["party"],
                        speaker_a=sa,
                        quote_a=qa["quote"],
                        speaker_b=sb,
                        quote_b=qb["quote"],
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("dissent compare failed: %s", exc)
                    continue
                if verdict and verdict.contradicts:
                    await _persist(
                        verdict,
                        issue_id=cand["issue_id"],
                        state=cand["state"],
                        party=cand["party"],
                        speaker_a=sa,
                        speaker_b=sb,
                        qa=qa,
                        qb=qb,
                    )
                    n_signals += 1
    return n_signals


@app.task(name="tasks.cm.score_dissent", bind=True, max_retries=1)
def score_dissent(self) -> dict[str, int]:
    try:
        return {"signals": asyncio.run(_run())}
    except Exception as exc:
        logger.exception("score_dissent failed")
        raise self.retry(exc=exc, countdown=600)
