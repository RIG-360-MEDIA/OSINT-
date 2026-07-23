"""draftsmith.stages.images — Stage 7: thumbnail candidates. No LLM.

    gather_images(job_id, plan, selected_items) -> list[models.ImageCandidate]

Assembles up to config.IMAGE_SLOTS candidates, mixed per config.IMAGE_MIX,
in a fixed provider order (corpus -> wikimedia -> web) so the natural slot
numbering matches the spec (corpus first / wikimedia next / web last):

  - corpus:    thumbnail_url of the top-relevance selected corpus_article
               evidence items (already frozen in EvidenceItem.extra from the
               gather stage's public.articles snapshot); falls back to an
               og:image scrape of the article URL when the row had none.
               attribution=outlet, needs_license_review=False.
  - wikimedia: Wikimedia Commons `generator=search` (gsrnamespace=6) on the
               plan's top entity; CC/PD-licensed images only, filtered via
               imageinfo extmetadata. attribution=Artist.
  - web:       SearXNG images engine (config.SEARXNG_URL) on a plan web
               query. needs_license_review is always True.

A provider that is unreachable, empty, or errors yields fewer candidates
for that slot range — this stage NEVER raises on a provider failure; the
job must still be able to reach 'images' -> 'ready'. Only a bad `job_id`/
`plan` argument (a programming error, not a provider outage) raises.

Persists the assembled candidates via db.save_images and returns exactly
what got persisted (real DB ids, per the frozen ImageCandidate contract).
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from html import unescape
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlparse

import httpx

from backend.draftsmith import config, db
from backend.draftsmith.models import EvidenceItem, ImageCandidate, ImageOrigin, QueryPlan

logger = logging.getLogger(__name__)

# Cerebras/WAF-style UA dodge, same reasoning as llm.py's _BROWSER_UA — several
# news CMSes and commons.wikimedia.org's edge both 403 default httpx/urllib UAs.
_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_FETCH_TIMEOUT = httpx.Timeout(12.0, connect=8.0)
_OG_IMAGE_FETCH_MAX_BYTES = 200_000   # only the <head> is needed; bound the read
_WIKI_OVERFETCH = 4                   # ask Commons for extra results before license filtering
_WIKI_MIN_RESULTS = 10
_COMMONS_API = "https://commons.wikimedia.org/w/api.php"

_ENTITY_TYPE_PRIORITY = ("person", "org", "place", "event", "other")
_OPEN_LICENSE_MARKERS = (
    "cc0", "cc-by", "cc by", "publicdomain", "public domain", "pd-", "pdm",
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I,
)
_OG_IMAGE_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I,
)


@dataclass(frozen=True)
class _RawImage:
    """Provider-shaped result, pre-slot-assignment and pre-persistence."""

    origin: ImageOrigin
    url: str
    thumb_url: Optional[str]
    license: Optional[str]
    license_url: Optional[str]
    attribution: Optional[str]
    needs_license_review: bool


# --- small helpers ------------------------------------------------------------

def _domain(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    host = urlparse(url).netloc
    return host or None


def _strip_html(value: str) -> str:
    return unescape(_HTML_TAG_RE.sub(" ", value)).strip()


def _emeta_value(extmetadata: Mapping[str, Any], key: str) -> str:
    entry = extmetadata.get(key)
    if isinstance(entry, Mapping):
        return str(entry.get("value") or "").strip()
    return ""


def _is_open_license(extmetadata: Mapping[str, Any]) -> bool:
    """CC/PD only. Any nonzero `Restrictions` (trademarked, insignia, ...)
    disqualifies regardless of the nominal license tag."""
    restrictions = _emeta_value(extmetadata, "Restrictions").strip().lower()
    if restrictions not in ("", "none"):
        return False
    haystack = (
        _emeta_value(extmetadata, "LicenseShortName").lower()
        + " " + _emeta_value(extmetadata, "UsageTerms").lower()
    ).replace("_", " ")
    return bool(haystack.strip()) and any(m in haystack for m in _OPEN_LICENSE_MARKERS)


def _top_entity_query(plan: QueryPlan) -> Optional[str]:
    """Pick the single most photographable entity: person > org > place >
    event > other, in plan order; falls back to the topic summary."""
    for etype in _ENTITY_TYPE_PRIORITY:
        for entity in plan.entities:
            if entity.type == etype and entity.name:
                return entity.name
    if plan.entities and plan.entities[0].name:
        return plan.entities[0].name
    return plan.topic_summary or None


def _web_query(plan: QueryPlan) -> Optional[str]:
    if plan.queries and plan.queries.web:
        return plan.queries.web[0]
    return plan.topic_summary or None


def _log_provider_failure(label: str, exc: BaseException) -> list[_RawImage]:
    logger.warning(
        "gather_images: %s provider raised %s: %s", label, type(exc).__name__, exc,
    )
    return []


# --- corpus (slots first) -----------------------------------------------------

async def _fetch_og_image(url: str, client: httpx.AsyncClient) -> str:
    """Best-effort og:image scrape. Returns "" on any failure — this is a
    fallback path for corpus articles missing `thumbnail_url`, never a hard
    dependency."""
    try:
        async with client.stream(
            "GET", url, headers={"User-Agent": _BROWSER_UA}, timeout=_FETCH_TIMEOUT,
        ) as resp:
            if resp.status_code != 200:
                return ""
            chunks: list[bytes] = []
            read = 0
            async for chunk in resp.aiter_bytes():
                chunks.append(chunk)
                read += len(chunk)
                if read >= _OG_IMAGE_FETCH_MAX_BYTES:
                    break
            html = b"".join(chunks).decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001 — best-effort scrape, never propagate
        logger.info("gather_images: og:image fetch failed for %s: %s", url, exc)
        return ""
    match = _OG_IMAGE_RE.search(html) or _OG_IMAGE_RE_ALT.search(html)
    return unescape(match.group(1)).strip() if match else ""


async def _corpus_candidates(
    selected_items: Sequence[EvidenceItem], want: int, client: httpx.AsyncClient,
) -> list[_RawImage]:
    if want <= 0:
        return []
    ranked = sorted(
        (i for i in selected_items if i.source_type == "corpus_article"),
        key=lambda i: i.relevance, reverse=True,
    )
    out: list[_RawImage] = []
    for item in ranked:
        if len(out) >= want:
            break
        thumb = str(item.extra.get("thumbnail_url") or "").strip()
        if not thumb and item.url:
            thumb = await _fetch_og_image(item.url, client)
        if not thumb:
            continue
        out.append(_RawImage(
            origin="corpus", url=thumb, thumb_url=None, license=None, license_url=None,
            attribution=item.outlet or _domain(item.url), needs_license_review=False,
        ))
    return out


# --- wikimedia commons ---------------------------------------------------------

async def _wikimedia_candidates(
    query: Optional[str], want: int, client: httpx.AsyncClient,
) -> list[_RawImage]:
    if want <= 0 or not query:
        return []
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": str(max(want * _WIKI_OVERFETCH, _WIKI_MIN_RESULTS)),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime",
        "iiurlwidth": "800",
        "format": "json",
    }
    try:
        resp = await client.get(
            _COMMONS_API, params=params, timeout=_FETCH_TIMEOUT,
            headers={"User-Agent": config.WIKI_USER_AGENT},
        )
        if resp.status_code != 200:
            logger.warning(
                "gather_images: wikimedia HTTP %d for query=%r", resp.status_code, query,
            )
            return []
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — provider outage must not fail the stage
        return _log_provider_failure("wikimedia", exc)

    pages = list((data.get("query") or {}).get("pages", {}).values())
    # `generator=search` ranks by relevance via each page's `index`, not dict order.
    pages.sort(key=lambda p: p.get("index", 10_000))

    out: list[_RawImage] = []
    for page in pages:
        if len(out) >= want:
            break
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        if not str(info.get("mime") or "").startswith("image/"):
            continue
        meta = info.get("extmetadata") or {}
        if not _is_open_license(meta):
            continue
        url = info.get("url") or ""
        if not url:
            continue
        artist = _strip_html(_emeta_value(meta, "Artist")) or "Wikimedia Commons"
        out.append(_RawImage(
            origin="wikimedia", url=url, thumb_url=info.get("thumburl"),
            license=_emeta_value(meta, "LicenseShortName") or None,
            license_url=_emeta_value(meta, "LicenseUrl") or None,
            attribution=artist, needs_license_review=False,
        ))
    return out


# --- web (searxng) --------------------------------------------------------------

async def _web_candidates(
    query: Optional[str], want: int, client: httpx.AsyncClient,
) -> list[_RawImage]:
    if want <= 0 or not query:
        return []
    try:
        resp = await client.get(
            config.SEARXNG_URL.rstrip("/") + "/search",
            params={"q": query, "format": "json", "categories": "images"},
            timeout=_FETCH_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning(
                "gather_images: searxng HTTP %d for query=%r", resp.status_code, query,
            )
            return []
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — provider outage must not fail the stage
        return _log_provider_failure("web", exc)

    out: list[_RawImage] = []
    for item in data.get("results") or []:
        if len(out) >= want:
            break
        img_url = item.get("img_src") or ""
        if not img_url:
            continue
        source_page = item.get("url") or ""
        out.append(_RawImage(
            origin="web", url=img_url,
            thumb_url=item.get("thumbnail_src") or item.get("thumbnail") or None,
            license=None, license_url=None,
            attribution=item.get("source") or _domain(source_page) or item.get("title"),
            needs_license_review=True,
        ))
    return out


# --- assembly + persistence ----------------------------------------------------

def _to_candidates(raw: Sequence[_RawImage], start_slot: int) -> list[ImageCandidate]:
    """Assign contiguous slot numbers starting at start_slot. `id` is left
    empty — db.save_images's INSERT lets Postgres generate the real id and
    the caller returns THAT row, not this pre-persist shape."""
    return [
        ImageCandidate(
            id="", slot=start_slot + i, origin=r.origin, url=r.url,
            thumb_url=r.thumb_url, license=r.license, license_url=r.license_url,
            attribution=r.attribution, needs_license_review=r.needs_license_review,
            selected=False,
        )
        for i, r in enumerate(raw)
    ]


async def gather_images(
    job_id: str, plan: QueryPlan, selected_items: Sequence[EvidenceItem],
) -> list[ImageCandidate]:
    """Stage 7 — thumbnail candidates. See module docstring for the mix.

    Raises ValueError only for a missing job_id/plan (caller error); every
    provider-level failure is caught, logged, and simply yields fewer
    candidates for that provider's slot range.
    """
    if not job_id:
        raise ValueError("gather_images: job_id is required")
    if plan is None:
        raise ValueError("gather_images: plan is required")

    corpus_want = max(0, config.IMAGE_MIX.get("corpus", 0))
    wiki_want = max(0, config.IMAGE_MIX.get("wikimedia", 0))
    web_want = max(0, config.IMAGE_MIX.get("web", 0))

    entity_query = _top_entity_query(plan)
    web_query = _web_query(plan)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        corpus_raw, wiki_raw, web_raw = await asyncio.gather(
            _corpus_candidates(selected_items, corpus_want, client),
            _wikimedia_candidates(entity_query, wiki_want, client),
            _web_candidates(web_query, web_want, client),
            return_exceptions=True,
        )

    if isinstance(corpus_raw, BaseException):
        corpus_raw = _log_provider_failure("corpus", corpus_raw)
    if isinstance(wiki_raw, BaseException):
        wiki_raw = _log_provider_failure("wikimedia", wiki_raw)
    if isinstance(web_raw, BaseException):
        web_raw = _log_provider_failure("web", web_raw)

    ordered_raw = [*corpus_raw, *wiki_raw, *web_raw][: config.IMAGE_SLOTS]
    images = _to_candidates(ordered_raw, start_slot=1)
    if not images:
        return []
    return await db.save_images(job_id, images)
