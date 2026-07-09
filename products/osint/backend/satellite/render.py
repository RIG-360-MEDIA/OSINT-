"""Best-quality per-source rendering — the standard change-desk output.

Optimised for image QUALITY, not tightest zoom: a wider AOI so Sentinel renders
at NATIVE resolution (crisp, not an upscaled crop), the CLEAREST available scene
(optical), proper true-colour (S2) / multi-pass despeckle (S1). Returns image
bytes + honest metadata (capture date, cloud, resolution, source, attribution).
Esri (sub-metre detail) delegates to esri.py. The caller/UI picks the source.
"""
from __future__ import annotations

import io
from typing import Any

import numpy as np

import esri
import imagery

_S2_RANGE = "2025-06-01/2026-12-31"   # wide window; we pick the best within it
_S1_RANGE = "2026-01-01/2026-12-31"


def _b2d(ds: Any, band: str) -> np.ndarray:
    a = ds[band].values
    return a[0] if a.ndim == 3 else a


def _tci(a: np.ndarray) -> np.ndarray:
    """Sentinel-2 true-colour: clip reflectance to 0-0.30, gamma 2.2 (natural)."""
    a = a.astype("float32") / 10000.0
    return np.clip(a / 0.30, 0, 1) ** (1 / 2.2)


def _png(arr: np.ndarray) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    return buf.getvalue()


def render_sentinel2(lat: float, lon: float, *, aoi_km: float = 5.0,
                     prefer: str = "clearest", max_cloud: float = 8.0) -> dict[str, Any]:
    """Best-quality true-colour Sentinel-2 chip. prefer='clearest' (lowest cloud)
    or 'latest'. Native ~10 m — crisp at the AOI's native pixel size."""
    bbox = imagery.bbox_from_point(lat, lon, aoi_km)
    cands = imagery.search(imagery.S2_L2A, bbox, _S2_RANGE, max_cloud=max_cloud, limit=60)
    if not cands:  # relax cloud if nothing clean
        cands = imagery.search(imagery.S2_L2A, bbox, _S2_RANGE, max_cloud=60, limit=60)
    if not cands:
        return {"ok": False, "source": "Sentinel-2", "error": "no scene in range"}
    it = (sorted(cands, key=lambda i: i.datetime, reverse=True)[0] if prefer == "latest"
          else sorted(cands, key=lambda i: i.properties.get("eo:cloud_cover", 100))[0])
    ds = imagery.load_clip([it], bbox, ["red", "green", "blue"], resolution=10)
    rgb = (np.dstack([_tci(_b2d(ds, "red")), _tci(_b2d(ds, "green")),
                      _tci(_b2d(ds, "blue"))]) * 255).astype("uint8")
    return {
        "ok": True, "image": _png(rgb), "mime": "image/png",
        "source": "Sentinel-2 · optical", "date": str(it.datetime)[:10],
        "cloud_pct": round(it.properties.get("eo:cloud_cover", -1), 1),
        "res_m": 10, "size_px": int(rgb.shape[0]),
        "attribution": "Copernicus Sentinel-2 (ESA)",
    }


def render_sentinel1(lat: float, lon: float, *, aoi_km: float = 5.0,
                     passes: int = 6) -> dict[str, Any]:
    """Best-quality Sentinel-1 VV radar chip — mean of the `passes` most recent
    RTC scenes (multilook despeckle). All-weather, ~this week, native 10 m."""
    bbox = imagery.bbox_from_point(lat, lon, aoi_km)
    items = sorted(imagery.search_pc(imagery.S1_RTC, bbox, _S1_RANGE, limit=30),
                   key=lambda i: i.datetime, reverse=True)[:passes]
    if not items:
        return {"ok": False, "source": "Sentinel-1", "error": "no RTC scene in range"}
    stack = [_b2d(imagery.load_clip([it], bbox, ["vv"], resolution=10), "vv") for it in items]
    h = min(a.shape[0] for a in stack)
    w = min(a.shape[1] for a in stack)
    vv = np.nanmean(np.stack([a[:h, :w] for a in stack]), axis=0)
    vvdb = 10 * np.log10(np.clip(vv, 1e-6, None))
    finite = vvdb[np.isfinite(vvdb)]
    lo, hi = np.nanpercentile(finite, [4, 96]) if finite.size else (0.0, 1.0)
    g = (np.clip((vvdb - lo) / (hi - lo + 1e-6), 0, 1) * 255).astype("uint8")
    return {
        "ok": True, "image": _png(g), "mime": "image/png",
        "source": "Sentinel-1 · radar", "date": str(items[0].datetime)[:10],
        "composite_dates": [str(x.datetime)[:10] for x in items],
        "res_m": 10, "size_px": int(g.shape[0]),
        "attribution": "Copernicus Sentinel-1 (ESA)",
    }


def render_esri(lat: float, lon: float, *, zoom: int = 18, grid: int = 8,
                wayback_release: int | None = None) -> dict[str, Any]:
    """Best-quality Esri sub-metre chip (~0.5 m). Delegates to esri.fetch_chip."""
    r = esri.fetch_chip(lat, lon, zoom=zoom, grid=grid, wayback_release=wayback_release)
    return {
        "ok": r["tiles_ok"] > 0, "image": r["image_jpeg"], "mime": "image/jpeg",
        "source": r["source"], "date": r.get("capture_date"),
        "res_m": r["m_per_px"], "size_px": r["size_px"],
        "attribution": r["attribution"],
    }


def render(lat: float, lon: float, source: str = "esri", **kw: Any) -> dict[str, Any]:
    """Dispatch to the requested source: esri | sentinel2 | sentinel1."""
    if source == "sentinel2":
        return render_sentinel2(lat, lon, **kw)
    if source == "sentinel1":
        return render_sentinel1(lat, lon, **kw)
    return render_esri(lat, lon, **kw)
