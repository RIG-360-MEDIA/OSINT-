"""
World Monitor — Telangana briefing endpoints.

Frontend at /worldmonitor (scope=telangana) hits /api/worldmonitor/telangana/
briefing for the assembled briefing data: weather, air quality, ACLED
events filtered to Telangana, Telugu RSS news, and an LLM-generated one-
paragraph summary.

Responses cached in-process for CACHE_TTL_S so we don't hammer upstream
APIs (ACLED has a free-tier quota; Groq is paid per token). Cache is
keyed by route only — no per-user variation today.

All endpoints require a Supabase session (matches the rest of rig).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any

import feedparser
import httpx
from fastapi import APIRouter, Depends, HTTPException

from backend.auth.auth_middleware import get_current_principal, get_current_user, require_page
from backend.nlp.groq_client import GroqCallFailed, GroqQuotaExhausted, generate

logger = logging.getLogger(__name__)

worldmonitor_router = APIRouter(
    prefix="/api/worldmonitor",
    tags=["worldmonitor"],
    dependencies=[Depends(require_page("worldmonitor"))],
)

# ─── config ──────────────────────────────────────────────────────────────

HYDERABAD_LAT = 17.385
HYDERABAD_LON = 78.4867
HYDERABAD_TZ = "Asia/Kolkata"
ACLED_TOKEN = os.getenv("ACLED_ACCESS_TOKEN", "").strip()
CACHE_TTL_S = int(os.getenv("WM_TG_CACHE_TTL_S", "1800"))  # 30 min
HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

TELANGANA_RSS_FEEDS = [
    ("thehindu-hyd", "The Hindu — Hyderabad", "https://www.thehindu.com/news/cities/Hyderabad/feeder/default.rss"),
    ("dc-hyd",       "Deccan Chronicle — Hyderabad", "https://www.deccanchronicle.com/rss/section/cities/hyderabad"),
    ("tg-today",     "Telangana Today", "https://www.telanganatoday.com/feed"),
    ("siasat-hyd",   "Siasat — Hyderabad", "https://www.siasat.com/feed/"),
]

# Telugu news YouTube channels — IDs scraped from each channel's @handle page.
# The legacy youtube.com/embed/live_stream?channel=<ID> URL pattern is broken
# in 2026; we instead resolve each channel's currently-live video ID by
# scraping /channel/<ID>/live and embed that video directly.
TELUGU_CHANNELS = [
    ("UCDCMjD1XIAsCZsYHNMGVcog", "V6 News"),
    ("UCPXTXMecYqnRKNdqdVOGSFg", "TV9 Telugu"),
    ("UCk0XiSICe9O0YO8oNFVpPAA", "T News"),
    ("UC_2irx_BQR7RsBKmUV9fePQ", "ABN Telugu"),
    ("UCfymZbh17_3T_UhgjkQ9fRQ", "10TV Telugu"),
    ("UCZ9m4KOh8Ei60428xeGYDCQ", "Sakshi TV"),
    ("UC-PPlFHLfi4wcFOe6DrReCQ", "News18 Telugu"),
    ("UCAR3h_9fLV82N2FH4cE4RKw", "TV5 News"),
    ("UCumtYpCY26F6Jr3satUgMvA", "NTV Telugu"),
]
YT_VIDEO_ID_RE = re.compile(r"watch\?v=([A-Za-z0-9_-]{11})")

# ─── tiny in-process TTL cache ───────────────────────────────────────────

_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Any | None:
    hit = _cache.get(key)
    if hit is None:
        return None
    expires_at, value = hit
    if time.time() > expires_at:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any, ttl: int = CACHE_TTL_S) -> None:
    _cache[key] = (time.time() + ttl, value)


# ─── upstream fetchers ───────────────────────────────────────────────────


async def _fetch_weather(client: httpx.AsyncClient) -> dict[str, Any]:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={HYDERABAD_LAT}&longitude={HYDERABAD_LON}"
        "&current=temperature_2m,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min"
        f"&timezone={HYDERABAD_TZ}&forecast_days=1"
    )
    r = await client.get(url)
    r.raise_for_status()
    j = r.json()
    return {
        "temp_c": j.get("current", {}).get("temperature_2m"),
        "max_c": (j.get("daily", {}).get("temperature_2m_max") or [None])[0],
        "min_c": (j.get("daily", {}).get("temperature_2m_min") or [None])[0],
        "weather_code": j.get("current", {}).get("weather_code"),
    }


async def _fetch_air(client: httpx.AsyncClient) -> dict[str, Any]:
    url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={HYDERABAD_LAT}&longitude={HYDERABAD_LON}"
        "&current=us_aqi,pm2_5,pm10"
    )
    r = await client.get(url)
    r.raise_for_status()
    cur = r.json().get("current", {})
    return {
        "aqi": cur.get("us_aqi"),
        "pm25": cur.get("pm2_5"),
        "pm10": cur.get("pm10"),
    }


async def _fetch_acled(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """ACLED Telangana events — past 7 days. Empty list on missing token / failure."""
    if not ACLED_TOKEN:
        return []
    url = "https://api.acleddata.com/acled/read"
    params = {
        "key": ACLED_TOKEN,
        "country": "India",
        "admin1": "Telangana",
        "limit": 50,
        "_format": "json",
    }
    try:
        r = await client.get(url, params=params)
        r.raise_for_status()
        events = r.json().get("data", []) or []
    except Exception as e:  # noqa: BLE001
        logger.warning("ACLED fetch failed: %s", e)
        return []

    # Trim to fields the UI needs
    return [
        {
            "event_date": e.get("event_date"),
            "event_type": e.get("event_type"),
            "sub_event_type": e.get("sub_event_type"),
            "actor1": e.get("actor1"),
            "location": e.get("location"),
            "fatalities": int(e.get("fatalities") or 0),
            "notes": (e.get("notes") or "")[:280],
        }
        for e in events[:50]
    ]


def _parse_feed_sync(label: str, src_id: str, url: str) -> list[dict[str, Any]]:
    """feedparser is sync — call from a thread."""
    try:
        d = feedparser.parse(url)
    except Exception as e:  # noqa: BLE001
        logger.warning("RSS parse failed (%s): %s", url, e)
        return []
    items: list[dict[str, Any]] = []
    for entry in (d.entries or [])[:10]:
        items.append(
            {
                "source": src_id,
                "source_label": label,
                "title": getattr(entry, "title", "") or "",
                "link": getattr(entry, "link", "") or "",
                "published": getattr(entry, "published", "") or getattr(entry, "updated", "") or "",
                "summary": (getattr(entry, "summary", "") or "")[:280],
            }
        )
    return items


async def _fetch_rss_all() -> list[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, _parse_feed_sync, label, src_id, url)
        for src_id, label, url in TELANGANA_RSS_FEEDS
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    flat: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, list):
            flat.extend(r)
    flat.sort(key=lambda x: x.get("published", ""), reverse=True)
    return flat[:30]


# ─── stability + summary composer ────────────────────────────────────────


def _stability(weather: dict[str, Any], air: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    aqi = air.get("aqi")
    max_c = weather.get("max_c")

    air_sub = 0.6 if aqi is None else max(0.0, 1.0 - min(float(aqi), 300.0) / 300.0)
    heat_sub = 0.6 if max_c is None else max(0.0, 1.0 - max(0.0, float(max_c) - 30.0) / 15.0)

    # Conflict sub-signal: 50 events in 7 days → 0; zero events → 1
    conflict_sub = max(0.0, 1.0 - len(events) / 50.0)
    news_sub = 1.0  # placeholder until anomaly scoring lands

    composite = air_sub * 0.30 + heat_sub * 0.25 + conflict_sub * 0.25 + news_sub * 0.20
    score = int(round(composite * 100))
    label = (
        "Calm" if score >= 75 else "Watchful" if score >= 60 else "Strained" if score >= 40 else "Critical"
    )
    return {"score": score, "label": label}


async def _generate_summary(
    weather: dict[str, Any],
    air: dict[str, Any],
    events: list[dict[str, Any]],
    news: list[dict[str, Any]],
) -> str:
    """LLM-write the one-paragraph briefing. Falls back to a templated line on Groq error."""
    # D-14 fix — be explicit when ACLED is unavailable. Previously the prompt
    # treated "events=[]" as "no incidents" and the LLM produced falsely
    # reassuring text like "Telangana remains stable, no reported incidents".
    acled_available = bool(ACLED_TOKEN)
    if acled_available:
        events_fact = f"ACLED events past 7 days: {len(events)}."
    else:
        events_fact = (
            "ACLED conflict-event data is UNAVAILABLE this run "
            "(token unset) — do NOT infer absence of incidents."
        )
    facts = [
        f"Hyderabad temp now {weather.get('temp_c')}°C, today max {weather.get('max_c')}°C.",
        f"AQI {air.get('aqi')} (PM2.5 {air.get('pm25')} µg/m³).",
        events_fact,
        f"Top news headlines today: " + "; ".join(n["title"] for n in news[:5]) if news else "No fresh headlines.",
    ]
    sys_prompt = (
        "You are a calm regional analyst writing a single-paragraph briefing about "
        "Telangana state in India. Write 3-5 sentences. Do NOT use bullet points. "
        "Use a neutral wire-service tone. Lead with the most important signal. "
        "Mention Hyderabad's air quality and weather only when notable. Cite "
        "concrete numbers. Avoid hedging adverbs. End with one forward-looking sentence. "
        "If a data source is marked UNAVAILABLE, say so plainly — never imply "
        "absence of data means absence of events."
    )
    user_prompt = "Today's signals:\n" + "\n".join(f"- {f}" for f in facts)
    try:
        text = await generate(sys_prompt, user_prompt)
        return text.strip()
    except (GroqCallFailed, GroqQuotaExhausted) as e:
        logger.warning("Groq summary fallback (%s)", e)
    except Exception as e:  # noqa: BLE001
        logger.warning("Summary generation failed: %s", e)

    # Templated fallback
    parts: list[str] = []
    if air.get("aqi") is not None:
        parts.append(f"Hyderabad AQI {int(air['aqi'])}.")
    if weather.get("max_c") is not None:
        parts.append(f"High of {int(weather['max_c'])}°C forecast.")
    if ACLED_TOKEN:
        parts.append(f"{len(events)} ACLED events recorded in the past week.")
    else:
        parts.append("ACLED conflict-event data unavailable this run.")
    parts.append(f"{len(news)} fresh headlines in the local press.")
    return " ".join(parts)


# ─── routes ──────────────────────────────────────────────────────────────


@worldmonitor_router.get("/telangana/briefing")
async def telangana_briefing(user: dict = Depends(get_current_principal)) -> dict[str, Any]:
    """Composite briefing — weather, air, events, news, stability index, summary."""
    cached = _cache_get("telangana:briefing")
    if cached:
        return {**cached, "cached": True}

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        weather, air, events, news = await asyncio.gather(
            _fetch_weather(client),
            _fetch_air(client),
            _fetch_acled(client),
            _fetch_rss_all(),
            return_exceptions=True,
        )

    weather = weather if isinstance(weather, dict) else {}
    air = air if isinstance(air, dict) else {}
    events = events if isinstance(events, list) else []
    news = news if isinstance(news, list) else []

    stability = _stability(weather, air, events)
    summary = await _generate_summary(weather, air, events, news)

    payload = {
        "scope": "telangana",
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "weather": weather,
        "air": air,
        "events": events,
        "news": news,
        "stability": stability,
        "summary": summary,
        "cached": False,
    }
    _cache_set("telangana:briefing", payload)
    return payload


@worldmonitor_router.get("/telangana/news")
async def telangana_news(user: dict = Depends(get_current_principal)) -> dict[str, Any]:
    """Just the Telugu / Hyderabad RSS items."""
    cached = _cache_get("telangana:news")
    if cached:
        return {**cached, "cached": True}
    items = await _fetch_rss_all()
    payload = {"items": items, "count": len(items), "cached": False}
    _cache_set("telangana:news", payload, ttl=900)  # 15 min
    return payload


async def _resolve_live_video(client: httpx.AsyncClient, channel_id: str) -> str | None:
    """Scrape the channel's /live page and pull the canonical video ID.
    Returns None if the channel is not currently broadcasting."""
    try:
        r = await client.get(
            f"https://www.youtube.com/channel/{channel_id}/live",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0)"},
            follow_redirects=True,
        )
        if r.status_code != 200:
            return None
        m = YT_VIDEO_ID_RE.search(r.text)
        return m.group(1) if m else None
    except Exception as e:  # noqa: BLE001
        logger.warning("YouTube live resolve failed for %s: %s", channel_id, e)
        return None


@worldmonitor_router.get("/telangana/live-channels")
async def telangana_live_channels(user: dict = Depends(get_current_principal)) -> dict[str, Any]:
    """Resolve current live video IDs for the configured Telugu news channels.
    Cached for 1 hour — live IDs change ~daily."""
    cached = _cache_get("telangana:live-channels")
    if cached:
        return {**cached, "cached": True}

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        ids = await asyncio.gather(*(_resolve_live_video(client, cid) for cid, _ in TELUGU_CHANNELS))

    channels = [
        {"channel_id": cid, "label": label, "video_id": vid, "live": vid is not None}
        for (cid, label), vid in zip(TELUGU_CHANNELS, ids)
    ]
    payload = {
        "channels": channels,
        "live_count": sum(1 for c in channels if c["live"]),
        "total": len(channels),
        "cached": False,
    }
    _cache_set("telangana:live-channels", payload, ttl=3600)
    return payload


@worldmonitor_router.get("/telangana/events")
async def telangana_events(user: dict = Depends(get_current_principal)) -> dict[str, Any]:
    """ACLED events filtered to Telangana, past 7 days."""
    if not ACLED_TOKEN:
        raise HTTPException(503, "ACLED token not configured (ACLED_ACCESS_TOKEN env)")
    cached = _cache_get("telangana:events")
    if cached:
        return {**cached, "cached": True}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        events = await _fetch_acled(client)
    payload = {"events": events, "count": len(events), "cached": False}
    _cache_set("telangana:events", payload)
    return payload
