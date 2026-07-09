"""Domain / Infrastructure collector — the digital-footprint OSINT source.

Given a domain, returns: registration (RDAP), live DNS (DNS-over-HTTPS),
subdomains (Certificate Transparency — crt.sh, certSpotter fallback), and the
hosting ASN / provider (ip-api). Together this maps an entity's public attack
surface and reveals hidden assets (dev/staging/webmail/vpn hosts) + who hosts
them + whether they're CDN-fronted. Free, no auth, no key.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

_DOH = "https://dns.google/resolve"
_RDAP = "https://rdap.org/domain/"
_CRTSH = "https://crt.sh/"
_CERTSPOTTER = "https://api.certspotter.com/v1/issuances"
_IPAPI = "http://ip-api.com/json/"
_DNS_TYPES = ("A", "AAAA", "MX", "NS", "TXT")
# ASN-org fragments that indicate a CDN/proxy fronting the real origin
_CDN_ORGS = ("cloudflare", "akamai", "fastly", "cloudfront", "amazon", "google",
             "azure", "incapsula", "imperva", "sucuri", "stackpath", "bunny")


def _looks_like_domain(s: str) -> bool:
    s = (s or "").strip().lower()
    return "." in s and " " not in s and len(s) <= 253


async def _subdomains(client: httpx.AsyncClient, domain: str) -> list[str]:
    """Subdomains from Certificate Transparency: crt.sh primary (needs a longer
    timeout than RDAP/DoH), certSpotter fallback. Never raises."""
    names: set[str] = set()
    try:
        r = await client.get(_CRTSH, params={"q": "%." + domain, "output": "json"},
                             timeout=20)
        if r.status_code == 200 and r.text.strip().startswith("["):
            for row in r.json():
                for nm in (row.get("name_value") or "").split("\n"):
                    nm = nm.lower().strip()
                    if nm and "*" not in nm and nm.endswith(domain):
                        names.add(nm)
    except Exception:
        pass
    if not names:                       # fallback CT source
        try:
            r = await client.get(_CERTSPOTTER,
                                 params={"domain": domain, "include_subdomains": "true",
                                         "expand": "dns_names"}, timeout=15)
            if r.status_code == 200:
                for iss in r.json():
                    for nm in iss.get("dns_names", []) or []:
                        nm = nm.lower().strip()
                        if "*" not in nm and nm.endswith(domain):
                            names.add(nm)
        except Exception:
            pass
    names.discard(domain)
    names.discard("www." + domain)
    return sorted(names)


async def _asn(client: httpx.AsyncClient, ip: str) -> dict[str, Any] | None:
    """Hosting ASN / provider / reverse-DNS for an IP (ip-api, keyless)."""
    try:
        r = await client.get(_IPAPI + ip,
                             params={"fields": "as,org,isp,countryCode,reverse"},
                             timeout=8)
        if r.status_code == 200:
            j = r.json()
            return {"asn": j.get("as"), "org": j.get("org") or j.get("isp"),
                    "country": j.get("countryCode"), "reverse": j.get("reverse") or None}
    except Exception:
        pass
    return None


async def domain_infra(domain: str) -> dict[str, Any]:
    """Registration + DNS + subdomains + hosting profile for a domain. Partial on
    any single-source failure."""
    domain = (domain or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if not _looks_like_domain(domain):
        return {"domain": domain, "error": "not a valid domain (infra needs a domain, e.g. ril.com)"}

    out: dict[str, Any] = {"domain": domain, "rdap": None, "dns": {},
                           "subdomains": [], "hosting": None}
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

        # Subdomains (CT) + hosting ASN (of the first A record) — concurrent.
        a_ip = (out["dns"].get("A") or [None])[0]
        subs, hosting = await asyncio.gather(
            _subdomains(client, domain),
            _asn(client, a_ip) if a_ip else _noop(),
        )
        out["subdomains"] = subs
        out["hosting"] = hosting

    # Derived signals: mail + hosting fingerprint + surface size + age.
    mx = out["dns"].get("MX") or []
    org = (out.get("hosting") or {}).get("org") or ""
    out["summary"] = {
        "has_mail": bool(mx),
        "mail_provider": ("google" if any("google" in m.lower() for m in mx)
                          else "microsoft" if any("outlook" in m.lower() or "microsoft" in m.lower() for m in mx)
                          else "other" if mx else None),
        "nameserver_count": len(out.get("rdap", {}).get("nameservers", []) if out.get("rdap") else []),
        "hosting_provider": org or None,
        "behind_cdn": (any(c in org.lower() for c in _CDN_ORGS) if org else None),
        "subdomain_count": len(out.get("subdomains") or []),
        "domain_created": ((out.get("rdap") or {}).get("created") or "")[:10] or None,
    }
    return out


async def _noop() -> None:
    return None
