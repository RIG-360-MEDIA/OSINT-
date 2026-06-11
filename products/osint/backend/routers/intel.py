"""Personalization (Cat-6) + agentic (Cat-5) endpoints.

  GET /api/brief/morning_ritual       — the one card to see today
  GET /api/brief/watchlist_relevance  — overload-killer ranked feed
  GET /api/brief/expand_watchlist     — suggested watchlist additions
  GET /api/brief/smart_filter         — agentic ranked + reasoned top stories
  GET /api/brief/coverage_qa?q=...     — grounded coverage Q&A agent
All generic (driven by the user's prefs); a new user just works.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from agents import cm_coverage_agent, smart_filter
from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from personalize import auto_expand_watchlist, morning_ritual, watchlist_relevance

router = APIRouter(prefix="/api/brief", tags=["brief"])


async def _prefs(user):
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        return db, prefs


@router.get("/morning_ritual")
async def get_morning_ritual(window_hours: int = Query(504, ge=24, le=2160),
                             user: dict | None = Depends(get_optional_user)) -> dict[str, Any]:
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        return await morning_ritual(db, prefs, window_hours) if prefs else {"personalized": False}


@router.get("/watchlist_relevance")
async def get_watchlist_relevance(window_hours: int = Query(96, ge=24, le=2160),
                                  limit: int = Query(10, ge=1, le=40),
                                  user: dict | None = Depends(get_optional_user)) -> dict[str, Any]:
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        return await watchlist_relevance(db, prefs, window_hours, limit) if prefs else {"items": []}


@router.get("/expand_watchlist")
async def get_expand_watchlist(window_hours: int = Query(504, ge=24, le=2160),
                               user: dict | None = Depends(get_optional_user)) -> dict[str, Any]:
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        return await auto_expand_watchlist(db, prefs, window_hours) if prefs else {"suggestions": []}


@router.get("/smart_filter")
async def get_smart_filter(window_hours: int = Query(96, ge=24, le=2160),
                           limit: int = Query(10, ge=1, le=40),
                           user: dict | None = Depends(get_optional_user)) -> dict[str, Any]:
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        return await smart_filter(db, prefs, window_hours, limit) if prefs else {"items": []}


@router.get("/coverage_qa")
async def get_coverage_qa(q: str = Query(..., min_length=3),
                          window_hours: int = Query(504, ge=24, le=2160),
                          user: dict | None = Depends(get_optional_user)) -> dict[str, Any]:
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        return await cm_coverage_agent(db, prefs, q, window_hours) if prefs else {"answer": None}
