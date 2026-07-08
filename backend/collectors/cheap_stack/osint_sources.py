"""Curated OSINT source sets — Telegram channels + Reddit intelligence subs.

Telegram has NO free global keyword search, so we search a curated channel SET
(`t.me/s/{channel}?q=`). Every channel here was liveness-verified on the Hetzner
box (2026-07-08) — it returns real posts via the public preview page, no bot
token. Channels with preview disabled / wrong handles were dropped.

Reddit search is already global, so `REDDIT_INTEL_SUBREDDITS` is a curated
high-signal WATCHLIST (all liveness-verified) — for subreddit-scoped searches
and as a monitoring set of the goldmine / underrated / intelligence communities.

~85 Telegram channels + ~85 Reddit subreddits across the categories below.
"""
from __future__ import annotations

# ── Telegram channels (liveness-verified, categorized) ───────────────────────

TELEGRAM_CHANNELS: dict[str, list[str]] = {
    # Global OSINT / conflict-monitoring — the heavy hitters
    "global_osint": [
        "OSINTdefender", "rybar", "intelslava", "WarMonitors", "Faytuks",
        "DDGeopolitics", "clashreport", "spectatorindex", "warfareanalysis",
        "worldsource24", "thewarnews", "EndgameWW3", "geopolitics_live",
        "WW3Media", "warmonitor",
    ],
    # Breaking-news wires / high-velocity aggregators
    "breaking_wire": [
        "disclosetv", "BNONews", "CollinRugg", "RadioGenoa",
    ],
    # OSINT community channels (discovered by mining r/OSINT recommendations)
    "osint_community": [
        "osint_anatomy", "UK_OSINT", "OsintUpdates", "osint_mindset",
        "sonar_official",
    ],
    # Ukraine / Russia / Israel theatre
    "conflict_theatre": [
        "DeepStateUA", "wartranslated", "sprinterobserver", "IsraelWarRoom",
    ],
    # Russia — state media + milbloggers (read critically)
    "russia": [
        "readovkanews", "mash", "bazabazon", "SolovievLive", "warfakes",
        "milinfolive", "dva_majora", "boris_rozhin", "tass_agency",
    ],
    # Ukraine — official + war reporting
    "ukraine": [
        "nexta_tv", "KyivIndependent_official", "Pravda_Gerashchenko",
        "insiderUKR", "war_home", "ukraine_watch", "serhii_flash",
        "operativnoZSU", "ukrpravda_news", "tsaplienko", "V_Zelenskiy_official",
        "odeskaODA",
    ],
    # China / Taiwan / IndoPacific
    "china_indopacific": [
        "EyesOnAsia", "ChinaOSINT", "HKMilitary", "china3army",
    ],
    # Middle East / Iran / Gaza
    "middle_east": [
        "IranIntl_En", "muraselon", "QudsNen", "abualiexpress", "englishabuali",
    ],
    # Cyber / infosec / threat intel
    "cyber_infosec": [
        "vxunderground", "malwrhunterteam", "TheHackerNews", "cyberknow20",
        "BleepingComputer", "CyberSecurityNews",
    ],
    # Aviation / naval / nuclear / space
    "air_sea_space": [
        "planespottersnet", "navalnews", "nuclear_news", "nextspaceflight",
    ],
    # Economics / markets / finance
    "economics_markets": [
        "financialjuice", "markettwits", "moneycontrolcom", "livemint",
    ],
    # India news + government
    "india_news": [
        "megh_updates", "mygovindia", "aninews", "zeenews", "sudarshannews",
        "ndtv", "timesofindia", "firstpost", "theprintindia", "IndianExpress",
        "thewire_in", "thequint", "scroll_in", "hindustantimes", "dnaindia",
        "htTweets",
    ],
    # India / IndoPacific defence + think-tanks
    "india_defence": [
        "indiandefensenews", "OrfOnline", "DRDO_India", "indiannavy",
    ],
    # Pakistan
    "pakistan": [
        "ARYNewsofficial", "propakistani",
    ],
    # Africa
    "africa": [
        "AfricaIntelligence",
    ],
    # Think-tanks / long-form analysis
    "think_tanks": [
        "criticalthreats", "carnegieendowment",
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
        "CredibleDiplomacy",     # the diplomacy counterpart to CredibleDefense
    ],
    # OSINT / intelligence tradecraft + primary footage
    "osint": [
        "OSINT", "intelligence", "CombatFootage",
        "UkraineWarVideoReport", "UkraineRussiaReport",
    ],
    # Cyber / threat intel / infosec
    "cyber": [
        "cybersecurity", "netsec", "Malware", "ReverseEngineering",
        "AskNetsec", "privacy", "blackhat", "onions",
    ],
    # Defence / military
    "military": [
        "Military", "MilitaryHistory", "MilitaryStrategy", "submarines",
        "WarshipPorn", "TankPorn", "WeaponsPorn", "WarplanePorn",
    ],
    # Geopolitics / international relations
    "geopolitics_ir": [
        "IRstudies", "foreignpolicy", "InternationalNews", "worldevents",
        "PoliticalScience", "GlobalTalk", "GeopoliticsIndia", "GeopoliticsIndia2",
    ],
    # Active-conflict tracking
    "conflict": [
        "UkrainianConflict", "russiawarinukraine", "syriancivilwar",
        "YemeniCrisis", "IsraelPalestine", "Kurdistan", "LebaneseArmy",
    ],
    # Regional — world
    "regional_world": [
        "taiwan", "HongKong", "korea", "japan", "Philippines", "Pakistan",
        "bangladesh", "afghanistan", "iran", "europe", "AskARussian",
        "Africa", "LatinAmerica", "Sino", "China_irl",
    ],
    # Regional — India
    "india": [
        "IndiaSpeaks", "IndianDefense", "unitedstatesofindia", "librandu",
        "IndianStreetBets", "IndiaInvestments", "indianews", "IndianModerate",
        "Kerala", "bangalore", "Kashmir",
    ],
    # Economics / energy / geoeconomics
    "economics": [
        "economics", "GlobalMarkets", "energy", "oil", "geopoliticaleconomy",
    ],
    # Science / space intelligence
    "science_space": [
        "space", "aerospace", "satellites",
    ],
    # Underrated / high-context / long-form
    "underrated": [
        "NonCredibleDefense",    # memes on top, but breaks real signal early
        "AfterTheLoop",          # "what's the context behind this news?"
        "NeutralPolitics",       # sourced, fact-first political analysis
        "NeutralNews",
        "anime_titties",         # (ironically named) serious world-news discussion
        "TrueReddit", "Foodforthought", "InDepthStories", "Ask_Politics",
        "Hostile_Takeovers",
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
