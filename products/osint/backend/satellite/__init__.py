"""Satellite change-detection — free Sentinel imagery, on-demand, result-only.

Isolated module (httpx / pystac-client / odc-stac / rasterio / numpy). Pulls only
the AOI window for a queried location on-demand; stores just the result, never the
raw archive. Does NOT touch rig-backend. Honest ceiling: ~10m — detects big
physical change (construction, flooding, deforestation, camps), not vehicles.
"""
