FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libgdk-pixbuf-2.0-0 \
      libffi8 libjpeg62-turbo libcairo2 shared-mime-info \
      fonts-dejavu-core fonts-indic fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Headless Chromium for the Daily Media Briefing PDF renderer (briefing/pdf.py).
# Renders the exact report HTML so screen == download == print. --with-deps pulls
# the required system libraries. ~300 MB; baked in so it survives rebuilds.
RUN pip install --no-cache-dir playwright \
    && python -m playwright install --with-deps chromium

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OSINT_HOST=0.0.0.0 \
    OSINT_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
