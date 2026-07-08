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


# ── WeChat: English -> Chinese term map (for Sogou Weixin search) ─────────────
# WeChat is Chinese-language, so English keywords under-return. This curated map
# (keys lowercased) covers the common India/China/Pakistan OSINT entities for an
# instant, exact translation; anything not here falls back to a live translator.

WECHAT_TERM_MAP: dict[str, str] = {
    # leaders
    "modi": "莫迪", "narendra modi": "莫迪", "xi jinping": "习近平", "xi": "习近平",
    "putin": "普京", "trump": "特朗普", "biden": "拜登",
    "jaishankar": "苏杰生", "rajnath singh": "拉杰纳特·辛格",
    "imran khan": "伊姆兰·汗", "shehbaz sharif": "夏巴兹·谢里夫",
    # countries / regions
    "india": "印度", "pakistan": "巴基斯坦", "china": "中国", "russia": "俄罗斯",
    "united states": "美国", "usa": "美国", "america": "美国",
    "bangladesh": "孟加拉国", "sri lanka": "斯里兰卡", "nepal": "尼泊尔",
    "afghanistan": "阿富汗", "iran": "伊朗", "taiwan": "台湾", "japan": "日本",
    "bhutan": "不丹", "myanmar": "缅甸", "maldives": "马尔代夫",
    "ladakh": "拉达克", "kashmir": "克什米尔", "arunachal": "阿鲁纳恰尔",
    "galwan": "加勒万", "doklam": "洞朗", "tibet": "西藏", "xinjiang": "新疆",
    "south china sea": "南海", "indo-pacific": "印太",
    # military
    "pla": "解放军", "pla navy": "解放军海军", "pla army": "解放军陆军",
    "pla air force": "解放军空军", "pla rocket force": "火箭军",
    "indian navy": "印度海军", "indian army": "印度陆军",
    "indian air force": "印度空军", "iaf": "印度空军",
    "rafale": "阵风", "brahmos": "布拉莫斯", "s-400": "S-400",
    "aircraft carrier": "航空母舰", "submarine": "潜艇", "missile": "导弹",
    "nuclear": "核武器", "hypersonic": "高超音速", "fighter jet": "战斗机",
    "border": "边境", "lac": "实际控制线", "line of actual control": "实际控制线",
    # orgs / events
    "brics": "金砖国家", "quad": "四方安全对话", "sco": "上海合作组织",
    "bjp": "印度人民党", "operation sindoor": "辛杜尔行动",
    "belt and road": "一带一路", "bri": "一带一路",
}
