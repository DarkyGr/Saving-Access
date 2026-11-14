# Backend image (used by docker-compose.yml for development and
# docker-compose.prod.yml for production).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# psycopg2-binary ships its own libpq: no compiler needed.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as an unprivileged user.
RUN useradd --system --uid 10001 --home /app savepass && chown -R savepass /app
USER savepass

EXPOSE 8000

# Migrations are applied separately (dev command / the "migrate" service in
# production) so the API can run with a least-privilege database role.
# --proxy-headers: trust X-Forwarded-For from the reverse proxy, so rate
# limits see the real client IP. The API port is not published in production.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
