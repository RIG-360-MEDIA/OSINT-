"""GET /api/me — authenticated user profile.

Used by brief-next to:
  - decide whether to redirect to /onboarding (when `onboarded` is False)
  - render header avatar / name
  - decide whether to show /admin link (when is_super_admin)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from auth.middleware import get_current_principal

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
async def get_me(
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    return principal
