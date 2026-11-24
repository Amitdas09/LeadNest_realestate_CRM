# LeadNest production image: builds the React CRM, then runs FastAPI (which serves the CRM).
# Multi-arch friendly: works on x86 and on Oracle Cloud's free Ampere (ARM) servers.

# ---- 1. Build the CRM screens -------------------------------------------------
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python API ------------------------------------------------------------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && useradd --create-home --uid 10001 leadnest && mkdir -p /app/secrets && chown -R leadnest /app
USER leadnest
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
ENTRYPOINT ["/entrypoint.sh"]
