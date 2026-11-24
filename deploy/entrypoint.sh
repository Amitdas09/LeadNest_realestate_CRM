#!/bin/sh
# Apply database migrations, then start the API (one process: it also runs the
# sheet poller and WhatsApp dispatcher, which must not be duplicated).
set -e
cd /app/backend
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips="*"
