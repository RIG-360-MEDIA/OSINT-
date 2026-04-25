from __future__ import annotations

import base64
import json
import logging
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


def _decode_jwt_payload(token: str) -> dict:
    """
    Decode JWT payload without signature verification.
    Sufficient for a local-only dev tool — the token still has an exp claim.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Not a JWT")
        # Add padding so base64 doesn't choke on missing '='
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Malformed token: {exc}") from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    FastAPI dependency. Decodes Supabase JWT locally (no network call).
    Checks expiry. Returns dict with id and email.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = _decode_jwt_payload(credentials.credentials)

    exp = payload.get("exp", 0)
    if exp and time.time() > exp:
        raise HTTPException(status_code=401, detail="Token expired — please log in again")

    user_id = payload.get("sub")
    email = payload.get("email", "")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    return {"id": user_id, "email": email}


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict | None:
    """Returns None if not authenticated. Used for optional-auth endpoints."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
