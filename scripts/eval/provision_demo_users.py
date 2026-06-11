"""Provision demo briefing users — BACKEND-ONLY onboarding (no browser wizard).

Run inside osint-backend:
    cat scripts/eval/provision_demo_users.py | ssh -i ~/.ssh/rig_hetzner root@HOST "docker exec -i osint-backend python -"

Creates 2 orgs + 2 confirmed Supabase users + analytics.users rows +
user_brief_prefs templates, with onboarded_at set (so they land straight
on /brief):

  1. Telangana CM & Government  — fully templated against the CURRENT (2026)
     Revanth Reddy government + opposition. Watchlist uses real
     entity_dictionary IDs (looked up 2026-05-29).
  2. Commonwealth Secretariat   — starter template (Commonwealth states +
     international topics); full build deferred per plan.

Idempotent: re-running updates password + prefs, never duplicates.
NOTE: contains demo passwords — do not commit.
"""
from __future__ import annotations

import asyncio
import json
import os

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE = os.environ["SUPABASE_SERVICE_KEY"]
DB_URL = os.environ["OSINT_DB_URL"]
ADMIN_H = {"Authorization": f"Bearer {SERVICE}", "apikey": SERVICE, "Content-Type": "application/json"}
engine = create_async_engine(DB_URL)

# ── Telangana watchlist — real entity_dictionary IDs, current 2026 govt ──────
TG_PRIMARY = {"id": "9a70e644-5a04-456e-a569-1a9e68aae1ed", "name": "Revanth Reddy",
              "party": "INC", "state": "Telangana", "type": "person", "role": "Chief Minister"}
TG_WATCH = [
    TG_PRIMARY,
    {"id": "0b53459b-16e9-457d-9a18-78b65226a17f", "name": "Bhatti Vikramarka", "party": "INC", "camp": "govt", "role": "Deputy CM"},
    {"id": "b100b94e-41c4-47d6-8d59-d280ec9b7a28", "name": "Uttam Kumar Reddy", "party": "INC", "camp": "govt"},
    {"id": "58740e81-5f1e-4f55-a563-723d5b84e7a4", "name": "D. Sridhar Babu", "party": "INC", "camp": "govt", "role": "IT Minister"},
    {"id": "b93b7e0a-847b-4d45-a6cf-49ba984b377f", "name": "Komatireddy Venkat Reddy", "party": "INC", "camp": "govt"},
    {"id": "cc2f87ce-88cb-4a7c-ad2a-2f89b70767d8", "name": "Ponguleti Srinivasa Reddy", "party": "INC", "camp": "govt"},
    {"id": "836942f8-b2fd-488e-8d57-b769fdc90d0a", "name": "Seethakka", "party": "INC", "camp": "govt"},
    {"id": "97d72b38-4d83-4cee-98d4-c23908534234", "name": "Konda Surekha", "party": "INC", "camp": "govt"},
    {"id": "0681f51f-6561-4450-ae1a-a8797b8c28c5", "name": "Damodar Raja Narasimha", "party": "INC", "camp": "govt", "role": "Health Minister"},
    {"id": "672c8c03-8534-4a7a-bda4-060f648421be", "name": "K. Chandrashekar Rao", "party": "BRS", "camp": "opposition"},
    {"id": "707039c1-5366-450b-9c1d-fa34f11aa7e8", "name": "K T Rama Rao", "party": "BRS", "camp": "opposition"},
    {"id": "e09538a0-89f8-497c-9e09-da7d53be4a7c", "name": "Harish Rao", "party": "BRS", "camp": "opposition"},
    {"id": "92a84982-18e1-4fcd-ac69-e2965794f789", "name": "Asaduddin Owaisi", "party": "AIMIM", "camp": "opposition"},
    {"id": "7f2f082e-b81f-4e0f-bbe5-94d3a396590b", "name": "Akbaruddin Owaisi", "party": "AIMIM", "camp": "opposition"},
    {"id": "ecd299f8-c97d-4216-991c-1818f34e680d", "name": "Bandi Sanjay Kumar", "party": "BJP", "camp": "opposition"},
    {"id": "ef8decc2-7b77-4a24-b8fb-ebc1fdca3e1c", "name": "G. Kishan Reddy", "party": "BJP", "camp": "opposition"},
]


def tg_prefs() -> dict:
    return {
        "primary_subject_id": TG_PRIMARY["id"],
        "primary_subject_meta": TG_PRIMARY,
        "watchlist": {"entity_ids": [e["id"] for e in TG_WATCH], "entity_meta": TG_WATCH, "auto_adjacents": True},
        "regions": {"states": ["Telangana"], "districts": ["Hyderabad", "Warangal", "Karimnagar", "Khammam", "Nalgonda", "Nizamabad"], "countries": ["IN"]},
        "topics": {"include": ["POLITICS", "SECURITY", "GOVERNANCE", "INFRASTRUCTURE", "HEALTH", "AGRICULTURE", "SOCIAL", "FINANCE", "ENVIRONMENT"], "exclude": ["SPORTS"]},
        "languages": {"read": ["en", "te", "hi"]},
        "sources": {"trusted": [], "excluded": []},
        "stance": {"toward": "balanced", "echo_floor": True},
        "events": {"types": ["protest", "court", "cabinet", "legislation", "scandal", "economy", "security", "election"]},
        "delivery": {"timezone": "Asia/Kolkata", "email_digest": False},
        "personality": {"depth": "deep", "voice": "formal", "density": "comfortable", "use_cases": ["monitor_self", "competitive", "policy"], "llm_tone": "analytical"},
    }


def cw_prefs() -> dict:
    return {
        "primary_subject_id": None,
        "primary_subject_meta": {"name": "Shirley Botchwey", "role": "Commonwealth Secretary-General", "note": "starter template; full build pending"},
        "watchlist": {"entity_ids": [], "entity_meta": [], "auto_adjacents": True},
        "regions": {"states": [], "districts": [], "countries": ["IN", "GB", "NG", "GH", "AU", "ZA", "KE", "LK", "PK"]},
        "topics": {"include": ["INTERNATIONAL", "GOVERNANCE", "FINANCE", "ENVIRONMENT", "SECURITY"], "exclude": []},
        "languages": {"read": ["en"]},
        "sources": {"trusted": [], "excluded": []},
        "stance": {"toward": "balanced", "echo_floor": True},
        "events": {"types": ["election", "diplomacy", "economy", "court"]},
        "delivery": {"timezone": "Europe/London", "email_digest": False},
        "personality": {"depth": "standard", "voice": "formal", "density": "comfortable", "use_cases": ["policy", "media_intel"], "llm_tone": "neutral"},
    }


async def get_user_by_email(email: str):
    target = email.strip().lower()
    async with httpx.AsyncClient(timeout=30) as c:
        page = 1
        while page <= 20:
            r = await c.get(f"{URL}/auth/v1/admin/users", headers=ADMIN_H, params={"per_page": 200, "page": page})
            r.raise_for_status()
            data = r.json()
            users = data.get("users") if isinstance(data, dict) else data
            if not users:
                return None
            for u in users:
                if (u.get("email") or "").strip().lower() == target:
                    return u
            if len(users) < 200:
                return None
            page += 1
    return None


async def ensure_user(email: str, pw: str, full_name: str):
    existing = await get_user_by_email(email)
    async with httpx.AsyncClient(timeout=30) as c:
        if existing:
            uid = existing["id"]
            await c.put(f"{URL}/auth/v1/admin/users/{uid}", headers=ADMIN_H,
                        json={"password": pw, "email_confirm": True, "user_metadata": {"full_name": full_name}})
            return uid, "updated"
        r = await c.post(f"{URL}/auth/v1/admin/users", headers=ADMIN_H,
                         json={"email": email, "password": pw, "email_confirm": True, "user_metadata": {"full_name": full_name}})
        if r.status_code >= 400:
            raise SystemExit(f"create_user failed {email}: {r.text}")
        return r.json()["id"], "created"


async def upsert_org(conn, name, role_template, notes):
    row = (await conn.execute(text("SELECT id::text AS id FROM analytics.orgs WHERE name=:n"), {"n": name})).fetchone()
    if row:
        return row.id
    row = (await conn.execute(text(
        "INSERT INTO analytics.orgs (name, role_template, notes) VALUES (:n,:r,:no) RETURNING id::text AS id"
    ), {"n": name, "r": role_template, "no": notes})).fetchone()
    return row.id


async def upsert_user(conn, uid, org_id, email, full_name, designation):
    await conn.execute(text("""
        INSERT INTO analytics.users (id, org_id, email, full_name, designation, is_super_admin, onboarded_at)
        VALUES (CAST(:uid AS uuid), CAST(:org AS uuid), :em, :fn, :des, FALSE, NOW())
        ON CONFLICT (id) DO UPDATE
          SET org_id = EXCLUDED.org_id, full_name = EXCLUDED.full_name,
              designation = EXCLUDED.designation,
              onboarded_at = COALESCE(analytics.users.onboarded_at, NOW())
    """), {"uid": uid, "org": org_id, "em": email, "fn": full_name, "des": designation})


async def upsert_prefs(conn, uid, p):
    await conn.execute(text("""
        INSERT INTO analytics.user_brief_prefs (
            user_id, primary_subject_id, primary_subject_meta, watchlist, regions,
            topics, languages, sources, stance, events, delivery, personality
        ) VALUES (
            CAST(:uid AS uuid), CAST(:psid AS uuid), CAST(:psm AS jsonb), CAST(:w AS jsonb),
            CAST(:reg AS jsonb), CAST(:top AS jsonb), CAST(:lang AS jsonb), CAST(:src AS jsonb),
            CAST(:st AS jsonb), CAST(:ev AS jsonb), CAST(:del AS jsonb), CAST(:pers AS jsonb)
        )
        ON CONFLICT (user_id) DO UPDATE SET
            primary_subject_id = EXCLUDED.primary_subject_id,
            primary_subject_meta = EXCLUDED.primary_subject_meta,
            watchlist = EXCLUDED.watchlist, regions = EXCLUDED.regions,
            topics = EXCLUDED.topics, languages = EXCLUDED.languages,
            sources = EXCLUDED.sources, stance = EXCLUDED.stance,
            events = EXCLUDED.events, delivery = EXCLUDED.delivery,
            personality = EXCLUDED.personality
    """), {
        "uid": uid, "psid": p["primary_subject_id"], "psm": json.dumps(p["primary_subject_meta"]),
        "w": json.dumps(p["watchlist"]), "reg": json.dumps(p["regions"]), "top": json.dumps(p["topics"]),
        "lang": json.dumps(p["languages"]), "src": json.dumps(p["sources"]), "st": json.dumps(p["stance"]),
        "ev": json.dumps(p["events"]), "del": json.dumps(p["delivery"]), "pers": json.dumps(p["personality"]),
    })


async def provision(email, pw, full_name, designation, org_name, role_template, org_notes, prefs):
    uid, action = await ensure_user(email, pw, full_name)
    async with engine.begin() as conn:
        org_id = await upsert_org(conn, org_name, role_template, org_notes)
        await upsert_user(conn, uid, org_id, email, full_name, designation)
        await upsert_prefs(conn, uid, prefs)
    return {"email": email, "password": pw, "uid": uid, "org_id": org_id,
            "action": action, "watch": len(prefs["watchlist"]["entity_ids"])}


async def main():
    tg = await provision(
        "maverick092005+telangana@gmail.com", "Telangana#2026",
        "Telangana CM & Government Cell", "Situation Brief — CMO",
        "Telangana CM & Government", "govt", "Demo: Telangana state govt situation brief", tg_prefs())
    cw = await provision(
        "maverick092005+commonwealth@gmail.com", "Commonwealth#2026",
        "Commonwealth Secretariat", "Situation Brief — Sec-Gen Office",
        "Commonwealth Secretariat", "govt", "Demo: Commonwealth international brief (starter)", cw_prefs())
    await engine.dispose()
    print("\n=== PROVISIONED DEMO USERS ===")
    for u in (tg, cw):
        print(f"\n{u['email']}  [{u['action']}]")
        print(f"  password : {u['password']}")
        print(f"  org_id   : {u['org_id']}")
        print(f"  watchlist: {u['watch']} entities  (onboarded)")
    print("\nLog in at the brief frontend with these credentials.")


if __name__ == "__main__":
    asyncio.run(main())
