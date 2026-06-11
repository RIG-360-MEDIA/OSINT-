"""RIG OSINT MCP server — exposes our intelligence as agent tools.

Thin transport over `agents.MCP_TOOLS`. Run as a SEPARATE process (stdio), not
inside the FastAPI app:  `python mcp_server.py`. Requires `fastmcp` (guarded so
the API image never breaks if it's absent). Each tool resolves the caller's prefs
by user_id and returns the same grounded payloads the HTTP API serves.
"""
from __future__ import annotations

import asyncio
from typing import Any

from agents import MCP_TOOLS
from brief_prefs import load_prefs
from db import get_db


async def _run(fn, user_id: str, **kwargs) -> Any:
    async with get_db() as db:
        prefs = await load_prefs(db, user_id)
        if not prefs:
            return {"error": "unknown user"}
        return await fn(db, prefs, **kwargs)


def build_server():  # pragma: no cover - transport wiring
    try:
        from fastmcp import FastMCP
    except ImportError as e:
        raise SystemExit("fastmcp not installed — `pip install fastmcp` to run the MCP transport") from e

    mcp = FastMCP("rig-osint")

    @mcp.tool()
    async def rig_posture_snapshot(user_id: str) -> dict:
        """Posture snapshot (pressure, hostility, opposition heat) for the user's principal."""
        return await _run(MCP_TOOLS["rig_posture_snapshot"][1], user_id)

    @mcp.tool()
    async def rig_smart_filter(user_id: str, limit: int = 10) -> dict:
        """Ranked, de-noised top stories for the user (overload-killer)."""
        return await _run(MCP_TOOLS["rig_smart_filter"][1], user_id, limit=limit)

    @mcp.tool()
    async def rig_coverage_qa(user_id: str, question: str) -> dict:
        """Answer a natural-language question about the principal's coverage, grounded in data."""
        return await _run(MCP_TOOLS["rig_coverage_qa"][1], user_id, question=question)

    return mcp


if __name__ == "__main__":  # pragma: no cover
    build_server().run()
