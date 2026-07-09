"""verify_image.py — Phase-1 image-verification POC (isolated; osint-backend).

Given an image (URL or file), gather VERIFICATION SIGNALS — never a verdict:
  1. Reverse search — where else it appears (Yandex, free, best-effort from a
     datacenter IP) + a strong heuristic: if it surfaces FACT-CHECK domains
     (Snopes/AltNews/BOOM/AFP...), it's very likely a known debunked/recycled image.
  2. EXIF/metadata — exiftool (fallback Pillow). Social uploads strip EXIF, so
     absence is INCONCLUSIVE, not suspicious.
  3. dHash — a perceptual fingerprint for near-duplicate matching (own corpus).

Honest ceiling: strong on where-it-appeared + EXIF; there is NO definitive
free deepfake verdict. Everything here is a confidence-scored LEAD for a human.
Free / no-paid. Does NOT touch rig-backend.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any

_UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124 Safari/537.36")}

# Reverse-search hitting any of these = the image is a known fact-checked claim.
_FACTCHECK = (
    "snopes.com", "altnews.in", "boomlive.in", "factcheck.org", "politifact.com",
    "fullfact.org", "leadstories.com", "factly.in", "vishvasnews.com",
    "factcheck.afp.com", "afp.com", "reuters.com/fact-check", "apnews.com",
    "thequint.com/news/webqoof", "logicallyfacts.com", "dfrac.org", "newschecker.in",
)
_SKIP_DOMAINS = ("yandex", "yastatic", "gstatic", "googletag", "w3.org", "mc.yandex")


def _get(url: str, timeout: int = 25, binary: bool = False) -> Any:
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout) as r:
        return r.read() if binary else r.read().decode("utf-8", "replace")


def reverse_yandex(image_url: str) -> dict[str, Any]:
    """Where the image appears, via Yandex reverse image (free, best-effort)."""
    u = "https://yandex.com/images/search?rpt=imageview&url=" + urllib.parse.quote(image_url, safe="")
    try:
        html = _get(u)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:90]}
    if re.search(r"smartcaptcha|showcaptcha|are you a robot", html, re.I):
        return {"ok": False, "error": "Yandex CAPTCHA (datacenter IP) — retry later / paid fallback"}
    domains: Counter[str] = Counter()
    for host in re.findall(r"https?://([a-z0-9.-]+\.[a-z]{2,})/", html, re.I):
        h = host.lower()
        if any(s in h for s in _SKIP_DOMAINS):
            continue
        domains[h] += 1
    fc = sorted({d for d in domains for f in _FACTCHECK if f.split("/")[0] in d})
    return {
        "ok": True,
        "distinct_domains": len(domains),
        "top_sources": [{"domain": d, "hits": n} for d, n in domains.most_common(12)],
        "factcheck_hits": fc,
        "appears_widely": len(domains) >= 8,
    }


def exif(path: str) -> dict[str, Any]:
    """Capture metadata — exiftool (complete) then Pillow fallback."""
    try:
        out = subprocess.run(["exiftool", "-json", "-G", path],
                             capture_output=True, text=True, timeout=20)
        if out.returncode == 0 and out.stdout.strip().startswith("["):
            d = json.loads(out.stdout)[0]
            keep = {k: v for k, v in d.items() if any(t in k for t in (
                "DateTimeOriginal", "CreateDate", "ModifyDate", "GPS", "Make",
                "Model", "Software", "LensModel"))}
            return {"tool": "exiftool", "fields": keep or None}
    except Exception:
        pass
    try:
        from PIL import ExifTags, Image
        ex = Image.open(path)._getexif() or {}
        named = {ExifTags.TAGS.get(k, k): v for k, v in ex.items()}
        keep = {k: str(v)[:70] for k, v in named.items() if k in (
            "DateTimeOriginal", "DateTime", "Make", "Model", "Software", "GPSInfo")}
        return {"tool": "Pillow", "fields": keep or None}
    except Exception as exc:
        return {"tool": "Pillow", "fields": None, "error": type(exc).__name__}


def dhash(path: str) -> str:
    """64-bit difference-hash — perceptual fingerprint for near-dupe matching."""
    from PIL import Image
    import numpy as np
    a = np.asarray(Image.open(path).convert("L").resize((9, 8)), dtype="int16")
    return "".join("1" if b else "0" for b in (a[:, 1:] > a[:, :-1]).flatten())


def verify(image: str, claimed_date: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"input": image, "claimed_date": claimed_date}
    local, url = image, None
    if image.startswith("http"):
        url = image
        local = "/tmp/_verify_img"
        data = _get(image, binary=True)
        open(local, "wb").write(data)
        out["bytes"] = len(data)

    from PIL import Image
    im = Image.open(local)
    out["dimensions"] = f"{im.width}x{im.height}"
    out["format"] = im.format
    out["dhash"] = dhash(local)
    out["exif"] = exif(local)
    if url:
        out["reverse"] = reverse_yandex(url)

    # honest, signal-not-proof synthesis
    rev = out.get("reverse") or {}
    signals: list[str] = []
    if rev.get("factcheck_hits"):
        signals.append("RED FLAG — appears on fact-check sites (" +
                       ", ".join(rev["factcheck_hits"]) +
                       ") → almost certainly a KNOWN debunked / recycled image")
    if rev.get("appears_widely"):
        signals.append(f"appears across {rev['distinct_domains']} distinct sites → widely "
                       "circulated (consistent with an old / recycled image, not an exclusive)")
    elif rev.get("ok") and rev.get("distinct_domains", 0) <= 2:
        signals.append("few/no earlier appearances found → consistent with an original / fresh image")
    if not (out.get("exif") or {}).get("fields"):
        signals.append("no EXIF metadata (stripped on social upload or removed) → capture "
                       "time/place UNKNOWN (inconclusive, not proof of anything)")
    out["signals"] = signals or ["no strong signals"]
    out["note"] = "SIGNALS not a verdict — leads for a human analyst. No free deepfake certainty."
    return out


def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", help="image URL or local file path")
    ap.add_argument("--claimed-date", default=None)
    a = ap.parse_args()
    print(json.dumps(verify(a.image, a.claimed_date), indent=2, default=str))


if __name__ == "__main__":
    _main()
