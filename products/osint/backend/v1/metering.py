"""Usage metering — a pure-ASGI middleware that records every /v1 request.

Why pure-ASGI (not BaseHTTPMiddleware): BaseHTTPMiddleware buffers the
response body, which would break the /v1/ask SSE stream. This wrapper only
observes the response-start message (status + headers) and never touches the
body, so streaming is unaffected.

The DB write is fire-and-forget (a detached task) wrapped so it can NEVER
fail or slow the client request. It also:
  * injects X-RateLimit-* headers (read from request.state), and
  * increments the monthly quota counter + the key's last_used_at.

Non-/v1 paths pass straight through, untouched.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs

from sqlalchemy import text
from starlette.types import ASGIApp, Receive, Scope, Send

from db import get_db

logger = logging.getLogger("osint-v1.metering")

# Hold references to detached tasks so the event loop doesn't GC them mid-flight.
_pending: set[asyncio.Task] = set()

# Never record more than this many query params, nor any value longer than this.
_MAX_PARAMS = 20
_MAX_VALUE_LEN = 200


class MeteringMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or not scope.get("path", "").startswith("/v1"):
            await self.app(scope, receive, send)
            return

        loop = asyncio.get_event_loop()
        start = loop.time()
        status_holder = {"code": 0}

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = int(message.get("status", 0))
                _inject_rate_headers(scope, message)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            latency_ms = int((loop.time() - start) * 1000)
            try:
                self._record(scope, status_holder["code"], latency_ms)
            except Exception:  # metering must never break the request
                logger.exception("metering record scheduling failed")

    def _record(self, scope: Scope, status: int, latency_ms: int) -> None:
        st = scope.get("state") or {}
        key_id = st.get("api_key_id")
        org_id = st.get("api_org_id")
        # Only meter authenticated requests — an unauthenticated 401 carries no
        # key/org and recording it would let anyone fill the table.
        if not key_id:
            return

        info = {
            "org_id": org_id,
            "key_id": key_id,
            "method": scope.get("method"),
            "endpoint": scope.get("path"),
            "status": status,
            "result_count": st.get("result_count"),
            "latency_ms": latency_ms,
            "ip": _client_ip(scope),
            "user_agent": _header(scope, b"user-agent"),
            "params": _safe_params(scope.get("query_string", b"")),
        }
        task = asyncio.ensure_future(_write_usage(info))
        _pending.add(task)
        task.add_done_callback(_pending.discard)


def _inject_rate_headers(scope: Scope, message: dict[str, Any]) -> None:
    st = scope.get("state") or {}
    lim = st.get("rl_limit")
    if lim is None:
        return
    headers = message.setdefault("headers", [])
    headers.append((b"x-ratelimit-limit", str(lim).encode()))
    rem = st.get("rl_remaining")
    if rem is not None:
        headers.append((b"x-ratelimit-remaining", str(max(0, int(rem))).encode()))
    reset = st.get("rl_reset")
    if reset is not None:
        headers.append((b"x-ratelimit-reset", str(int(reset)).encode()))


def _header(scope: Scope, name: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k == name:
            try:
                return v.decode("latin-1")[:_MAX_VALUE_LEN]
            except Exception:
                return None
    return None


def _client_ip(scope: Scope) -> str | None:
    # Honour a proxy header if present (Caddy sets X-Forwarded-For); else peer.
    fwd = _header(scope, b"x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    client = scope.get("client")
    if client:
        return str(client[0])
    return None


def _safe_params(query_string: bytes) -> dict[str, str]:
    """Parse + truncate query params for the usage log. No secrets live here
    (the key is a header), but cap size to keep the log bounded."""
    try:
        raw = parse_qs(query_string.decode("latin-1"), keep_blank_values=False)
    except Exception:
        return {}
    out: dict[str, str] = {}
    for k, vals in list(raw.items())[:_MAX_PARAMS]:
        if vals:
            out[k[:64]] = str(vals[0])[:_MAX_VALUE_LEN]
    return out


def _period_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _write_usage(info: dict[str, Any]) -> None:
    """Insert one usage row + bump the quota counter + last_used_at.

    Fully isolated: any failure is logged and swallowed so the served request
    is never affected.
    """
    try:
        async with get_db() as db:
            async with db.begin():
                await db.execute(text("""
                    INSERT INTO analytics.api_usage_events
                        (org_id, key_id, method, endpoint, status_code,
                         result_count, latency_ms, ip, user_agent, params)
                    VALUES
                        (CAST(:org AS uuid), CAST(:key AS uuid), :method, :endpoint,
                         :status, :result_count, :latency, CAST(:ip AS inet),
                         :ua, CAST(:params AS jsonb))
                """), {
                    "org": info["org_id"],
                    "key": info["key_id"],
                    "method": info["method"],
                    "endpoint": info["endpoint"],
                    "status": info["status"],
                    "result_count": info["result_count"],
                    "latency": info["latency_ms"],
                    "ip": info["ip"],
                    "ua": info["user_agent"],
                    "params": _json(info["params"]),
                })
                await db.execute(text("""
                    INSERT INTO analytics.api_usage_counters (key_id, period, request_count)
                    VALUES (CAST(:key AS uuid), :period, 1)
                    ON CONFLICT (key_id, period)
                    DO UPDATE SET request_count = analytics.api_usage_counters.request_count + 1
                """), {"key": info["key_id"], "period": _period_now()})
                await db.execute(text("""
                    UPDATE analytics.api_keys SET last_used_at = now()
                     WHERE id = CAST(:key AS uuid)
                """), {"key": info["key_id"]})
    except Exception:
        logger.exception("usage write failed (swallowed)")


def _json(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj)
    except Exception:
        return "{}"
