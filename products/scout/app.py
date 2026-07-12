"""RIG Scout — one keyword, every source, raw data.

    GET /scout?keyword=&limit=   -> per-source envelopes (full records, newest-first)
    GET /                        -> the standalone UI
    GET /health

Standalone webapp (NOT bolted into any existing product). Phase 1: fan-out + show all
data per source. No ranking across sources, no dedup, no deductions — that comes later.

    uvicorn products.scout.app:app --host 0.0.0.0 --port 8610
"""
from __future__ import annotations

from pathlib import Path


def _load_local_env() -> None:
    """Dev convenience: load repo-root/local `.env` (session cookies for reddit/twitter)
    into the environment so Scout runs off-container. No-op in prod; real env wins."""
    import os

    for envp in (Path(__file__).resolve().parents[2] / ".env", Path(__file__).parent / ".env"):
        if not envp.exists():
            continue
        for line in envp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


_load_local_env()

from fastapi import FastAPI, Query                       # noqa: E402  (after env load)
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402

import products.scout.judge as J                           # noqa: E402
import products.scout.plan as P                            # noqa: E402
import products.scout.sources as S                        # noqa: E402


def _ask_sources(pl: "P.QueryPlan") -> list[str]:
    return pl.sources if pl.sources else [n for n in S.ORDER if n != "identity"]

app = FastAPI(title="RIG Scout")
_STATIC = Path(__file__).parent / "static"


@app.get("/scout")
async def scout(keyword: str = Query(..., min_length=1, max_length=120),
                limit: int = Query(8, ge=1, le=50)) -> JSONResponse:
    sources = await S.scout(keyword, limit=limit)
    return JSONResponse({"keyword": keyword, "sources": sources})


@app.get("/scout/sources")
def scout_sources() -> JSONResponse:
    """The ordered source list, so the UI can paint skeleton panels immediately."""
    return JSONResponse({"sources": S.source_list()})


@app.get("/scout/one")
async def scout_one(name: str = Query(..., max_length=40),
                    keyword: str = Query(..., min_length=1, max_length=120),
                    limit: int = Query(8, ge=1, le=50)) -> JSONResponse:
    """Run ONE source — the UI calls these in parallel so each panel streams in on its own."""
    return JSONResponse(await S.run_one(name, keyword, limit=limit))


@app.get("/scout/ask/plan")
def ask_plan(q: str = Query(..., min_length=1, max_length=200)) -> JSONResponse:
    """Parse a natural-language ask into a TRANSPARENT plan (shown before running)."""
    pl = P.rule_parse(q)
    d = P.to_dict(pl)
    d["resolved_sources"] = _ask_sources(pl)
    return JSONResponse(d)


@app.get("/scout/ask/one")
async def ask_one(name: str = Query(..., max_length=40),
                  q: str = Query(..., min_length=1, max_length=200)) -> JSONResponse:
    """Run ONE source for a natural-language ask: fan-out on the plan's query, then apply the
    plan's filters (time-window / sentiment / sort / top-N). UI calls these in parallel."""
    pl = P.rule_parse(q)
    # fetch wider than top_n when we're going to filter/sort/rank, so there's material to work with
    fetch = 50 if (pl.window_minutes or pl.sentiment or pl.anchor or pl.sort != "relevance") else max(pl.top_n, 15)
    # perspective → run the co-occurrence query set; otherwise the single query
    env = await S.run_multi(name, pl.queries or [pl.query], limit=min(fetch, 50))
    if env.get("items"):
        items, judged = await J.refine(pl, env["items"])
        env["items"] = items
        env["count"] = len(items)
        if pl.sentiment or pl.anchor:
            env["note"] = ((env.get("note") or "") + f" · judged by {judged}").strip(" ·")
    return JSONResponse(env)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")
