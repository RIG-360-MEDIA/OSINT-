"""Esri World Imagery — the sub-metre 'detail' source (user-selectable layer).

A companion to the free Sentinel sources: where Sentinel-2/1 (10 m) answer
"did something change here, and when?", Esri World Imagery (~0.5 m) answers
"what does it actually look like — buildings, courts, countable vehicles?".

The analyst chooses the layer per need (see SOURCES): sharp-but-older (Esri),
current-but-coarse (Sentinel-2), or all-weather radar (Sentinel-1). Esri current
basemap OR a dated Wayback version (for a sub-metre before/after).

Licence note: Esri imagery (Maxar/Vexcel) is used here under a research/reference
licence — we keep the DERIVED result (annotation / count / change) with
attribution, not a redistributed raw-tile archive. Attribution is always returned.
"""
from __future__ import annotations

import io
import json
import math
import urllib.request
from typing import Any

_UA = {"User-Agent": "rig-osint-research"}
_CURRENT = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile"
_WAYBACK = ("https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery"
            "/WMTS/1.0.0/default028mm/MapServer/tile")
_WB_CONFIG = "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json"
_META = "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/identify"
_ATTRIB = "Source: Esri, Maxar, Earthstar Geographics"

# The three selectable layers the product offers — the user picks.
SOURCES = {
    "esri":       {"label": "Esri sub-metre", "res_m": 0.5, "trait": "sharpest — buildings/vehicles; ~months old"},
    "sentinel2":  {"label": "Sentinel-2",     "res_m": 10,  "trait": "current (days); coarse; cloud-limited"},
    "sentinel1":  {"label": "Sentinel-1 radar", "res_m": 10, "trait": "current; all-weather through cloud; not a photo"},
}


def _get(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=25).read()


def _deg2tile(lat: float, lon: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def capture_date(lat: float, lon: float) -> str | None:
    """Acquisition date of the CURRENT Esri basemap at a point (or None).

    So we always tell the client how old the sharp image is — never imply
    it's live."""
    ext = f"{lon-0.02},{lat-0.02},{lon+0.02},{lat+0.02}"
    url = (f"{_META}?f=json&geometry={lon},{lat}&geometryType=esriGeometryPoint&sr=4326"
           f"&tolerance=2&mapExtent={ext}&imageDisplay=600,600,96&returnGeometry=false")
    try:
        r = json.loads(_get(url))
        return (r.get("results") or [{}])[0].get("attributes", {}).get("SRC_DATE2")
    except Exception:
        return None


def wayback_versions(limit: int | None = None) -> list[tuple[int, str]]:
    """Dated Wayback releases [(release_num, title)], newest first — the dates
    available for a sub-metre before/after."""
    try:
        cfg = json.loads(_get(_WB_CONFIG))
        rel = sorted(((int(k), v.get("itemTitle", "")) for k, v in cfg.items()),
                     reverse=True)
        return rel[:limit] if limit else rel
    except Exception:
        return []


def fetch_chip(lat: float, lon: float, *, zoom: int = 18, grid: int = 8,
               wayback_release: int | None = None) -> dict[str, Any]:
    """Stitched sub-metre chip (JPEG bytes) + metadata for a point.

    Current basemap by default; pass a `wayback_release` (from wayback_versions)
    for a historical date. `zoom` ~18 ≈ 0.5 m/px; `grid` tiles per side."""
    from PIL import Image  # lazy — only needed when we actually pull pixels

    base = f"{_WAYBACK}/{wayback_release}" if wayback_release else _CURRENT
    x0, y0 = _deg2tile(lat, lon, zoom)
    x0 -= grid // 2
    y0 -= grid // 2
    W = 256 * grid
    canvas = Image.new("RGB", (W, W), (15, 15, 15))
    ok = 0
    for i in range(grid):
        for j in range(grid):
            try:
                tile = Image.open(io.BytesIO(_get(f"{base}/{zoom}/{y0 + j}/{x0 + i}")))
                canvas.paste(tile.convert("RGB"), (i * 256, j * 256))
                ok += 1
            except Exception:
                pass
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=88)
    return {
        "image_jpeg": buf.getvalue(),
        "tiles_ok": ok,
        "tiles_total": grid * grid,
        "size_px": W,
        "m_per_px": round(156543.03 * math.cos(math.radians(lat)) / (2 ** zoom), 2),
        "source": "Esri World Imagery"
                  + (f" — Wayback {wayback_release}" if wayback_release else " — current"),
        "capture_date": capture_date(lat, lon) if wayback_release is None else None,
        "attribution": _ATTRIB,
    }
