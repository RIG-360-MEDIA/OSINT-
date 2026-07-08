"""Curated OSINT source sets — Telegram channels + Reddit intelligence subs.

Telegram has NO free global keyword search, so we search a curated channel SET
(`t.me/s/{channel}?q=`). Every channel here was liveness-verified on the Hetzner
box (2026-07-08) — it returns real posts via the public preview page, no bot
token. Channels with preview disabled / wrong handles were dropped.

Reddit search is already global, so `REDDIT_INTEL_SUBREDDITS` is a curated
high-signal WATCHLIST — for subreddit-scoped searches and as a monitoring set of
the goldmine / underrated / intelligence communities.
"""
from __future__ import annotations

# ── Telegram channels (liveness-verified, categorized) ───────────────────────

TELEGRAM_CHANNELS: dict[str, list[str]] = {
    # Global OSINT / conflict-monitoring — the heavy hitters
    "global_osint": [
        "OSINTdefender", "rybar", "intelslava", "WarMonitors", "Faytuks",
        "DDGeopolitics", "clashreport", "spectatorindex", "warfareanalysis",
        "worldsource24", "thewarnews", "EndgameWW3", "geopolitics_live",
    ],
    # Ukraine / Russia / Israel theatre
    "conflict_theatre": [
        "DeepStateUA", "wartranslated", "sprinterobserver", "IsraelWarRoom",
    ],
    # India news + government
    "india_news": [
        "megh_updates", "mygovindia", "aninews", "zeenews", "sudarshannews",
        "ndtv", "timesofindia", "firstpost", "theprintindia", "IndianExpress",
    ],
    # India / IndoPacific defence + think-tanks
    "india_defence": [
        "indiandefensenews", "OrfOnline",
    ],
}


def all_telegram_channels() -> list[str]:
    """Flat, de-duplicated list of every curated channel."""
    seen: set[str] = set()
    out: list[str] = []
    for group in TELEGRAM_CHANNELS.values():
        for ch in group:
            if ch not in seen:
                seen.add(ch)
                out.append(ch)
    return out


# ── Reddit intelligence subreddits (curated watchlist) ───────────────────────
# The Reddit collector searches ALL of Reddit globally, so this is a high-signal
# set for scoped search + monitoring — the goldmines, the underrated, the niche.

REDDIT_INTEL_SUBREDDITS: dict[str, list[str]] = {
    # THE goldmines — heavily-moderated, expert-level analysis
    "goldmine": [
        "CredibleDefense",       # the gold standard; strict moderation, analysts
        "WarCollege",            # ask-the-experts on military history/doctrine
        "LessCredibleDefence",   # looser sister of CredibleDefense, still high signal
        "geopolitics",
    ],
    # OSINT / intelligence tradecraft + primary footage
    "osint": [
        "OSINT", "intelligence", "CombatFootage",
        "UkraineWarVideoReport", "UkraineRussiaReport",
    ],
    # Underrated / niche — less obvious, high context-per-post
    "underrated": [
        "NonCredibleDefense",    # memes on top, but breaks real signal early
        "AfterTheLoop",          # "what's the context behind this news?"
        "NeutralPolitics",       # sourced, fact-first political analysis
        "anime_titties",         # (ironically named) serious world-news discussion
        "WarplanePorn",
    ],
    # Regional — India / China / IndoPacific
    "regional": [
        "GeopoliticsIndia", "IndianDefense", "IndiaSpeaks",
        "Kashmir", "Sino", "China_irl", "geopolitics",
    ],
}


def all_intel_subreddits() -> list[str]:
    """Flat, de-duplicated list of every curated subreddit."""
    seen: set[str] = set()
    out: list[str] = []
    for group in REDDIT_INTEL_SUBREDDITS.values():
        for sub in group:
            if sub not in seen:
                seen.add(sub)
                out.append(sub)
    return out
