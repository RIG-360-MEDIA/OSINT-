# RIG Media Verify — image verification service (isolated).
# On infrastructure_rig-network so Caddy reverse-proxies it by name (rigmedia:8701).
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pillow numpy fastapi "uvicorn[standard]" psycopg2-binary

WORKDIR /app
COPY *.py /app/

ENV PYTHONUNBUFFERED=1
EXPOSE 8701
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8701"]
