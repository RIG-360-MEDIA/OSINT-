"""Personalization: saved searches + alerts, watched entities, mutes, catch-me-up."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.appdb.models import Mute, ReadArticle, SavedSearch, User, WatchedEntity
from app.db import connect
from app.deps import current_user, get_db, get_embedder, settings
from app.entities import entity_feed, is_uuid
from app.personalization_store import aware_utc, build_personalization
from app.personalize import apply_mutes, fetch_doc_entities, personalize
from app.retrieval import retrieve_and_curate
from app.schemas import RetrievedDoc
from app.schemas_account import (
    AlertResponse,
    MuteIn,
    MuteOut,
    SavedSearchIn,
    SavedSearchOut,
    WatchIn,
    WatchOut,
)

router = APIRouter(tags=["personalize"])


def _csv(langs: list[str] | None) -> str | None:
    return ",".join(langs) if langs else None


def _split(langs: str | None) -> list[str] | None:
    return langs.split(",") if langs else None


def _new_since(docs: list[RetrievedDoc], last_seen: datetime | None):
    last = aware_utc(last_seen)
    new = [
        d for d in docs
        if d.published_at and (last is None or aware_utc(d.published_at) > last)
    ]
    pubs = [aware_utc(d.published_at) for d in docs if d.published_at]
    high = max(pubs) if pubs else last
    return new, high


# ---------------------------------------------------------------- saved searches
@router.post("/saved", response_model=SavedSearchOut)
async def create_saved(
    body: SavedSearchIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> SavedSearchOut:
    ss = SavedSearch(user_id=user.id, name=body.name, query=body.query, languages=_csv(body.languages))
    db.add(ss)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, f"a saved search named '{body.name}' already exists")
    await db.refresh(ss)
    return _saved_out(ss)


@router.get("/saved", response_model=list[SavedSearchOut])
async def list_saved(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(SavedSearch).where(SavedSearch.user_id == user.id))
    return [_saved_out(r) for r in rows]


@router.delete("/saved/{saved_id}")
async def delete_saved(saved_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    ss = await db.get(SavedSearch, saved_id)
    if not ss or ss.user_id != user.id:
        raise HTTPException(404, "saved search not found")
    await db.delete(ss)
    await db.commit()
    return {"deleted": saved_id}


@router.get("/saved/{saved_id}/alerts", response_model=AlertResponse)
async def saved_alerts(saved_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    ss = await db.get(SavedSearch, saved_id)
    if not ss or ss.user_id != user.id:
        raise HTTPException(404, "saved search not found")
    qvec = await asyncio.to_thread(get_embedder().embed, ss.query)
    async with connect(settings) as conn:
        docs = await retrieve_and_curate(
            conn, settings, ss.query, qvec, _split(ss.languages), top_k=25, rerank_enabled=False
        )
    new, high = _new_since(docs, ss.last_seen_published_at)
    ss.last_seen_published_at = high
    ss.last_checked_at = datetime.now(timezone.utc)
    await db.commit()
    return AlertResponse(new_count=len(new), items=new)


# ---------------------------------------------------------------- watched entities
@router.post("/watch", response_model=WatchOut)
async def add_watch(
    body: WatchIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> WatchOut:
    if not is_uuid(body.entity_id):
        raise HTTPException(422, "entity_id must be a UUID")
    name = body.canonical_name
    if not name:
        async with connect(settings) as conn:
            name = (
                await conn.execute(
                    text("SELECT canonical_name FROM entity_dictionary WHERE id = CAST(:id AS uuid)"),
                    {"id": body.entity_id},
                )
            ).scalar()
        if not name:
            raise HTTPException(404, "entity not found in dictionary")
    we = WatchedEntity(user_id=user.id, entity_id=body.entity_id, canonical_name=name)
    db.add(we)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "already watching this entity")
    await db.refresh(we)
    return _watch_out(we)


@router.get("/watch", response_model=list[WatchOut])
async def list_watch(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(WatchedEntity).where(WatchedEntity.user_id == user.id))
    return [_watch_out(r) for r in rows]


@router.delete("/watch/{watch_id}")
async def delete_watch(watch_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    we = await db.get(WatchedEntity, watch_id)
    if not we or we.user_id != user.id:
        raise HTTPException(404, "watch not found")
    await db.delete(we)
    await db.commit()
    return {"deleted": watch_id}


@router.get("/watch/{watch_id}/new", response_model=AlertResponse)
async def watch_new(watch_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    we = await db.get(WatchedEntity, watch_id)
    if not we or we.user_id != user.id:
        raise HTTPException(404, "watch not found")
    async with connect(settings) as conn:
        docs = await entity_feed(conn, settings, we.entity_id, k=30)
    new, high = _new_since(docs, we.last_seen_published_at)
    we.last_seen_published_at = high
    await db.commit()
    return AlertResponse(new_count=len(new), items=new)


# ---------------------------------------------------------------- mutes
@router.post("/mutes", response_model=MuteOut)
async def add_mute(body: MuteIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if body.kind == "entity" and not is_uuid(body.value):
        raise HTTPException(422, "entity mute value must be a UUID")
    m = Mute(user_id=user.id, kind=body.kind, value=body.value)
    db.add(m)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "already muted")
    await db.refresh(m)
    return MuteOut(id=m.id, kind=m.kind, value=m.value, created_at=m.created_at)


@router.get("/mutes", response_model=list[MuteOut])
async def list_mutes(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(Mute).where(Mute.user_id == user.id))
    return [MuteOut(id=m.id, kind=m.kind, value=m.value, created_at=m.created_at) for m in rows]


@router.delete("/mutes/{mute_id}")
async def delete_mute(mute_id: int, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    m = await db.get(Mute, mute_id)
    if not m or m.user_id != user.id:
        raise HTTPException(404, "mute not found")
    await db.delete(m)
    await db.commit()
    return {"deleted": mute_id}


# ---------------------------------------------------------------- catch-me-up
@router.post("/read")
async def mark_read(article_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if not is_uuid(article_id):
        raise HTTPException(422, "article_id must be a UUID")
    exists = await db.scalar(
        select(ReadArticle).where(ReadArticle.user_id == user.id, ReadArticle.article_id == article_id)
    )
    if not exists:
        db.add(ReadArticle(user_id=user.id, article_id=article_id))
        await db.commit()
    return {"read": article_id}


@router.get("/catchup", response_model=AlertResponse)
async def catchup(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """New articles from your watched entities + saved searches since last visit,
    de-duplicated, with read + muted items removed. Updates the catch-up marker."""
    since = aware_utc(user.last_catchup_at)
    watched = (await db.scalars(select(WatchedEntity).where(WatchedEntity.user_id == user.id))).all()
    saved = (await db.scalars(select(SavedSearch).where(SavedSearch.user_id == user.id))).all()
    read_ids = set(
        (await db.scalars(select(ReadArticle.article_id).where(ReadArticle.user_id == user.id))).all()
    )
    p = await build_personalization(db, user.id)

    collected: dict[str, RetrievedDoc] = {}
    async with connect(settings) as conn:
        for w in watched:
            for d in await entity_feed(conn, settings, w.entity_id, k=20):
                if d.published_at and (since is None or aware_utc(d.published_at) > since):
                    collected.setdefault(d.id, d)
        for ss in saved:
            qvec = await asyncio.to_thread(get_embedder().embed, ss.query)
            docs = await retrieve_and_curate(
                conn, settings, ss.query, qvec, _split(ss.languages), top_k=20, rerank_enabled=False
            )
            for d in docs:
                if d.published_at and (since is None or aware_utc(d.published_at) > since):
                    collected.setdefault(d.id, d)

        items = [d for d in collected.values() if d.id not in read_ids]
        if not p.is_noop and items:
            doc_entities = await fetch_doc_entities(conn, [d.id for d in items], p.relevant_entity_ids)
            items = personalize(items, p, doc_entities)
        else:
            items = apply_mutes(items, p)

    items.sort(key=lambda d: aware_utc(d.published_at) or aware_utc(datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    user.last_catchup_at = datetime.now(timezone.utc)
    await db.commit()
    return AlertResponse(new_count=len(items), items=items)


# ---------------------------------------------------------------- serializers
def _saved_out(ss: SavedSearch) -> SavedSearchOut:
    return SavedSearchOut(
        id=ss.id, name=ss.name, query=ss.query, languages=_split(ss.languages),
        last_seen_published_at=ss.last_seen_published_at, last_checked_at=ss.last_checked_at,
        created_at=ss.created_at,
    )


def _watch_out(we: WatchedEntity) -> WatchOut:
    return WatchOut(
        id=we.id, entity_id=we.entity_id, canonical_name=we.canonical_name,
        last_seen_published_at=we.last_seen_published_at, created_at=we.created_at,
    )
