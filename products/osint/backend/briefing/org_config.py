"""Per-org candidate-selection config for the briefing pipeline.

The judge/report engine is multi-tenant, but candidate SELECTION (which web
articles / newspapers to pull for an org) was hardcoded to Telangana. This module
holds the per-state knobs — geography, vernacular language, newspaper sources,
print-paper markers, entertainment mutes. Adding a state = one entry here, no
engine change. `for_org` defaults to Telangana so an unknown org is safe.
"""
from __future__ import annotations

from typing import Any

TELANGANA = "31ad3fa9-25eb-4b3c-8a56-360696fc680a"
KARNATAKA = "dc6edb88-1392-447c-91bb-259944dd3971"

# entertainment literals common to every org (state-specific film terms live in
# each org's mute_extra). NOT "review/serial/song" — they kill real gov coverage.
BASE_MUTE = ["trailer", "box office", " ott ", "cinema", " ipl ", "fantasy league"]

ORG_CONFIG: dict[str, dict[str, Any]] = {
    TELANGANA: {
        "geo_states": ["Telangana"],
        "geo_like": ["%telangana%", "%hyderabad%"],
        "district_like": ["%telangana%", "%hyderabad%", "%warangal%", "%khammam%",
                          "%karimnagar%", "%nizamabad%", "%medak%", "%nalgonda%"],
        "np_language": "te",
        "np_sources": ["Telangana Today", "Deccan Chronicle", "Sakshi", "Eenadu",
                       "Namaste Telangana", "Mana Telangana", "Andhra Jyothi", "Manam"],
        "print_markers": ("eenadu", "sakshi", "namaste telangana", "namasthe telangana",
                          "mana telangana", "andhra jyothi", "andhra jyothy", "andhrajyothy",
                          "deccan chronicle", "the hindu", "times of india", "indian express",
                          "telangana today", "manam", "siasat", "deccan herald", "hans india"),
        "mute_extra": ["telangana film"],
    },
    KARNATAKA: {
        "geo_states": ["Karnataka"],
        "geo_like": ["%karnataka%", "%bengaluru%", "%bangalore%"],
        "district_like": ["%karnataka%", "%bengaluru%", "%bangalore%", "%mysuru%", "%mysore%",
                          "%hubli%", "%dharwad%", "%mangaluru%", "%mangalore%", "%belagavi%",
                          "%kalaburagi%", "%tumakuru%", "%shivamogga%", "%hassan%", "%udupi%",
                          "%ballari%", "%vijayapura%", "%davanagere%", "%chikkamagaluru%"],
        "np_language": "kn",
        "np_sources": ["Prajavani", "Vijaya Karnataka", "Vijayavani", "Udayavani",
                       "Kannada Prabha", "Deccan Herald", "The Hindu"],
        "print_markers": ("prajavani", "vijaya karnataka", "vijayavani", "udayavani",
                          "kannada prabha", "deccan herald", "the hindu", "times of india",
                          "indian express"),
        "mute_extra": ["kannada film", "sandalwood"],
        # KA TV is ingested via Scout keyword-search + free_transcript and marked
        # transcript_source='ka_scout' (separate from Telangana's relay pipeline).
        "tv_source_tag": "ka_scout",
    },
}

# transcript_source markers that belong to a specific tenant's TV ingestion; a
# default org must EXCLUDE these so another tenant's clips never leak in.
TENANT_TV_TAGS = ("ka_scout",)


def for_org(org_id: str) -> dict[str, Any]:
    """Candidate-selection config for an org; Telangana as the safe default."""
    return ORG_CONFIG.get(org_id, ORG_CONFIG[TELANGANA])
