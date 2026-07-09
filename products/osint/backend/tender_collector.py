"""Public-tender collector — real OPEN procurement notices for a keyword.

Two free, no-key sources, both verified live from the datacenter:

  • TED (EU "Tenders Electronic Daily") — the official EU-wide procurement API.
    REAL keyword search, structured (title / buyer / country / deadline / CPV /
    link). Open contract notices only (awards excluded). Covers defence, naval,
    edged-weapons, ammunition, etc. across the EU/EEA — genuine sales leads for
    exporters (e.g. an edged-weapons maker like Windlass).

  • India CPPP (eprocure.gov.in central portal) — the latest ACTIVE tenders feed,
    parsed to structured rows. HONEST LIMIT: CPPP exposes no free keyword API, so
    this is the latest-active firehose keyword-filtered client-side (thin for
    niche terms; richest when filtered by buyer organisation such as Ministry of
    Defence / Ordnance / Military Engineer Services).

Read-only external lookups; no paid aggregators. `tender_search` never raises —
each source degrades to an honest labelled state on failure.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

_TED = "https://api.ted.europa.eu/v3/notices/search"
_CPPP = "https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124 Safari/537.36")
_TED_FIELDS = [
    "publication-number", "publication-date", "notice-title", "buyer-name",
    "buyer-country", "deadline-receipt-tender-date-lot", "classification-cpv",
    "notice-type", "place-of-performance", "links",
]


def _first(v: Any) -> Any:
    """First element of a TED list-valued field, else the value itself."""
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _flat(v: Any, prefer: str = "eng") -> str:
    """Flatten a TED multilingual field ({lang: [text]}) to English if present."""
    if isinstance(v, dict):
        v = v.get(prefer) or next(iter(v.values()), "")
    if isinstance(v, list):
        v = v[0] if v else ""
    return str(v or "").strip()


def _ted_notice(n: dict[str, Any]) -> dict[str, Any]:
    pub = n.get("publication-number") or ""
    dl = _first(n.get("deadline-receipt-tender-date-lot"))
    return {
        "source": "TED (EU)",
        "title": _flat(n.get("notice-title"))[:300],
        "buyer": _flat(n.get("buyer-name"))[:160],
        "country": _first(n.get("buyer-country")),
        "deadline": (dl or "")[:10] or None,
        "published": (n.get("publication-date") or "")[:10],
        "cpv": _first(n.get("classification-cpv")),
        "notice_type": n.get("notice-type"),
        "ref": pub,
        "url": f"https://ted.europa.eu/en/notice/-/detail/{pub}" if pub else None,
    }


async def _ted_search(keyword: str, limit: int, months: int = 12) -> dict[str, Any]:
    """Open EU/EEA tenders matching `keyword`, most-recent first."""
    since = (datetime.now(timezone.utc) - timedelta(days=30 * months)).strftime("%Y%m%d")
    kw = keyword.replace('"', "").strip()
    query = (f'(notice-title~"{kw}" OR FT~"{kw}") '
             f'AND publication-date>={since} SORT BY publication-date DESC')
    body = {"query": query, "fields": _TED_FIELDS,
            "limit": min(max(limit * 4, 40), 100), "paginationMode": "PAGE_NUMBER"}
    out: dict[str, Any] = {"ok": False, "tenders": [], "total_matches": None}
    try:
        async with httpx.AsyncClient(timeout=25, headers={"User-Agent": _UA}) as cl:
            r = await cl.post(_TED, json=body,
                              headers={"Content-Type": "application/json",
                                       "Accept": "application/json"})
        if r.status_code != 200:
            out["error"] = f"TED HTTP {r.status_code}"
            return out
        data = r.json()
        out["total_matches"] = data.get("totalNoticeCount")
        notices = [_ted_notice(n) for n in data.get("notices", [])]
        # keep OPEN contract notices (cn-*), drop awards (can-*) and other types
        open_notices = [t for t in notices if (t["notice_type"] or "").startswith("cn")]
        # precision: a TED title reads "Country – CPV-category – desc", so a keyword
        # in the TITLE is a real subject match; a full-text-only hit pulls unrelated
        # docs (e.g. 'sword' inside a construction spec). Prefer titled matches,
        # fall back to all open notices so a genuine match is never zeroed out.
        toks = [t for t in re.findall(r"[a-z0-9]+", kw.lower()) if len(t) >= 3]
        titled = [t for t in open_notices
                  if kw.lower() in t["title"].lower()
                  or (toks and all(x in t["title"].lower() for x in toks))]
        chosen = titled or open_notices
        chosen.sort(key=lambda t: t["published"] or "", reverse=True)
        out["tenders"] = chosen[:limit]
        out["title_matched"] = len(titled)
        out["ok"] = True
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


# ── India CPPP latest-active feed ───────────────────────────────────────────

_CPPP_ROW = re.compile(r'<tr style="border-bottom[^>]*>(.*?)</tr>', re.DOTALL)
_CPPP_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_CPPP_A = re.compile(r'<a href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)


def _cppp_strip(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _cppp_rows(html: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _CPPP_ROW.findall(html):
        cells = _CPPP_CELL.findall(row)
        if len(cells) < 6:
            continue
        am = _CPPP_A.search(cells[4])
        rows.append({
            "source": "India CPPP",
            "published": _cppp_strip(cells[1]),
            "deadline": _cppp_strip(cells[2]),
            "title": _cppp_strip(cells[4]),
            "buyer": _cppp_strip(cells[5]),
            "url": (am.group(1) if am else None),
            "country": "IN",
        })
    return rows


async def _cppp_search(keyword: str, limit: int, pages: int = 4) -> dict[str, Any]:
    """Latest active India tenders, keyword-filtered client-side (honest partial)."""
    out: dict[str, Any] = {"ok": False, "tenders": [], "scanned": 0}
    rows: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=25, headers={"User-Agent": _UA},
                                     follow_redirects=True) as cl:
            for p in range(1, pages + 1):
                r = await cl.get(_CPPP, params={"page": str(p)})
                if r.status_code == 200:
                    rows += _cppp_rows(r.text)
        out["scanned"] = len(rows)
        kw = keyword.lower().strip()
        toks = [t for t in re.findall(r"[a-z0-9]+", kw) if len(t) >= 3]
        matched = [
            row for row in rows
            if kw in (row["title"] + " " + row["buyer"]).lower()
            or (toks and all(t in (row["title"] + " " + row["buyer"]).lower() for t in toks))
        ]
        # dedupe by url
        seen: set[str] = set()
        uniq = [r for r in matched if not (r["url"] in seen or seen.add(r["url"]))]
        out["tenders"] = uniq[:limit]
        out["ok"] = True
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


async def tender_search(
    keyword: str, *, region: str = "all", limit: int = 15,
) -> dict[str, Any]:
    """Open public tenders matching a keyword. `region`: 'eu' | 'india' | 'all'.

    TED (EU) is the real keyword-searchable engine; India CPPP is a latest-active
    feed keyword-filtered client-side (labelled — no free keyword API). Partial on
    any single-source failure."""
    keyword = (keyword or "").strip()
    if not keyword:
        return {"query": keyword, "error": "empty query (tender search needs a keyword)"}

    out: dict[str, Any] = {"query": keyword, "region": region, "tenders": [],
                           "sources": {}, "summary": None}

    if region in ("eu", "all"):
        ted = await _ted_search(keyword, limit)
        out["sources"]["ted_eu"] = {
            "ok": ted["ok"], "total_matches": ted.get("total_matches"),
            "returned": len(ted["tenders"]), "error": ted.get("error"),
            "note": "official EU procurement API — open contract notices, recent-first",
        }
        out["tenders"] += ted["tenders"]

    if region in ("india", "all"):
        cppp = await _cppp_search(keyword, limit)
        out["sources"]["india_cppp"] = {
            "ok": cppp["ok"], "scanned": cppp.get("scanned"),
            "returned": len(cppp["tenders"]), "error": cppp.get("error"),
            "note": ("latest-active feed, keyword-filtered client-side — CPPP has no "
                     "free keyword API, so niche terms are sparse; richest filtered "
                     "by buyer org (Min. of Defence / Ordnance / MES)"),
        }
        out["tenders"] += cppp["tenders"]

    out["summary"] = {
        "total_returned": len(out["tenders"]),
        "ted_open_matches": out["sources"].get("ted_eu", {}).get("total_matches"),
        "regions": [k for k, v in out["sources"].items() if v.get("ok")],
    }
    return out
