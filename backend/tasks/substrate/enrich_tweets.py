"""Tweet content enrichment via Twitter's free oEmbed endpoint.

publish.twitter.com/oembed is a public unauthenticated endpoint Twitter
provides for third-party tweet embedding. We use it to recover tweet
content (text, author, language, hashtags, mentions) for the tweet URLs
that articles cite. No API key, no rate limits in any practical sense,
zero cost. Works for any public tweet not from a private/deleted account.

This module is called inline during run_corpus_pass.process_one() so new
v2 articles automatically get tweet content, and there is a backfill
function for already-extracted v2 articles.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any, Iterable

from sqlalchemy import text

log = logging.getLogger(__name__)

OEMBED_URL = "https://publish.twitter.com/oembed"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

TWEET_ID_RE = re.compile(r"/status(?:es)?/(\d+)")
LANG_BLOCKQUOTE_RE = re.compile(r'<blockquote[^>]+lang="([^"]+)"')
LANG_P_RE = re.compile(r'<p[^>]+lang="([^"]+)"')
P_BODY_RE = re.compile(r'<p[^>]*>(.*?)</p>', re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")
PIC_RE = re.compile(r'pic\.twitter\.com/\w+')
TCO_RE = re.compile(r'https?://t\.co/\w+')
HASHTAG_RE = re.compile(r'#(\w+)')
MENTION_RE = re.compile(r'@(\w+)')
DATE_TAIL_RE = re.compile(
    r'>([A-Z][a-z]+ \d{1,2},? \d{4})</a>'
)


def extract_tweet_id(tweet_url: str) -> str | None:
    """Pull the numeric tweet id out of a status URL."""
    m = TWEET_ID_RE.search(tweet_url)
    return m.group(1) if m else None


def is_tweet_url(url: str | None) -> bool:
    if not url:
        return False
    u = url.lower()
    return (
        ("twitter.com/" in u or "x.com/" in u)
        and "/status/" in u
        and TWEET_ID_RE.search(u) is not None
    )


def _decode_entities(s: str) -> str:
    """Decode the handful of HTML entities Twitter emits in tweet bodies."""
    return (
        s.replace("&quot;", '"')
         .replace("&#39;", "'")
         .replace("&amp;", "&")
         .replace("&lt;", "<")
         .replace("&gt;", ">")
         .replace("&mdash;", "—")
         .replace("&nbsp;", " ")
    )


def _parse_oembed_html(html: str, author_handle: str | None) -> dict[str, Any]:
    """Parse the rich data out of Twitter's oEmbed `html` field."""
    parsed: dict[str, Any] = {
        "tweet_text": None,
        "language": None,
        "posted_at": None,
        "has_image": False,
        "image_urls": [],
        "hashtags": [],
        "mentions": [],
        "links_in_tweet": [],
    }

    lang_m = LANG_BLOCKQUOTE_RE.search(html) or LANG_P_RE.search(html)
    if lang_m:
        parsed["language"] = lang_m.group(1).lower()

    body_m = P_BODY_RE.search(html)
    body_text = ""
    if body_m:
        raw_body = body_m.group(1)
        body_text = HTML_TAG_RE.sub("", raw_body)
        body_text = _decode_entities(body_text).strip()
        body_text = re.sub(r"\s+", " ", body_text)
        parsed["tweet_text"] = body_text[:4000] or None

    pics = PIC_RE.findall(html)
    if pics:
        parsed["has_image"] = True
        parsed["image_urls"] = sorted(set(pics))[:10]

    tcos = TCO_RE.findall(html)
    parsed["links_in_tweet"] = sorted(set(tcos))[:20]

    if body_text:
        parsed["hashtags"] = sorted({h.lower() for h in HASHTAG_RE.findall(body_text)})[:25]
        raw_mentions = {m.lower() for m in MENTION_RE.findall(body_text)}
        if author_handle:
            raw_mentions.discard(author_handle.lstrip("@").lower())
        parsed["mentions"] = sorted(raw_mentions)[:25]

    date_m = DATE_TAIL_RE.search(html)
    if date_m:
        try:
            parsed["posted_at"] = datetime.strptime(date_m.group(1), "%B %d, %Y").date()
        except ValueError:
            try:
                parsed["posted_at"] = datetime.strptime(date_m.group(1), "%B %d %Y").date()
            except ValueError:
                parsed["posted_at"] = None

    return parsed


def _fetch_oembed_sync(tweet_url: str, timeout: float = 8.0) -> dict[str, Any]:
    """Blocking oEmbed call; safe to wrap in asyncio.to_thread()."""
    api = OEMBED_URL + "?" + urllib.parse.urlencode({
        "url": tweet_url,
        "omit_script": "1",
        "hide_thread": "1",
        "dnt": "true",
    })
    req = urllib.request.Request(api, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return {"ok": True, "data": json.loads(r.read().decode())}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")[:200]
        if e.code == 404:
            return {"ok": False, "status": "not_found", "error": body}
        if e.code == 401 or e.code == 403:
            return {"ok": False, "status": "private", "error": body}
        if e.code == 429:
            return {"ok": False, "status": "rate_limited", "error": body}
        return {"ok": False, "status": "error", "error": f"HTTP {e.code}: {body}"}
    except urllib.error.URLError as e:
        return {"ok": False, "status": "error", "error": f"URLError: {e.reason}"}
    except (TimeoutError, OSError) as e:
        return {"ok": False, "status": "error", "error": f"net: {e}"}
    except json.JSONDecodeError as e:
        return {"ok": False, "status": "error", "error": f"bad json: {e}"}


async def _fetch_oembed(tweet_url: str) -> dict[str, Any]:
    return await asyncio.to_thread(_fetch_oembed_sync, tweet_url)


def _normalize_handle(author_url: str | None) -> str | None:
    """Pull @handle out of author_url like https://twitter.com/Foo."""
    if not author_url:
        return None
    m = re.search(r"(?:twitter|x)\.com/(\w+)", author_url)
    return m.group(1) if m else None


async def enrich_tweet(
    db, article_id: str, tweet_url: str, *, delay: float = 0.0
) -> dict[str, Any]:
    """Fetch one tweet's content via oEmbed and upsert into article_tweets.

    Returns a result dict with at minimum {tweet_id, fetch_status}.
    Idempotent: ON CONFLICT (article_id, tweet_id) updates the existing row.
    """
    cleaned_url = tweet_url.split("?")[0].rstrip("/")
    tweet_id = extract_tweet_id(cleaned_url)
    if not tweet_id:
        return {"tweet_id": None, "fetch_status": "skipped", "reason": "no_tweet_id"}

    if delay > 0:
        await asyncio.sleep(delay)

    res = await _fetch_oembed(cleaned_url)
    if not res.get("ok"):
        await db.execute(
            text(
                """
                INSERT INTO article_tweets
                  (article_id, tweet_id, tweet_url, fetch_status, fetch_error)
                VALUES (:aid, :tid, :url, :st, :err)
                ON CONFLICT (article_id, tweet_id) DO UPDATE
                  SET fetch_status = EXCLUDED.fetch_status,
                      fetch_error  = EXCLUDED.fetch_error,
                      fetched_at   = now()
                """
            ),
            {
                "aid": article_id, "tid": tweet_id, "url": cleaned_url,
                "st": res.get("status", "error"),
                "err": (res.get("error") or "")[:500],
            },
        )
        return {"tweet_id": tweet_id, "fetch_status": res.get("status", "error")}

    data = res["data"]
    html = data.get("html", "") or ""
    author_name = data.get("author_name") or None
    author_url = data.get("author_url") or None
    author_handle = _normalize_handle(author_url)

    parsed = _parse_oembed_html(html, author_handle)

    await db.execute(
        text(
            """
            INSERT INTO article_tweets (
              article_id, tweet_id, tweet_url,
              author_handle, author_name, author_profile_url,
              tweet_text, tweet_html, language, posted_at,
              has_image, image_urls, hashtags, mentions, links_in_tweet,
              fetched_at, fetch_status
            )
            VALUES (
              :aid, :tid, :url,
              :handle, :name, :purl,
              :ttext, :thtml, :lang, :posted,
              :hasimg, :imgs, :tags, :ments, :links,
              now(), 'ok'
            )
            ON CONFLICT (article_id, tweet_id) DO UPDATE SET
              author_handle = EXCLUDED.author_handle,
              author_name = EXCLUDED.author_name,
              author_profile_url = EXCLUDED.author_profile_url,
              tweet_text = EXCLUDED.tweet_text,
              tweet_html = EXCLUDED.tweet_html,
              language = EXCLUDED.language,
              posted_at = EXCLUDED.posted_at,
              has_image = EXCLUDED.has_image,
              image_urls = EXCLUDED.image_urls,
              hashtags = EXCLUDED.hashtags,
              mentions = EXCLUDED.mentions,
              links_in_tweet = EXCLUDED.links_in_tweet,
              fetched_at = now(),
              fetch_status = 'ok',
              fetch_error = NULL
            """
        ),
        {
            "aid": article_id, "tid": tweet_id, "url": cleaned_url,
            "handle": author_handle, "name": author_name, "purl": author_url,
            "ttext": parsed["tweet_text"], "thtml": html[:8000],
            "lang": parsed["language"], "posted": parsed["posted_at"],
            "hasimg": parsed["has_image"],
            "imgs": parsed["image_urls"],
            "tags": parsed["hashtags"],
            "ments": parsed["mentions"],
            "links": parsed["links_in_tweet"],
        },
    )
    return {
        "tweet_id": tweet_id,
        "fetch_status": "ok",
        "author_handle": author_handle,
        "language": parsed["language"],
    }


async def enrich_article_tweets(
    db, article_id: str, tweet_urls: Iterable[str], *, per_call_delay: float = 0.4
) -> dict[str, int]:
    """Enrich every tweet URL for one article. Polite pacing keeps us
    invisible to whatever rate-limiting publish.twitter.com applies."""
    seen: set[str] = set()
    counts = {"ok": 0, "not_found": 0, "private": 0, "rate_limited": 0, "error": 0, "skipped": 0}
    for url in tweet_urls:
        cleaned = (url or "").split("?")[0].rstrip("/")
        if not is_tweet_url(cleaned):
            continue
        tid = extract_tweet_id(cleaned)
        if not tid or tid in seen:
            continue
        seen.add(tid)
        try:
            res = await enrich_tweet(db, article_id, cleaned, delay=per_call_delay)
            counts[res.get("fetch_status", "error")] = counts.get(res.get("fetch_status", "error"), 0) + 1
        except Exception as e:
            log.warning("enrich_tweet failed for %s: %s", cleaned, e)
            counts["error"] += 1
    return counts
