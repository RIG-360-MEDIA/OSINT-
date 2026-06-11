"""Bilingual rule — every non-English text shown in the UI carries an English
translation. The corpus's stored 'translations' are unreliable (lead_text_translated
is still Telugu for ~84% of te articles), so we translate the actual text via the
free Google endpoint (through httpx — no extra dep, no Groq quota) and cache each
string in analytics.text_en so it is translated only once. Strict script-detection
means we NEVER label a non-English string as English. Failures degrade silently
(no _en field) rather than fabricate.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

import httpx
from sqlalchemy import text as _sql

_NONLATIN = re.compile(r"[^\x00-\x7f]")
_GT = "https://translate.googleapis.com/translate_a/single"


def is_english(s: str | None, thresh: float = 0.12) -> bool:
    """True if the string is predominantly ASCII/Latin (so it needs no translation)."""
    if not s:
        return True
    return len(_NONLATIN.findall(s)) / max(len(s), 1) < thresh


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


async def _translate_one(client: httpx.AsyncClient, q: str) -> str | None:
    try:
        r = await client.get(_GT, params={"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": q[:4800]}, timeout=8.0)
        if r.status_code != 200:
            return None
        data = r.json()
        out = "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
        return out or None
    except Exception:  # noqa: BLE001 — translation is best-effort; never break the page
        return None


async def ensure_en(db, texts: set[str]) -> dict[str, str]:
    """Map each non-English text -> English, using the cache; translate cache misses."""
    texts = {t for t in texts if t and not is_english(t)}
    if not texts:
        return {}
    hashes = {t: _md5(t) for t in texts}
    rows = (await db.execute(_sql(
        "SELECT src_hash, text_en FROM analytics.text_en WHERE src_hash = ANY(:h)"
    ), {"h": list(hashes.values())})).fetchall()
    cached = {r.src_hash: r.text_en for r in rows}
    res: dict[str, str] = {t: cached[h] for t, h in hashes.items() if h in cached}
    miss = [t for t in texts if t not in res]
    if miss:
        wrote = False
        async with httpx.AsyncClient() as client:
            for t in miss:
                en = await _translate_one(client, t)
                if en:
                    res[t] = en
                    await db.execute(_sql(
                        "INSERT INTO analytics.text_en (src_hash, text_en) VALUES (:h, :e) ON CONFLICT (src_hash) DO NOTHING"
                    ), {"h": hashes[t], "e": en})
                    wrote = True
        if wrote:
            await db.commit()
    return res


async def attach_en(db, items: list[dict[str, Any]], text_key: str = "headline",
                    en_key: str | None = None) -> list[dict[str, Any]]:
    """Attach `<text_key>_en` (English) to each item whose `text_key` is non-English
    and that doesn't already carry a real translation."""
    en_key = en_key or f"{text_key}_en"
    need = [it for it in items
            if it.get(text_key) and not it.get(en_key) and not is_english(it[text_key])]
    if not need:
        return items
    enmap = await ensure_en(db, {it[text_key] for it in need})
    for it in need:
        en = enmap.get(it[text_key])
        if en:
            it[en_key] = en
    return items
