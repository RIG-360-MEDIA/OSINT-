"""Thin httpx wrapper over Supabase Auth REST API.

Avoids pulling the heavyweight supabase-py SDK into osint-backend just for
two endpoints: create-user (admin) and password sign-in. Both are simple
HTTP calls — keep the dep footprint small.

Env:
    SUPABASE_URL              e.g. https://abcd.supabase.co
    SUPABASE_SERVICE_KEY      service_role JWT (server-side only, never to browser)
    SUPABASE_ANON_KEY         anon JWT (server can use it for sign-in too)
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import HTTPException

_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


def _admin_headers() -> dict[str, str]:
    if not (_URL and _SERVICE_KEY):
        raise HTTPException(status_code=500, detail="Supabase admin env not configured")
    return {
        "Authorization": f"Bearer {_SERVICE_KEY}",
        "apikey": _SERVICE_KEY,
        "Content-Type": "application/json",
    }


def _anon_headers() -> dict[str, str]:
    if not (_URL and _ANON_KEY):
        raise HTTPException(status_code=500, detail="Supabase anon env not configured")
    return {
        "apikey": _ANON_KEY,
        "Content-Type": "application/json",
    }


async def create_user(
    *,
    email: str,
    password: str,
    user_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a confirmed Supabase auth user. Returns the auth.user record."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{_URL}/auth/v1/admin/users",
            headers=_admin_headers(),
            json={
                "email": email.strip().lower(),
                "password": password,
                "email_confirm": True,
                "user_metadata": user_metadata or {},
            },
        )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Supabase create_user: {r.text}")
    return r.json()


async def sign_in_with_password(
    *,
    email: str,
    password: str,
) -> dict[str, Any]:
    """Exchange email+password for a Supabase session. Returns access_token, refresh_token, user."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{_URL}/auth/v1/token?grant_type=password",
            headers=_anon_headers(),
            json={"email": email.strip().lower(), "password": password},
        )
    if r.status_code >= 400:
        raise HTTPException(status_code=401, detail=f"Supabase sign_in: {r.text}")
    return r.json()


async def get_user_by_email(email: str) -> dict[str, Any] | None:
    """Look up an existing Supabase user by exact email. Returns None if absent.

    CRITICAL: GoTrue's /admin/users endpoint does NOT filter by the `email`
    query param — it returns a paginated list of ALL users and ignores it.
    Taking users[0] blindly (the old bug) linked new signups to a random
    existing identity. We MUST filter client-side by exact email match.
    """
    target = email.strip().lower()
    async with httpx.AsyncClient(timeout=30) as client:
        # Page through to be safe; most installs are small but don't assume.
        page = 1
        while page <= 20:  # hard cap: 20 pages × 200 = 4000 users
            r = await client.get(
                f"{_URL}/auth/v1/admin/users",
                headers=_admin_headers(),
                params={"per_page": 200, "page": page},
            )
            if r.status_code >= 400:
                raise HTTPException(status_code=500, detail=f"Supabase get_user: {r.text}")
            data = r.json()
            users = data.get("users") if isinstance(data, dict) else data
            if not users:
                return None
            for u in users:
                if (u.get("email") or "").strip().lower() == target:
                    return u
            if len(users) < 200:  # last page
                return None
            page += 1
    return None
