"""Keyword Intel Desk — standalone app.

One keyword in → run all cheap_stack collectors live → per-platform top posts +
a Goldmine/Insights synthesis. Serves its own single-page UI. Runs as an
isolated sidecar (reuses the backend image + creds; does NOT touch rig-backend).

    uvicorn products.keyword_desk.app:app --host 0.0.0.0 --port 8600
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from backend.collectors.cheap_stack.keyword_search import REGISTRY
from products.keyword_desk.insights import build_insights

app = FastAPI(title="Keyword Intel Desk")
_STATIC = Path(__file__).parent / "static"


def _post_dict(p: dict[str, Any]) -> dict[str, Any]:
    """Serializable, UI-facing subset of a collector post."""
    d = {
        "platform": p.get("platform"),
        "id": str(p.get("platform_post_id") or ""),
        "author": p.get("author_username"),
        "channel": p.get("channel") or p.get("subreddit") or p.get("account"),
        "text": (p.get("post_text") or "")[:500],
        "url": p.get("post_url"),
        "posted_at": p.get("posted_at"),
        "upvotes": p.get("upvotes"), "likes": p.get("likes"),
        "comments": p.get("comment_count"), "shares": p.get("shares"),
        "views": p.get("views"), "duration": p.get("duration"),
        "thumbnail": p.get("thumbnail"),
        "media_url": p.get("media_url") or (p.get("media_urls") or [None])[0],
        "external_url": p.get("external_url"),
        "verified": bool(p.get("verified")),
    }
    if p.get("platform") == "wechat":
        d["title"] = p.get("title")
        d["content_len"] = len(p.get("content") or "")
    return d


async def _run(platform: str, keyword: str, limit: int) -> tuple[str, dict[str, Any]]:
    fn = REGISTRY[platform]
    try:
        r = await fn(keyword, limit=limit)
        return platform, {
            "ok": r.ok, "note": r.note, "count": r.count,
            "elapsed_s": round(r.elapsed_s, 1), "error": r.error,
            "posts": list(r.posts),                     # raw — for insights
        }
    except Exception as exc:
        return platform, {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                          "posts": [], "count": 0, "note": None}


@app.get("/api/search")
async def search(keyword: str, limit: int = 8) -> JSONResponse:
    keyword = (keyword or "").strip()
    if not keyword:
        return JSONResponse({"error": "empty keyword"}, status_code=400)
    started = time.monotonic()
    pairs = await asyncio.gather(*[_run(p, keyword, limit) for p in REGISTRY])
    raw = {p: d for p, d in pairs}

    # Goldmine transcript — spoken content of the top YouTube video
    transcript = None
    yt = raw.get("youtube", {}).get("posts", [])
    if yt:
        top = max(yt, key=lambda x: int(x.get("views") or 0))
        try:
            from backend.collectors.youtube_v2.free_transcript import fetch_free_transcript
            ft = fetch_free_transcript(top["platform_post_id"])
            if ft:
                transcript = {
                    "video_id": top["platform_post_id"],
                    "title": (top.get("post_text") or "")[:90],
                    "url": top.get("post_url"), "provider": ft.provider,
                    "chars": ft.chars, "excerpt": ft.text[:1400],
                }
        except Exception:
            pass

    insights = build_insights(keyword, raw)
    insights["goldmine"]["transcript"] = transcript

    platforms = {
        p: {"ok": d["ok"], "note": d.get("note"), "count": d.get("count", 0),
            "elapsed_s": d.get("elapsed_s"), "error": d.get("error"),
            "posts": [_post_dict(x) for x in d.get("posts", [])]}
        for p, d in raw.items()
    }
    return JSONResponse({
        "keyword": keyword,
        "took_ms": int((time.monotonic() - started) * 1000),
        "platforms": platforms,
        "insights": insights,
    })


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "platforms": list(REGISTRY)}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")
