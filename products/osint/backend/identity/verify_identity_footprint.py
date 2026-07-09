"""verify_identity_footprint.py — Phase-1 identity-footprint POC (isolated; osint-backend).

Given ONE selector (username / email / phone), map the PUBLIC account footprint tied to
it. Public account traces only — NOTHING that de-anonymises a private individual.

  IN SCOPE (this file only does these):
    username -> cross-platform PUBLIC accounts (maigret), filtered + confidence-scored
    email    -> public registration traces (holehe) + breach-boolean HOOK (disabled: free-only)
    phone    -> validation / region / carrier / line-type (phonenumbers, offline)

  OFF-LIMITS (deliberately NOT built, never call): data-broker people-search (address/
  relatives/PII), breach DATA dumps, face search, dark-web crawling.

Hard rules honoured: results are LEADS with per-hit confidence, never assertions; a
"found account" is a real reachable profile (maigret's content check + our own filter drop
search/aggregate false positives); and the classic trap is surfaced loudly —
**same username != same person across platforms**. Free / no-paid. Does NOT touch rig-backend.

Run (box venv has the tools):
    MAIGRET_BIN=/root/idvenv/bin/maigret HOLEHE_BIN=/root/idvenv/bin/holehe \
        /root/idvenv/bin/python verify_identity_footprint.py <selector> [--top-sites N]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import tempfile
from urllib.parse import urlparse

MAIGRET_BIN = os.environ.get("MAIGRET_BIN", "maigret")
HOLEHE_BIN = os.environ.get("HOLEHE_BIN", "holehe")

SAME_USERNAME_CAVEAT = (
    "Same username != same person. These accounts merely share a handle; a handle can be "
    "held by different people (or squatters) on different platforms. Confidence below scores "
    "ACCOUNT REACHABILITY, not identity — corroborate (matching name/avatar/bio, cross-links) "
    "before attributing any account to a specific person."
)
NOT_A_VERDICT = "Signals / leads for a human analyst — not a verdict, and not an identity ruling."

# maigret 'claimed' hits whose URL is a search/aggregate page, not a real profile = false positives.
_FALSE_POSITIVE_MARKERS = (
    "?q=", "&q=", "search=", "/search", "/filter", "btng", "scholar.google",
    "/groups/", "/usr/", "query=", "/tag/", "/tags/", "/hashtag/",
)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().-]{5,}$")


def detect_selector(s: str) -> str:
    s = s.strip()
    if _EMAIL_RE.match(s):
        return "email"
    if _PHONE_RE.match(s) and sum(c.isdigit() for c in s) >= 7:
        return "phone"
    return "username"


def _run(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"tool not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"


# ---------------------------------------------------------------- username

def _score_hit(username: str, url: str, ids: dict | None) -> tuple[str, str]:
    """Confidence for a maigret 'claimed' hit. rejected = false positive, drop it."""
    u = (url or "").lower()
    un = username.lower()
    if not u:
        return "rejected", "no profile URL"
    if any(m in u for m in _FALSE_POSITIVE_MARKERS):
        return "rejected", "search/aggregate URL, not a profile"
    parsed = urlparse(u)
    in_path = un in parsed.path.lower().replace("@", "")
    in_query = un in (parsed.query or "").lower()
    if not (in_path or in_query):
        return "rejected", "handle absent from profile URL (generic/landing page)"
    if ids:  # maigret parsed real profile content (name, id, links) -> strongest
        return "high", "profile content parsed (name/id extracted)"
    return "medium", "handle-in-path profile URL (reachable, content not parsed)"


def username_footprint(username: str, top_sites: int = 300, timeout: int = 200) -> dict:
    out: dict = {"tool": "maigret", "top_sites": top_sites}
    with tempfile.TemporaryDirectory(prefix="idf_") as fo:
        rc, _so, se = _run(
            [MAIGRET_BIN, username, "--timeout", "12", "--top-sites", str(top_sites),
             "-n", "40", "--no-progressbar", "--no-color", "-J", "simple", "-fo", fo],
            timeout,
        )
        reports = glob.glob(os.path.join(fo, "*.json"))
        main = next((f for f in reports if username.lower() in os.path.basename(f).lower()), None)
        if not main:
            return {**out, "error": se.strip()[:160] or f"no report (rc={rc})",
                    "confirmed": [], "rejected": [], "checked": 0}
        data = json.load(open(main, encoding="utf-8"))
        confirmed, rejected = [], []
        for site, v in data.items():
            if not isinstance(v, dict):
                continue
            status = (v.get("status") or {})
            if str(status.get("status", "")).lower() != "claimed":
                continue
            url = v.get("url_user") or ""
            ids = status.get("ids") or {}
            conf, reason = _score_hit(username, url, ids)
            rec = {"site": site, "url": url, "confidence": conf}
            if conf == "rejected":
                rejected.append({**rec, "reason": reason})
            else:
                if ids:
                    rec["extracted"] = {k: str(ids[k])[:80] for k in list(ids)[:6]}
                confirmed.append(rec)
        # maigret's recursive discovery drops extra report files = LINKED handles (leads only).
        related = sorted({
            os.path.basename(f).replace("report_", "").replace("_simple.json", "")
            for f in reports if f != main
        })
    confirmed.sort(key=lambda r: 0 if r["confidence"] == "high" else 1)
    return {**out, "checked": len(data), "confirmed_count": len(confirmed),
            "confirmed": confirmed, "rejected_count": len(rejected), "rejected": rejected,
            "related_handles": related,
            "related_note": "linked handles maigret surfaced — LEADS to corroborate, not confirmed same person"}


# ---------------------------------------------------------------- email

def _breach_boolean(email: str) -> dict:
    """HOOK — disabled this phase (HIBP has no free tier; ~$53/yr). Never returns leaked data."""
    if os.environ.get("HIBP_API_KEY"):
        return {"checked": False, "note": "HIBP key present but breach lookup not wired in Phase 1"}
    return {"checked": False,
            "note": "breach-boolean disabled (free-only). To enable: set HIBP_API_KEY (paid) — "
                    "returns only WHETHER the email was in a breach, never the leaked data."}


def email_footprint(email: str, timeout: int = 150) -> dict:
    out: dict = {"tool": "holehe", "breach": _breach_boolean(email)}
    rc, so, se = _run([HOLEHE_BIN, email, "--only-used", "--no-color"], timeout)
    if rc in (127, 124):
        return {**out, "error": se.strip()[:160], "registered_sites": []}
    sites = sorted({m.group(1) for m in re.finditer(r"^\[\+\]\s+(\S+)", so, re.M)})
    return {**out, "registered_sites": sites, "count": len(sites),
            "confidence": "medium",
            "caveat": "registration tells only (public signup presence). Widely-used / throwaway "
                      "addresses light up everywhere — treat hits as leads, verify before relying. "
                      "holehe is unmaintained (module rot possible); absence != not-registered."}


# ---------------------------------------------------------------- phone

def phone_footprint(phone: str, region: str | None = None) -> dict:
    try:
        import phonenumbers
        from phonenumbers import PhoneNumberType, carrier, geocoder, number_type
    except ImportError:
        return {"tool": "phonenumbers", "error": "phonenumbers not installed"}
    try:
        n = phonenumbers.parse(phone, region)
    except phonenumbers.NumberParseException as exc:
        return {"tool": "phonenumbers", "valid": False,
                "error": f"{exc}"[:100] + " (give E.164, e.g. +<country><number>)"}
    types = {PhoneNumberType.MOBILE: "mobile", PhoneNumberType.FIXED_LINE: "fixed_line",
             PhoneNumberType.VOIP: "voip", PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_or_mobile",
             PhoneNumberType.TOLL_FREE: "toll_free", PhoneNumberType.PREMIUM_RATE: "premium_rate"}
    return {
        "tool": "phonenumbers",
        "valid": phonenumbers.is_valid_number(n),
        "possible": phonenumbers.is_possible_number(n),
        "e164": phonenumbers.format_number(n, phonenumbers.PhoneNumberFormat.E164),
        "region": geocoder.description_for_number(n, "en") or None,
        "carrier": carrier.name_for_number(n, "en") or None,
        "line_type": types.get(number_type(n), "unknown"),
        "note": "carrier = ORIGINAL network (stale after porting); VoIP/burner detection is "
                "limited to what the numbering plan flags. Owner is NOT identified (out of scope).",
    }


# ---------------------------------------------------------------- dispatch

def footprint(selector: str, top_sites: int = 300, region: str | None = None) -> dict:
    kind = detect_selector(selector)
    out: dict = {"selector": selector, "type": kind, "note": NOT_A_VERDICT}
    if kind == "username":
        out["result"] = username_footprint(selector, top_sites=top_sites)
        out["caveat"] = SAME_USERNAME_CAVEAT
    elif kind == "email":
        out["result"] = email_footprint(selector)
        out["caveat"] = SAME_USERNAME_CAVEAT
    else:
        out["result"] = phone_footprint(selector, region=region)
    return out


def _main() -> None:
    ap = argparse.ArgumentParser(description="Map the PUBLIC account footprint of a selector.")
    ap.add_argument("selector", help="username, email, or phone (E.164 e.g. +14155552671)")
    ap.add_argument("--top-sites", type=int, default=300, help="maigret site count (username)")
    ap.add_argument("--region", default=None, help="default region for a national phone number")
    a = ap.parse_args()
    print(json.dumps(footprint(a.selector, top_sites=a.top_sites, region=a.region),
                     indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    _main()
