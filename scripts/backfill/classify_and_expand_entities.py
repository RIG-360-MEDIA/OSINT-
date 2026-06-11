"""classify_and_expand_entities.py — turn a 5000-name harvest into entity_dictionary rows.

Reads /tmp/harvest_top5000.tsv (name <TAB> mention_count), batches names through
Groq qwen3-32b in groups of 20, asks for structured classification, and inserts
verified rows into entity_dictionary with aliases + state + party + entity_type.

Run inside rig-backend container:
    docker exec rig-backend python3 /tmp/classify_and_expand_entities.py

Categorization buckets (matches existing entity_dictionary.entity_type values):
  person, organization, location, constituency, role, junk

Junk = drop (placeholders like 'unclear', 'someone', 'a witness')
Role = added with entity_type='role' (Farmers, Police, Officials, Spokesperson)
Location = added with entity_type='location' (country names)
Org = added with entity_type='organization' (parties, ministries, courts)
Person = added with entity_type='person' (politicians, leaders, CEOs)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from typing import Any

import httpx
from sqlalchemy import text

# Import backend's existing infra
sys.path.insert(0, "/app")
from backend.database import get_db
from backend.nlp.groq_client import call_groq

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("expand")

INPUT_FILE = os.environ.get("HARVEST_FILE", "/tmp/harvest_top5000.tsv")
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "20"))
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "6"))
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"

SYSTEM_PROMPT = """You are classifying names from Indian + global news articles for an entity dictionary.

For each name, decide:
- type: one of person | organization | location | role | junk
  - person = a specific individual (Trump, Modi, Putin, a cricketer, a CEO)
  - organization = political party, ministry, court, company, NGO, institution
  - location = country, state, city (NOT people)
  - role = generic role/group (Farmers, Police, Officials, Spokesperson, Citizens, Doctors)
  - junk = placeholder / unparseable / a noun phrase that isn't an entity
- country: ISO-2 country code if relevant (IN for India, US, GB, RU, CN etc.) or null
- state: Indian state name if relevant (e.g. "Telangana") or null
- party: political party abbreviation if a politician (BJP, INC, TDP, BRS, AAP, etc.) or null
- role_title: official role for persons (e.g. "Prime Minister", "Chief Minister", "CEO") or null
- aliases: list of 2-5 common short variants (e.g. for "Narendra Modi" → ["Modi", "PM Modi", "Shri Modi"])
- canonical: the cleanest full form of the name (e.g. "Donald Trump" not "D Trump")

Return ONLY a JSON object: {"results": [{"name": <input>, "type": ..., "country": ..., "state": ..., "party": ..., "role_title": ..., "aliases": [...], "canonical": ...}, ...]}
"""


def load_harvest() -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    with open(INPUT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or "|" not in line:
                continue
            name, count = line.rsplit("|", 1)
            try:
                rows.append((name.strip(), int(count)))
            except ValueError:
                continue
    return rows


async def classify_batch(batch: list[tuple[str, int]]) -> list[dict[str, Any]]:
    names = [n for n, _ in batch]
    user_msg = "Classify these names:\n" + "\n".join(f"- {n}" for n in names)
    try:
        raw = await call_groq(
            system=SYSTEM_PROMPT,
            user=user_msg,
            task_type="classification",
            json_response=True,
            max_tokens_override=4000,
        )
        data = json.loads(raw)
        results = data.get("results", [])
        # Pair each result back with its mention count
        name_to_count = {n: c for n, c in batch}
        for r in results:
            r["mention_count"] = name_to_count.get(r.get("name"), 0)
        return results
    except Exception as e:  # noqa: BLE001
        log.warning("batch failed: %s", e)
        return []


_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize(s: str) -> str:
    """Strip NULL bytes and other control chars asyncpg refuses to insert."""
    if not isinstance(s, str):
        return ""
    return _CONTROL_CHAR_RE.sub("", s).strip()


def normalize_aliases(name: str, aliases: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for a in (aliases or []) + [name]:
        if not isinstance(a, str):
            continue
        a_clean = _sanitize(a)
        if 2 <= len(a_clean) <= 80 and a_clean.lower() not in seen:
            out.append(a_clean)
            seen.add(a_clean.lower())
    return out[:6]


async def insert_entity(db: Any, row: dict[str, Any]) -> bool:
    etype = (row.get("type") or "").lower().strip()
    if etype not in {"person", "organization", "location", "role"}:
        return False  # skip junk
    canonical = _sanitize(row.get("canonical") or row.get("name") or "")
    if len(canonical) < 2 or len(canonical) > 200:
        return False
    aliases = normalize_aliases(canonical, row.get("aliases"))

    # Skip if already exists (by canonical_name OR an alias collision)
    exists = await db.execute(
        text("""
            SELECT 1 FROM entity_dictionary
             WHERE LOWER(canonical_name) = LOWER(:n)
                OR EXISTS (SELECT 1 FROM unnest(aliases) a WHERE LOWER(a) = LOWER(:n))
             LIMIT 1
        """),
        {"n": canonical},
    )
    if exists.fetchone():
        return False

    await db.execute(
        text("""
            INSERT INTO entity_dictionary
              (canonical_name, entity_type, aliases, state, party, metadata)
            VALUES (:cn, :et, :al, :st, :pt, :md)
        """),
        {
            "cn": canonical,
            "et": etype,
            "al": aliases,
            "st": row.get("state"),
            "pt": row.get("party"),
            "md": json.dumps({
                "source": "harvest_expansion_2026-05-26",
                "country": row.get("country"),
                "role_title": row.get("role_title"),
                "mention_count": row.get("mention_count"),
            }),
        },
    )
    return True


async def main() -> int:
    rows = load_harvest()
    log.info("loaded %d names from %s", len(rows), INPUT_FILE)
    if DRY_RUN:
        log.info("DRY_RUN=1 — will not write to DB")

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    batches = [rows[i : i + BATCH_SIZE] for i in range(0, len(rows), BATCH_SIZE)]
    log.info("%d batches of %d", len(batches), BATCH_SIZE)

    counters = {"persons": 0, "organizations": 0, "locations": 0, "roles": 0, "junk": 0, "skipped_dupe": 0, "inserted": 0}

    async def process(batch: list[tuple[str, int]], idx: int) -> None:
        async with sem:
            results = await classify_batch(batch)
            async with get_db() as db:
                for r in results:
                    etype = (r.get("type") or "").lower()
                    counters[etype + "s" if etype != "junk" else "junk"] = counters.get(etype + "s" if etype != "junk" else "junk", 0) + 1
                    if DRY_RUN:
                        continue
                    try:
                        if await insert_entity(db, r):
                            counters["inserted"] += 1
                        else:
                            counters["skipped_dupe"] += 1
                    except Exception as exc:  # noqa: BLE001
                        counters["insert_error"] = counters.get("insert_error", 0) + 1
                        log.warning("insert failed for %r: %s", r.get("canonical") or r.get("name"), exc)
                        await db.rollback()
                try:
                    await db.commit()
                except Exception:
                    await db.rollback()
            if idx % 10 == 0:
                log.info("batch %d/%d  counters=%s", idx, len(batches), counters)

    await asyncio.gather(*(process(b, i) for i, b in enumerate(batches)))
    log.info("DONE  counters=%s", counters)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
