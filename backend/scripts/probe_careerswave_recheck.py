"""Re-probe the 18 failing papers carefully: try alternate slugs and inspect HTML."""
from __future__ import annotations

import asyncio
import re
import sys
from datetime import date

sys.path.insert(0, "/app")

import httpx

from backend.collectors.newspaper_collector import (
    _GDRIVE_FILE_ID_RE,
    _find_gdrive_id_near_date,
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Original failing URLs from the previous probe.
FAILS = [
    # 11 × HTTP 404
    ("Indian Express",     "en", "https://www.careerswave.in/indian-express-epaper-pdf-free-download/"),
    ("Bartaman",           "bn", "https://www.careerswave.in/bartaman-epaper-pdf-free-download/"),
    ("Prajavani",          "kn", "https://www.careerswave.in/prajavani-epaper-pdf-free-download/"),
    ("Udayavani",          "kn", "https://www.careerswave.in/udayavani-epaper-pdf-free-download/"),
    ("Malayala Manorama",  "ml", "https://www.careerswave.in/malayala-manorama-epaper-pdf-free-download/"),
    ("Mathrubhumi",        "ml", "https://www.careerswave.in/mathrubhumi-epaper-pdf-free-download/"),
    ("Ajit",               "pa", "https://www.careerswave.in/ajit-epaper-pdf-free-download/"),
    ("Daily Thanthi",      "ta", "https://www.careerswave.in/daily-thanthi-epaper-pdf-free-download/"),
    ("Dinamalar",          "ta", "https://www.careerswave.in/dinamalar-epaper-pdf-free-download/"),
    ("Dinamani",           "ta", "https://www.careerswave.in/dinamani-epaper-pdf-free-download/"),
    ("Namaste Telangana",  "te", "https://www.careerswave.in/namaste-telangana-epaper-pdf-free-download/"),
    # 6 × NO_PDF
    ("Greater Kashmir",    "en", "https://www.careerswave.in/greater-kashmir-epaper-pdf-free-download/"),
    ("Nagaland Post",      "en", "https://www.careerswave.in/nagaland-post-epaper-pdf-free-download/"),
    ("O Heraldo",          "en", "https://www.careerswave.in/o-heraldo-epaper-pdf-free-download/"),
    ("Nai Dunia",          "hi", "https://www.careerswave.in/nai-dunia-epaper-pdf-free-download/"),
    ("Samachar Jagat",     "hi", "https://www.careerswave.in/samachar-jagat-epaper-pdf-free-download/"),
    ("Eenadu",             "te", "https://www.careerswave.in/eenadu-epaper-pdf-free-download/"),
    # 1 × UNDATED
    ("Rashtriya Sahara",   "hi", "https://www.careerswave.in/rashtriya-sahara-epaper-pdf-free-download/"),
]

# Alternate slug patterns to try when the canonical one 404s.
ALT_SLUG_PATTERNS = [
    "{slug}-epaper-pdf-free-download",
    "{slug}-newspaper-in-pdf",
    "{slug}-newspaper-pdf-free-download",
    "{slug}-epaper",
    "the-{slug}-epaper-pdf-free-download",
    "{slug}-paper-pdf-free-download",
    "{slug}-e-paper-pdf-free-download",
    "{slug}-today-epaper-pdf-free-download",
]


def slug_variants(name: str) -> list[str]:
    s = name.lower().replace("'", "").replace(".", "")
    base = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    no_space = base.replace("-", "")
    parts = base.split("-")
    if len(parts) > 1:
        joined = parts[0] + parts[1]
        return list({base, no_space, joined, "-".join(parts[::-1])})
    return [base, no_space]


async def fetch_status(client: httpx.AsyncClient, url: str) -> tuple[int, str]:
    try:
        r = await client.get(url, timeout=15)
        return r.status_code, r.text if r.status_code == 200 else ""
    except Exception as exc:
        return -1, str(exc)[:60]


async def find_real_url(client: httpx.AsyncClient, name: str) -> tuple[str | None, int]:
    """Try alternate slug patterns and return the first one that returns 200."""
    tried = 0
    for slug in slug_variants(name):
        for pat in ALT_SLUG_PATTERNS:
            tried += 1
            url = f"https://www.careerswave.in/{pat.format(slug=slug)}/"
            code, _ = await fetch_status(client, url)
            if code == 200:
                return url, tried
    return None, tried


async def search_careerswave(client: httpx.AsyncClient, name: str) -> str | None:
    """Use careerswave's site search to look for the paper."""
    q = name.replace(" ", "+")
    url = f"https://www.careerswave.in/?s={q}"
    code, html = await fetch_status(client, url)
    if code != 200:
        return None
    m = re.search(
        r'href="(https://www\.careerswave\.in/[^"]*' + re.escape(name.lower().split()[0])
        + r'[^"]*epaper[^"]*)"',
        html,
        re.IGNORECASE,
    )
    return m.group(1) if m else None


def html_summary(html: str) -> str:
    """Extract the page title + first <h1>/<h2> + count of drive links."""
    title_m = re.search(r"<title>([^<]+)</title>", html)
    h1_m = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
    drive_count = len(_GDRIVE_FILE_ID_RE.findall(html))
    today = date.today()
    today_str = today.strftime("%d-%m-%Y")
    today_dash = today.strftime("%d %B %Y")
    has_today = today_str in html or today_dash in html
    return (
        f"title={title_m.group(1)[:50] if title_m else '?'!r:<55} "
        f"h1={(h1_m.group(1)[:40] if h1_m else '?'):<42} "
        f"drive_links={drive_count} "
        f"today_str_in_html={has_today}"
    )


async def main() -> None:
    async with httpx.AsyncClient(
        follow_redirects=True, headers={"User-Agent": UA}
    ) as client:

        print(f"Re-checking {len(FAILS)} failing papers — today is {date.today().isoformat()}\n")

        for name, lang, url in FAILS:
            code, html = await fetch_status(client, url)
            if code == 200:
                # NO_PDF / UNDATED case → inspect HTML
                today = date.today()
                fid = None
                for offset in (0, 1, 2):
                    target = today.fromordinal(today.toordinal() - offset)
                    fid = _find_gdrive_id_near_date(html, target)
                    if fid:
                        break
                summary = html_summary(html)
                if fid:
                    print(f"[{lang}] {name:<22} 200 OK now → DATED_OK ({fid[:14]}…)")
                else:
                    m = _GDRIVE_FILE_ID_RE.search(html)
                    if m:
                        print(f"[{lang}] {name:<22} 200 → UNDATED ({m.group(1)[:14]}…) | {summary}")
                    else:
                        print(f"[{lang}] {name:<22} 200 → STILL NO_PDF | {summary}")
                continue

            # 404: try alternate slugs + site search
            alt, tried = await find_real_url(client, name)
            if alt:
                code2, html2 = await fetch_status(client, alt)
                today = date.today()
                fid = None
                for offset in (0, 1, 2):
                    target = today.fromordinal(today.toordinal() - offset)
                    fid = _find_gdrive_id_near_date(html2, target)
                    if fid:
                        break
                if fid:
                    print(f"[{lang}] {name:<22} 404 → ALT FOUND ({tried} tries): {alt} → DATED_OK")
                else:
                    m = _GDRIVE_FILE_ID_RE.search(html2)
                    print(f"[{lang}] {name:<22} 404 → ALT FOUND but {'UNDATED' if m else 'NO_PDF'}: {alt}")
                continue

            # Site search
            via_search = await search_careerswave(client, name)
            if via_search:
                print(f"[{lang}] {name:<22} 404 → SEARCH HIT: {via_search}")
            else:
                print(f"[{lang}] {name:<22} 404 confirmed (tried {tried} slug variants + site search)")


if __name__ == "__main__":
    asyncio.run(main())
