"""
Sprint-0 corpus-wide substrate extraction runner.

Usage (inside rig-backend container):
    python3 -m backend.tasks.substrate.run_corpus_pass --limit 100   # smoke
    python3 -m backend.tasks.substrate.run_corpus_pass --all          # full corpus
    python3 -m backend.tasks.substrate.run_corpus_pass --since 7      # last N days

Per-article: trafilatura HTML re-fetch + BS4 structural parse + Groq
semantic enrichment. Writes to articles, article_links, article_media,
article_locations, article_events.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
import unicodedata
from typing import Any
from urllib.parse import urlparse, urlunparse

import trafilatura
from bs4 import BeautifulSoup
from sqlalchemy import text

from backend.database import get_db
from backend.nlp.groq_client import (
    FAST_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)
from backend.tasks.substrate.enrich_tweets import (
    enrich_article_tweets,
    is_tweet_url,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("substrate")


# ─────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# Full browser-like header set — required by sources whose WAFs check more
# than just the User-Agent (PIB, Sunday Guardian, etc reject default UAs).
# See docs/mistakes.md — the same Cloudflare-1010 pattern as #8 / #12.
_BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
MIN_BODY_CHARS = 120
MAX_BODY_FOR_GROQ = 2400
GROQ_TASK_TYPE = "profile_extraction"     # 1000-token cap

ARTICLE_TYPES = {
    "news", "opinion", "analysis", "explainer", "listicle",
    "horoscope", "recipe", "live_blog", "photo_essay",
    "interview", "press_release", "sports_result", "other",
}

# Coarse city → (country, lat, lng) lookup. Covers typical Indian + global
# coverage centres; unlisted cities fall through to country-only resolution.
GEO: dict[str, tuple[str, float, float]] = {
    # India · top
    "hyderabad":      ("India",     17.385,  78.486),
    "secunderabad":   ("India",     17.439,  78.498),
    "new delhi":      ("India",     28.613,  77.209),
    "delhi":          ("India",     28.704,  77.103),
    "mumbai":         ("India",     19.076,  72.877),
    "bengaluru":      ("India",     12.972,  77.594),
    "bangalore":      ("India",     12.972,  77.594),
    "chennai":        ("India",     13.083,  80.270),
    "kolkata":        ("India",     22.572,  88.363),
    "ahmedabad":      ("India",     23.022,  72.571),
    "pune":           ("India",     18.520,  73.856),
    "lucknow":        ("India",     26.847,  80.946),
    "patna":          ("India",     25.594,  85.137),
    "bhopal":         ("India",     23.259,  77.412),
    "jaipur":         ("India",     26.913,  75.787),
    "thiruvananthapuram": ("India", 8.524,   76.937),
    "kochi":          ("India",     9.931,   76.267),
    # Telangana
    "karimnagar":     ("India",     18.434,  79.131),
    "khammam":        ("India",     17.246,  80.150),
    "warangal":       ("India",     17.978,  79.594),
    "adilabad":       ("India",     19.665,  78.530),
    "nizamabad":      ("India",     18.671,  78.094),
    "nalgonda":       ("India",     17.054,  79.267),
    "mahbubnagar":    ("India",     16.748,  77.985),
    "medak":          ("India",     18.046,  78.265),
    "siddipet":       ("India",     18.103,  78.853),
    # Andhra Pradesh
    "vijayawada":     ("India",     16.506,  80.648),
    "visakhapatnam":  ("India",     17.687,  83.219),
    "amaravati":      ("India",     16.512,  80.516),
    "tirupati":       ("India",     13.628,  79.420),
    "guntur":         ("India",     16.306,  80.436),
    # Other Indian states (a tier of common ones)
    "chandigarh":     ("India",     30.733,  76.779),
    "indore":         ("India",     22.719,  75.857),
    "nagpur":         ("India",     21.146,  79.088),
    "guwahati":       ("India",     26.144,  91.736),
    "bhubaneswar":    ("India",     20.296,  85.824),
    "ranchi":         ("India",     23.344,  85.310),
    "raipur":         ("India",     21.251,  81.629),
    # Global
    "london":         ("United Kingdom",  51.507,  -0.128),
    "new york":       ("United States",   40.713, -74.006),
    "washington":     ("United States",   38.908, -77.036),
    "san francisco":  ("United States",   37.775, -122.419),
    "los angeles":    ("United States",   34.052, -118.243),
    "paris":          ("France",          48.857,  2.353),
    "berlin":         ("Germany",         52.520, 13.405),
    "tokyo":          ("Japan",           35.689, 139.692),
    "beijing":        ("China",           39.904, 116.407),
    "shanghai":       ("China",           31.230, 121.474),
    "hong kong":      ("China",           22.302, 114.177),
    "singapore":      ("Singapore",        1.352, 103.820),
    "dubai":          ("United Arab Emirates", 25.276, 55.296),
    "moscow":         ("Russia",          55.755, 37.617),
    "tehran":         ("Iran",            35.689, 51.389),
    "jerusalem":      ("Israel",          31.768, 35.214),
    "tel aviv":       ("Israel",          32.085, 34.781),
    "kiev":           ("Ukraine",         50.450, 30.524),
    "kyiv":           ("Ukraine",         50.450, 30.524),
    "lagos":          ("Nigeria",          6.524,  3.379),
    "abuja":          ("Nigeria",          9.058,  7.495),
    "dhaka":          ("Bangladesh",      23.811, 90.412),
    "islamabad":      ("Pakistan",        33.684, 73.048),
    "karachi":        ("Pakistan",        24.861, 67.010),
    "kabul":          ("Afghanistan",     34.555, 69.207),
    "colombo":        ("Sri Lanka",        6.927, 79.861),
    "kathmandu":      ("Nepal",           27.717, 85.324),
}

# Junk-title patterns for article-type fallback (Unicode-aware).
JUNK_TITLE_RE = [
    re.compile(r"\bhoroscope\b", re.IGNORECASE),
    re.compile(r"\brashifal\b", re.IGNORECASE),
    re.compile(r"\b(top|best)\s+\d+\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+(things|ways|reasons|tips|hacks)\b", re.IGNORECASE),
    re.compile(r"\brecipe\b", re.IGNORECASE),
    re.compile(r"\bvastu\b", re.IGNORECASE),
    re.compile(r"\bnumerology\b", re.IGNORECASE),
    re.compile(r"\baaj\s+ka\b", re.IGNORECASE),
    re.compile(r"\bweather\s+(forecast|update)\b", re.IGNORECASE),
]


# ─────────────────────────────────────────────────────────────────────
# QUALITY SCORE (Unicode-aware: Indic combining marks count as letters)
# ─────────────────────────────────────────────────────────────────────

def _is_letter_or_mark(c: str) -> bool:
    if c.isalpha():
        return True
    return unicodedata.category(c).startswith("M")


def body_quality(body: str | None) -> str:
    if not body:
        return "low"
    if len(body) < MIN_BODY_CHARS:
        return "low"
    chars = sum(1 for c in body if _is_letter_or_mark(c))
    ratio = chars / max(1, len(body))
    if ratio < 0.55:
        return "low"
    if ratio < 0.7 or len(body) < 400:
        return "medium"
    return "high"


# ─────────────────────────────────────────────────────────────────────
# STRUCTURAL EXTRACTION (BeautifulSoup, no LLM)
# ─────────────────────────────────────────────────────────────────────

def _normalize_url(u: str) -> str | None:
    try:
        p = urlparse(u.strip())
        if not p.scheme or not p.netloc:
            return None
        return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path or "/", "", "", ""))
    except Exception:
        return None


def _domain(u: str) -> str | None:
    try:
        return urlparse(u).netloc.lower() or None
    except Exception:
        return None


_YT_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)([A-Za-z0-9_\-]{11})"
)
_VIMEO_RE = re.compile(r"vimeo\.com/(?:video/)?(\d{6,})")
_TWEET_RE = re.compile(r"twitter\.com/[^/]+/status/(\d{10,})|x\.com/[^/]+/status/(\d{10,})")

#
# Byline blacklist — INTENTIONALLY NARROW.
# Only truly generic strings (single-word, wire-service initialisms, "admin",
# unattributed "correspondent") are rejected here. Source-level bylines like
# "The Hindu Bureau", "Telangana Today", "V6 Velugu", "Punch Editorial Board"
# are KEPT — they are how those outlets attribute their staff reporting and
# carry real information for downstream consumers.
#
_BYLINE_BAD_EQ = {
    # voice-over / audio noise
    "carbonatix", "audio by carbonatix", "voiced by carbonatix",
    # wire services (initialisms / generic)
    "reuters", "ap", "associated press", "ani", "pti", "ians",
    "afp", "agencies", "agence france-presse", "press trust of india",
    "indo-asian news service", "tass", "wire service", "wire",
    # truly generic role labels (no outlet attached)
    "staff", "staff reporter", "staff writer", "team", "bureau",
    "correspondent", "newsroom", "desk", "online desk", "news desk",
    "web desk", "the staff", "by staff", "editor", "the editor",
    "our reporter", "our correspondent", "our staff", "our writer",
    "guest author", "guest writer", "guest contributor",
    "anonymous", "admin", "administrator",
    # generic editorial credits used when no real author is attached
    "authors & contributors", "authors and contributors",
    "editorial board", "the editorial board", "editorial",
}
_BYLINE_BAD_PREFIX = (
    "audio by ", "voiced by ", "powered by ", "narrated by ",
    "in association with ", "courtesy ", "via ",
)
# Truly junk substrings only. Keeps source-attributed bylines like
# "The Hindu Bureau" / "Telangana Today" / "Punch Editorial Board" alive.
_BYLINE_BAD_SUBSTR = (
    "@", "http", "www.", ".com", ".net", ".org",
    "newsroom",
    # vernacular "desk" / "web" tokens — still pure-noise on their own
    "ಡೆಸ್ಕ್", "డెస్క్", "डेस्क", "डेस्क्",
    "ವೆಬ್", "వెబ్", "वेब",
)
_BYLINE_ACRONYM_RE = re.compile(r"^[A-Z0-9.\-]{2,5}$")
_BYLINE_LOGIN_RE = re.compile(r"^[a-z0-9_.\-]+$")
_BYLINE_HAS_LETTER_RE = re.compile(
    r"[A-Za-zÀ-ɏऀ-෿฀-࿿぀-鿿]"
)
# Junk timestamp patterns like "23:45 IST" or "2026-05-11: ..." leaking
# from CSS selectors that overshot.
_BYLINE_TIMESTAMP_RE = re.compile(r"^\d+\s*[:\-]")
_BYLINE_BAD_CHARS_RE = re.compile(r"[<>]")


def _clean_byline(raw: str) -> str | None:
    """Trim leading 'By ' / authorship-noise and apply rejection filters."""
    if not raw:
        return None
    s = raw.strip()
    # Strip wrapping quotes commonly emitted by meta content / JSON-LD.
    s = s.strip('"\'')
    s = re.sub(r"^(?:by|reported by|written by|story by|from)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\|\s*.*$", "", s)
    s = re.sub(
        r"\s*,?\s*(?:publish(?:ed)?\s*date|published|posted|updated|date)\s*[:\-].*$",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\s+", " ", s).strip(" ,;-—")
    if len(s) < 3 or len(s) > 80:
        return None
    # Safety: reject HTML fragments, urls, and junk timestamps.
    if _BYLINE_BAD_CHARS_RE.search(s):
        return None
    if _BYLINE_TIMESTAMP_RE.match(s):
        return None
    low = s.lower()
    if "http" in low or "www." in low:
        return None
    if low in _BYLINE_BAD_EQ:
        return None
    if any(low.startswith(p) for p in _BYLINE_BAD_PREFIX):
        return None
    if any(sub in low for sub in _BYLINE_BAD_SUBSTR):
        return None
    if _BYLINE_LOGIN_RE.fullmatch(s):
        return None
    if _BYLINE_ACRONYM_RE.fullmatch(s):
        return None
    if not _BYLINE_HAS_LETTER_RE.search(s):
        return None
    return s[:200]


def _extract_byline(soup: BeautifulSoup) -> str | None:
    """Pull author name from meta tags → JSON-LD → CSS selectors.

    Order: cheap-first. ``<meta>`` lookups are O(1) per attr and are now the
    most common hit (newsrooms standardised on OpenGraph + Twitter cards
    long before they shipped JSON-LD). JSON-LD is the most semantically
    reliable but requires a JSON parse per ``<script>`` block. CSS
    selectors are the noisiest fallback.

    Handles JSON-LD ``author`` in all three shapes Schema.org permits:
      - ``"author": {"name": "X"}``       (object)
      - ``"author": [{"name": "X"}]``     (array of objects or strings)
      - ``"author": "X"``                 (plain string)
    """
    candidates: list[str] = []

    # 1. <meta> tags (cheap, very high hit rate post-2015)
    for attr_key, attr_val in (
        ("name", "author"),
        ("name", "DC.creator"),
        ("name", "dc.creator"),
        ("name", "sailthru.author"),
        ("name", "twitter:creator"),
        ("name", "parsely-author"),
        ("property", "article:author"),
        ("property", "og:article:author"),
        ("property", "author"),
    ):
        for m in soup.find_all("meta", attrs={attr_key: attr_val}):
            content = (m.get("content") or "").strip()
            if content and not content.startswith("http"):
                candidates.append(content)

    # 2. JSON-LD structured data (NewsArticle / Article / BlogPosting)
    for script in soup.find_all("script", type="application/ld+json")[:10]:
        try:
            data = json.loads((script.string or "").strip())
        except (json.JSONDecodeError, ValueError, AttributeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            block_list = graph if isinstance(graph, list) else [item]
            for blk in block_list:
                if not isinstance(blk, dict):
                    continue
                author = blk.get("author")
                if author is None:
                    continue
                # Normalise to a list so all three shapes funnel through
                # the same loop below.
                authors = author if isinstance(author, list) else [author]
                for a in authors:
                    if isinstance(a, dict):
                        name = a.get("name")
                        if isinstance(name, str) and name.strip():
                            candidates.append(name.strip())
                    elif isinstance(a, str):
                        val = a.strip()
                        # Plain string form. Skip url-only authors
                        # (Schema.org allows author=URL).
                        if val and not val.startswith("http"):
                            candidates.append(val)

    # 3. <link rel="author"> (rare but very reliable when present)
    for link_el in soup.find_all("link", rel="author"):
        href = (link_el.get("href") or "").strip()
        title = (link_el.get("title") or "").strip()
        if title:
            candidates.append(title)
        elif href and not href.startswith("http"):
            candidates.append(href)

    # 4. CSS selectors (rel/itemprop/class hints) — noisiest fallback
    for sel in (
        '[rel="author"]',
        '[itemprop="author"] [itemprop="name"]',
        '[itemprop="author"]',
        '.byline-name', '.byline__name', '.byline a', '.byline',
        '.author-name', '.author__name', '.author a', '.author',
        '[class*="byline"]', '[class*="Author"]', '[class*="author"]',
    ):
        for el in soup.select(sel)[:3]:
            text = el.get_text(" ", strip=True)
            if text:
                candidates.append(text[:200])

    for raw in candidates:
        cleaned = _clean_byline(raw)
        if cleaned:
            return cleaned
    return None


def parse_html(html: str, article_url: str) -> dict[str, Any]:
    """
    Returns a dict with structural extractions.
    Does not call any LLM. ~50ms typical.
    """
    soup = BeautifulSoup(html, "html.parser")
    home_domain = _domain(article_url) or ""

    # ─── language ─────────────────────────────────────────────────────
    lang = None
    if soup.html and soup.html.get("lang"):
        lang = soup.html["lang"].split("-")[0].lower()[:5]

    # ─── canonical url ────────────────────────────────────────────────
    canonical = None
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        canonical = link["href"]

    # ─── og / twitter image (hero) ───────────────────────────────────
    hero_url = None
    for prop in ("og:image", "twitter:image", "twitter:image:src"):
        m = soup.find("meta", attrs={"property": prop}) or soup.find(
            "meta", attrs={"name": prop}
        )
        if m and m.get("content"):
            hero_url = m["content"].strip()
            break

    # ─── outbound links ──────────────────────────────────────────────
    links: list[dict[str, Any]] = []
    seen_links: set[str] = set()
    for a in soup.find_all("a", href=True)[:120]:  # hard cap
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        norm = _normalize_url(href)
        if not norm or norm in seen_links:
            continue
        seen_links.add(norm)
        dom = _domain(norm)
        link_type = "internal" if dom and dom == home_domain else "external"
        links.append(
            {
                "url": href,
                "normalized": norm,
                "domain": dom,
                "anchor": (a.get_text(" ", strip=True) or "")[:240],
                "link_type": link_type,
                "position": len(links),
            }
        )

    # ─── inline images ───────────────────────────────────────────────
    images: list[dict[str, Any]] = []
    for img in soup.find_all("img")[:30]:
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if not src or src.startswith("data:"):
            continue
        # very small icons / 1x1 trackers — skip
        try:
            w = int(img.get("width") or 0)
            h = int(img.get("height") or 0)
        except (TypeError, ValueError):
            w, h = 0, 0
        if 0 < w < 60 and 0 < h < 60:
            continue
        images.append(
            {
                "url": src.strip(),
                "alt": (img.get("alt") or "").strip()[:240] or None,
                "width": w or None,
                "height": h or None,
                "position": len(images),
            }
        )

    # ─── embedded videos (YouTube / Vimeo / <video>) ─────────────────
    videos: list[dict[str, Any]] = []
    for iframe in soup.find_all("iframe", src=True):
        src = iframe["src"]
        m = _YT_RE.search(src)
        if m:
            videos.append({"provider": "youtube", "external_id": m.group(1), "url": src})
            continue
        m = _VIMEO_RE.search(src)
        if m:
            videos.append({"provider": "vimeo", "external_id": m.group(1), "url": src})
    for v in soup.find_all("video", src=True):
        videos.append({"provider": "native", "external_id": None, "url": v["src"]})

    # ─── embedded tweets ─────────────────────────────────────────────
    tweets: list[dict[str, Any]] = []
    for bq in soup.find_all("blockquote", class_=lambda c: c and "twitter-tweet" in c):
        tweet_id = None
        a = bq.find("a", href=True)
        if a:
            m = _TWEET_RE.search(a["href"])
            if m:
                tweet_id = m.group(1) or m.group(2)
        if tweet_id:
            tweets.append(
                {
                    "external_id": tweet_id,
                    "url": a["href"],
                    "caption": bq.get_text(" ", strip=True)[:600],
                }
            )

    byline = _extract_byline(soup)

    return {
        "lang": lang,
        "canonical": canonical,
        "hero_url": hero_url,
        "byline": byline,
        "links": links,
        "images": images,
        "videos": videos,
        "tweets": tweets,
    }


# ─────────────────────────────────────────────────────────────────────
# GROQ SEMANTIC ENRICHMENT
# ─────────────────────────────────────────────────────────────────────

GROQ_SYS = """Extract structured intel from this news article. Output JSON ONLY matching the schema.

REQUIRED fields (ALL must be present):
  article_type: one of [news, opinion, analysis, explainer, listicle, horoscope, recipe, live_blog, photo_essay, interview, press_release, sports_result, other]
  primary_subject: 1 short sentence describing what the article is FUNDAMENTALLY about
  summaries: {preview: str<=50ch, snippet: str<=200ch, executive: str<=1000ch}
  locations: [{text: str, country: str|null, region: str|null, city: str|null, is_primary: bool}] max 5, can be []
  events: [{date: YYYY-MM-DD|null, description: <=14 words, event_type: announcement|meeting|filing|statement|protest|release|election|accident|market_event|legal|sports_result|other, actors: [names], is_future: bool}] max 6, can be []
  quotes: [{speaker: str, text: str, context: press_conference|interview|tweet|statement|parliament|court|press_release|article|other, is_verbatim: bool}] max 5, can be []
  actor_stances: [{actor: str, stance: supportive|neutral|critical, intensity: 0-1}] max 5, can be []
  claims: [{subject: str, predicate: str, object: str, text: str, claimant: article|<name>, type: attributable|asserted|disputed, verifiable: bool}] max 5, can be []
  numbers: [{value: str, unit: str|null, context: str}] max 5, can be []
  register: {rhetorical_style: factual|analytical|polemical|sympathetic|mocking|promotional|sensational, primary_emotion: neutral|alarm|approval|mockery|urgency|lament|curiosity|admiration, is_breaking: bool}

RULES:
- country MUST be the full English name of a sovereign nation: "India", "United States", "Ghana", "United Kingdom". NEVER an ISO code ("IN", "US", "GH"). NEVER the literal string "null" — use JSON null.
- EVERY location object MUST include ALL 5 fields: text, country, region, city, is_primary. Use JSON null for fields that don't apply. Do NOT omit any field from the object.
- If location.text is a SOVEREIGN COUNTRY or a place INSIDE a sovereign country, you MUST populate country. If unsure of country, EXCLUDE the location entirely.
- Supranational locations (continents like "Asia"/"Europe"; oceans/seas/gulfs/straits like "Pacific Ocean"/"Strait of Hormuz"; geopolitical regions like "Middle East"/"EU"; or global scope like "world") MAY have country=null — just populate location.text and leave country/region/city as null.
- If city is populated, country MUST also be populated. NEVER set city without country.
- For India articles: if the article body names ANY specific city/town/district/mandal/constituency by name, you MUST populate the city field. Country must always be "India" for these.
  Anchors — Telangana: Hyderabad, Khammam, Karimnagar, Warangal, Nizamabad
  AP: Visakhapatnam, Vijayawada, Amaravati, Tirupati
  Karnataka: Bengaluru, Mysuru, Hubballi
  TN: Chennai, Madurai, Coimbatore
  Maharashtra: Mumbai, Pune, Nashik
  Kerala: Thiruvananthapuram, Kochi
  UP: Lucknow, Varanasi
  WB: Kolkata
  Gujarat: Ahmedabad
  Punjab: Chandigarh, Ludhiana
- events: past events (is_future=false) OR scheduled future events (is_future=true with date).
- quotes: ONLY verbatim text (in actual quotation marks in the article) gets is_verbatim=true. Paraphrases is_verbatim=false. context MUST use underscore form: "press_release" (NOT "press release"), "press_conference" (NOT "press conference"). Use exact enum spellings.
- actor_stances: per named entity, what is THIS article's posture toward them? intensity MUST match stance:
    * stance='neutral' → intensity MUST be 0.0 (no exceptions).
    * stance='supportive'/'critical' weak (mere mention, formal language, brief endorsement) → 0.3-0.5.
    * stance='supportive'/'critical' clear (active advocacy, explicit criticism, multiple lines of argument) → 0.6-0.8.
    * stance='supportive'/'critical' maximal (defining ideological commitment, hostile rhetoric, sustained campaign) → 0.9-1.0. RESERVED for rare cases — most strong stances are 0.7-0.8, not 1.0.
- claims: factual assertions by article OR named speakers. EVERY claim MUST be decomposed into subject + predicate + object. `text` carries the natural-language form.
    Example: "Modi announced a new policy" -> {subject: "Narendra Modi", predicate: "announced", object: "a new policy", text: "Modi announced a new policy", claimant: "article", type: "asserted", verifiable: false}
    subject = entity claim is ABOUT (NEVER "article" or pronoun; resolve pronouns).
    predicate = verb/relation phrase. object = target/value/recipient.
    claimant = WHO makes the claim ("article" if reporter; speaker name if attributed). Distinct from subject.
    OMIT the claim if you cannot identify all three SPO parts cleanly.
- numbers: every value with unit (lakh, crore, percent, count, date, currency). value as STRING to preserve "1.5 lakh" / "₹40 lakh" etc.
- event_type MUST be one of: announcement, meeting, filing, statement, protest, release, election, accident, market_event, legal, sports_result, other. NEVER invent new types.
- If article is empty/junk: article_type=other, all arrays empty, register defaults to neutral/factual.
- NEVER return the literal string "null". Use JSON null.
- Output ONLY the JSON object. No markdown fences, no prose."""


GROQ_SYS_NON_ENGLISH = GROQ_SYS + """

LANGUAGE NOTE: This article is in a non-English language.
FIRST internally translate the body to English.
THEN extract structured data FROM THE TRANSLATION.
Add ONE extra field to the JSON output:
  english_translation: str (a faithful English translation of the article body, max 1500 chars)
Keep names of people, places, organizations in their original transliterated form."""


# ─────────────────────────────────────────────────────────────────────
# v2 extraction constants
# ─────────────────────────────────────────────────────────────────────

# Per-script body-truncation caps. Indic and CJK scripts have higher token
# density than Latin, but our prompt asks them to translate, which means the
# output absorbs ~600 tokens for the translation field. Caps balance input
# context with output budget within the model's 8K context window.
MAX_BODY_FOR_GROQ_ENGLISH = 2400
MAX_BODY_FOR_GROQ_INDIC = 2200
MAX_BODY_FOR_GROQ_CJK = 1800

MAX_TOKENS_ENGLISH = 3000   # 2026-05-28 (v2): lowered 5000 → 3000. The 5000
                            # bump was for Cerebras zai-glm reasoning overhead,
                            # but D17 added reasoning_effort=none which cuts
                            # actual Cerebras output to ~800 tokens. Groq
                            # qwen3-32b output is ~1500-2500 tokens. Both fit
                            # in 3000 with margin. Side-effect of the old 5000:
                            # every Groq call reserved 5K of the 6K per-org
                            # TPM budget → ~1.2 calls/min/org → constant 429s.
                            # 3000 gives Groq ~2 calls/min/org headroom.
MAX_TOKENS_NON_ENGLISH = 3500  # extra room for english_translation field

INDIC_LANGS = ("te", "hi", "kn", "or", "ta", "ml", "bn", "pa", "mr", "gu", "ur")
CJK_LANGS = ("zh", "ja", "ko")
RTL_LANGS = ("ar", "fa")

# URL patterns that mean the article is structurally low-value — skip LLM
# extraction entirely (saves the Groq call). Stamped as junk + article_type=other.
JUNK_URL_PATTERNS = (
    "/photo-gallery/",
    "/photogallery/",
    "/slideshow/",
    "/pictures-of-day/",
    "/horoscope/",
    "/recipe/",
    "/cricket-live-score/",
    "/live-score/",
    "/tag/",
    "/category/",
    "/author/",
)


def is_junk_url(url: str | None) -> bool:
    if not url:
        return False
    u = url.lower()
    return any(p in u for p in JUNK_URL_PATTERNS)


def _get_extraction_context(article: dict) -> tuple[str, str, int]:
    """Returns (body_text, sys_prompt, max_output_tokens) based on article language."""
    lang = (article.get("language_iso") or "en").lower()
    body = article.get("full_text_scraped") or article.get("body") or ""
    if lang in INDIC_LANGS:
        return body[:MAX_BODY_FOR_GROQ_INDIC], GROQ_SYS_NON_ENGLISH, MAX_TOKENS_NON_ENGLISH
    if lang in CJK_LANGS or lang in RTL_LANGS:
        return body[:MAX_BODY_FOR_GROQ_CJK], GROQ_SYS_NON_ENGLISH, MAX_TOKENS_NON_ENGLISH
    return body[:MAX_BODY_FOR_GROQ_ENGLISH], GROQ_SYS, MAX_TOKENS_ENGLISH


def coerce_null_strings(obj: Any) -> Any:
    """Recursively replace literal string 'null' / 'None' with actual None.
    Some Groq responses include "null" as a string instead of JSON null.
    Catches that at parse time so persistence doesn't store the bad value.
    """
    if isinstance(obj, dict):
        return {k: coerce_null_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [coerce_null_strings(x) for x in obj]
    if isinstance(obj, str) and obj.strip().lower() in ("null", "none", ""):
        return None
    return obj


async def groq_semantic(
    title: str,
    body: str,
    sys_prompt: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any] | None:
    """Call Groq for v2 extraction. sys_prompt / max_tokens override let the
    runner switch between English and non-English (with embedded translation)
    paths without changing this function."""
    user_prompt = (
        f"TITLE: {title}\n\nBODY:\n{body}\n\n"
        "Return ONLY the JSON object."
    )
    # Two-attempt loop. 2026-05-28: added because Cerebras gpt-oss-120b
    # truncates verbose substrate JSON ~46% of the time (free-tier output cap
    # ≈1000 tokens, but our schema often needs 2-3K). Before this retry, ~25%
    # of all drained articles were silently lost. The UnifiedPool rotates to
    # a different slot on retry, so the second attempt typically lands on
    # Groq (qwen3-32b) or Ollama, both of which finish cleanly.
    parsed: Any = None
    raw_for_parse = ""
    for attempt in range(2):
        try:
            raw = await call_groq(
                system=sys_prompt or GROQ_SYS,
                user=user_prompt,
                pillar="articles",
                task_type=GROQ_TASK_TYPE,
                json_response=True,
                max_tokens_override=max_tokens,
            )
        except (GroqCallFailed, GroqQuotaExhausted) as exc:
            logger.warning("substrate: groq failed (attempt %d): %s", attempt + 1, exc)
            if attempt == 0:
                continue  # retry once on transport-level failure
            return None
        # Robust JSON parse — vLLM (without strict grammar) and some models
        # occasionally wrap JSON in markdown fences or prose preamble.
        # First try strict parse; if that fails, strip fences and isolate
        # the outermost { ... } block, then retry.
        raw_for_parse = (raw or "").strip()
        try:
            parsed = json.loads(raw_for_parse)
            break  # parsed cleanly — exit retry loop
        except (TypeError, ValueError):
            cleaned = raw_for_parse
            # strip markdown code fences
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```\s*$", "", cleaned)
            # isolate outermost {...}
            first = cleaned.find("{")
            last = cleaned.rfind("}")
            if first >= 0 and last > first:
                cleaned = cleaned[first:last + 1]
            try:
                parsed = json.loads(cleaned)
                break  # cleaned + parsed — exit retry loop
            except (TypeError, ValueError):
                if attempt == 0:
                    logger.info(
                        "groq_semantic: parse fail on attempt 1 (likely Cerebras "
                        "truncation), retrying. raw[-160:]=%r",
                        raw_for_parse[-160:],
                    )
                    continue  # rotate to next pool slot
                logger.warning(
                    "groq_semantic: json parse failed after 2 attempts. "
                    "raw[:240]=%r",
                    raw_for_parse[:240],
                )
                return None
    if not isinstance(parsed, dict):
        logger.warning(
            "groq_semantic: parsed but not a dict (got %s). raw[:120]=%r",
            type(parsed).__name__, raw_for_parse[:120],
        )
        return None
    # Coerce literal "null" strings to actual None across the whole tree.
    parsed = coerce_null_strings(parsed)
    # Light validation — keep the structural defaults consistent.
    at = parsed.get("article_type")
    if at not in ARTICLE_TYPES:
        parsed["article_type"] = "other"
    for k in ("locations", "events", "quotes", "actor_stances", "claims", "numbers"):
        if not isinstance(parsed.get(k), list):
            parsed[k] = []
    if not isinstance(parsed.get("summaries"), dict):
        parsed["summaries"] = {}
    if not isinstance(parsed.get("register"), dict):
        parsed["register"] = {}
    return parsed


def _lookup_geo(city: str | None, country: str | None) -> tuple[float | None, float | None]:
    if city:
        key = city.strip().lower()
        if key in GEO:
            return GEO[key][1], GEO[key][2]
    return None, None


def title_says_junk(title: str | None) -> bool:
    if not title:
        return False
    return any(p.search(title) for p in JUNK_TITLE_RE)


# ─────────────────────────────────────────────────────────────────────
# HTTP FETCH HELPER (browser-like headers)
# ─────────────────────────────────────────────────────────────────────

def _fetch_html_browser(url: str, timeout: float = 15.0) -> str | None:
    """Fetch HTML with a full browser-like header set. Returns None on
    any failure. Recovers PIB / Sunday Guardian / similar sources whose
    WAFs reject the default trafilatura User-Agent."""
    import gzip
    import urllib.error
    import urllib.request
    try:
        req = urllib.request.Request(url, headers=_BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            if r.headers.get("Content-Encoding", "").lower() == "gzip":
                data = gzip.decompress(data)
            charset = r.headers.get_content_charset() or "utf-8"
            return data.decode(charset, errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        return None
    except Exception:  # noqa: BLE001 — defensive, never propagate fetch failures
        return None


# ─────────────────────────────────────────────────────────────────────
# PER-ARTICLE PIPELINE
# ─────────────────────────────────────────────────────────────────────

async def process_one(db, article: dict[str, Any]) -> dict[str, Any]:
    aid = article["id"]
    url = article["url"]
    title = article.get("title") or ""

    # 0. URL pre-filter: skip slideshows / horoscopes / recipe pages / tag
    # listings — these don't carry substantive content. Saves a fetch + a
    # Groq call. Stamped as junk + article_type='other'.
    if is_junk_url(url):
        await db.execute(
            text(
                "UPDATE articles SET substrate_processed_at=now(), "
                "substrate_status='junk', article_type='other', "
                "extraction_version=3 WHERE id=:id"
            ),
            {"id": aid},
        )
        await db.commit()
        return {"status": "junk"}

    # 1. Fetch HTML — try browser-header urllib first (recovers PIB / SG
    # / similar UA-checking sites), fall back to trafilatura.fetch_url
    # for sites where its own retry/encoding logic handles edge cases
    # better. Both are wrapped in asyncio.to_thread to keep the event
    # loop free for parallel work.
    html = await asyncio.to_thread(_fetch_html_browser, url)
    if not html:
        html = await asyncio.to_thread(trafilatura.fetch_url, url)
    if html is None:
        await db.execute(
            text(
                "UPDATE articles SET substrate_processed_at=now(), "
                "substrate_status='fetch_failed' WHERE id=:id"
            ),
            {"id": aid},
        )
        await db.commit()
        return {"status": "fetch_failed"}

    # 2. trafilatura body
    body = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        include_links=False,
        deduplicate=True,
        favor_precision=True,
    ) or ""

    # 3. Structural parse
    structural = parse_html(html, url)

    # 4. Quality + word count
    quality = body_quality(body)
    word_count = len(body.split()) if body else 0
    reading_min = max(1, round(word_count / 220)) if word_count else 0

    if quality == "low" or word_count < 60 or title_says_junk(title):
        # short-circuit before we burn a Groq call — but still mark as v2
        # so the re-pass query doesn't pull it back in.
        await _update_article(
            db, aid,
            body=body or None,
            quality="low" if quality == "low" else "medium",
            word_count=word_count,
            reading_min=reading_min,
            article_type="other",
            canonical=structural["canonical"],
            language=structural["lang"],
            hero_url=structural["hero_url"],
            status="junk" if quality == "low" or title_says_junk(title) else "ok",
            extraction_version=3,
        )
        await _persist_structural(db, aid, structural)
        await db.commit()
        return {"status": "junk" if quality == "low" else "ok_no_groq"}

    # 5. Groq enrichment — script-aware context picks the right prompt
    # (English vs non-English-with-translation) and max_tokens budget.
    # Article dict for context selector — includes the body we just extracted
    # plus language detected from the HTML parse.
    extraction_article = {
        "language_iso": (structural.get("lang") or article.get("language_iso") or "en"),
        "full_text_scraped": body,
    }
    ctx_body, ctx_sys, ctx_max_tok = _get_extraction_context(extraction_article)
    semantic = await groq_semantic(title, ctx_body, ctx_sys, ctx_max_tok)

    # Pull all v2 fields with safe defaults.
    if semantic:
        article_type = semantic.get("article_type") or "other"
        primary_subject = semantic.get("primary_subject")
        summaries = semantic.get("summaries") or {}
        summary_preview = (summaries.get("preview") or "")[:500] or None
        summary_snippet = (summaries.get("snippet") or "")[:1000] or None
        summary_executive = (summaries.get("executive") or "")[:4000] or None
        locations = semantic.get("locations") or []
        events = semantic.get("events") or []
        quotes = semantic.get("quotes") or []
        stances = semantic.get("actor_stances") or []
        claims = semantic.get("claims") or []
        numbers = semantic.get("numbers") or []
        register = semantic.get("register") or {}
        register_style = (register.get("rhetorical_style") or None)
        register_emotion = (register.get("primary_emotion") or None)
        register_is_breaking = bool(register.get("is_breaking", False))
        english_translation = (semantic.get("english_translation") or "")[:8000] or None
    else:
        article_type = "other"
        primary_subject = None
        summary_preview = summary_snippet = summary_executive = None
        locations = events = quotes = stances = claims = numbers = []
        register_style = register_emotion = None
        register_is_breaking = False
        english_translation = None

    byline = structural.get("byline")

    # 6. Persist — extended _update_article writes all the v2 columns.
    await _update_article(
        db, aid,
        body=body,
        quality=quality,
        word_count=word_count,
        reading_min=reading_min,
        article_type=article_type,
        canonical=structural["canonical"],
        language=structural["lang"],
        hero_url=structural["hero_url"],
        status="ok",
        primary_subject=primary_subject,
        summary_preview=summary_preview,
        summary_snippet=summary_snippet,
        summary_executive=summary_executive,
        register_style=register_style,
        register_emotion=register_emotion,
        register_is_breaking=register_is_breaking,
        english_translation=english_translation,
        byline=byline,
        extraction_version=3,
    )
    await _persist_structural(db, aid, structural)
    await _persist_locations(db, aid, locations)
    await _persist_events(db, aid, events)
    await _persist_quotes(db, aid, quotes)
    await _persist_claims(db, aid, claims)
    await _persist_stances(db, aid, stances)
    await _persist_numbers(db, aid, numbers)
    await db.commit()
    return {
        "status": "ok",
        "links": len(structural["links"]),
        "images": len(structural["images"]),
        "videos": len(structural["videos"]),
        "tweets": len(structural["tweets"]),
        "locations": len(locations),
        "events": len(events),
        "quotes": len(quotes),
        "claims": len(claims),
        "stances": len(stances),
        "numbers": len(numbers),
    }


async def _update_article(
    db, aid: str, *,
    body: str | None,
    quality: str,
    word_count: int,
    reading_min: int,
    article_type: str,
    canonical: str | None,
    language: str | None,
    hero_url: str | None,
    status: str,
    # v2 extraction fields (added 2026-05-12)
    primary_subject: str | None = None,
    summary_preview: str | None = None,
    summary_snippet: str | None = None,
    summary_executive: str | None = None,
    register_style: str | None = None,
    register_emotion: str | None = None,
    register_is_breaking: bool = False,
    english_translation: str | None = None,
    byline: str | None = None,
    extraction_version: int = 3,
) -> None:
    await db.execute(
        text(
            """
            UPDATE articles
            SET full_text_scraped       = COALESCE(:body, full_text_scraped),
                lead_text_translated    = COALESCE(LEFT(:body, 2000), lead_text_translated),
                body_quality            = :quality,
                word_count              = :wc,
                reading_minutes         = :rm,
                article_type            = :atype,
                canonical_url           = COALESCE(:canonical, canonical_url),
                language_iso            = COALESCE(:lang, language_iso),
                thumbnail_url           = COALESCE(:hero, thumbnail_url),
                substrate_processed_at  = now(),
                substrate_status        = :status,
                quotes_extracted        = TRUE,
                claims_extracted        = TRUE,
                primary_subject         = COALESCE(:ps, primary_subject),
                summary_preview         = COALESCE(:sp, summary_preview),
                summary_snippet         = COALESCE(:ss, summary_snippet),
                summary_executive       = COALESCE(:se, summary_executive),
                register_style          = COALESCE(:rs, register_style),
                register_emotion        = COALESCE(:re, register_emotion),
                register_is_breaking    = :rb,
                full_text_translated    = COALESCE(:tr, full_text_translated),
                byline                  = COALESCE(:byline, byline),
                extraction_version      = :ev
            WHERE id = :id
            """
        ),
        {
            "id": aid,
            "body": body,
            "quality": quality,
            "wc": word_count,
            "rm": reading_min,
            "atype": article_type,
            "canonical": canonical,
            "lang": language,
            "hero": hero_url,
            "status": status,
            "ps": primary_subject,
            "sp": summary_preview,
            "ss": summary_snippet,
            "se": summary_executive,
            "rs": register_style,
            "re": register_emotion,
            "rb": bool(register_is_breaking),
            "tr": english_translation,
            "byline": (byline.strip() if isinstance(byline, str) and byline.strip() else None),
            "ev": int(extraction_version),
        },
    )


# ─────────────────────────────────────────────────────────────────────
# v2 persistence helpers — mirror _persist_locations / _persist_events
# ─────────────────────────────────────────────────────────────────────

async def _persist_quotes(db, aid: str, quotes: list[dict[str, Any]]) -> None:
    """Replace all article_quotes rows for this article.

    Uses the existing v1 schema:
      article_quotes(article_id, speaker_name, quote_text, is_direct,
                     speaker_entity_id, quote_text_en, speaker_name_en, ...)

    Mapping from our v2 extraction JSON:
      speaker        → speaker_name
      text           → quote_text
      is_verbatim    → is_direct (same semantic)
      context        → context (added 2026-05-12 in migration 073)
      speaker_entity_id stays NULL (filled later by entity resolution pass)
    """
    valid_contexts = {
        "press_conference", "interview", "tweet", "statement",
        "parliament", "court", "press_release", "article", "other",
    }
    await db.execute(
        text("DELETE FROM article_quotes WHERE article_id = :id"), {"id": aid}
    )
    if not quotes:
        return
    for q in quotes[:5]:
        if not isinstance(q, dict):
            continue
        quote_text_v = (q.get("text") or "").strip()
        speaker = (q.get("speaker") or "").strip()
        if not quote_text_v or not speaker:
            continue
        raw_ctx = (q.get("context") or "").strip().lower().replace(" ", "_")
        ctx = raw_ctx if raw_ctx in valid_contexts else None
        await db.execute(
            text(
                """
                INSERT INTO article_quotes
                  (article_id, speaker_name, quote_text, is_direct, context)
                VALUES (:aid, :sp, :tx, :vb, :ctx)
                """
            ),
            {
                "aid": aid,
                "sp": speaker[:200],
                "tx": quote_text_v[:4000],
                "vb": bool(q.get("is_verbatim", True)),
                "ctx": ctx,
            },
        )


async def _persist_claims(db, aid: str, claims: list[dict[str, Any]]) -> None:
    """Replace all article_claims rows for this article.

    Schema:
      article_claims(article_id, claim_text, subject_text, subject_entity_id,
                     predicate, object_text, confidence, embedding, ...)

    Mapping from v3 substrate JSON (2026-05-26 — SPO triple now extracted):
      subject       → subject_text (the entity the claim is ABOUT)
      predicate     → predicate    (verb / relation phrase)
      object        → object_text  (target / value / recipient)
      text          → claim_text   (natural-language sentence)
      verifiable    → confidence   (true → 0.85, false → 0.5)
      claimant      → (not stored as a column; lives inside claim_text context)
      subject_entity_id → NULL (filled later by entity resolution)

    Backward-compat: if subject/predicate/object are missing (old model output
    or junk), fall back to claimant→subject_text and leave predicate/object NULL.
    """
    await db.execute(
        text("DELETE FROM article_claims WHERE article_id = :id"), {"id": aid}
    )
    if not claims:
        return
    for c in claims[:5]:
        if not isinstance(c, dict):
            continue
        claim_text_v = (c.get("text") or "").strip()
        if not claim_text_v:
            continue
        subject_v = (c.get("subject") or "").strip() or None
        predicate_v = (c.get("predicate") or "").strip() or None
        object_v = (c.get("object") or "").strip() or None
        # Fallback: if the model did not emit SPO, put the claimant in subject_text
        # so existing entity-link code still finds something to resolve against.
        if not subject_v:
            subject_v = (c.get("claimant") or "article")
        # Map verifiable bool → confidence float
        verifiable = bool(c.get("verifiable", False))
        confidence = 0.85 if verifiable else 0.5
        await db.execute(
            text(
                """
                INSERT INTO article_claims
                  (article_id, claim_text, subject_text, predicate, object_text, confidence)
                VALUES (:aid, :tx, :sub, :pr, :ob, :cf)
                """
            ),
            {
                "aid": aid,
                "tx": claim_text_v[:4000],
                "sub": subject_v[:200] if subject_v else None,
                "pr": predicate_v[:200] if predicate_v else None,
                "ob": object_v[:600] if object_v else None,
                "cf": confidence,
            },
        )


async def _persist_stances(db, aid: str, stances: list[dict[str, Any]]) -> None:
    await db.execute(
        text("DELETE FROM article_stances WHERE article_id = :id"), {"id": aid}
    )
    if not stances:
        return
    for s in stances[:5]:
        if not isinstance(s, dict):
            continue
        actor = (s.get("actor") or "").strip()
        if not actor:
            continue
        try:
            intensity = float(s.get("intensity") or 0.5)
        except (TypeError, ValueError):
            intensity = 0.5
        intensity = max(0.0, min(1.0, intensity))
        await db.execute(
            text(
                """
                INSERT INTO article_stances
                  (article_id, actor, stance, intensity)
                VALUES (:aid, :ac, :st, :it)
                """
            ),
            {
                "aid": aid,
                "ac": actor[:200],
                "st": (s.get("stance") or "neutral")[:40],
                "it": intensity,
            },
        )


async def _persist_numbers(db, aid: str, numbers: list[dict[str, Any]]) -> None:
    await db.execute(
        text("DELETE FROM article_numbers WHERE article_id = :id"), {"id": aid}
    )
    if not numbers:
        return
    for i, n in enumerate(numbers[:5]):
        if not isinstance(n, dict):
            continue
        value = n.get("value")
        if value is None or value == "":
            continue
        # Coerce to string — schema stores as text to preserve "1.5 lakh" etc.
        await db.execute(
            text(
                """
                INSERT INTO article_numbers
                  (article_id, value, unit, context, position)
                VALUES (:aid, :v, :u, :c, :p)
                """
            ),
            {
                "aid": aid,
                "v": str(value)[:200],
                "u": (n.get("unit") or None),
                "c": (n.get("context") or "")[:400],
                "p": i,
            },
        )


async def _persist_structural(db, aid: str, s: dict[str, Any]) -> None:
    # links
    if s["links"]:
        await db.execute(
            text("DELETE FROM article_links WHERE article_id = :id"), {"id": aid}
        )
        for link in s["links"]:
            await db.execute(
                text(
                    """
                    INSERT INTO article_links
                      (article_id, outbound_url, outbound_url_normalized,
                       outbound_domain, anchor_text, link_type, position)
                    VALUES (:aid, :u, :n, :d, :a, :t, :p)
                    """
                ),
                {
                    "aid": aid, "u": link["url"], "n": link["normalized"],
                    "d": link["domain"], "a": link["anchor"],
                    "t": link["link_type"], "p": link["position"],
                },
            )

        # tweet content enrichment (free oEmbed; non-fatal if it fails)
        tweet_urls = [lk["url"] for lk in s["links"] if is_tweet_url(lk.get("url"))]
        if tweet_urls:
            try:
                counts = await enrich_article_tweets(db, aid, tweet_urls)
                logger.info(
                    "tweet enrichment for %s: %s", aid, counts
                )
            except Exception as e:
                logger.warning("tweet enrichment failed for %s: %s", aid, e)

    # media
    await db.execute(
        text("DELETE FROM article_media WHERE article_id = :id"), {"id": aid}
    )
    pos = 0
    if s["hero_url"]:
        await db.execute(
            text(
                "INSERT INTO article_media "
                "(article_id, media_type, url, position, is_hero) "
                "VALUES (:aid, 'image', :u, :p, true)"
            ),
            {"aid": aid, "u": s["hero_url"], "p": pos},
        )
        pos += 1
    for img in s["images"]:
        await db.execute(
            text(
                """
                INSERT INTO article_media
                  (article_id, media_type, url, alt_text, width, height, position)
                VALUES (:aid, 'image', :u, :a, :w, :h, :p)
                """
            ),
            {
                "aid": aid, "u": img["url"], "a": img["alt"],
                "w": img.get("width"), "h": img.get("height"), "p": pos,
            },
        )
        pos += 1
    for v in s["videos"]:
        await db.execute(
            text(
                """
                INSERT INTO article_media
                  (article_id, media_type, url, external_id, position)
                VALUES (:aid, 'video', :u, :ext, :p)
                """
            ),
            {"aid": aid, "u": v["url"], "ext": v.get("external_id"), "p": pos},
        )
        pos += 1
    for t in s["tweets"]:
        await db.execute(
            text(
                """
                INSERT INTO article_media
                  (article_id, media_type, url, external_id, caption, position)
                VALUES (:aid, 'tweet', :u, :ext, :c, :p)
                """
            ),
            {
                "aid": aid, "u": t["url"], "ext": t["external_id"],
                "c": t.get("caption"), "p": pos,
            },
        )
        pos += 1


async def _persist_locations(db, aid: str, locs: list[dict[str, Any]]) -> None:
    if not locs:
        return
    await db.execute(
        text("DELETE FROM article_locations WHERE article_id = :id"), {"id": aid}
    )
    for loc in locs[:5]:
        if not isinstance(loc, dict):
            continue
        text_v = (loc.get("text") or "").strip()
        if not text_v:
            continue
        country = (loc.get("country") or "").strip() or None
        region = (loc.get("region") or "").strip() or None
        city = (loc.get("city") or "").strip() or None
        lat, lng = _lookup_geo(city, country)
        await db.execute(
            text(
                """
                INSERT INTO article_locations
                  (article_id, location_text, country, region, city,
                   lat, lng, confidence, is_primary)
                VALUES (:aid, :t, :c, :r, :ct, :la, :ln, 0.85, :p)
                """
            ),
            {
                "aid": aid, "t": text_v, "c": country, "r": region, "ct": city,
                "la": lat, "ln": lng,
                "p": bool(loc.get("is_primary")),
            },
        )


async def _persist_events(db, aid: str, evs: list[dict[str, Any]]) -> None:
    if not evs:
        return
    await db.execute(
        text("DELETE FROM article_events WHERE article_id = :id"), {"id": aid}
    )
    for i, ev in enumerate(evs[:6]):
        if not isinstance(ev, dict):
            continue
        desc = (ev.get("description") or "").strip()
        if not desc:
            continue
        date_str = ev.get("date")
        date_val = None  # actual date object for asyncpg
        try:
            from datetime import date as _date
            if date_str:
                date_val = _date.fromisoformat(date_str)
        except (TypeError, ValueError):
            date_val = None
        actors = ev.get("actors") or []
        if not isinstance(actors, list):
            actors = []
        await db.execute(
            text(
                """
                INSERT INTO article_events
                  (article_id, event_date, event_description, event_type,
                   actors, confidence, position, is_future)
                VALUES (:aid, :d, :desc, :et, :ac, 0.8, :p, :fut)
                """
            ),
            {
                "aid": aid, "d": date_val, "desc": desc[:600],
                "et": (ev.get("event_type") or "other")[:40],
                "ac": [str(a)[:200] for a in actors][:8],
                "p": i,
                "fut": bool(ev.get("is_future", False)),
            },
        )


# ─────────────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────

async def run(args: argparse.Namespace) -> int:
    async with get_db() as db:
        if args.all:
            cnt_q = text(
                "SELECT COUNT(*) FROM articles WHERE substrate_processed_at IS NULL "
                "AND url IS NOT NULL"
            )
            params: dict[str, Any] = {}
        elif args.since:
            cnt_q = text(
                "SELECT COUNT(*) FROM articles WHERE substrate_processed_at IS NULL "
                "AND url IS NOT NULL AND collected_at > now() - make_interval(days => :d)"
            )
            params = {"d": args.since}
        else:
            cnt_q = text(
                "SELECT COUNT(*) FROM ("
                "  SELECT 1 FROM articles "
                "  WHERE substrate_processed_at IS NULL AND url IS NOT NULL "
                "  ORDER BY collected_at DESC LIMIT :lim"
                ") sub"
            )
            params = {"lim": args.limit}
        total = (await db.execute(cnt_q, params)).scalar() or 0

    if total == 0:
        logger.info("nothing to process. exit.")
        return 0

    logger.info("substrate-pass: processing %d articles", total)
    quartiles = {int(total * 0.25), int(total * 0.5), int(total * 0.75), total}

    # 2026-05-28 (D19): atomic-claim with FOR UPDATE SKIP LOCKED. The old
    # SELECT-only query let N concurrent drain instances pick the same rows
    # and race to write substrate output, wasting 15-30% of LLM calls and
    # producing duplicate work. The UPDATE...RETURNING pattern now marks each
    # batch substrate_status='processing' so other workers' inner SELECT skips
    # them. Orphaned 'processing' rows from a hard-killed script are re-picked
    # by the next D1 reset cycle.
    fetched_q = text(
        """
        UPDATE articles
           SET substrate_status = 'processing'
         WHERE id IN (
           SELECT id FROM articles
            WHERE substrate_processed_at IS NULL AND url IS NOT NULL
              AND (substrate_status IS NULL OR substrate_status = 'pending')
            ORDER BY collected_at DESC
            LIMIT :batch
            FOR UPDATE SKIP LOCKED
         )
        RETURNING id::text AS id, title, url
        """
    )

    started = time.time()
    counters = {"ok": 0, "junk": 0, "fetch_failed": 0, "errors": 0, "ok_no_groq": 0}
    processed = 0
    sem = asyncio.Semaphore(8)

    async def _one_with_db(row: dict[str, Any]) -> str:
        async with sem:
            try:
                async with get_db() as db:
                    res = await process_one(db, row)
                return res.get("status", "errors")
            except Exception as exc:
                logger.exception("error on article %s: %s", row["id"], exc)
                try:
                    async with get_db() as db:
                        await db.execute(
                            text(
                                "UPDATE articles SET substrate_processed_at=now(), "
                                "substrate_status='extract_failed' WHERE id=:id"
                            ),
                            {"id": row["id"]},
                        )
                        await db.commit()
                except Exception:
                    pass
                return "errors"

    while processed < total:
        async with get_db() as db:
            rows = (await db.execute(fetched_q, {"batch": 64})).mappings().all()
            # Commit the atomic UPDATE so the 'processing' marker persists and
            # other concurrent workers actually see and skip these rows.
            await db.commit()
        if not rows:
            break
        results = await asyncio.gather(
            *(_one_with_db(dict(r)) for r in rows), return_exceptions=False
        )
        for status in results:
            counters[status] = counters.get(status, 0) + 1
        processed += len(rows)
        # progress report at quartile crossings
        for q in sorted(quartiles):
            if processed >= q and q not in (counters.get("_reported", set()) or set()):
                if "_reported" not in counters:
                    counters["_reported"] = set()
                if q in counters["_reported"]:
                    continue
                counters["_reported"].add(q)
                elapsed = time.time() - started
                pct = processed / total * 100
                rate = processed / max(elapsed, 1)
                eta_min = (total - processed) / max(rate, 0.1) / 60
                # strip the bookkeeping key from log
                log_counters = {k: v for k, v in counters.items() if k != "_reported"}
                logger.info(
                    "PROGRESS %.0f%% (%d/%d) · %.1f art/sec · ETA %.0f min · %s",
                    pct, processed, total, rate, eta_min, log_counters,
                )
                break
        await asyncio.sleep(0.05)

    elapsed = time.time() - started
    logger.info(
        "DONE in %.0f sec (%.1f min) · processed=%d · counters=%s",
        elapsed, elapsed / 60, processed, counters,
    )
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="run on entire corpus")
    g.add_argument("--since", type=int, help="last N days only")
    g.add_argument("--limit", type=int, help="smoke-test on N most-recent articles")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
