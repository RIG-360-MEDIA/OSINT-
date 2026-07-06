"""Domain / Infrastructure collector — the first non-social OSINT source.

Given a domain, returns registration (RDAP) + live DNS records via DNS-over-HTTPS.
Fast and reliable (crt.sh timed out from the box; RDAP + DoH respond in <1s), free,
no auth. This is the Tasking-brain 'infra' source made live for org/domain keywords.
"""
from __future__ import annotations

from typing import Any

import httpx

_DOH = "https://dns.google/resolve"
_RDAP = "https://rdap.org/domain/"
_DNS_TYPES = ("A", "AAAA", "MX", "NS", "TXT")


def _looks_like_domain(s: str) -> bool:
    s = (s or "").strip().lower()
    return "." in s and " " not in s and len(s) <= 253


async def domain_infra(domain: str) -> dict[str, Any]:
    """Registration + DNS profile for a domain. Returns partial data on any failure."""
    domain = (domain or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if not _looks_like_domain(domain):
        return {"domain": domain, "error": "not a valid domain (infra needs a domain, e.g. ril.com)"}

    out: dict[str, Any] = {"domain": domain, "rdap": None, "dns": {}}
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        # Registration data (RDAP).
        try:
            r = await client.get(_RDAP + domain)
            if r.status_code == 200:
                d = r.json()
                ev = {e.get("eventAction"): e.get("eventDate") for e in d.get("events", [])}
                registrar = None
                for ent in d.get("entities", []) or []:
                    if "registrar" in (ent.get("roles") or []):
                        for item in (ent.get("vcardArray", [None, []])[1] or []):
                            if item and item[0] == "fn":
                                registrar = item[3]
                out["rdap"] = {
                    "registrar": registrar,
                    "created": ev.get("registration"),
                    "expires": ev.get("expiration"),
                    "last_changed": ev.get("last changed"),
                    "status": d.get("status"),
                    "nameservers": [ns.get("ldhName") for ns in d.get("nameservers", []) or []],
                }
            else:
                out["rdap_status"] = r.status_code
        except Exception as exc:
            out["rdap_error"] = type(exc).__name__

        # Live DNS records (DNS-over-HTTPS).
        for rtype in _DNS_TYPES:
            try:
                rr = await client.get(_DOH, params={"name": domain, "type": rtype}, timeout=8)
                out["dns"][rtype] = [a.get("data") for a in (rr.json().get("Answer") or [])] if rr.status_code == 200 else []
            except Exception:
                out["dns"][rtype] = []

    # a small derived signal: mail + hosting fingerprint
    mx = out["dns"].get("MX") or []
    out["summary"] = {
        "has_mail": bool(mx),
        "mail_provider": ("google" if any("google" in m.lower() for m in mx)
                          else "microsoft" if any("outlook" in m.lower() or "microsoft" in m.lower() for m in mx)
                          else "other" if mx else None),
        "nameserver_count": len(out.get("rdap", {}).get("nameservers", []) if out.get("rdap") else []),
    }
    return out
