"""End-to-end auth-flow validator for osint-backend.

Runs INSIDE the osint-backend container (where SUPABASE_* + OSINT_DB_URL +
httpx + sqlalchemy are all present). Hits the app at localhost:8000.

Covers the full invite → accept → login → /api/me path PLUS the negative/
edge cases that matter for an invite-only product. Creates one throwaway
test user + org + invite and tears them all down at the end.

Run:
    cat scripts/eval/auth_e2e.py | ssh … "docker exec -i osint-backend python -"
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

API = "http://localhost:8000"
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
ANON = os.environ["SUPABASE_ANON_KEY"]
SERVICE = os.environ["SUPABASE_SERVICE_KEY"]
DB_URL = os.environ["OSINT_DB_URL"]

ADMIN_EMAIL = os.environ.get("OSINT_BOOTSTRAP_ADMIN_EMAIL", "maverick092005@gmail.com")
ADMIN_PW = os.environ.get("AUTH_E2E_ADMIN_PW", "App!e2005")

TS = int(time.time())
TEST_EMAIL = f"authtest-{TS}@example.com"
TEST_PW = "TestPass123!"

engine = create_async_engine(DB_URL)
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = ""):
    RESULTS.append((name, passed, detail))
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail and not passed else ""))


async def supa_login(email: str, pw: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=30) as c:
        return await c.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": ANON, "Content-Type": "application/json"},
            json={"email": email, "password": pw},
        )


async def api(method: str, path: str, token: str | None = None, json_body=None) -> httpx.Response:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=60) as c:
        return await c.request(method, f"{API}{path}", headers=headers, json=json_body)


async def main():
    print(f"\nAuth E2E — test user: {TEST_EMAIL}\n" + "─" * 70)

    # ── 1. Admin login ──────────────────────────────────────────────────────
    r = await supa_login(ADMIN_EMAIL, ADMIN_PW)
    admin_token = r.json().get("access_token") if r.status_code == 200 else None
    check("admin login (correct creds) → 200 + token", r.status_code == 200 and bool(admin_token), f"status={r.status_code}")
    if not admin_token:
        print("CANNOT CONTINUE — admin login failed.")
        await _report_and_exit()
        return

    # ── 2. Admin login negatives ──────────────────────────────────────────────
    r = await supa_login(ADMIN_EMAIL, "wrong-password-xyz")
    check("admin login (wrong password) → 4xx", 400 <= r.status_code < 500, f"status={r.status_code}")

    r = await supa_login("nobody-here@example.com", "whatever123")
    check("login (nonexistent email) → 4xx", 400 <= r.status_code < 500, f"status={r.status_code}")

    # ── 3. /api/me gating ─────────────────────────────────────────────────────
    r = await api("GET", "/api/me")
    check("/api/me no token → 401", r.status_code == 401, f"status={r.status_code}")

    r = await api("GET", "/api/me", token="garbage.token.here")
    check("/api/me garbage token → 401", r.status_code == 401, f"status={r.status_code}")

    r = await api("GET", "/api/me", token=admin_token)
    me = r.json() if r.status_code == 200 else {}
    check("/api/me admin token → 200 + is_super_admin", r.status_code == 200 and me.get("is_super_admin") is True, f"status={r.status_code} super={me.get('is_super_admin')}")

    # ── 4. Admin route gating (no token / non-admin later) ────────────────────
    r = await api("GET", "/api/admin/invites")
    check("/api/admin/invites no token → 401", r.status_code == 401, f"status={r.status_code}")

    r = await api("POST", "/api/admin/orgs", json_body={"name": "x", "role_template": "govt"})
    check("/api/admin/orgs POST no token → 401", r.status_code == 401, f"status={r.status_code}")

    # ── 5. Org creation ───────────────────────────────────────────────────────
    r = await api("POST", "/api/admin/orgs", token=admin_token,
                  json_body={"name": f"E2E Test Org {TS}", "role_template": "govt", "notes": "auth_e2e"})
    org = r.json() if r.status_code == 200 else {}
    org_id = org.get("id")
    check("create org (valid) → 200 + id", r.status_code == 200 and bool(org_id), f"status={r.status_code}")

    r = await api("POST", "/api/admin/orgs", token=admin_token,
                  json_body={"name": "Bad", "role_template": "not-a-real-template"})
    check("create org (bad role_template) → 422", r.status_code == 422, f"status={r.status_code}")

    # ── 6. Invite creation ────────────────────────────────────────────────────
    r = await api("POST", "/api/admin/invites", token=admin_token,
                  json_body={"email": TEST_EMAIL, "org_id": org_id, "role_template": "govt", "expires_in_days": 14, "notes": "auth_e2e"})
    inv = r.json() if r.status_code == 200 else {}
    invite_link = inv.get("link", "")
    invite_token = invite_link.split("invite=")[-1] if "invite=" in invite_link else None
    check("create invite (valid) → 200 + link", r.status_code == 200 and bool(invite_token), f"status={r.status_code}")

    r = await api("POST", "/api/admin/invites", token=admin_token,
                  json_body={"email": "not-an-email", "org_id": org_id, "role_template": "govt"})
    check("create invite (bad email) → 422", r.status_code == 422, f"status={r.status_code}")

    r = await api("POST", "/api/admin/invites", token=admin_token,
                  json_body={"email": "x@example.com", "org_id": "00000000-0000-0000-0000-000000000000", "role_template": "govt"})
    check("create invite (nonexistent org) → 404", r.status_code == 404, f"status={r.status_code}")

    r = await api("POST", "/api/admin/invites", token=admin_token,
                  json_body={"email": "x@example.com", "org_id": org_id, "role_template": "wrong"})
    check("create invite (bad role) → 422", r.status_code == 422, f"status={r.status_code}")

    # ── 7. Invite peek ────────────────────────────────────────────────────────
    if invite_token:
        r = await api("GET", f"/api/onboarding/invite/{invite_token}")
        pk = r.json() if r.status_code == 200 else {}
        check("peek invite (valid) → 200 + email match", r.status_code == 200 and pk.get("email") == TEST_EMAIL, f"status={r.status_code}")

    r = await api("GET", "/api/onboarding/invite/forged.jwt.token")
    check("peek invite (forged) → 401", r.status_code == 401, f"status={r.status_code}")

    # ── 8. Invite accept — negatives first ────────────────────────────────────
    if invite_token:
        r = await api("POST", "/api/onboarding/accept",
                      json_body={"invite_token": invite_token, "password": "short", "full_name": "T"})
        check("accept (weak password <8) → 422", r.status_code == 422, f"status={r.status_code}")

        r = await api("POST", "/api/onboarding/accept",
                      json_body={"invite_token": "forged.jwt.token", "password": TEST_PW, "full_name": "T"})
        check("accept (forged token) → 401", r.status_code == 401, f"status={r.status_code}")

        # ── happy path ──
        r = await api("POST", "/api/onboarding/accept",
                      json_body={"invite_token": invite_token, "password": TEST_PW, "full_name": "Auth E2E User", "designation": "Tester"})
        acc = r.json() if r.status_code == 200 else {}
        user_token = (acc.get("session") or {}).get("access_token")
        user_id = acc.get("user_id")
        check("accept invite (valid) → 200 + session", r.status_code == 200 and bool(user_token), f"status={r.status_code} body={str(acc)[:120]}")

        # ── single-use: second accept must fail ──
        r = await api("POST", "/api/onboarding/accept",
                      json_body={"invite_token": invite_token, "password": TEST_PW, "full_name": "Dup"})
        check("accept SAME invite again → 409 (single-use)", r.status_code == 409, f"status={r.status_code}")
    else:
        user_token, user_id = None, None

    # ── 9. New user /api/me ───────────────────────────────────────────────────
    if user_token:
        r = await api("GET", "/api/me", token=user_token)
        m = r.json() if r.status_code == 200 else {}
        check("new user /api/me → 200, not super_admin, not onboarded",
              r.status_code == 200 and m.get("is_super_admin") is False and m.get("onboarded") is False,
              f"status={r.status_code} super={m.get('is_super_admin')} onb={m.get('onboarded')}")
        check("new user has correct email + org", m.get("email") == TEST_EMAIL and m.get("org_id") == org_id,
              f"email={m.get('email')} org={m.get('org_id')}")

    # ── 10. New user login round-trip ─────────────────────────────────────────
    r = await supa_login(TEST_EMAIL, TEST_PW)
    check("new user can log in with their password → 200", r.status_code == 200 and bool(r.json().get("access_token")), f"status={r.status_code}")

    r = await supa_login(TEST_EMAIL, "wrong-pw-now")
    check("new user wrong password → 4xx", 400 <= r.status_code < 500, f"status={r.status_code}")

    # ── 11. Bootstrap negatives ───────────────────────────────────────────────
    if user_token:
        r = await api("POST", "/api/admin/bootstrap", token=user_token, json_body={"full_name": "Hacker"})
        check("bootstrap as non-bootstrap-email → 403", r.status_code == 403, f"status={r.status_code}")

    r = await api("POST", "/api/admin/bootstrap", token=admin_token, json_body={"full_name": "Maverick"})
    check("bootstrap when super-admin already exists → 409", r.status_code == 409, f"status={r.status_code}")

    # ── 12. Non-admin hitting admin route ─────────────────────────────────────
    if user_token:
        r = await api("GET", "/api/admin/invites", token=user_token)
        check("non-admin GET /api/admin/invites → 403", r.status_code == 403, f"status={r.status_code}")

    # ── Teardown ──────────────────────────────────────────────────────────────
    await _teardown(user_id, org_id, TEST_EMAIL)
    await _report_and_exit()


async def _teardown(user_id, org_id, email):
    print("─" * 70 + "\nTEARDOWN:")
    # delete analytics rows
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM analytics.user_brief_prefs WHERE user_id = (SELECT id FROM analytics.users WHERE email=:e)"), {"e": email})
            await conn.execute(text("DELETE FROM analytics.invites WHERE email=:e"), {"e": email})
            await conn.execute(text("DELETE FROM analytics.users WHERE email=:e"), {"e": email})
            if org_id:
                await conn.execute(text("DELETE FROM analytics.orgs WHERE id = CAST(:o AS uuid)"), {"o": org_id})
        print("  analytics rows deleted")
    except Exception as e:
        print(f"  analytics teardown error: {e}")
    # delete supabase user
    if user_id:
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                await c.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                               headers={"Authorization": f"Bearer {SERVICE}", "apikey": SERVICE})
            print(f"  supabase user {user_id[:8]}… deleted")
        except Exception as e:
            print(f"  supabase teardown error: {e}")


async def _report_and_exit():
    await engine.dispose()
    n = len(RESULTS)
    passed = sum(1 for _, p, _ in RESULTS if p)
    print("─" * 70)
    print(f"AUTH E2E: {passed}/{n} passed")
    fails = [(nm, d) for nm, p, d in RESULTS if not p]
    if fails:
        print("\nFAILURES:")
        for nm, d in fails:
            print(f"  ✗ {nm}  [{d}]")


if __name__ == "__main__":
    asyncio.run(main())
