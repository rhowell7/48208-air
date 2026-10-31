FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PGDATA=/var/lib/postgresql/data \
    DEBUG=False

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql \
    postgresql-client \
    gosu \
    tini \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) cloudflared_arch="amd64" ;; \
      arm64) cloudflared_arch="arm64" ;; \
      *) echo "Unsupported architecture for cloudflared: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${cloudflared_arch}.deb" -o /tmp/cloudflared.deb; \
    apt-get update; \
    apt-get install -y --no-install-recommends /tmp/cloudflared.deb; \
    rm -f /tmp/cloudflared.deb; \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY manage.py /app/
COPY aqi_tracker /app/aqi_tracker
COPY config /app/config
COPY templates /app/templates
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && chown -R appuser:appuser /app

EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
