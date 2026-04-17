"""
Geographic tagging — extracts geo_primary and geo_secondary from article content.

Priority order (first match wins for geo_primary):
  1. GPE/LOC/location/constituency entity found in title
  2. GPE/LOC/location/constituency entity found in first 300 chars
  3. Known Indian state/city keyword in title
  4. NULL — never default to 'India' or 'World'
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_KNOWN_GEOS: tuple[str, ...] = (
    "Telangana", "Hyderabad", "Nizamabad", "Warangal", "Karimnagar",
    "Andhra Pradesh", "Vijayawada", "Visakhapatnam", "Guntur",
    "Mumbai", "Delhi", "Chennai", "Kolkata", "Bangalore", "Bengaluru",
    "Maharashtra", "Karnataka", "Tamil Nadu", "Kerala", "Gujarat",
    "Rajasthan", "Punjab", "Haryana", "Uttar Pradesh", "Bihar", "Odisha",
    "Jharkhand", "Assam", "West Bengal", "Madhya Pradesh",
    "Chhattisgarh", "Goa", "Jammu", "Kashmir", "Uttarakhand", "Himachal",
)

_GEO_ENTITY_LABELS: frozenset[str] = frozenset({"GPE", "LOC"})
_GEO_ENTITY_TYPES: frozenset[str] = frozenset({"location", "constituency"})


async def tag_geography(
    title: str,
    lead_text_translated: str | None,
    entities_extracted: list[dict],
) -> tuple[str | None, list[str]]:
    """
    Extract geographic focus from title, body, and extracted entities.

    Returns (geo_primary, geo_secondary).
    geo_primary is None when no clear geographic focus is found.
    geo_secondary contains up to 5 additional locations.
    """
    if not title:
        return None, []

    title_l = title.lower()
    body_start = (lead_text_translated or "")[:300].lower()

    geo_primary: str | None = None
    geo_secondary: list[str] = []

    def _is_geo_entity(ent: dict) -> bool:
        return (
            ent.get("label") in _GEO_ENTITY_LABELS
            or ent.get("type") in _GEO_ENTITY_TYPES
        )

    # Priority 1 — geo entity in title
    for ent in entities_extracted:
        if not _is_geo_entity(ent):
            continue
        name = ent["name"]
        if name.lower() not in title_l:
            continue
        if geo_primary is None:
            geo_primary = name
        else:
            geo_secondary.append(name)

    # Priority 2 — geo entity in first 300 chars
    if geo_primary is None:
        for ent in entities_extracted:
            if not _is_geo_entity(ent):
                continue
            name = ent["name"]
            if name.lower() not in body_start:
                continue
            if geo_primary is None:
                geo_primary = name
            else:
                geo_secondary.append(name)

    # Priority 3 — known geo keyword in title
    if geo_primary is None:
        for geo in _KNOWN_GEOS:
            if geo.lower() in title_l:
                geo_primary = geo
                break

    # NULL is the honest answer — never default to India or World
    return geo_primary, geo_secondary[:5]
