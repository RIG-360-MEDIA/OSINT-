"""Bucket 2: annotations, personalized brief (+ schedule), delivery channels."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.appdb.models import BriefSchedule, DeliveryChannel, Note, User
from app.brief import generate_brief
from app.db import connect
from app.deps import current_user, get_db, get_embedder, settings
from app.entities import is_uuid
from app.llm import get_llm
from app.schemas_account import (
    BriefResponse,
    BriefScheduleIn,
    BriefScheduleOut,
    ChannelIn,
    ChannelOut,
    NoteIn,
    NoteOut,
)

router = APIRouter(tags=["brief"])


# ---------------------------------------------------------------- annotations
@router.post("/notes", response_model=NoteOut)
async def add_note(body: NoteIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if not is_uuid(body.article_id):
        raise HTTPException(422, "article_id must be a UUID")
    note = Note(user_id=user.id, article_id=body.article_id, body=body.body)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return NoteOut(id=note.id, article_id=note.article_id, body=note.body, created_at=note.created_at)


@router.get("/notes", response_model=list[NoteOut])
async def list_notes(article_id: str | None = None, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(Note).where(Note.user_id == user.id)
    if article_id:
        stmt = stmt.where(Note.article_id == article_id)
    rows = await db.scalars(stmt.order_by(Note.created_at.desc()))
    return [NoteOut(id=n.id, article_id=n.article_id, body=n.body, created_at=n.created_at) for n in rows]


@router.delete("/notes/{note_id}")
async def delete_note(note_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    n = await db.get(Note, note_id)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "note not found")
    await db.delete(n)
    await db.commit()
    return {"deleted": note_id}


# ---------------------------------------------------------------- brief
@router.get("/me/brief", response_model=BriefResponse)
async def my_brief(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Generate the user's brief now from their watches + saved searches (cited)."""
    async with connect(settings) as conn:
        result = await generate_brief(conn, db, settings, user, get_embedder(), get_llm(settings))
    return BriefResponse(**result)


@router.get("/me/brief/schedule", response_model=BriefScheduleOut)
async def get_schedule(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    sch = await db.get(BriefSchedule, user.id)
    if not sch:
        return BriefScheduleOut(cadence="off", hour_utc=2, languages=None, last_sent_at=None)
    return _sched_out(sch)


@router.put("/me/brief/schedule", response_model=BriefScheduleOut)
async def set_schedule(body: BriefScheduleIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    sch = await db.get(BriefSchedule, user.id)
    langs = ",".join(body.languages) if body.languages else None
    if sch:
        sch.cadence, sch.hour_utc, sch.languages = body.cadence, body.hour_utc, langs
    else:
        sch = BriefSchedule(user_id=user.id, cadence=body.cadence, hour_utc=body.hour_utc, languages=langs)
        db.add(sch)
    await db.commit()
    await db.refresh(sch)
    return _sched_out(sch)


# ---------------------------------------------------------------- delivery channels
@router.post("/channels", response_model=ChannelOut)
async def add_channel(body: ChannelIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if body.kind == "webhook" and not body.target.startswith(("http://", "https://")):
        raise HTTPException(422, "webhook target must be an http(s) URL")
    ch = DeliveryChannel(user_id=user.id, kind=body.kind, target=body.target)
    db.add(ch)
    await db.commit()
    await db.refresh(ch)
    return _chan_out(ch)


@router.get("/channels", response_model=list[ChannelOut])
async def list_channels(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(DeliveryChannel).where(DeliveryChannel.user_id == user.id))
    return [_chan_out(c) for c in rows]


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(DeliveryChannel, channel_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "channel not found")
    await db.delete(c)
    await db.commit()
    return {"deleted": channel_id}


def _sched_out(s: BriefSchedule) -> BriefScheduleOut:
    return BriefScheduleOut(
        cadence=s.cadence, hour_utc=s.hour_utc,
        languages=s.languages.split(",") if s.languages else None, last_sent_at=s.last_sent_at,
    )


def _chan_out(c: DeliveryChannel) -> ChannelOut:
    return ChannelOut(id=c.id, kind=c.kind, target=c.target, active=bool(c.active), created_at=c.created_at)
