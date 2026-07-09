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
import io
import json
import os
import re
import subprocess
import tempfile
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
        out = subprocess.run(["exiftool", "-n", "-json", "-G", path],  # -n = numeric GPS
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


def _dhash_img(im: "Any") -> str:
    import numpy as np
    a = np.asarray(im.convert("L").resize((9, 8)), dtype="int16")
    return "".join("1" if b else "0" for b in (a[:, 1:] > a[:, :-1]).flatten())


def dhash(path: str) -> str:
    """64-bit difference-hash — perceptual fingerprint for near-dupe matching."""
    from PIL import Image
    return _dhash_img(Image.open(path))


def dhash_bytes(data: bytes) -> str:
    """dHash from raw image bytes (no temp file) — used by the corpus indexer."""
    from PIL import Image
    return _dhash_img(Image.open(io.BytesIO(data)))


def _gps(exif_fields: dict[str, Any] | None) -> tuple[float, float] | None:
    """Pull decimal (lat, lon) from exiftool -n fields, if present."""
    if not exif_fields:
        return None
    lat = lon = None
    for k, v in exif_fields.items():
        kl = k.lower()
        try:
            if kl.endswith("gpslatitude"):
                lat = float(v)
            elif kl.endswith("gpslongitude"):
                lon = float(v)
            elif kl.endswith("gpsposition") and isinstance(v, str):
                parts = v.replace(",", " ").split()
                if len(parts) >= 2:
                    lat, lon = float(parts[0]), float(parts[1])
        except (TypeError, ValueError):
            continue
    return (lat, lon) if lat is not None and lon is not None else None


def geolocate(exif_fields: dict[str, Any] | None) -> dict[str, Any]:
    """Where was it taken — from EXIF GPS (reverse-geocoded via Nominatim).

    Most social images have GPS stripped, so this usually returns 'no GPS'."""
    coords = _gps(exif_fields)
    if not coords:
        return {"has_gps": False, "note": "no GPS in metadata (typical after social upload)"}
    lat, lon = coords
    place = None
    try:
        u = ("https://nominatim.openstreetmap.org/reverse?format=json"
             f"&lat={lat}&lon={lon}&zoom=14")
        place = json.loads(_get(u, timeout=15)).get("display_name")
    except Exception:
        pass
    return {"has_gps": True, "lat": round(lat, 6), "lon": round(lon, 6),
            "place": place, "map": f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}"}


def ela(path: str) -> dict[str, Any]:
    """Error-Level Analysis — recompress and diff; regions at a different
    compression level are possible edits/splices. SIGNAL only: ELA on already
    re-saved social images is noisy and NOT proof of tampering."""
    try:
        from PIL import Image, ImageChops
        import numpy as np
        im = Image.open(path).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        buf.seek(0)
        diff = ImageChops.difference(im, Image.open(buf))
        arr = np.asarray(diff, dtype="float32")
        Image.fromarray(np.clip(arr * 15, 0, 255).astype("uint8")).save(path + ".ela.png")
        return {"ok": True, "ela_png": path + ".ela.png",
                "mean_diff": round(float(arr.mean()), 2),
                "max_diff": round(float(arr.max()), 1),
                "note": "bright ELA regions = different compression level (possible edit); "
                        "noisy on re-saved social images — SIGNAL not proof"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:80]}


def verify(image: str, claimed_date: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"input": image, "claimed_date": claimed_date}
    local, url, tmp = image, None, None
    if image.startswith("http"):
        url = image
        fd, tmp = tempfile.mkstemp(suffix="_verify")   # unique path — safe under concurrency
        os.close(fd)
        data = _get(image, binary=True)
        with open(tmp, "wb") as fh:
            fh.write(data)
        local = tmp
        out["bytes"] = len(data)

    try:
        from PIL import Image
        im = Image.open(local)
        out["dimensions"] = f"{im.width}x{im.height}"
        out["format"] = im.format
        out["dhash"] = dhash(local)
        out["exif"] = exif(local)
        out["geolocation"] = geolocate((out["exif"] or {}).get("fields"))
        out["ela"] = ela(local)
        if url:
            out["reverse"] = reverse_yandex(url)
    finally:
        if tmp:                                         # never leave temp files for a URL fetch
            for p in (tmp, tmp + ".ela.png"):
                try:
                    os.remove(p)
                except OSError:
                    pass

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
    geo = out.get("geolocation") or {}
    if geo.get("has_gps"):
        where = geo.get("place") or f"{geo.get('lat')},{geo.get('lon')}"
        signals.append(f"EXIF GPS present → taken at {where} "
                       "(cross-check against the claimed location)")
        # Fusion: pull the satellite view of that exact spot to corroborate what's there.
        base = os.environ.get("GEO_PUBLIC_BASE", "https://api.rig360media.com/geo").rstrip("/")
        out["satellite"] = {
            "lat": geo["lat"], "lon": geo["lon"], "place": geo.get("place"),
            "imagery": f"{base}/imagery?lat={geo['lat']}&lon={geo['lon']}&source=esri",
            "viewer": f"{base}/?lat={geo['lat']}&lon={geo['lon']}&source=esri",
            "change_api": f"{base}/change",
            "note": "satellite view of the EXIF-GPS spot — corroborate what is actually there",
        }
        signals.append("satellite corroboration available → the GPS spot can be pulled from "
                       "orbit (and change-detected between dates) to confirm/deny the scene")
    ela_r = out.get("ela") or {}
    if ela_r.get("ok") and ela_r.get("max_diff", 0) >= 40:
        signals.append(f"ELA shows high-contrast regions (max diff {ela_r['max_diff']}) → possible "
                       "edit/splice — SIGNAL only, verify visually (noisy on re-saved images)")
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
