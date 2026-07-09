"""Sentinel imagery access via STAC — AWS Earth Search (primary), on-demand.

Reads ONLY the AOI window from the public Cloud-Optimized GeoTIFFs (anonymous,
no key, not requester-pays). Sentinel-2 L2A (10m optical) + Sentinel-1 GRD
(radar, sees through cloud). Copernicus open data — commercial use OK.
"""
from __future__ import annotations

import math
import os
from typing import Any

# GDAL/rasterio config for anonymous public-COG reads from the sentinel-cogs bucket.
os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("AWS_REGION", "us-west-2")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
os.environ.setdefault("VSI_CACHE", "TRUE")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF,.tiff")

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
S2_L2A = "sentinel-2-l2a"
S1_GRD = "sentinel-1-grd"        # AWS: NOT map-projected (GCPs) — not usable by odc
S1_RTC = "sentinel-1-rtc"        # PC: terrain-corrected, UTM-gridded, analysis-ready


def bbox_from_point(lat: float, lon: float, km: float) -> tuple[float, float, float, float]:
    """A square AOI (lon/lat) of side ~`km` centred on a point."""
    dlat = km / 111.0
    dlon = km / (111.0 * max(0.1, math.cos(math.radians(lat))))
    return (lon - dlon / 2, lat - dlat / 2, lon + dlon / 2, lat + dlat / 2)


def _client() -> Any:
    from pystac_client import Client
    return Client.open(EARTH_SEARCH)


def search_pc(collection: str, bbox: tuple[float, float, float, float],
              date_range: str, limit: int = 25) -> list[Any]:
    """STAC items from Planetary Computer, SAS-signed for anonymous read.

    Used for Sentinel-1 RTC (terrain-corrected radar) — AWS only serves raw GRD
    in SAR geometry, which isn't a clean map grid. PC's RTC is UTM-projected."""
    import planetary_computer as pc
    from pystac_client import Client
    s = Client.open(PC_STAC).search(collections=[collection], bbox=list(bbox),
                                    datetime=date_range, limit=limit)
    return [pc.sign(it) for it in s.items()]


def search(collection: str, bbox: tuple[float, float, float, float],
           date_range: str, max_cloud: float | None = None,
           limit: int = 25) -> list[Any]:
    """STAC items for a collection intersecting the AOI in a date range."""
    query = {"eo:cloud_cover": {"lt": max_cloud}} if max_cloud is not None else None
    s = _client().search(collections=[collection], bbox=list(bbox),
                         datetime=date_range, query=query, limit=limit)
    return list(s.items())


def clearest(items: list[Any]) -> Any | None:
    """Least-cloudy item (optical)."""
    if not items:
        return None
    return sorted(items, key=lambda it: it.properties.get("eo:cloud_cover", 100.0))[0]


def load_clip(items: list[Any], bbox: tuple[float, float, float, float],
              bands: list[str], resolution: float) -> Any:
    """Load the AOI window for the given items/bands into an xarray Dataset
    (native UTM grid at `resolution` metres). Eager — the AOI is small."""
    import odc.stac
    ds = odc.stac.load(
        items, bands=bands, bbox=list(bbox), resolution=resolution,
        groupby="solar_day", chunks={},
    )
    return ds.load()
