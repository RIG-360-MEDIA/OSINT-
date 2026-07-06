"""Assembles every /v1 endpoint router into one mountable router."""
from __future__ import annotations

from fastapi import APIRouter

from . import admin
from .endpoints import (
    analytics,
    articles,
    entities,
    keyword_sentiment,
    meta,
    usage,
    webhooks,
)

router = APIRouter()
router.include_router(meta.router)
router.include_router(entities.router)
router.include_router(articles.router)
router.include_router(analytics.router)
router.include_router(keyword_sentiment.router)
router.include_router(usage.router)
router.include_router(webhooks.router)
router.include_router(admin.router)  # staff-only (JWT), not key-auth
