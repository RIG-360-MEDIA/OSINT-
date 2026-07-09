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

import asyncio
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

# CPV procurement-category presets — precise category search, immune to the
# keyword ambiguity that plagues edged-weapon terms ('bayonet'=fitting,
# 'sabre'=the travel system, 'machete'⊂'machine'). Codes VERIFIED live on TED:
# 35311000 returns real sword tenders (Greece/Athens: Swords); 35400000 is
# military VEHICLES (deliberately excluded from 'edged').
_CPV_PRESETS = {
    "edged": "35311100",              # Swords (precise code — Windlass core)
    "swords": "35311100",
    "weapons": "35311100,35320000",   # edged + light firearms
    "firearms": "35320000",
    "ammunition": "35330000",
    "defence": "35000000",            # broad security/police/defence equipment
    "military-vehicles": "35400000",
}


def _resolve_cpv(cpv: str) -> str:
    """Preset name → CPV code list; else pass through raw 6–8 digit codes."""
    key = (cpv or "").lower().strip()
    if key in _CPV_PRESETS:
        return _CPV_PRESETS[key]
    return ",".join(re.findall(r"\d{6,8}", cpv or ""))


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


async def _ted_search(keyword: str, limit: int, months: int = 12,
                      cpv: str | None = None) -> dict[str, Any]:
    """Open EU/EEA tenders, most-recent first.

    Two modes: keyword (`notice-title~`/`FT~`, title-match precedence to cut
    body-only noise) and CPV-category (`classification-cpv IN (...)`, precise —
    no keyword ambiguity). They combine: a CPV + keyword narrows within a
    category. CPV mode trusts the category, so it skips the title filter."""
    since = (datetime.now(timezone.utc) - timedelta(days=30 * months)).strftime("%Y%m%d")
    kw = keyword.replace('"', "").strip()
    cpv_codes = _resolve_cpv(cpv) if cpv else ""

    clauses: list[str] = []
    if cpv_codes:
        clauses.append(f"classification-cpv IN ({cpv_codes})")
    if kw:
        clauses.append(f'(notice-title~"{kw}" OR FT~"{kw}")')
    clauses.append(f"publication-date>={since}")
    query = " AND ".join(clauses) + " SORT BY publication-date DESC"

    body = {"query": query, "fields": _TED_FIELDS,
            "limit": min(max(limit * 4, 40), 100), "paginationMode": "PAGE_NUMBER"}
    out: dict[str, Any] = {"ok": False, "tenders": [], "total_matches": None,
                           "mode": "cpv" if cpv_codes else "keyword"}
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
        # keep OPEN contract notices (cn-*), drop awards (can-*)
        open_notices = [t for t in notices if (t["notice_type"] or "").startswith("cn")]
        if cpv_codes:
            # category is authoritative — no title filter needed
            chosen = open_notices
        else:
            # precision: a TED title reads "Country – CPV-category – desc", so a
            # keyword in the TITLE is a real subject match; a full-text-only hit
            # pulls unrelated docs. Prefer titled matches, fall back so a genuine
            # match is never zeroed out.
            toks = [t for t in re.findall(r"[a-z0-9]+", kw.lower()) if len(t) >= 3]
            titled = [t for t in open_notices
                      if kw.lower() in t["title"].lower()
                      or (toks and all(x in t["title"].lower() for x in toks))]
            chosen = titled or open_notices
            out["title_matched"] = len(titled)
        chosen.sort(key=lambda t: t["published"] or "", reverse=True)
        out["tenders"] = chosen[:limit]
        out["ok"] = True
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


# ── National-portal discovery (SearXNG dorks) — where Windlass's real buyers post ──

_PORTALS = [
    ("India MoD (defproc)", "defproc.gov.in"),
    ("India CPPP", "eprocure.gov.in"),
    ("US SAM.gov", "sam.gov"),
    ("UK Contracts Finder", "contractsfinder.service.gov.uk"),
    ("UN UNGM", "ungm.org"),
    ("Australia AusTender", "tenders.gov.au"),
]


async def _portal_dorks(keyword: str, per_portal: int = 3) -> list[dict[str, Any]]:
    """Site-scoped dork of each national procurement portal for the keyword.

    Reaches tenders on the portals the free structured APIs DON'T cover (India
    MoD, US, UK, ...). Discovery leads (title + url), not structured rows."""
    from searxng_collector import web_search

    async def one(name: str, dom: str) -> list[dict[str, Any]]:
        try:
            r = await web_search(f'{keyword} tender site:{dom}', limit=per_portal)
        except Exception:
            return []
        return [{"portal": name, "domain": dom, "title": x.get("title"),
                 "url": x.get("url")}
                for x in r.get("results", [])[:per_portal] if x.get("url")]

    batches = await asyncio.gather(*[one(n, d) for n, d in _PORTALS],
                                   return_exceptions=True)
    leads: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for b in batches:
        if not isinstance(b, list):
            continue
        for lead in b:
            key = (lead["domain"], (lead.get("title") or "").strip().lower())
            if key not in seen:
                seen.add(key)
                leads.append(lead)
    return leads


# ── World Bank Procurement Notices (GLOBAL — all borrower countries incl. India) ──

_WB = "https://search.worldbank.org/api/v2/procnotices"


def _wb_date(s: str) -> str:
    """WB noticedate is '07-Jul-2026' → ISO; passthrough on any other shape."""
    try:
        return datetime.strptime((s or "").strip(), "%d-%b-%Y").strftime("%Y-%m-%d")
    except Exception:
        return (s or "")[:10]


def _wb_notice(n: dict[str, Any]) -> dict[str, Any]:
    pid = n.get("project_id") or ""
    return {
        "source": "World Bank",
        "title": (n.get("bid_description") or n.get("project_name") or "").strip()[:300],
        "buyer": (n.get("project_name") or "").strip()[:160],
        "country": n.get("project_ctry_name"),
        "deadline": (n.get("submission_date") or "")[:10] or None,
        "published": _wb_date(n.get("noticedate") or ""),
        "notice_type": n.get("notice_type"),
        "ref": n.get("bid_reference_no") or n.get("id"),
        "url": (f"https://projects.worldbank.org/en/projects-operations/project-detail/{pid}"
                if pid else None),
    }


async def _wb_search(keyword: str, limit: int, country: str | None = None) -> dict[str, Any]:
    """Open World Bank-financed procurement notices matching `keyword`, worldwide.

    Covers every WB borrower country (India, Africa, Asia, LatAm). `os=0` is
    REQUIRED — omitting it 500s. Drops 'Contract Award' (already awarded); optional
    client-side country filter."""
    out: dict[str, Any] = {"ok": False, "tenders": [], "total_matches": None}
    params = {"format": "json", "qterm": keyword.strip(),
              "rows": min(max(limit * 5, 50), 100), "os": 0}
    try:
        async with httpx.AsyncClient(timeout=25, headers={"User-Agent": _UA}) as cl:
            r = await cl.get(_WB, params=params, headers={"Accept": "application/json"})
        if r.status_code != 200:
            out["error"] = f"WB HTTP {r.status_code}"
            return out
        data = r.json()
        out["total_matches"] = data.get("total")
        notices = [_wb_notice(n) for n in data.get("procnotices", [])]
        # open only: drop awarded contracts
        opened = [t for t in notices if "award" not in (t["notice_type"] or "").lower()]
        if country:
            c = country.lower().strip()
            opened = [t for t in opened if (t["country"] or "").lower() == c]
        opened.sort(key=lambda t: t["published"] or "", reverse=True)
        out["tenders"] = opened[:limit]
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
    keyword: str, *, region: str = "all", country: str | None = None,
    cpv: str | None = None, portals: bool = False, limit: int = 15,
) -> dict[str, Any]:
    """Open public tenders matching a keyword, worldwide.

    `region`:
      • 'world' (default global) — World Bank Procurement Notices, EVERY borrower
        country (India, Africa, Asia, LatAm). Keyword-searchable, free.
      • 'eu' — TED (official EU procurement API).
      • 'india' — World Bank(India) + India CPPP latest-active feed.
      • 'all' — TED + World Bank(global) + CPPP.
    `country` (optional) — client-side filter on World Bank results (e.g. 'India',
    'Kenya', 'Brazil') so any single country can be targeted.

    Where no structured API exists for a country, the SearXNG web-search source
    (GET /websearch, e.g. '<keyword> tender <country>') is the universal fallback.
    Partial on any single-source failure — each source degrades to a labelled state."""
    keyword = (keyword or "").strip()
    if not keyword and not cpv:
        return {"query": keyword,
                "error": "empty query (tender search needs a keyword or a cpv category)"}

    region = (region or "all").lower()
    out: dict[str, Any] = {"query": keyword, "region": region, "country": country,
                           "cpv": cpv, "tenders": [], "sources": {}, "summary": None}

    # TED runs for EU/all, OR whenever a CPV category is requested (CPV is a TED
    # feature and is the precise, ambiguity-free path).
    if region in ("eu", "all") or cpv:
        ted = await _ted_search(keyword, limit, cpv=cpv)
        out["sources"]["ted_eu"] = {
            "ok": ted["ok"], "total_matches": ted.get("total_matches"),
            "returned": len(ted["tenders"]), "error": ted.get("error"),
            "mode": ted.get("mode"),
            "note": ("official EU procurement API — open contract notices, recent-first"
                     + (f"; CPV category {_resolve_cpv(cpv)}" if cpv else "")),
        }
        out["tenders"] += ted["tenders"]

    if region in ("world", "global", "india", "all"):
        wb_country = "India" if region == "india" else country
        wb = await _wb_search(keyword, limit, country=wb_country)
        out["sources"]["world_bank"] = {
            "ok": wb["ok"], "total_matches": wb.get("total_matches"),
            "returned": len(wb["tenders"]), "error": wb.get("error"),
            "country_filter": wb_country,
            "note": ("World Bank Procurement Notices — every borrower country "
                     "(incl. India); open notices, awards excluded"),
        }
        out["tenders"] += wb["tenders"]

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

    # National-portal discovery — reaches buyers the structured APIs miss
    # (India MoD, US SAM, UK, ...). Needs a keyword (site-scoped dork).
    if portals and keyword:
        out["portal_leads"] = await _portal_dorks(keyword)

    out["summary"] = {
        "total_returned": len(out["tenders"]),
        "ted_open_matches": out["sources"].get("ted_eu", {}).get("total_matches"),
        "worldbank_open_matches": out["sources"].get("world_bank", {}).get("total_matches"),
        "portal_leads": len(out.get("portal_leads", [])) if portals else None,
        "sources_ok": [k for k, v in out["sources"].items() if v.get("ok")],
    }
    return out
