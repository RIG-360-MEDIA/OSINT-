"""Unsupervised 10m change detection — honest, no training, interpretable.

Optical (Sentinel-2): spectral-index differencing (NDVI/NDWI/NDBI) + Change
Vector Analysis magnitude. Radar (Sentinel-1): VV backscatter change — the
standard flood method (water is smooth → low backscatter → clean before/after
delta THROUGH cloud). All at ~10m: detects big physical change, not vehicles.
"""
from __future__ import annotations

import numpy as np


def _nd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a = a.astype("float32"); b = b.astype("float32")
    return (a - b) / (a + b + 1e-6)


def ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Vegetation. Drops on deforestation / land clearing."""
    return _nd(nir, red)


def ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Open water (McFeeters). Rises on flooding."""
    return _nd(green, nir)


def ndbi(swir: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """Built-up. Rises on construction."""
    return _nd(swir, nir)


def cva_magnitude(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """Change Vector Analysis: L2 magnitude of the multi-band difference.

    `before`/`after` are (band, y, x) reflectance stacks (0-1). Direction-agnostic
    'how much did the surface change' — the general change map."""
    diff = after.astype("float32") - before.astype("float32")
    return np.sqrt(np.nansum(diff ** 2, axis=0))


def to_db(power: np.ndarray) -> np.ndarray:
    """Sentinel-1 GRD linear power → decibels."""
    p = np.asarray(power, dtype="float32")
    return 10.0 * np.log10(np.clip(p, 1e-6, None))


def s1_flood(vv_before_db: np.ndarray, vv_after_db: np.ndarray,
             drop_db: float = 4.0, water_db: float = -15.0) -> dict:
    """New-water (flood) mask from Sentinel-1 VV backscatter.

    Flood pixel = backscatter dropped by >=`drop_db` AND the after-scene is
    water-dark (< `water_db`). Returns the dB-change array + boolean mask +
    flooded-area fraction."""
    change = vv_after_db - vv_before_db
    mask = (change <= -abs(drop_db)) & (vv_after_db < water_db)
    valid = np.isfinite(change)
    frac = float(mask[valid].mean()) if valid.any() else 0.0
    return {"change_db": change, "mask": mask, "flood_fraction": frac}


def change_fraction(magnitude: np.ndarray, threshold: float) -> dict:
    """Fraction of AOI whose change magnitude exceeds a threshold + the mask."""
    valid = np.isfinite(magnitude)
    mask = valid & (magnitude >= threshold)
    frac = float(mask[valid].mean()) if valid.any() else 0.0
    return {"mask": mask, "changed_fraction": frac}
