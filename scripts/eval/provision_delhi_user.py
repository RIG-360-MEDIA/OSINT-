"""Provision the 2nd demo persona — Delhi CM & Government — end-to-end.

Proves the relevance engine is GENERIC (persona = configuration, not code):
same backend, a completely different watchlist (BJP govt + AAP opposition vs
Telangana's INC + BRS), grounded in the CURRENT (2025-26) Rekha Gupta
government and resolved against real entity_dictionary IDs.

Run inside osint-backend:
    cat scripts/eval/provision_delhi_user.py | ssh -i ~/.ssh/rig_hetzner root@HOST \
        "docker exec -i osint-backend python -"

Idempotent: re-running updates password + prefs, never duplicates.
NOTE: contains a demo password — do not commit.
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

EMAIL = "maverick092005+delhi@gmail.com"
PASSWORD = "Delhi#2026"

# (display_name, dict ILIKE pattern, party, role, camp, tier, kind) — current
# Delhi government + opposition, resolved against public.entity_dictionary.
# PRIMARY is the first row (Rekha Gupta).
ROSTER = [
    # ── Government (BJP) — core ──────────────────────────────────────────────
    ("Rekha Gupta", "%rekha gupta%", "BJP", "Chief Minister", "govt", "core", "person"),
    ("Parvesh Verma", "%parvesh verma%", "BJP", "Deputy CM", "govt", "core", "person"),
    ("Ashish Sood", "%ashish sood%", "BJP", "Home/Education Min.", "govt", "core", "person"),
    ("Kapil Mishra", "%kapil mishra%", "BJP", "Law Min.", "govt", "core", "person"),
    ("Virendra Sachdeva", "%virendra sachdeva%", "BJP", "Delhi BJP chief", "govt", "core", "person"),
    ("Vijender Gupta", "%vijender gupta%", "BJP", "Speaker", "govt", "core", "person"),
    # ── Opposition (AAP) — core ──────────────────────────────────────────────
    ("Arvind Kejriwal", "%kejriwal%", "AAP", "AAP National Convenor", "opposition", "core", "person"),
    ("Atishi", "%atishi%", "AAP", "Leader of Opposition", "opposition", "core", "person"),
    ("Manish Sisodia", "%sisodia%", "AAP", "ex-Deputy CM", "opposition", "core", "person"),
    ("Saurabh Bharadwaj", "%saurabh bharadwaj%", "AAP", "ex-Minister", "opposition", "core", "person"),
    ("Gopal Rai", "%gopal rai%", "AAP", "Delhi AAP chief", "opposition", "core", "person"),
    # ── Congress (minor) — extended ──────────────────────────────────────────
    ("Devender Yadav", "%devender yadav%", "INC", "Delhi Congress chief", "opposition", "extended", "person"),
    # ── Centre (Delhi Police / services sit with MHA) — extended ─────────────
    ("Narendra Modi", "%narendra modi%", "BJP", "Prime Minister", "centre", "extended", "person"),
    ("Amit Shah", "%amit shah%", "BJP", "Home Minister", "centre", "extended", "person"),
    # (Lt. Governor Vinai Kumar Saxena is not in entity_dictionary — only
    #  unrelated Saxenas exist, so we omit rather than mis-resolve.)
    # ── Agencies / bodies — extended ─────────────────────────────────────────
    ("Delhi Police", "%delhi police%", None, None, "agency", "extended", "org"),
    ("Enforcement Directorate", "%enforcement directorate%", None, None, "agency", "extended", "org"),
    ("Central Bureau of Investigation", "%central bureau of investigation%", None, None, "agency", "extended", "org"),
    ("Election Commission of India", "%election commission of india%", None, None, "agency", "extended", "org"),
    ("Delhi Metro", "%delhi metro%", None, None, "body", "extended", "org"),
    # ── Parties — extended ───────────────────────────────────────────────────
    ("Bharatiya Janata Party", "%bharatiya janata party%", None, "Party", "party", "extended", "org"),
    ("Aam Aadmi Party", "%aam aadmi party%", None, "Party", "party", "extended", "org"),
    ("Indian National Congress", "%indian national congress%", None, "Party", "party", "extended", "org"),
    # (Yamuna river, Manish Sisodia, MCD, DDA, Devender Yadav are not clean
    #  entity_dictionary entries — carried as keywords below instead.)
]

# Concepts that are NOT dictionary entities → free-text keywords for relevance.
KEYWORDS = ["Sheesh Mahal", "air pollution", "AQI", "Ayushman Bharat",
            "Mahila Samriddhi", "Yamuna", "Manish Sisodia", "odd-even", "GRAP", "CAQM"]


def delhi_prefs(primary: dict, watch: list[dict]) -> dict:
    return {
        "primary_subject_id": primary["id"],
        "primary_subject_meta": primary,
        "watchlist": {"entity_ids": [e["id"] for e in watch], "entity_meta": watch,
                      "keywords": KEYWORDS, "auto_adjacents": True},
        "regions": {"states": ["Delhi"], "districts": ["New Delhi", "North Delhi",
                    "South Delhi", "East Delhi", "West Delhi", "Central Delhi", "Shahdara"],
                    "countries": ["IN"]},
        "topics": {"include": ["POLITICS", "GOVERNANCE", "SECURITY", "INFRASTRUCTURE",
                   "ENVIRONMENT", "HEALTH", "SOCIAL", "FINANCE"], "exclude": ["SPORTS"]},
        "languages": {"read": ["en", "hi"]},
        "sources": {"trusted": [], "excluded": []},
        "stance": {"toward": "balanced", "echo_floor": True},
        "events": {"types": ["protest", "court", "cabinet", "legislation", "scandal",
                   "economy", "security", "election", "pollution"]},
        "delivery": {"timezone": "Asia/Kolkata", "email_digest": False},
        "personality": {"depth": "deep", "voice": "formal", "density": "comfortable",
                        "use_cases": ["monitor_self", "competitive", "policy"], "llm_tone": "analytical"},
    }


async def resolve_roster(conn) -> tuple[list[dict], list[str]]:
    meta, unresolved = [], []
    for (name, pat, party, role, camp, tier, kind) in ROSTER:
        row = (await conn.execute(text("""
            SELECT id::text AS id, canonical_name FROM public.entity_dictionary
             WHERE canonical_name ILIKE :p ORDER BY length(canonical_name) ASC LIMIT 1
        """), {"p": pat})).fetchone()
        if row is None:
            unresolved.append(name)
            continue
        meta.append({"id": row.id, "name": name, "resolved": row.canonical_name,
                     "party": party, "role": role, "camp": camp, "tier": tier, "kind": kind})
    return meta, unresolved


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


async def main():
    uid, action = await ensure_user(EMAIL, PASSWORD, "Delhi CM & Government Cell")
    async with engine.begin() as conn:
        meta, unresolved = await resolve_roster(conn)
        if not meta:
            raise SystemExit("No entities resolved — aborting.")
        primary = {"id": meta[0]["id"], "name": meta[0]["name"], "party": "BJP",
                   "state": "Delhi", "type": "person", "role": "Chief Minister"}
        prefs = delhi_prefs(primary, meta)
        org_id = await upsert_org(conn, "Delhi CM & Government", "govt",
                                  "Demo: Delhi NCT govt situation brief")
        await upsert_user(conn, uid, org_id, EMAIL, "Delhi CM & Government Cell", "Situation Brief — CMO")
        await upsert_prefs(conn, uid, prefs)
    await engine.dispose()

    core = [m for m in meta if m["tier"] == "core"]
    ext = [m for m in meta if m["tier"] == "extended"]
    print(f"\n=== DELHI USER PROVISIONED [{action}] ===")
    print(f"email    : {EMAIL}")
    print(f"password : {PASSWORD}")
    print(f"uid      : {uid}")
    print(f"primary  : {primary['name']} ({primary['id']})")
    print(f"watchlist: {len(meta)} entities ({len(core)} core, {len(ext)} extended) + {len(KEYWORDS)} keywords")
    if unresolved:
        print(f"UNRESOLVED (dropped): {unresolved}")
    print("\nCORE:")
    for m in core:
        tag = f"  [{m['resolved']}]" if m["resolved"] != m["name"] else ""
        print(f"  - {m['name']} ({m['camp']}){tag}")
    print("\nEXTENDED:")
    for m in ext:
        tag = f"  [{m['resolved']}]" if m["resolved"] != m["name"] else ""
        print(f"  - {m['name']} ({m['camp']}){tag}")


if __name__ == "__main__":
    asyncio.run(main())
