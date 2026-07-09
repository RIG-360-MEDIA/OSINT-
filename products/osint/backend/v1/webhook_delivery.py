"""Webhook delivery worker — push new matching coverage to subscribers, HMAC-signed.

Run as ``python -m v1.webhook_delivery`` inside osint-backend (it has the DB, the
key-hash secret, and the keys module). A cron fires it every couple of minutes.

Per active webhook: find new items (org scope + the subscription filter, collected
after the last-delivered watermark), sign the JSON body with the webhook's derived
secret, POST with retry/backoff, log every attempt to api_webhook_deliveries, and
advance last_delivered_at. Delivery is ordered + at-least-once: on a failure we stop
and retry from the same point next run (watermark never skips an undelivered item).
A webhook that fails _DISABLE_AFTER runs in a row is deactivated (dead-letter).
SSRF-guarded: https only, and the host must resolve to public IPs.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import socket
import urllib.parse
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from db import get_db

from . import keys as keymod
from .settings import hash_secret

_BATCH = 20            # max items delivered per webhook per run
_TIMEOUT = 8.0
_MAX_ATTEMPTS = 3
_DISABLE_AFTER = 15    # consecutive failed runs -> deactivate the webhook
# tests only — HARD-disabled in production regardless of the env var, so setting it
# in prod can never bypass the SSRF guard / TLS verification (fail-closed like hash_secret).
_ALLOW_INSECURE = (os.getenv("WEBHOOK_ALLOW_INSECURE") == "1"
                   and os.getenv("OSINT_ENVIRONMENT", "production").lower() != "production")

_STANCE_SETS = {
    "supportive": ("supportive", "positive"),
    "critical": ("critical", "negative"),
    "neutral": ("neutral",),
}


def _ssrf_ok(url: str) -> bool:
    """True only for an https URL whose host resolves entirely to public IPs."""
    try:
        u = urllib.parse.urlparse(url)
        host = u.hostname
        if not host:
            return False
        if _ALLOW_INSECURE and host in ("127.0.0.1", "localhost"):
            return True
        if u.scheme != "https":
            return False
        infos = socket.getaddrinfo(host, u.port or 443, proto=socket.IPPROTO_TCP)
        for *_, sockaddr in infos:
            ip = ipaddress.ip_address(sockaddr[0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
        return bool(infos)
    except Exception:
        return False


async def _matching_items(db, *, all_entities, entity_ids, flt, watermark, limit):
    clauses = ["a.collected_at > :wm", "NOT COALESCE(a.is_duplicate,false)",
               "a.substrate_status='ok'", "a.title IS NOT NULL"]
    params: dict = {"wm": watermark, "lim": limit}
    if not all_entities:
        if not entity_ids:
            return []
        clauses.append("EXISTS (SELECT 1 FROM article_entity_mentions aem "
                       "WHERE aem.article_id=a.id AND aem.entity_id=ANY(CAST(:eids AS uuid[])))")
        params["eids"] = entity_ids
    fe = flt.get("entity")
    if fe:
        clauses.append("EXISTS (SELECT 1 FROM article_entity_mentions aem2 "
                       "WHERE aem2.article_id=a.id AND aem2.entity_id=CAST(:fe AS uuid))")
        params["fe"] = fe
    ft = flt.get("topic")
    if ft:
        clauses.append("a.topic_category = :ft")
        params["ft"] = ft
    fs = _STANCE_SETS.get((flt.get("sentiment") or "").lower())
    if fs:
        clauses.append("EXISTS (SELECT 1 FROM article_stances st "
                       "WHERE st.article_id=a.id AND lower(st.stance)=ANY(:fs))")
        params["fs"] = list(fs)
    where = " AND ".join(clauses)
    rows = (await db.execute(text(f"""
        SELECT a.id::text id, a.title headline, s.name source, a.url,
               a.topic_category topic, a.collected_at, a.published_at
          FROM articles a JOIN sources s ON s.id=a.source_id
         WHERE {where} ORDER BY a.collected_at ASC LIMIT :lim
    """), params)).fetchall()
    return [dict(r._mapping) for r in rows]


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def _deliver(client, url, secret, item) -> int:
    body = json.dumps({
        "event": "coverage.matched",
        "article": {
            "id": item["id"], "headline": item["headline"], "source": item["source"],
            "url": item["url"], "topic": item["topic"],
            "published_at": item["published_at"].isoformat() if item["published_at"] else None,
        },
    }, separators=(",", ":")).encode("utf-8")
    resp = await client.post(url, content=body, timeout=_TIMEOUT, headers={
        "Content-Type": "application/json",
        "X-RIG-Event": "coverage.matched",
        "X-RIG-Signature": _sign(secret, body),
    })
    return resp.status_code


async def _log(wid, item_id, status, code, attempts, error):
    async with get_db() as db:
        await db.execute(text("""
            INSERT INTO analytics.api_webhook_deliveries
                (webhook_id, event, item_id, status, response_code, attempts, error)
            VALUES (CAST(:id AS uuid),'coverage.matched', CAST(:it AS uuid), :st,:rc,:at,:er)
        """), {"id": wid, "it": item_id, "st": status, "rc": code, "at": attempts, "er": error})
        await db.commit()


async def run_once() -> int:
    root = hash_secret()
    async with get_db() as db:
        hooks = (await db.execute(text("""
            SELECT w.id::text id, w.url, w.filter, w.last_delivered_at,
                   COALESCE(w.failure_count,0) failure_count,
                   COALESCE(s.all_entities,false) all_entities, s.entity_ids
              FROM analytics.api_webhooks w
              LEFT JOIN analytics.org_api_scope s ON s.org_id = w.org_id
             WHERE w.is_active
        """))).fetchall()

    delivered = 0
    async with httpx.AsyncClient(follow_redirects=False, verify=not _ALLOW_INSECURE) as client:
        for h in hooks:
            wid, url = h.id, h.url
            flt = h.filter or {}
            wm = h.last_delivered_at or datetime(2000, 1, 1, tzinfo=timezone.utc)
            eids = [str(x) for x in (h.entity_ids or [])]

            if not _ssrf_ok(url):
                async with get_db() as db:
                    await db.execute(text("UPDATE analytics.api_webhooks SET is_active=false WHERE id=CAST(:id AS uuid)"), {"id": wid})
                    await db.commit()
                await _log(wid, None, "failed", None, 0, "ssrf_blocked")
                continue

            async with get_db() as db:
                items = await _matching_items(db, all_entities=h.all_entities, entity_ids=eids,
                                              flt=flt, watermark=wm, limit=_BATCH)

            secret = keymod.derive_webhook_secret(wid, root)
            newest_wm, fails = wm, h.failure_count
            for item in items:
                code = err = None
                ok_ = False
                attempt = 0
                for attempt in range(1, _MAX_ATTEMPTS + 1):
                    try:
                        code = await _deliver(client, url, secret, item)
                        if 200 <= code < 300:
                            ok_ = True
                            break
                        err = f"http_{code}"
                    except Exception as e:  # noqa: BLE001
                        err = type(e).__name__
                    await asyncio.sleep(0.4 * attempt)
                await _log(wid, item["id"], "delivered" if ok_ else "failed", code, attempt, None if ok_ else err)
                if ok_:
                    newest_wm, fails = item["collected_at"], 0
                    delivered += 1
                else:
                    fails += 1
                    break  # ordered at-least-once: retry from here next run

            async with get_db() as db:
                deactivate = fails >= _DISABLE_AFTER
                await db.execute(text("""
                    UPDATE analytics.api_webhooks
                       SET failure_count=:f, last_delivered_at=:wm,
                           is_active = CASE WHEN :deact THEN false ELSE is_active END
                     WHERE id=CAST(:id AS uuid)
                """), {"f": fails, "wm": newest_wm, "deact": deactivate, "id": wid})
                await db.commit()
    return delivered


if __name__ == "__main__":
    print("delivered=", asyncio.run(run_once()))
