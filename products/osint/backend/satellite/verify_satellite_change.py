"""verify_satellite_change.py — Phase-1 proof of satellite change-detection.

    python verify_satellite_change.py --lat 26.73 --lon 67.78 \
        --before 2022-06-01/2022-06-30 --after 2022-09-01/2022-09-30 \
        --km 15 --mode radar --label sindh_flood

Location + two date windows → fetch the two Sentinel scenes (AWS Earth Search,
free) for the AOI → unsupervised change map + the two source images → PNGs + an
honest summary. `--mode radar` uses Sentinel-1 (flood, through cloud);
`--mode optical` uses Sentinel-2 (NDVI/NDWI/NDBI + CVA). ~10m ceiling: big
physical change, not vehicles. On-demand; stores only the result PNGs.
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np

import imagery
import change

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _stretch(a: np.ndarray, lo_pct: float = 2, hi_pct: float = 98) -> np.ndarray:
    a = a.astype("float32")
    finite = a[np.isfinite(a)]
    if finite.size == 0:
        return np.zeros_like(a)
    lo, hi = np.percentile(finite, [lo_pct, hi_pct])
    return np.clip((a - lo) / (hi - lo + 1e-6), 0, 1)


def _save_rgb(r, g, b, path, title):
    rgb = np.dstack([_stretch(r), _stretch(g), _stretch(b)])
    plt.figure(figsize=(5, 5)); plt.imshow(rgb); plt.title(title); plt.axis("off")
    plt.tight_layout(); plt.savefig(path, dpi=110); plt.close()


def _save_gray(a, path, title):
    plt.figure(figsize=(5, 5)); plt.imshow(_stretch(a), cmap="gray")
    plt.title(title); plt.axis("off"); plt.tight_layout(); plt.savefig(path, dpi=110); plt.close()


def _save_map(a, path, title, cmap, vmin=None, vmax=None):
    plt.figure(figsize=(5.4, 5)); im = plt.imshow(a, cmap=cmap, vmin=vmin, vmax=vmax)
    plt.title(title); plt.axis("off"); plt.colorbar(im, fraction=0.046)
    plt.tight_layout(); plt.savefig(path, dpi=110); plt.close()


def _reduce_time(da) -> np.ndarray:
    """Collapse the time dimension to a single 2-D image (median over passes)."""
    arr = da.values
    if arr.ndim == 3:
        return np.nanmedian(np.where(arr == 0, np.nan, arr), axis=0)
    return arr


def run_radar(bbox, before, after, out, label, km):
    """Sentinel-1 VV flood detection: before vs after backscatter."""
    # Sentinel-1 RTC from Planetary Computer (terrain-corrected, UTM-gridded).
    ib = imagery.search_pc(imagery.S1_RTC, bbox, before, limit=25)
    ia = imagery.search_pc(imagery.S1_RTC, bbox, after, limit=25)
    info = {"before_scenes": len(ib), "after_scenes": len(ia)}
    if not ib or not ia:
        return {**info, "error": "no Sentinel-1 RTC scenes for one of the windows"}

    db = imagery.load_clip(ib, bbox, ["vv"], resolution=10)
    da = imagery.load_clip(ia, bbox, ["vv"], resolution=10)
    vv_b = change.to_db(_reduce_time(db["vv"]))
    vv_a = change.to_db(_reduce_time(da["vv"]))
    info["vv_before_dB"] = [round(float(np.nanpercentile(vv_b, 5)), 1), round(float(np.nanpercentile(vv_b, 95)), 1)]
    info["vv_after_dB"] = [round(float(np.nanpercentile(vv_a, 5)), 1), round(float(np.nanpercentile(vv_a, 95)), 1)]

    flood = change.s1_flood(vv_b, vv_a)
    info["flood_fraction_pct"] = round(100 * flood["flood_fraction"], 1)

    _save_gray(vv_b, f"{out}/{label}_before_vv.png", f"{label} · VV before (dB)")
    _save_gray(vv_a, f"{out}/{label}_after_vv.png", f"{label} · VV after (dB)")
    _save_map(flood["change_db"], f"{out}/{label}_change.png",
              f"{label} · VV change (blue=new water)", cmap="RdBu", vmin=-10, vmax=10)
    _save_map(flood["mask"].astype("float32"), f"{out}/{label}_flood_mask.png",
              f"{label} · flood mask ({info['flood_fraction_pct']}% of AOI)", cmap="Blues")
    info["outputs"] = [f"{label}_before_vv.png", f"{label}_after_vv.png",
                       f"{label}_change.png", f"{label}_flood_mask.png"]
    return info


def run_optical(bbox, before, after, out, label, km, max_cloud=25):
    """Sentinel-2 optical change: least-cloudy scene per window; indices + CVA."""
    bands = ["red", "green", "blue", "nir", "swir16"]
    ib = imagery.clearest(imagery.search(imagery.S2_L2A, bbox, before, max_cloud=max_cloud))
    ia = imagery.clearest(imagery.search(imagery.S2_L2A, bbox, after, max_cloud=max_cloud))
    if not ib or not ia:
        return {"error": "no low-cloud Sentinel-2 scene for one of the windows"}
    info = {
        "before_date": ib.datetime.strftime("%Y-%m-%d"), "before_cloud": round(ib.properties.get("eo:cloud_cover", -1), 1),
        "after_date": ia.datetime.strftime("%Y-%m-%d"), "after_cloud": round(ia.properties.get("eo:cloud_cover", -1), 1),
    }
    db = imagery.load_clip([ib], bbox, bands, resolution=10)
    da = imagery.load_clip([ia], bbox, bands, resolution=10)

    def g(ds, b):
        return _reduce_time(ds[b]).astype("float32") / 10000.0   # S2 L2A scale

    rb, gb, bb, nb, sb = (g(db, x) for x in bands)
    ra, ga, ba, na, sa = (g(da, x) for x in bands)

    d_ndvi = change.ndvi(na, ra) - change.ndvi(nb, rb)
    d_ndwi = change.ndwi(ga, na) - change.ndwi(gb, nb)
    d_ndbi = change.ndbi(sa, na) - change.ndbi(sb, nb)
    cva = change.cva_magnitude(np.stack([rb, gb, bb, nb, sb]), np.stack([ra, ga, ba, na, sa]))
    ch = change.change_fraction(cva, threshold=0.12)
    info["changed_fraction_pct"] = round(100 * ch["changed_fraction"], 1)
    info["mean_dNDVI"] = round(float(np.nanmean(d_ndvi)), 3)
    info["mean_dNDWI"] = round(float(np.nanmean(d_ndwi)), 3)
    info["mean_dNDBI"] = round(float(np.nanmean(d_ndbi)), 3)

    _save_rgb(rb, gb, bb, f"{out}/{label}_before_rgb.png", f"{label} · {info['before_date']}")
    _save_rgb(ra, ga, ba, f"{out}/{label}_after_rgb.png", f"{label} · {info['after_date']}")
    _save_map(cva, f"{out}/{label}_cva.png", f"{label} · change magnitude (CVA)", cmap="magma")
    _save_map(d_ndbi, f"{out}/{label}_dNDBI.png", f"{label} · Δ built-up (red=new)", cmap="RdBu_r", vmin=-0.4, vmax=0.4)
    info["outputs"] = [f"{label}_before_rgb.png", f"{label}_after_rgb.png",
                       f"{label}_cva.png", f"{label}_dNDBI.png"]
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--before", required=True, help="STAC date range e.g. 2022-06-01/2022-06-30")
    ap.add_argument("--after", required=True)
    ap.add_argument("--km", type=float, default=15)
    ap.add_argument("--mode", choices=["radar", "optical"], default="radar")
    ap.add_argument("--label", default="aoi")
    ap.add_argument("--out", default="/root/sat-out")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    bbox = imagery.bbox_from_point(args.lat, args.lon, args.km)
    print(f"AOI bbox={tuple(round(x,4) for x in bbox)} mode={args.mode}")
    fn = run_radar if args.mode == "radar" else run_optical
    result = fn(bbox, args.before, args.after, args.out, args.label, args.km)
    print("\n=== RESULT ===")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
