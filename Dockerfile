# Spotter — single container: build the React frontend, serve it from FastAPI (spec §16).
FROM node:20-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
# Azure Speech SDK native deps (OpenSSL 3, CA certs, ALSA lib) on Debian bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends libssl3 ca-certificates libasound2 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist ./app/static
ENV CACHE_MODE=replay PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
