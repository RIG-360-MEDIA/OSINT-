"""Idempotently wire the YouTube cookie jar into rig-backend.

Adds, mirroring the existing YOUTUBE_PROXY_URL pattern:
  - env:    YOUTUBE_COOKIES_PATH: ${YOUTUBE_COOKIES_PATH:-}
  - volume: ../secrets/youtube_cookies.txt:/app/secrets/youtube_cookies.txt:ro

Anchors:
  env line   -> inserted right after the line containing 'YOUTUBE_PROXY_URL:'
  volume line-> inserted right after the line containing 'rig-beat-schedule:/app/beat'
Indentation is copied from each anchor line so YAML stays valid.

Run: python3 patch_cookie_mount.py /root/rig/infrastructure/docker-compose.yml
"""
from __future__ import annotations

import sys
from pathlib import Path

ENV_ANCHOR = "YOUTUBE_PROXY_URL:"
ENV_NEW = "YOUTUBE_COOKIES_PATH: ${YOUTUBE_COOKIES_PATH:-}"
VOL_ANCHOR = "rig-beat-schedule:/app/beat"
VOL_NEW = "- ../secrets/youtube_cookies.txt:/app/secrets/youtube_cookies.txt:ro"


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def patch(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    if "YOUTUBE_COOKIES_PATH" in text:
        print("ABORT: YOUTUBE_COOKIES_PATH already present — no change.")
        return 1

    backup = path.with_suffix(path.suffix + ".bak-cookie")
    backup.write_text(text, encoding="utf-8")
    print(f"backup written: {backup}")

    out: list[str] = []
    did_env = did_vol = False
    for line in text.splitlines(keepends=True):
        out.append(line)
        if ENV_ANCHOR in line and not did_env:
            out.append(f"{_indent(line)}{ENV_NEW}\n")
            did_env = True
        elif VOL_ANCHOR in line and not did_vol:
            out.append(f"{_indent(line)}{VOL_NEW}\n")
            did_vol = True

    if not (did_env and did_vol):
        print(f"FAIL: anchors not found (env={did_env} vol={did_vol}) — no write.")
        return 2

    path.write_text("".join(out), encoding="utf-8")
    print("OK: added YOUTUBE_COOKIES_PATH env + read-only cookie volume.")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "docker-compose.yml")
    raise SystemExit(patch(target))
