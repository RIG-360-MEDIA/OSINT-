"""
Analyst router — RAG-powered intelligence analyst endpoints.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user
from backend.database import get_db

logger = logging.getLogger(__name__)

analyst_router = APIRouter(prefix="/api/analyst", tags=["analyst"])


class QueryRequest(BaseModel):
    question: str
    mode: str = ""
    session_id: str = ""


# ── Session management ────────────────────────────────────────────────────────

@analyst_router.get("/session")
async def get_session(
    user: dict = Depends(get_current_user),
) -> dict:
    """Get or create the current analyst session for this user."""
    async with get_db() as db:
        result = await db.execute(text("""
            SELECT id::text AS session_id, created_at, updated_at
            FROM analyst_sessions
            WHERE user_id = :user_id
            ORDER BY updated_at DESC
            LIMIT 1
        """), {"user_id": user["id"]})
        session = result.fetchone()

        if not session:
            result = await db.execute(text("""
                INSERT INTO analyst_sessions (user_id)
                VALUES (:user_id)
                RETURNING id::text AS session_id
            """), {"user_id": user["id"]})
            await db.commit()
            row = result.fetchone()
            return {"session_id": row.session_id, "turns": [], "is_new": True}

        turns_result = await db.execute(text("""
            SELECT
              id::text,
              question,
              answer,
              evidence_count,
              confidence,
              retrieval_ms,
              created_at
            FROM analyst_turns
            WHERE session_id = CAST(:session_id AS uuid)
            ORDER BY created_at ASC
        """), {"session_id": session.session_id})
        turns = turns_result.fetchall()

        return {
            "session_id": session.session_id,
            "turns": [
                {
                    "id": t.id,
                    "question": t.question,
                    "answer": t.answer,
                    "evidence_count": t.evidence_count,
                    "confidence": t.confidence,
                    "created_at": t.created_at.isoformat(),
                }
                for t in turns
            ],
            "is_new": False,
        }


@analyst_router.post("/session/new")
async def new_session(
    user: dict = Depends(get_current_user),
) -> dict:
    """Start a fresh investigation session."""
    async with get_db() as db:
        result = await db.execute(text("""
            INSERT INTO analyst_sessions (user_id)
            VALUES (:user_id)
            RETURNING id::text AS session_id
        """), {"user_id": user["id"]})
        await db.commit()
        row = result.fetchone()
        return {"session_id": row.session_id}


# ── Core query endpoint ───────────────────────────────────────────────────────

@analyst_router.post("/query")
async def analyst_query(
    req: QueryRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Core RAG endpoint: embed question → semantic retrieval → Groq analysis.
    """
    from backend.nlp.rag_engine import (
        retrieve_relevant_articles,
        retrieve_relevant_clips,
        retrieve_relevant_govt_docs,
        build_context,
        detect_mode,
        compute_confidence,
        generate_followups,
        MODE_PROMPTS,
        VALID_MODES,
        KNOWLEDGE_HIERARCHY_BLOCK,
    )
    from backend.nlp.groq_client import generate

    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    async with get_db() as db:
        # Ghost-row upsert so FK constraints hold
        await db.execute(text("""
            INSERT INTO users (id, email)
            VALUES (:id, :email)
            ON CONFLICT (id) DO NOTHING
        """), {"id": user["id"], "email": user["email"]})

        # Fetch user profile
        profile_result = await db.execute(text("""
            SELECT role_context, geo_primary, geo_secondary, signal_priorities
            FROM user_profiles
            WHERE user_id = :user_id
        """), {"user_id": user["id"]})
        profile_row = profile_result.fetchone()

        if not profile_row:
            raise HTTPException(
                status_code=404,
                detail="User profile not found. Complete onboarding first.",
            )

        user_profile = dict(profile_row._mapping)

        # Resolve or create session
        session_id = req.session_id
        session_history: list[dict] = []

        if session_id:
            history_result = await db.execute(text("""
                SELECT question, answer
                FROM analyst_turns
                WHERE session_id = CAST(:sid AS uuid)
                ORDER BY created_at ASC
                LIMIT 5
            """), {"sid": session_id})
            session_history = [
                dict(r._mapping) for r in history_result.fetchall()
            ]
        else:
            sess_result = await db.execute(text("""
                INSERT INTO analyst_sessions (user_id)
                VALUES (:user_id)
                RETURNING id::text AS session_id
            """), {"user_id": user["id"]})
            session_id = sess_result.fetchone().session_id
            # Commit immediately so the row is visible to the fresh db2
            # session used for the history-write step at the end.
            await db.commit()

        # Mode resolution
        requested_mode = req.mode.strip().upper()
        auto_mode = ""
        if requested_mode in VALID_MODES:
            mode = requested_mode
        else:
            auto_mode = await detect_mode(req.question)
            mode = auto_mode

        # Build geo filter from user profile
        import ast
        geo_filter: list[str] = []
        if user_profile.get("geo_primary"):
            geo_filter.append(str(user_profile["geo_primary"]).strip())
        if user_profile.get("geo_secondary"):
            raw_geo = user_profile["geo_secondary"]
            try:
                parsed = ast.literal_eval(str(raw_geo)) if isinstance(raw_geo, str) else raw_geo
                if isinstance(parsed, list):
                    geo_filter.extend([str(g).strip() for g in parsed if g])
                else:
                    geo_filter.append(str(raw_geo).strip())
            except Exception:
                geo_filter.append(str(raw_geo).strip())

        # Retrieve relevant articles AND govt documents concurrently.
        # Articles call returns (list, method, elapsed_ms); govt call returns list[dict].
        articles_task = retrieve_relevant_articles(
            query=req.question,
            user_id=user["id"],
            db=db,
            geo_filter=geo_filter or None,
            mode=mode,
        )
        govt_task = retrieve_relevant_govt_docs(
            query=req.question,
            user_id=user["id"],
            db=db,
            geo_filter=geo_filter or None,
            mode=mode,
        )
        articles_result, govt_docs_result = await asyncio.gather(
            articles_task, govt_task, return_exceptions=True,
        )

        if isinstance(articles_result, Exception):
            logger.error("Article retrieval failed: %s", articles_result)
            raise articles_result
        articles, retrieval_method, elapsed_ms = articles_result

        if isinstance(govt_docs_result, Exception):
            logger.warning("Govt-doc retrieval failed: %s", govt_docs_result)
            govt_docs: list[dict] = []
        else:
            govt_docs = govt_docs_result or []

        if not articles and not govt_docs:
            return {
                "mode": mode,
                "auto_detected": bool(auto_mode),
                "answer": (
                    "## INSUFFICIENT COVERAGE\n\n"
                    "No relevant articles or government documents were found in "
                    "your intelligence feed for this question.\n\n"
                    "**Possible reasons:**\n"
                    "- The topic may not have been covered by your monitored sources\n"
                    "- The pipeline may still be processing recent articles\n\n"
                    "Try searching the Coverage Room directly or broaden your question."
                ),
                "articles": [],
                "govt_docs": [],
                "confidence": "LOW",
                "followups": [],
                "session_id": session_id,
                "retrieval_ms": elapsed_ms,
                "retrieval_method": retrieval_method,
                "article_count": 0,
                "govt_doc_count": 0,
            }

        # Retrieve relevant YouTube clips (parallel intelligence source)
        clips = await retrieve_relevant_clips(
            query=req.question,
            user_id=user["id"],
            db=db,
            top_k=3,
        )

        # Build context and call Groq
        context = build_context(
            articles=articles,
            user_profile=user_profile,
            session_history=session_history,
            query=req.question,
            clips=clips if clips else None,
        )

        # Append govt-document block (additive — articles tagged [Article] above,
        # docs tagged [Document] here so the LLM can cite each kind distinctly).
        if govt_docs:
            doc_items: list[str] = []
            for i, d in enumerate(govt_docs, 1):
                intel = d.get("intel_json") or {}
                what = (intel.get("what_it_does") or "").strip()
                nature = intel.get("document_nature") or d.get("document_type") or ""
                section = d.get("section_heading") or ""
                pub = d.get("published_at") or d.get("collected_at") or ""
                pub_short = pub[:10] if pub else ""
                section_str = f" | Section: {section}" if section else ""
                what_str = f"\nWhat it does: {what}" if what else ""
                doc_items.append(
                    f"[Document {i}] {d.get('title','(untitled)')}\n"
                    f"Source: {d.get('source_name','')} | Type: {nature}"
                    f" | Geo: {d.get('source_geography','')}"
                    f" | Date: {pub_short}{section_str}"
                    f" | Relevance: {d.get('score_final',0.0):.2f}"
                    f"{what_str}\n"
                    f"{(d.get('snippet') or '')}\n"
                )
            context += (
                f"\n\nGOVT DOCUMENT EVIDENCE ({len(doc_items)} documents):\n"
                "When citing a document, use the form: "
                "(Doc: <title>, p.<page_number> if available).\n\n"
                + "\n---\n".join(doc_items)
            )

        system_prompt = KNOWLEDGE_HIERARCHY_BLOCK + "\n\n" + MODE_PROMPTS[mode]
        answer = await generate(
            system=system_prompt,
            user=f"QUESTION: {req.question}\n\n{context}",
            task_type="rag_response",
        )

        confidence, confidence_pct = compute_confidence(
            articles, retrieval_method, query=req.question, mode=mode,
        )
        followups = await generate_followups(
            question=req.question,
            mode=mode,
            articles=articles,
            user_profile=user_profile,
        )

    # Persist turn in a FRESH session — the retrieval session above may be
    # in an aborted-transaction state from a failed govt-doc subquery.
    # Logically independent: history write must not corrupt the answer.
    try:
        async with get_db() as db2:
            await db2.execute(text("""
                INSERT INTO analyst_turns (
                  session_id, question, answer,
                  evidence_count, confidence, retrieval_ms
                ) VALUES (
                  CAST(:session_id AS uuid), :question, :answer,
                  :evidence_count, :confidence, :retrieval_ms
                )
            """), {
                "session_id": session_id,
                "question": req.question,
                "answer": answer,
                "evidence_count": len(articles),
                "confidence": confidence,
                "retrieval_ms": elapsed_ms,
            })

            await db2.execute(text("""
                UPDATE analyst_sessions
                SET updated_at = NOW()
                WHERE id = CAST(:sid AS uuid)
            """), {"sid": session_id})

            await db2.commit()
    except Exception as exc:
        # History persistence is best-effort — never fail the user-visible answer.
        logger.error("Failed to persist analyst turn: %s", exc)

    return {
        "mode": mode,
        "auto_detected": bool(auto_mode),
        "answer": answer,
        "articles": articles,
        "govt_docs": govt_docs,
        "confidence": confidence,
        "confidence_pct": confidence_pct,
        "followups": followups,
        "session_id": session_id,
        "retrieval_ms": elapsed_ms,
        "retrieval_method": retrieval_method,
        "article_count": len(articles),
        "govt_doc_count": len(govt_docs),
    }


# ── Context suggestions ───────────────────────────────────────────────────────

@analyst_router.get("/context")
async def get_context_suggestions(
    user: dict = Depends(get_current_user),
) -> dict:
    """Return 3 suggested investigation questions based on the user's top Tier 1 articles."""
    async with get_db() as db:
        result = await db.execute(text("""
            SELECT
              a.title,
              a.topic_category,
              a.geo_primary,
              uar.score_final,
              uar.relevance_explanation
            FROM user_article_relevance uar
            JOIN articles a ON a.id = uar.article_id
            WHERE uar.user_id = :user_id
              AND uar.relevance_tier = 1
            ORDER BY uar.score_final DESC
            LIMIT 5
        """), {"user_id": user["id"]})
        top_articles = result.fetchall()

        suggestions: list[str] = []
        for a in top_articles:
            category = a.topic_category or ""
            title_short = (a.title or "")[:60]
            if category in ("RISK", "SECURITY"):
                suggestions.append(f"What are the risk indicators in: {title_short}?")
            elif category in ("POLITICS", "GOVERNANCE"):
                suggestions.append(f"What is the political dynamic behind: {title_short}?")
            else:
                suggestions.append(f"What should I know about: {title_short}?")

        return {"suggestions": suggestions[:3]}


# ── Session history endpoints ─────────────────────────────────────────────────

@analyst_router.get("/sessions")
async def list_sessions(
    user: dict = Depends(get_current_user),
) -> dict:
    """List all investigation sessions for this user with summary info."""
    async with get_db() as db:
        result = await db.execute(text("""
            SELECT
              s.id::text AS session_id,
              s.created_at,
              s.updated_at,
              COUNT(t.id) AS turn_count,
              MIN(t.question) AS first_question,
              MAX(t.created_at) AS last_activity
            FROM analyst_sessions s
            LEFT JOIN analyst_turns t ON t.session_id = s.id
            WHERE s.user_id = :user_id
            GROUP BY s.id, s.created_at, s.updated_at
            HAVING COUNT(t.id) > 0
            ORDER BY s.updated_at DESC
            LIMIT 20
        """), {"user_id": user["id"]})
        sessions = result.fetchall()

        return {
            "sessions": [
                {
                    "session_id": s.session_id,
                    "created_at": s.created_at.isoformat(),
                    "updated_at": s.updated_at.isoformat(),
                    "turn_count": s.turn_count,
                    "first_question": s.first_question,
                    "last_activity": (
                        s.last_activity.isoformat()
                        if s.last_activity else None
                    ),
                }
                for s in sessions
            ],
            "total": len(sessions),
        }


@analyst_router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Get all turns for a past session. Verifies user ownership."""
    async with get_db() as db:
        ownership = await db.execute(text("""
            SELECT id FROM analyst_sessions
            WHERE id = :sid::uuid
              AND user_id = :user_id
        """), {"sid": session_id, "user_id": user["id"]})
        if not ownership.fetchone():
            raise HTTPException(status_code=404, detail="Session not found")

        turns_result = await db.execute(text("""
            SELECT
              id::text,
              question,
              answer,
              evidence_count,
              confidence,
              retrieval_ms,
              created_at
            FROM analyst_turns
            WHERE session_id = :sid::uuid
            ORDER BY created_at ASC
        """), {"sid": session_id})
        turns = turns_result.fetchall()

        return {
            "session_id": session_id,
            "turns": [
                {
                    "id": t.id,
                    "question": t.question,
                    "answer": t.answer,
                    "evidence_count": t.evidence_count,
                    "confidence": t.confidence,
                    "retrieval_ms": t.retrieval_ms,
                    "created_at": t.created_at.isoformat(),
                }
                for t in turns
            ],
            "turn_count": len(turns),
        }
