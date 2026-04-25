"""Wikidata adapter — structured entity lookup. Free, no key.

Resolves a name to a Q-id via wbsearchentities, then pulls the entity claims
for date_of_birth (P569), occupation (P106), country (P27), employer (P108),
position_held (P39), official_website (P856), Twitter (P2002), GitHub (P2037),
Facebook (P2013), Instagram (P2003), image (P18), aliases.

For every claim whose value is itself a Q-id (occupation, country, employer,
position_held, etc.), we batch-resolve those Q-ids to their human-readable
English labels via wbgetentities (props=labels|descriptions). Findings then
carry a payload like {"qid": "Q668", "label": "India", "description": "..."}
instead of a raw "Q668" string — massive readability win.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.adapters.base import AdapterContext, AdapterSpec, Finding

log = logging.getLogger(__name__)

_API = "https://www.wikidata.org/w/api.php"
# Wikidata returns 403 to default httpx UA. Their policy requires identifying UA.
_UA = "RIG-Surveillance-Dossier/1.0 (https://rig.local; contact: ops@rig.local)"
_HEADERS = {"User-Agent": _UA, "Accept": "application/json"}

# property id  →  human-friendly field name on the Finding
_PROPS_OF_INTEREST: dict[str, str] = {
    "P569":  "date_of_birth",
    "P570":  "date_of_death",
    "P19":   "place_of_birth",
    "P106":  "occupation",
    "P27":   "country_of_citizenship",
    "P108":  "employer",
    "P39":   "position_held",
    "P102":  "political_party",
    "P184":  "doctoral_advisor",
    "P69":   "educated_at",
    "P856":  "official_website",
    "P2002": "twitter",
    "P2037": "github",
    "P2013": "facebook",
    "P2003": "instagram",
    "P3185": "vk",
    "P2397": "youtube",
    "P3984": "subreddit",
    "P3789": "telegram",
    "P6634": "linkedin",
    "P18":   "image",          # commons filename → resolved to URL below
    "P21":   "gender",
    "P735":  "given_name",
    "P734":  "family_name",
}

# Properties whose values are Q-ids that should be resolved to labels.
_QID_VALUED_FIELDS = {
    "occupation", "country_of_citizenship", "employer", "position_held",
    "political_party", "doctoral_advisor", "educated_at", "place_of_birth",
    "gender", "given_name", "family_name",
}

# Properties whose values are bare external IDs that we want to keep as strings
# (twitter handle, github user, etc.) — never look them up as Q-ids.
_STRING_VALUED_FIELDS = {
    "twitter", "github", "facebook", "instagram", "vk", "youtube", "subreddit",
    "telegram", "linkedin", "official_website",
}

_BATCH_SIZE = 50  # wbgetentities allows up to 50 ids per call


# ── Public entry point ────────────────────────────────────────────────────────

async def fetch(ctx: AdapterContext) -> list[Finding]:
    if ctx.target_type != "name":
        return []

    try:
        async with httpx.AsyncClient(timeout=ctx.timeout_s, headers=_HEADERS) as client:
            qid, label, description = await _search_entity(client, ctx.target)
            if not qid:
                return []
            entity = await _fetch_entity(client, qid)

            # First pass — collect raw claims and gather Q-ids needing labels.
            raw_claims = _extract_claims(entity)
            qids_to_resolve: set[str] = set()
            for field_name, raw_value in raw_claims:
                if (
                    field_name in _QID_VALUED_FIELDS
                    and isinstance(raw_value, str)
                    and raw_value.startswith("Q")
                ):
                    qids_to_resolve.add(raw_value)

            # Batch-resolve Q-id labels.
            label_map = await _resolve_labels(client, qids_to_resolve)

            # Resolve image filename (if present) to a Commons URL.
            image_filename: str | None = None
            for fname, val in raw_claims:
                if fname == "image" and isinstance(val, str):
                    image_filename = val
                    break

    except (httpx.HTTPError, ValueError) as e:
        log.warning("wikidata fetch failed for %s: %s", ctx.target, e)
        return []

    # ── Build identity finding (richest first) ────────────────────────────────
    identity_value: dict[str, Any] = {
        "qid": qid,
        "label": label,
        "description": description,
        "wikidata_url": f"https://www.wikidata.org/wiki/{qid}",
    }
    if image_filename:
        identity_value["image_url"] = _commons_image_url(image_filename)

    findings: list[Finding] = [
        Finding(
            source="wikidata",
            field="identity",
            value=identity_value,
            source_url=f"https://www.wikidata.org/wiki/{qid}",
            confidence=0.95,
        )
    ]

    # ── Build per-claim findings with resolved labels ────────────────────────
    for field_name, raw_value in raw_claims:
        if field_name == "image":
            continue  # already merged into identity
        rich_value = _enrich_value(field_name, raw_value, label_map)
        if rich_value is None:
            continue
        findings.append(
            Finding(
                source="wikidata",
                field=field_name,
                value=rich_value,
                source_url=f"https://www.wikidata.org/wiki/{qid}",
                confidence=0.9,
            )
        )
    return findings


# ── Wikidata API helpers ──────────────────────────────────────────────────────

async def _search_entity(
    client: httpx.AsyncClient, name: str
) -> tuple[str | None, str | None, str | None]:
    params = {
        "action": "wbsearchentities",
        "format": "json",
        "language": "en",
        "search": name,
        "limit": 1,
    }
    r = await client.get(_API, params=params)
    r.raise_for_status()
    hits = (r.json().get("search") or [])
    if not hits:
        return (None, None, None)
    h = hits[0]
    return (h.get("id"), h.get("label"), h.get("description"))


async def _fetch_entity(client: httpx.AsyncClient, qid: str) -> dict[str, Any]:
    params = {
        "action": "wbgetentities",
        "format": "json",
        "ids": qid,
        "props": "claims|labels|descriptions|aliases",
        "languages": "en",
    }
    r = await client.get(_API, params=params)
    r.raise_for_status()
    return (r.json().get("entities") or {}).get(qid) or {}


async def _resolve_labels(
    client: httpx.AsyncClient, qids: set[str]
) -> dict[str, dict[str, str | None]]:
    """Batch-resolve Q-ids → {qid: {"label": "...", "description": "..."}}."""
    if not qids:
        return {}
    out: dict[str, dict[str, str | None]] = {}
    qid_list = sorted(qids)
    for i in range(0, len(qid_list), _BATCH_SIZE):
        chunk = qid_list[i : i + _BATCH_SIZE]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(chunk),
            "props": "labels|descriptions",
            "languages": "en",
        }
        try:
            r = await client.get(_API, params=params)
            r.raise_for_status()
            entities = (r.json().get("entities") or {})
        except (httpx.HTTPError, ValueError) as e:
            log.warning("wikidata label batch failed: %s", e)
            continue
        for qid, ent in entities.items():
            label = (((ent.get("labels") or {}).get("en") or {}).get("value"))
            desc = (((ent.get("descriptions") or {}).get("en") or {}).get("value"))
            out[qid] = {"label": label, "description": desc}
    return out


# ── Claim extraction & enrichment ─────────────────────────────────────────────

def _extract_claims(entity: dict[str, Any]) -> list[tuple[str, Any]]:
    """Return a flat list of (field_name, raw_value) tuples for tracked claims."""
    claims = entity.get("claims") or {}
    out: list[tuple[str, Any]] = []
    for pid, field_name in _PROPS_OF_INTEREST.items():
        statements = claims.get(pid) or []
        for stmt in statements:
            value = _extract_value(stmt)
            if value is None or value == "":
                continue
            out.append((field_name, value))
    return out


def _extract_value(stmt: dict[str, Any]) -> Any:
    snak = (stmt.get("mainsnak") or {})
    dv = snak.get("datavalue") or {}
    val = dv.get("value")
    if isinstance(val, dict):
        if "id" in val:               # Q-id reference
            return val["id"]
        if "time" in val:             # date — strip leading "+", trim to YYYY-MM-DD
            t = str(val["time"])
            if t.startswith("+"):
                t = t[1:]
            # "+1950-09-17T00:00:00Z" → "1950-09-17"
            return t.split("T", 1)[0]
        if "amount" in val:
            return val["amount"]
    return val


def _enrich_value(
    field_name: str,
    raw_value: Any,
    label_map: dict[str, dict[str, str | None]],
) -> Any:
    """Turn raw claim values into rich payloads suitable for UI rendering."""
    # Q-id valued fields → resolve to {qid, label, description}
    if field_name in _QID_VALUED_FIELDS and isinstance(raw_value, str) \
            and raw_value.startswith("Q"):
        meta = label_map.get(raw_value) or {}
        return {
            "qid": raw_value,
            "label": meta.get("label") or raw_value,
            "description": meta.get("description"),
            "wikidata_url": f"https://www.wikidata.org/wiki/{raw_value}",
        }

    # Social handles → return bare string (so cascade can pick them up).
    if field_name in _STRING_VALUED_FIELDS:
        return raw_value if isinstance(raw_value, str) else None

    # Dates and everything else → pass-through.
    return raw_value


def _commons_image_url(filename: str, width: int = 320) -> str:
    """Build a Wikimedia Commons thumbnail URL from a bare filename.

    Uses the Special:FilePath endpoint which auto-resolves to the right thumb.
    """
    # FilePath accepts spaces; httpx will URL-encode.
    return (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        f"{filename}?width={width}"
    )


SPEC = AdapterSpec(
    name="wikidata",
    supported_types=("name",),
    fetch=fetch,
    sensitive=False,
)
