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

import products.scout.sources as S                        # noqa: E402

app = FastAPI(title="RIG Scout")
_STATIC = Path(__file__).parent / "static"


@app.get("/scout")
async def scout(keyword: str = Query(..., min_length=1, max_length=120),
                limit: int = Query(8, ge=1, le=25)) -> JSONResponse:
    sources = await S.scout(keyword, limit=limit)
    return JSONResponse({"keyword": keyword, "sources": sources})


@app.get("/scout/sources")
def scout_sources() -> JSONResponse:
    """The ordered source list, so the UI can paint skeleton panels immediately."""
    return JSONResponse({"sources": S.source_list()})


@app.get("/scout/one")
async def scout_one(name: str = Query(..., max_length=40),
                    keyword: str = Query(..., min_length=1, max_length=120),
                    limit: int = Query(8, ge=1, le=25)) -> JSONResponse:
    """Run ONE source — the UI calls these in parallel so each panel streams in on its own."""
    return JSONResponse(await S.run_one(name, keyword, limit=limit))


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")
