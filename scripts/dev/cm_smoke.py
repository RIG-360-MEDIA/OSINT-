"""Authed smoke test for /api/cm/* endpoints.

Mints a local Supabase-shaped JWT (auth_middleware decodes payload without
signature verification — see backend/auth/auth_middleware.py) and hits
every CM endpoint, printing status + first 200 chars of body.

Usage:
    docker exec rig-backend python scripts/dev/cm_smoke.py
or, from host:
    python scripts/dev/cm_smoke.py http://localhost:8000
"""
from __future__ import annotations

import base64
import json
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def _b64url(d: bytes) -> str:
    return base64.urlsafe_b64encode(d).rstrip(b"=").decode()


def make_token(user_id: str = "00000000-0000-0000-0000-000000000001") -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "email": "smoke@cm-page.local",
        "exp": int(time.time()) + 3600,
        "aud": "authenticated",
    }
    return ".".join(
        [
            _b64url(json.dumps(header).encode()),
            _b64url(json.dumps(payload).encode()),
            _b64url(b"signature-not-verified"),
        ]
    )


ENDPOINTS = [
    "/api/cm/dashboard",
    "/api/cm/pulse",
    "/api/cm/issues",
    "/api/cm/silence",
    "/api/cm/spokespersons",
    "/api/cm/cabinet-onmessage",
    "/api/cm/dissent",
    "/api/cm/trajectory",
    "/api/cm/heatmap",
    "/api/cm/promises",
    "/api/cm/counter-narratives",
    "/api/cm/risk-window",
    "/api/cm/quotes",
    "/api/cm/voice-share",
    "/api/cm/divergence/language",
    "/api/cm/divergence/medium",
]


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    state = sys.argv[2] if len(sys.argv) > 2 else "TG"
    token = make_token()
    headers = {"Authorization": f"Bearer {token}"}
    qs = urlencode({"state": state})

    failures = 0
    for path in ENDPOINTS:
        url = f"{base}{path}?{qs}"
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=20) as resp:
                body = resp.read().decode()
                head = body[:160].replace("\n", " ")
                print(f"  200  {path:38s}  {head}")
        except HTTPError as exc:
            failures += 1
            try:
                err_body = exc.read().decode()[:200]
            except Exception:
                err_body = ""
            print(f"  {exc.code}  {path:38s}  {err_body}")
        except URLError as exc:
            failures += 1
            print(f"  ERR  {path:38s}  {exc.reason}")

    if failures:
        print(f"\n{failures} endpoints failed")
        return 1
    print(f"\nall {len(ENDPOINTS)} endpoints returned 200")
    return 0


if __name__ == "__main__":
    sys.exit(main())
