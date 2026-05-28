"""Replay clock CLI for the OSINT brief.

Drives the analytics.replay_clock table created by migration 077. Lets you
move the simulated clock forward so the brief endpoints (which read via
analytics.now_sim() and analytics.now_sim_date()) see articles arriving at
their natural cadence against a frozen DB.

Usage (from products/osint/backend/ with venv activated):

    python ../../scripts/replay.py status
    python ../../scripts/replay.py reset 2026-05-27T06:00:00Z
    python ../../scripts/replay.py tick 15
    python ../../scripts/replay.py clear

Connects via OSINT_DB_URL (the same env var osint-backend uses).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Load .env from the osint-backend dir (next to ./products/osint/backend/.env)
BACKEND_ENV = Path(__file__).parent.parent / "products" / "osint" / "backend" / ".env"
if BACKEND_ENV.exists():
    load_dotenv(BACKEND_ENV)


async def _conn():
    db_url = os.environ.get("OSINT_DB_URL")
    if not db_url:
        sys.exit("OSINT_DB_URL not set (load .env or export it)")
    engine = create_async_engine(db_url)
    return engine


async def cmd_status() -> None:
    engine = await _conn()
    async with engine.connect() as c:
        row = (await c.execute(text(
            "SELECT sim_now, note, updated_at, NOW() AS real_now, analytics.now_sim() AS effective "
            "FROM analytics.replay_clock WHERE id = 1"
        ))).fetchone()
    if row is None:
        print("(replay_clock empty)")
        return
    print(f"  sim_now    : {row.sim_now}")
    print(f"  real_now   : {row.real_now}")
    print(f"  effective  : {row.effective}")
    print(f"  note       : {row.note}")
    print(f"  updated_at : {row.updated_at}")
    if row.sim_now is None:
        print("  → REPLAY OFF (analytics.now_sim() returns real NOW())")
    else:
        delta_sec = (row.real_now - row.sim_now).total_seconds()
        print(f"  → REPLAY ON  (offset = {delta_sec / 3600:.1f}h behind real time)")
    await engine.dispose()


async def cmd_reset(target: str) -> None:
    engine = await _conn()
    async with engine.begin() as c:
        new_sim = (await c.execute(
            text("SELECT analytics.reset_clock(CAST(:t AS TIMESTAMPTZ))"),
            {"t": target},
        )).scalar_one()
    print(f"sim_now = {new_sim}")
    await engine.dispose()


async def cmd_tick(minutes: int) -> None:
    engine = await _conn()
    async with engine.begin() as c:
        new_sim = (await c.execute(
            text("SELECT analytics.tick(:m)"),
            {"m": int(minutes)},
        )).scalar_one()
    print(f"sim_now = {new_sim}")
    await engine.dispose()


async def cmd_clear() -> None:
    engine = await _conn()
    async with engine.begin() as c:
        await c.execute(text("SELECT analytics.clear_clock()"))
    print("sim_now cleared — analytics.now_sim() now returns real NOW()")
    await engine.dispose()


def main() -> None:
    p = argparse.ArgumentParser(description="Replay clock CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Show current sim_now and effective time")
    p_reset = sub.add_parser("reset", help="Set sim_now to ISO timestamp")
    p_reset.add_argument("target", help='ISO8601, e.g. "2026-05-27T06:00:00Z"')
    p_tick = sub.add_parser("tick", help="Advance sim_now by N minutes")
    p_tick.add_argument("minutes", type=int)
    sub.add_parser("clear", help="Clear sim_now (back to real NOW())")
    args = p.parse_args()

    if args.cmd == "status":
        asyncio.run(cmd_status())
    elif args.cmd == "reset":
        asyncio.run(cmd_reset(args.target))
    elif args.cmd == "tick":
        asyncio.run(cmd_tick(args.minutes))
    elif args.cmd == "clear":
        asyncio.run(cmd_clear())


if __name__ == "__main__":
    main()
