"""Rebuild the Telangana CM user's watchlist — expanded, alias-resolved, tiered.

Keeps the original 16 (known ids), adds the dictionary-confirmed additions
(resolved by canonical name → cleanest matching row), and stores the
concepts that AREN'T dictionary entities (HYDRAA, Six Guarantees, …) as free
`keywords` for text matching. Media houses (Eenadu/Sakshi) are sources, not
entities — handled separately.

Run inside osint-backend:
  cat scripts/eval/update_telangana_watchlist.py | ssh … "docker exec -i osint-backend python -"
"""
from __future__ import annotations
import asyncio, json, os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

USER_ID = "03f93124-eec3-46ac-a41e-829cb663b615"
engine = create_async_engine(os.environ["OSINT_DB_URL"])

# (id, name, party, role, camp, tier, kind) — the original 16 (ids already known good)
EXISTING = [
    ("9a70e644-5a04-456e-a569-1a9e68aae1ed", "Revanth Reddy", "INC", "Chief Minister", "govt", "core", "person"),
    ("0b53459b-16e9-457d-9a18-78b65226a17f", "Bhatti Vikramarka", "INC", "Deputy CM", "govt", "core", "person"),
    ("b100b94e-41c4-47d6-8d59-d280ec9b7a28", "Uttam Kumar Reddy", "INC", "Minister", "govt", "core", "person"),
    ("58740e81-5f1e-4f55-a563-723d5b84e7a4", "D. Sridhar Babu", "INC", "IT Minister", "govt", "core", "person"),
    ("b93b7e0a-847b-4d45-a6cf-49ba984b377f", "Komatireddy Venkat Reddy", "INC", "Minister", "govt", "core", "person"),
    ("cc2f87ce-88cb-4a7c-ad2a-2f89b70767d8", "Ponguleti Srinivasa Reddy", "INC", "Minister", "govt", "core", "person"),
    ("836942f8-b2fd-488e-8d57-b769fdc90d0a", "Seethakka", "INC", "Minister", "govt", "core", "person"),
    ("97d72b38-4d83-4cee-98d4-c23908534234", "Konda Surekha", "INC", "Minister", "govt", "core", "person"),
    ("0681f51f-6561-4450-ae1a-a8797b8c28c5", "Damodar Raja Narasimha", "INC", "Health Minister", "govt", "core", "person"),
    ("672c8c03-8534-4a7a-bda4-060f648421be", "K. Chandrashekar Rao", "BRS", "ex-CM", "opposition", "core", "person"),
    ("707039c1-5366-450b-9c1d-fa34f11aa7e8", "K T Rama Rao", "BRS", None, "opposition", "core", "person"),
    ("e09538a0-89f8-497c-9e09-da7d53be4a7c", "Harish Rao", "BRS", None, "opposition", "core", "person"),
    ("92a84982-18e1-4fcd-ac69-e2965794f789", "Asaduddin Owaisi", "AIMIM", None, "opposition", "core", "person"),
    ("7f2f082e-b81f-4e0f-bbe5-94d3a396590b", "Akbaruddin Owaisi", "AIMIM", None, "opposition", "core", "person"),
    ("ecd299f8-c97d-4216-991c-1818f34e680d", "Bandi Sanjay Kumar", "BJP", None, "opposition", "core", "person"),
    ("ef8decc2-7b77-4a24-b8fb-ebc1fdca3e1c", "G. Kishan Reddy", "BJP", None, "opposition", "core", "person"),
]

# (display_name, pattern, party, role, camp, tier, kind) — resolved against entity_dictionary
NEW = [
    ("Tummala Nageswara Rao", "%tummala nageswara%", "INC", "Agriculture Min.", "govt", "core", "person"),
    ("Ponnam Prabhakar", "%ponnam prabhakar%", "INC", "Transport Min.", "govt", "core", "person"),
    ("Jupally Krishna Rao", "%jupally krishna%", "INC", "Excise Min.", "govt", "core", "person"),
    ("Mahesh Kumar Goud", "%mahesh kumar goud%", "INC", "TPCC President", "govt", "core", "person"),
    ("Rahul Gandhi", "%rahul gandhi%", "INC", "High command", "high_command", "extended", "person"),
    ("Sonia Gandhi", "%sonia gandhi%", "INC", "High command", "high_command", "extended", "person"),
    ("Priyanka Gandhi", "%priyanka gandhi%", "INC", "High command", "high_command", "extended", "person"),
    ("Mallikarjun Kharge", "%mallikarjun kharge%", "INC", "AICC President", "high_command", "extended", "person"),
    ("K.C. Venugopal", "%venugopal%", "INC", "AICC Gen-Sec", "high_command", "extended", "person"),
    ("K. Kavitha", "%kavitha%", "BRS", "MLC", "opposition", "core", "person"),
    ("Eatala Rajender", "%eatala rajender%", "BJP", "MP", "opposition", "core", "person"),
    ("Narendra Modi", "%narendra modi%", "BJP", "Prime Minister", "centre", "extended", "person"),
    ("Amit Shah", "%amit shah%", "BJP", "Home Minister", "centre", "extended", "person"),
    ("Nirmala Sitharaman", "%nirmala sitharaman%", "BJP", "Finance Minister", "centre", "extended", "person"),
    ("Chandrababu Naidu", "%chandrababu naidu%", "TDP", "AP CM", "rival", "extended", "person"),
    ("Y.S. Jagan Mohan Reddy", "%jagan mohan reddy%", "YSRCP", "ex-AP CM", "rival", "extended", "person"),
    ("Pawan Kalyan", "%pawan kalyan%", "JSP", "AP Dy CM", "rival", "extended", "person"),
    ("Gov. Jishnu Dev Varma", "%jishnu dev varma%", None, "Governor", "constitutional", "extended", "person"),
    ("Telangana High Court", "%telangana high court%", None, None, "constitutional", "extended", "org"),
    ("Enforcement Directorate", "%enforcement directorate%", None, None, "agency", "extended", "org"),
    ("Central Bureau of Investigation", "%central bureau of investigation%", None, None, "agency", "extended", "org"),
    ("Income Tax Department", "%income tax department%", None, None, "agency", "extended", "org"),
    ("Election Commission", "%election commission%", None, None, "agency", "extended", "org"),
    ("Indian National Congress", "%indian national congress%", None, "Party", "party", "extended", "org"),
    ("Bharat Rashtra Samithi", "%bharat rashtra samithi%", None, "Party", "party", "extended", "org"),
    ("Bharatiya Janata Party", "%bharatiya janata party%", None, "Party", "party", "extended", "org"),
    ("AIMIM", "%majlis-e-ittehadul%", None, "Party", "party", "extended", "org"),
    ("Telugu Desam Party", "%telugu desam party%", None, "Party", "party", "extended", "org"),
    ("YSR Congress Party", "%ysr congress party%", None, "Party", "party", "extended", "org"),
    ("Maoists (CPI-Maoist)", "%maoists%", None, None, "security", "extended", "org"),
    ("Kaleshwaram", "%kaleshwaram%", None, "Irrigation project", "project", "core", "project"),
    ("Musi River Front", "%musi river front%", None, "Rejuvenation project", "project", "core", "project"),
    ("Hyderabad Metro Rail", "%hyderabad metro rail%", None, None, "project", "extended", "project"),
    ("Outer Ring Road", "%outer ring road%", None, None, "project", "extended", "project"),
    ("Pharma City", "%pharma city%", None, None, "project", "extended", "project"),
    ("Polavaram", "%polavaram%", None, "Irrigation project", "project", "extended", "project"),
    ("Amaravati", "%amaravati%", None, "AP capital", "project", "extended", "project"),
    ("GHMC", "%greater hyderabad municipal%", None, None, "body", "extended", "org"),
    ("HMDA", "%hmda%", None, None, "body", "extended", "org"),
    ("TCS", "%tata consultancy%", None, None, "company", "extended", "org"),
    ("Microsoft", "%microsoft%", None, None, "company", "extended", "org"),
    ("Google", "%google%", None, None, "company", "extended", "org"),
    ("Amazon", "%amazon%", None, None, "company", "extended", "org"),
    ("Dr. Reddy's Laboratories", "%reddy%laboratories%", None, None, "company", "extended", "org"),
    ("Bharat Biotech", "%bharat biotech%", None, None, "company", "extended", "org"),
    ("Adani", "%adani%", None, None, "company", "extended", "org"),
    ("Reliance", "%reliance%", None, None, "company", "extended", "org"),
    ("GMR Group", "%gmr group%", None, None, "company", "extended", "org"),
    ("TV9", "%tv9%", None, None, "media", "extended", "org"),
    ("Chiranjeevi", "%chiranjeevi%", None, "Actor", "tollywood", "extended", "person"),
    ("Mahesh Babu", "%mahesh babu%", None, "Actor", "tollywood", "extended", "person"),
    ("Prabhas", "%prabhas%", None, "Actor", "tollywood", "extended", "person"),
]

# Concepts that are NOT dictionary entities → free-text keywords for relevance.
KEYWORDS = ["HYDRAA", "Future City", "Six Guarantees", "caste census", "Dharani",
            "Megha Engineering", "Rythu Bharosa", "Allu Arjun"]


async def main():
    meta, ids, unresolved = [], [], []
    # existing
    for (eid, name, party, role, camp, tier, kind) in EXISTING:
        ids.append(eid)
        meta.append({"id": eid, "name": name, "party": party, "role": role,
                     "camp": camp, "tier": tier, "kind": kind})
    # resolve new
    async with engine.begin() as conn:
        for (name, pat, party, role, camp, tier, kind) in NEW:
            row = (await conn.execute(text("""
                SELECT id::text AS id, canonical_name FROM public.entity_dictionary
                 WHERE canonical_name ILIKE :p ORDER BY length(canonical_name) ASC LIMIT 1
            """), {"p": pat})).fetchone()
            if row is None:
                unresolved.append(name)
                continue
            ids.append(row.id)
            meta.append({"id": row.id, "name": name, "resolved": row.canonical_name,
                         "party": party, "role": role, "camp": camp, "tier": tier, "kind": kind})

        watchlist = {"entity_ids": ids, "entity_meta": meta, "keywords": KEYWORDS, "auto_adjacents": True}
        await conn.execute(text("""
            UPDATE analytics.user_brief_prefs SET watchlist = CAST(:w AS jsonb)
             WHERE user_id = CAST(:u AS uuid)
        """), {"w": json.dumps(watchlist), "u": USER_ID})

    await engine.dispose()
    core = [m for m in meta if m["tier"] == "core"]
    ext = [m for m in meta if m["tier"] == "extended"]
    print(f"\n=== WATCHLIST UPDATED for Telangana user ===")
    print(f"total entities: {len(meta)}  ({len(core)} core, {len(ext)} extended)  + {len(KEYWORDS)} keywords")
    if unresolved:
        print(f"UNRESOLVED (kept as keyword candidates): {unresolved}")
    print("\nCORE:")
    for m in core:
        print(f"  - {m['name']}" + (f"  [{m.get('resolved')}]" if m.get('resolved') and m['resolved'] != m['name'] else ""))
    print("\nEXTENDED:")
    for m in ext:
        print(f"  - {m['name']}" + (f"  [{m.get('resolved')}]" if m.get('resolved') and m['resolved'] != m['name'] else ""))
    print(f"\nKEYWORDS: {KEYWORDS}")


if __name__ == "__main__":
    asyncio.run(main())
