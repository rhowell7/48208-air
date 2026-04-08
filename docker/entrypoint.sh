#!/usr/bin/env bash
set -euo pipefail

POSTGRES_DB="48208_air"
POSTGRES_USER="appuser"
POSTGRES_SOCKET_DIR="/var/run/postgresql"

postgres_bin_dir() {
  find /usr/lib/postgresql -mindepth 2 -maxdepth 2 -type d -name bin | sort -V | tail -n 1
}

PG_BIN="$(postgres_bin_dir)"
export PATH="$PG_BIN:$PATH"

child_pids=()

on_exit() {
  local status=$?
  if [ "${#child_pids[@]}" -gt 0 ]; then
    kill -TERM "${child_pids[@]}" 2>/dev/null || true
    wait "${child_pids[@]}" 2>/dev/null || true
  fi
  exit "$status"
}

trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p "$PGDATA"
mkdir -p "$POSTGRES_SOCKET_DIR"
chown -R postgres:postgres /var/lib/postgresql
chown postgres:postgres "$POSTGRES_SOCKET_DIR"
chmod 2775 "$POSTGRES_SOCKET_DIR"

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  gosu postgres initdb -D "$PGDATA" >/dev/null
fi

gosu postgres postgres -D "$PGDATA" \
  -c "listen_addresses=" \
  -c "unix_socket_directories=$POSTGRES_SOCKET_DIR" &
pg_pid=$!
child_pids+=("$pg_pid")

until pg_isready -h "$POSTGRES_SOCKET_DIR" -U postgres >/dev/null 2>&1; do
  if ! kill -0 "$pg_pid" 2>/dev/null; then
    wait "$pg_pid"
    exit 1
  fi
  sleep 1
done

gosu postgres createuser -h "$POSTGRES_SOCKET_DIR" "$POSTGRES_USER" 2>/dev/null || true
gosu postgres createdb -h "$POSTGRES_SOCKET_DIR" -O "$POSTGRES_USER" "$POSTGRES_DB" 2>/dev/null || true

export DATABASE_URL="postgres://${POSTGRES_USER}@/${POSTGRES_DB}?host=${POSTGRES_SOCKET_DIR}"

if [ -n "${CLOUDFLARED_TOKEN:-}" ] && [ -z "${TRUST_PROXY_HEADERS:-}" ]; then
  export TRUST_PROXY_HEADERS="True"
fi

if [ -z "${SECRET_KEY:-}" ]; then
  export SECRET_KEY="$(gosu appuser python -c \
    'from django.core.management import utils; print(utils.get_random_secret_key(), end="")'
  )"
fi

gosu appuser python manage.py migrate
gosu appuser python manage.py load_stations
gosu appuser python manage.py collectstatic --noinput

gosu appuser gunicorn --bind 0.0.0.0:8000 config.wsgi:application &
child_pids+=("$!")

(
  interval="${POLL_INTERVAL_SECONDS:-3600}"
  anchor_ts=$(date +%s)
  while true; do
    gosu appuser python manage.py fetch_aqi || true
    # Keep a fixed-rate schedule from container start and skip missed slots.
    now=$(date +%s)
    next_run=$((anchor_ts + ((((now - anchor_ts) / interval) + 1) * interval)))
    sleep "$((next_run - now))"
  done
) &
child_pids+=("$!")

if [ -n "${CLOUDFLARED_TOKEN:-}" ]; then
  gosu appuser cloudflared tunnel run --token "${CLOUDFLARED_TOKEN}" &
  child_pids+=("$!")
fi

wait -n "${child_pids[@]}"
