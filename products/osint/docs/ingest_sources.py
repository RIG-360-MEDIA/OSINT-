#!/usr/bin/env python3
"""
ingest_sources.py — INGEST_PROMPT Steps 1-3: dedup, feed-discovery, verify.

Reads the CSV + an existing-domains file; for each NEW source discovers its feed
(<link alternate> -> common paths -> scrape fallback) and verifies it live
(RSS: HTTP 200 + >=1 parseable item; scrape: 200 + >=5 article links).

Outputs a JSON results file ONLY. It does NOT write to the database — per the
HARD SAFETY RULES, every DB write goes through `docker exec rig-postgres psql`.
Run it inside rig-backend so verification sees the same IP/geo as production fetch.

Env: CSV_PATH /tmp/sources_to_add.csv · EXIST_PATH /tmp/existing_domains.txt
     OUT /tmp/sources_results.json · WORKERS 8
"""
from __future__ import annotations

import concurrent.futures as cf
import csv
import json
import os
import re
from collections import Counter
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

CSV_PATH = os.environ.get("CSV_PATH", "/tmp/sources_to_add.csv")
EXIST_PATH = os.environ.get("EXIST_PATH", "/tmp/existing_domains.txt")
OUT = os.environ.get("OUT", "/tmp/sources_results.json")
WORKERS = int(os.environ.get("WORKERS", "8"))
TIMEOUT = 12.0
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
FEED_PATHS = ["/feed", "/feed/", "/rss", "/rss.xml", "/atom.xml", "/?feed=rss2"]
ARTICLE_RE = re.compile(r"/20\d\d/|/news/|/article/|/story/|/articles?/|-\d{5,}")


def domain_of(url: str) -> str:
    u = url if "://" in url else "https://" + url
    host = urlparse(u).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def fetch(client: httpx.Client, url: str):
    try:
        return client.get(url, follow_redirects=True, timeout=TIMEOUT,
                          headers={"User-Agent": UA})
    except Exception:
        return None


def find_feed(client, home):
    r = fetch(client, home)
    if r is None:
        return None, None, "home: connect error"
    if r.status_code != 200:
        return None, None, f"home: HTTP {r.status_code}"
    base = f"{urlparse(str(r.url)).scheme}://{urlparse(str(r.url)).netloc}"
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        for ln in soup.find_all("link"):
            rel = " ".join(ln.get("rel") or []).lower()
            typ = (ln.get("type") or "").lower()
            if "alternate" in rel and ("rss" in typ or "atom" in typ or "xml" in typ):
                href = ln.get("href")
                if href:
                    return urljoin(str(r.url), href), "rss", "link-alternate"
    except Exception:
        pass
    for p in FEED_PATHS:
        fr = fetch(client, base + p)
        if fr is not None and fr.status_code == 200:
            head = fr.text[:600].lower()
            ctype = fr.headers.get("content-type", "").lower()
            if "xml" in ctype or "<rss" in head or "<feed" in head or "<?xml" in head:
                return str(fr.url), "rss", f"path {p}"
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        al = {a.get("href") for a in soup.find_all("a", href=True)
              if a.get("href") and ARTICLE_RE.search(a.get("href"))}
        if len(al) >= 5:
            return None, "scrape", f"{len(al)} article links"
    except Exception:
        pass
    return None, None, "no feed; <5 article links"


def verify_rss(client, url):
    r = fetch(client, url)
    if r is None:
        return False, "rss: connect error"
    if r.status_code != 200:
        return False, f"rss: HTTP {r.status_code}"
    fp = feedparser.parse(r.content)
    items = [e for e in fp.entries if e.get("title") and (e.get("link") or e.get("links"))]
    return (True, f"{len(items)} items") if items else (False, "rss: 0 items")


def verify_scrape(client, home):
    r = fetch(client, home)
    if r is None:
        return False, "home: connect error"
    if r.status_code != 200:
        return False, f"home: HTTP {r.status_code}"
    soup = BeautifulSoup(r.text, "html.parser")
    al = {a.get("href") for a in soup.find_all("a", href=True)
          if a.get("href") and ARTICLE_RE.search(a.get("href"))}
    return (True, f"{len(al)} links") if len(al) >= 5 else (False, f"{len(al)} links (<5)")


def process(row, existing):
    name = (row.get("name") or "").strip()
    url = (row.get("url") or "").strip()
    dom = domain_of(url)
    res = {
        "name": name, "url": url, "domain": dom,
        "reach_tier": row.get("reach_tier"), "language": row.get("language"),
        "country_iso": row.get("country_iso"), "geo_state": row.get("geo_state"),
        "category": row.get("category"), "group": row.get("group"),
        "access_status": row.get("access_status"),
        "source_type": None, "rss_url": None, "verified": False,
    }
    if not dom:
        res.update(status="skip", reason="no domain"); return res
    if dom in existing:
        res.update(status="dupe", reason="domain already in sources"); return res
    home = url if "://" in url else "https://" + url
    with httpx.Client() as client:
        rss_url, stype, dreason = find_feed(client, home)
        if stype == "rss" and rss_url:
            ok, vreason = verify_rss(client, rss_url)
            res.update(source_type="rss", rss_url=rss_url, verified=ok,
                       status="ok" if ok else "unverified",
                       reason=f"{dreason}; verify {vreason}")
        elif stype == "scrape":
            ok, vreason = verify_scrape(client, home)
            res.update(source_type="scrape", rss_url=None, verified=ok,
                       status="ok" if ok else "unverified",
                       reason=f"{dreason}; verify {vreason}")
        else:
            res.update(source_type=None, rss_url=None, verified=False,
                       status="nofeed", reason=dreason)
    return res


def main():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    existing = {l.strip().lower() for l in open(EXIST_PATH, encoding="utf-8") if l.strip()}
    print(f"loaded {len(rows)} rows, {len(existing)} existing domains")
    results = []
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(process, r, existing): r for r in rows}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                rr = futs[fut]
                results.append({"name": rr.get("name"), "url": rr.get("url"),
                                "status": "error", "reason": str(exc)[:120], "verified": False})
            if i % 25 == 0:
                print(f"  ...{i}/{len(rows)}", flush=True)
    json.dump(results, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    st = Counter(r.get("status") for r in results)
    print("=== SUMMARY ===")
    print("total", len(results), "| status", dict(st))
    print("verified", sum(1 for r in results if r.get("verified")),
          "| rss", sum(1 for r in results if r.get("source_type") == "rss"),
          "| scrape", sum(1 for r in results if r.get("source_type") == "scrape"))
    print("OUT", OUT)


if __name__ == "__main__":
    main()
