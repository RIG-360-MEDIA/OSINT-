"""Bucket 3 — the research agent endpoint (per-user, threaded, cited)."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import run_agent
from app.agent.tools import AgentContext
from app.appdb.models import AgentMessage, User
from app.db import connect
from app.deps import get_db, get_embedder, optional_user, settings
from app.llm import get_llm
from app.schemas_account import AgentRequest, AgentResponse

router = APIRouter(tags=["agent"])


@router.post("/agent", response_model=AgentResponse)
async def agent_endpoint(
    req: AgentRequest,
    user: User | None = Depends(optional_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    """Anonymous-friendly. Threaded memory (load history + persist) only when
    authenticated; anonymous runs are single-turn (no server-side memory)."""
    thread_id = req.thread_id or str(uuid4())

    history: list[dict] = []
    if user and req.thread_id:
        rows = await db.scalars(
            select(AgentMessage)
            .where(AgentMessage.thread_id == thread_id, AgentMessage.user_id == user.id)
            .order_by(AgentMessage.created_at)
        )
        history = [{"role": m.role, "content": m.content} for m in rows]

    async with connect(settings) as conn:
        ctx = AgentContext(conn=conn, settings=settings, embedder=get_embedder())
        result = await run_agent(ctx, get_llm(settings), history, req.message, req.max_steps)

    if user:
        db.add(AgentMessage(thread_id=thread_id, user_id=user.id, role="user", content=req.message))
        db.add(AgentMessage(thread_id=thread_id, user_id=user.id, role="assistant", content=result["answer"] or ""))
        await db.commit()

    return AgentResponse(thread_id=thread_id, **result)
