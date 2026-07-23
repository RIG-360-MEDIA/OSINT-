"""draftsmith.config — every tunable in one place. No magic numbers elsewhere.

Values chosen from the live-verified box budget (8 cores, ~3.6 GB free RAM,
Cerebras gpt-oss-120b writer). Overridable via env where noted.
"""

from __future__ import annotations

import os

# --- model / provider --------------------------------------------------------
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_MODEL = "gpt-oss-120b"          # reuse the live generator's model + key pool (gc._CEREBRAS_KEYS)
PLANNER_TEMP = 0.2
VERIFY_TEMP = 0.0
REPAIR_TEMP = 0.2
# writer temperature is derived from the creativity dial: BASE + creativity * STEP
WRITER_TEMP_BASE = 0.5
WRITER_TEMP_STEP = 0.04
LLM_MAX_RETRIES = 3                        # tolerant-parse reprompt + temperature step-down

# --- worker ------------------------------------------------------------------
CONCURRENCY = int(os.environ.get("DRAFTSMITH_CONCURRENCY", "1"))   # RAM-bound; max 2
LEASE_SECONDS = 600
MAX_ATTEMPTS = 2
SOFT_TIME_LIMIT = 900                      # celery soft_time_limit; worst-case stage sum ~12 min

# --- per-stage timeouts (seconds) -------------------------------------------
TIMEOUTS = {
    "plan": 60,
    "gather_global": 220,       # seed embed (~40s) + slowest fan-out adapter
    "gather_source": 60,        # one DB-only adapter incl. a possible ~40s seed embed fallback
    "gather_seed_embed": 50,    # single shared seed embed in gather_all (remote LaBSE ~30-40s/call)
    "gather_web_fetch": 15,
    "rank": 60,                 # embedding-free now; ample
    "draft": 180,
    "verify": 90,
    "repair": 120,
    "images": 90,
}
MAX_REPAIR_ROUNDS = 2
# proceed to ranking only if ≥ this many source families returned, incl. ≥1 tier-1
GATHER_MIN_FAMILIES = 2

# --- source_id prefixes (citation handle families) --------------------------
SOURCE_ID_PREFIX = {
    "corpus_article": "c",
    "story_fact": "f",
    "youtube_clip": "y",
    "web": "w",
    "wikipedia": "k",
    "twitter": "t",
    "reddit": "r",
    "tiktok": "s",
    "telegram": "s",
    "instagram": "s",
    "wechat": "s",
}

# --- trust tiers -------------------------------------------------------------
# Base tier by source; refined per-item (watchlisted YT → 1, verified twitter → 2,
# web by outlet allowlist below).
BASE_TRUST_TIER = {
    "corpus_article": 1,
    "story_fact": 1,
    "youtube_clip": 2,      # → 1 when is_watchlisted
    "web": 3,               # → 1/2 via WEB_OUTLET_TIER
    "wikipedia": 1,         # context/background only (enforced in prompt)
    "twitter": 3,           # → 2 when verified
    "reddit": 3,
    "tiktok": 3,
    "telegram": 3,
    "instagram": 3,
    "wechat": 3,
}

# Outlet → tier for web/corpus results (substring match on host/outlet, lowercased).
# Wire services + majors = 1; known regional = 2; everything else = 3.
WEB_OUTLET_TIER = {
    "reuters.com": 1, "apnews.com": 1, "bloomberg.com": 1, "afp.com": 1,
    "bbc.co.uk": 1, "bbc.com": 1, "nytimes.com": 1, "washingtonpost.com": 1,
    "theguardian.com": 1, "wsj.com": 1, "ft.com": 1, "lemonde.fr": 1,
    "aljazeera.com": 1, "politico.eu": 1, "politico.com": 1, "cnn.com": 2,
    "dw.com": 2, "france24.com": 2, "kyivindependent.com": 2,
}
WEB_DEFAULT_TIER = 3

# --- selection caps into the BRIEF (per source_type) ------------------------
SELECT_CAPS = {
    "story_fact": 40,
    "corpus_article": 12,
    "web": 8,
    "youtube_clip": 6,
    "twitter": 8,
    "reddit": 5,
    "tiktok": 3,
    "telegram": 3,
    "instagram": 3,
    "wechat": 3,
    "wikipedia": 3,
}
# hard floors — never trim below these even under the token budget
SELECT_FLOOR = {"story_fact": 20, "corpus_article": 6}

# char caps on each item's snapshot text when placed in the BRIEF
CHAR_CAPS = {
    "corpus_article": 1500, "web": 2000, "youtube_clip": 800,
    "twitter": 500, "reddit": 500, "tiktok": 500, "telegram": 500,
    "instagram": 500, "wechat": 500, "wikipedia": 1200, "story_fact": 0,  # 0 = as-is
}

# --- gather fetch caps (raw rows pulled per adapter, pre-selection) ----------
FETCH_CAPS = {
    "warehouse_fts": 40, "warehouse_vector": 40, "story_fact": 60,
    "youtube_clip": 20, "twitter": 25, "reddit": 15, "tiktok": 10,
    "telegram": 10, "instagram": 10, "wechat": 10, "web": 10, "web_fetch": 8,
    "wikipedia": 5,
}

# --- relevance scoring weights ----------------------------------------------
RELEVANCE_WEIGHTS = {"cosine": 0.60, "recency": 0.25, "tier": 0.15}
TIER_WEIGHT = {1: 1.0, 2: 0.6, 3: 0.3}
RECENCY_HALFLIFE_DAYS = 3.0
DEDUP_COSINE = 0.95            # (legacy) LaBSE near-dup threshold; rank is now embedding-free
DEDUP_TEXT_RATIO = 0.90       # difflib near-dup threshold on the normalised leading text
DEDUP_TEXT_PREFIX_CHARS = 400  # chars of leading text compared for the near-dup ratio

# --- bundle budget -----------------------------------------------------------
BUNDLE_TOKEN_CEILING = 40_000  # pre-Headroom; trim lowest-relevance first, respect floors

# --- dial ladders (prompt lines injected by stage; sweepable in eval) --------
# creativity 0-10 → one of four register lines
CREATIVITY_LADDER = {
    (0, 2): "Register: conventional wire-desk prose. Clear, direct, no stylistic risk.",
    (3, 5): "Register: assured explainer voice — vivid where it earns it, never showy.",
    (6, 8): "Register: confident narrative craft — a strong arc, fresh framing, memorable lines.",
    (9, 10): "Register: take real structural and figurative risks — surprising but always precise; every image earns its place.",
}
# moxy 0-10 → one of four personality lines. Moxy is VOICE, never a licence to invent.
MOXY_LADDER = {
    (0, 0): "Voice: institutional and neutral. No asides.",
    (1, 3): "Voice: lightly wry where the facts allow a knowing aside; stays sober on serious material.",
    (4, 6): "Voice: pointed framing and confident asides — clearly analysis, never an invented fact.",
    (7, 10): "Voice: sharp, characterful, willing to editorialise the framing (not the facts); any edge lands on the powerful, never on victims.",
}

# --- images ------------------------------------------------------------------
IMAGE_SLOTS = 6
IMAGE_MIX = {"corpus": 2, "wikimedia": 2, "web": 2}

# --- publish -----------------------------------------------------------------
MANUAL_STORY_PUBLISHABLE_STATUS = "PUBLISHABLE"  # manual_stories filter is LIKE 'PUBLISHABLE%'

# --- external services -------------------------------------------------------
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://rig-searxng:8080")
WIKI_USER_AGENT = os.environ.get("WIKI_USER_AGENT", "RigWireDraftsmith/1.0 (contact: ops@rig)")

# --- api ---------------------------------------------------------------------
API_PORT = int(os.environ.get("DRAFTSMITH_PORT", "8077"))
API_TOKEN_ENV = "DRAFTSMITH_API_TOKEN"   # resolved at request time; never inlined


def creativity_line(creativity: int) -> str:
    for (lo, hi), line in CREATIVITY_LADDER.items():
        if lo <= creativity <= hi:
            return line
    return CREATIVITY_LADDER[(3, 5)]


def moxy_line(moxy: int) -> str:
    for (lo, hi), line in MOXY_LADDER.items():
        if lo <= moxy <= hi:
            return line
    return MOXY_LADDER[(1, 3)]


def writer_temperature(creativity: int) -> float:
    return round(WRITER_TEMP_BASE + creativity * WRITER_TEMP_STEP, 3)
