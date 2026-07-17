"""Unauthenticated /v1 meta endpoints (liveness only — no data)."""
from __future__ import annotations

from fastapi import APIRouter

from ..errors import ok

router = APIRouter(prefix="/v1", tags=["meta"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    return ok({"status": "ok", "api": "rig-intelligence", "version": "v1"})
