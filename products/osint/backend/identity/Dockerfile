# RIG Identity Footprint — public-account-footprint service (isolated).
# On infrastructure_rig-network so Caddy reverse-proxies it by name (rigident:8702).
FROM python:3.12-slim

# maigret (username), holehe (email registration), phonenumbers (phone) + the web layer.
RUN pip install --no-cache-dir \
      maigret holehe phonenumbers fastapi "uvicorn[standard]"

WORKDIR /app
COPY *.py /app/

ENV PYTHONUNBUFFERED=1
EXPOSE 8702
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8702"]
