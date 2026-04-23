"""
Hit every frontend page's backend endpoint as the production user
(pranavpuri03@gmail.com) and report what works vs what's broken.
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx


SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
EMAIL = "pranavpuri03@gmail.com"
PASSWORD = "App!e2005"

API = "http://localhost:8000"


def login() -> str:
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"},
        json={"email": EMAIL, "password": PASSWORD},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def call(token: str, method: str, path: str, **kw) -> dict:
    started = time.time()
    try:
        r = httpx.request(
            method, f"{API}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=kw.pop("timeout", 30),
            **kw,
        )
        ms = int((time.time() - started) * 1000)
        try:
            body = r.json()
        except Exception:
            body = {"_raw": r.text[:300]}
        return {"status": r.status_code, "ms": ms, "body": body}
    except Exception as exc:
        return {"status": "ERROR", "ms": int((time.time() - started) * 1000), "body": {"_err": str(exc)[:200]}}


def line(name: str, path: str, res: dict, summary: str = "") -> None:
    print(f"  [{res['status']}] {res['ms']:>5}ms  {name:<22} {path:<40} {summary}", flush=True)


def main() -> None:
    print("=== auth ===", flush=True)
    token = login()
    print(f"  token acquired ({len(token)} chars)\n", flush=True)

    print("=== onboarding ===", flush=True)
    r = call(token, "GET", "/api/onboarding/status")
    line("onboarding_status", "/api/onboarding/status", r,
         f"has_profile={r['body'].get('has_profile')}")

    print("\n=== brief ===", flush=True)
    r = call(token, "GET", "/api/brief/today")
    keys = list(r["body"].keys()) if isinstance(r["body"], dict) else []
    line("brief_today", "/api/brief/today", r, f"keys={keys[:6]}")

    print("\n=== coverage ===", flush=True)
    r = call(token, "GET", "/api/coverage/feed?limit=3")
    if isinstance(r["body"], dict):
        n = len(r["body"].get("articles", []))
        totals = r["body"].get("totals", {})
        line("coverage_feed", "/api/coverage/feed?limit=3", r,
             f"articles={n} totals={totals}")
    else:
        line("coverage_feed", "/api/coverage/feed?limit=3", r)

    print("\n=== threads ===", flush=True)
    r = call(token, "GET", "/api/threads?limit=5")
    if isinstance(r["body"], dict):
        line("threads", "/api/threads?limit=5", r,
             f"thread_count={r['body'].get('thread_count')} escalating={r['body'].get('escalating_count')}")
    else:
        line("threads", "/api/threads?limit=5", r)

    print("\n=== clips ===", flush=True)
    r = call(token, "GET", "/api/clips/feed?limit=3")
    if isinstance(r["body"], dict):
        line("clips_feed", "/api/clips/feed?limit=3", r,
             f"clips={len(r['body'].get('clips', []))} total={r['body'].get('total')}")
    else:
        line("clips_feed", "/api/clips/feed?limit=3", r)

    print("\n=== clippings (P16 cutting room) ===", flush=True)
    for path in ("/api/clippings/feed?limit=3", "/api/cuttings/feed?limit=3"):
        r = call(token, "GET", path)
        line("clippings", path, r, "")
        if r["status"] == 200:
            break

    print("\n=== signals (P17) ===", flush=True)
    for path in ("/api/signals/feed?limit=3", "/api/signals?limit=3"):
        r = call(token, "GET", path)
        line("signals", path, r)
        if r["status"] == 200:
            break

    print("\n=== analyst (POST) ===", flush=True)
    r = call(token, "POST", "/api/analyst/query",
             json={"question": "What's the latest GHMC tender activity?", "mode": "SITUATION"},
             timeout=90)
    if isinstance(r["body"], dict):
        keys = list(r["body"].keys())[:10]
        ans = (r["body"].get("answer") or "")[:120].replace("\n", " ")
        line("analyst_query", "/api/analyst/query", r,
             f"keys={keys}; answer='{ans}...'")
    else:
        line("analyst_query", "/api/analyst/query", r)

    # ── DEEP DIVE: DOCUMENTS ──────────────────────────────────────────────
    print("\n=== DOCUMENTS DEEP DIVE ===", flush=True)
    r = call(token, "GET", "/api/documents/feed?limit=20")
    body = r["body"] if isinstance(r["body"], dict) else {}
    docs = body.get("documents", [])
    line("documents_feed", "/api/documents/feed?limit=20", r,
         f"docs={len(docs)} total={body.get('total')} geo_counts={body.get('geography_counts')}")

    if docs:
        print("\n--- TOP 5 RANKED DOCUMENTS (as the user sees them) ---", flush=True)
        for i, d in enumerate(docs[:5], 1):
            sf = d.get("score_final")
            score_str = f"{sf:.2f}" if isinstance(sf, (int, float)) else "NULL"
            print(f"\n  #{i}  T{d.get('relevance_tier')}  score={score_str}  urgency={d.get('urgency')}")
            print(f"      title: {d.get('title','')[:80]}")
            print(f"      source: {d.get('source_name')} | geo: {d.get('source_geography')} | type: {d.get('document_type')}")
            why = (d.get('why_it_matters') or '')[:140].replace("\n", " ")
            print(f"      why_it_matters: {why if why else '(none)'}")
            sa = (d.get('suggested_action') or '')[:140].replace("\n", " ")
            print(f"      suggested_action: {sa if sa else '(none)'}")

        # detail endpoint test
        first_id = docs[0]["doc_id"]
        rd = call(token, "GET", f"/api/documents/{first_id}")
        print(f"\n  /api/documents/{{doc_id}} → status {rd['status']}, body keys: {list(rd['body'].keys())[:8] if isinstance(rd['body'], dict) else '?'}")

        # summary endpoint test (POST)
        rs = call(token, "POST", f"/api/documents/{first_id}/summary", timeout=45)
        if isinstance(rs["body"], dict) and rs["status"] == 200:
            cached = rs["body"].get("cached")
            summary = (rs["body"].get("summary") or "")[:200].replace("\n", " ")
            print(f"  POST /api/documents/{{id}}/summary → status {rs['status']} cached={cached}")
            print(f"      summary preview: {summary}...")
        else:
            print(f"  POST /api/documents/{{id}}/summary → status {rs['status']} body={rs['body']}")

    # ── DEBUG ──────────────────────────────────────────────────────────────
    print("\n=== /debug pages ===", flush=True)
    for path in ("/debug/pipeline-health", "/debug/govt-collection-health", "/debug/groq-status"):
        r = call(token, "GET", path)
        line("debug", path, r,
             f"keys={list(r['body'].keys())[:5] if isinstance(r['body'], dict) else '?'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FATAL: {exc}")
        sys.exit(1)
