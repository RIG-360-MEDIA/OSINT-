# RIG Geospatial change desk — satellite imagery source-picker (isolated service).
# On infrastructure_rig-network so Caddy reverse-proxies it by name (riggeo:8700).
# rasterio's manylinux wheel bundles GDAL, so no apt GDAL layer is needed.
FROM python:3.12-slim

# libexpat1: XML parsing for the pystac/pyproj STAC chain (needed by /change; slim lacks it).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      pystac-client odc-stac rasterio pystac planetary-computer \
      numpy pillow matplotlib fastapi "uvicorn[standard]"

WORKDIR /app
COPY *.py /app/

# GDAL config for anonymous public-COG reads (also set in imagery.py at import).
ENV AWS_NO_SIGN_REQUEST=YES AWS_REGION=us-west-2 \
    GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR PYTHONUNBUFFERED=1

EXPOSE 8700
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8700"]
