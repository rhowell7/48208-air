# 48208-air

A Django app that collects and visualizes air quality data around Southeast Michigan using open source air sensors.

**Live site: [breckenridgeblockclub.com](https://breckenridgeblockclub.com)**

![Dashboard Sample](docs/dashboard_sample.png)

The primary sensor (`A548659`, GAIA A12) is located in the Core City neighborhood and feeds into the [World Air Quality Index](https://aqicn.org) global network. It is currently the **only community air sensor in Detroit's Core City neighborhood with public AQICN reporting** (many PurpleAir sensors exist in the region but are not aggregated into AQICN).

The network also tracks upwind stations (Ann Arbor, Ypsilanti) for early wildfire smoke warning, and downwind stations (Windsor, Grosse Pointe) for plume confirmation, based on the region's prevailing SW to NE winds.

A recurring theme in the data: dramatic PM2.5 spikes during Canadian wildfire season (May-October), visible as AQI readings above 100 dominated by fine particulate matter drifting southeast across the Great Lakes into Detroit.

A secondary purpose of this project is **pre-construction baseline documentation** for a proposed large industrial facility nearby. Readings are timestamped and archived so that post-construction air quality can be compared against a statistically sound pre-construction baseline across PM2.5, PM10, NO2, and SO2.

---

## Regional station network

Stations are seeded via `load_stations` and organized by wind relationship to the primary sensor:

| Wind position | Stations | Purpose |
|---|---|---|
| **Upwind** | Ann Arbor (x5), Ypsilanti | Early warning, smoke arrives here before 48208 |
| **Primary** | Detroit - Core City | Home sensor, baseline + real-time |
| **Crosswind** | Dearborn, Allen Park, Oak Park, Hamtramck (x4) | Industrial comparison reference |
| **Downwind** | Windsor (x3), Grosse Pointe | Plume confirmation, wind reversal detection |

The Hamtramck cluster (4 sensors) was placed around the GM Factory ZERO EV assembly plant, a useful EJ monitoring comparison for 48208's cumulative industrial burden.

Two offline Michigan DEQ stations (`Detroit - W Lafayette`, `Detroit - Southwest`) are included as `active=False` and together provide a continuous official baseline for SW Detroit from 2014 through June 2025.

---

## How the site runs

The current production setup runs on a laptop via a Cloudflare Tunnel.

```
cron (hourly)
    └─ fetch_aqi → SQLite DB
                        └─ Gunicorn (port 8000, localhost only)
                                └─ Cloudflare Tunnel → breckenridgeblockclub.com
```

- **Gunicorn** serves the Django app on `127.0.0.1:8000`
- **Cloudflare Tunnel** (`cloudflared`) proxies public HTTPS traffic to Gunicorn
- **cron** polls all active stations every hour via `fetch_aqi`
- **SQLite** stores all readings (~95 MB/year, adequate for this scale — PostgreSQL will be needed for TODO 8 which requires `StdDev()` aggregation)
- Gunicorn and cloudflared run as systemd user services and start automatically on boot, surviving reboots, logout, sleep, and hibernate

---

## Initial Setup

### 1. Create virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate.fish  # or activate for bash/zsh
pip install -r requirements.txt
```

### 2. Get a WAQI API token

Free token at: https://aqicn.org/api/

The free tier allows 1,000 requests/day, sufficient for hourly polling of 18 active stations (432/day).

### 3. Configure settings

```bash
cp .env.example .env
# Edit .env and set SECRET_KEY, WAQI_API_TOKEN, ALLOWED_HOSTS
```

Settings are loaded from `.env` via `python-dotenv`. See `.env.example` for all available options.

### 4. Run migrations and seed stations

```bash
python manage.py migrate
python manage.py load_stations
```

### 5. Import historical data (optional)

Download daily CSV exports from [aqicn.org/data-platform/](https://aqicn.org/data-platform/) for each station and place them in `historical_data/`. Then:

```bash
python manage.py import_historical --dry-run  # preview
python manage.py import_historical            # load
```

Note: `historical_data/` is excluded from git per WAQI data use terms.

---

## Local development

```bash
python manage.py fetch_aqi        # pull latest readings
python manage.py runserver        # starts at http://127.0.0.1:8000/
```

`DEBUG=True` in `.env` is fine for local dev. Django's built-in server serves static files automatically, so `collectstatic` is not needed locally.

---

## Production setup

### Collect static files

Required when `DEBUG=False`. Whitenoise serves the hashed, pre-gzipped files from `staticfiles/`.

```bash
python manage.py collectstatic --no-input
```

### Set up systemd services

Gunicorn and cloudflared run as systemd user services (no root required). Unit files live in `~/.config/systemd/user/` and are not checked into this repo since they contain machine-specific paths.

`48208-air.service`:
```ini
[Unit]
Description=48208-air Gunicorn
After=network.target

[Service]
WorkingDirectory=/home/path/to/48208-air
EnvironmentFile=/home/path/to/48208-air/.env
ExecStart=/home/path/to/48208-air/.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

`cloudflared.service`:
```ini
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
ExecStart=/usr/local/bin/cloudflared tunnel run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Then enable both:

```bash
systemctl --user daemon-reload
systemctl --user enable --now 48208-air cloudflared

# Start services at boot even without logging in
loginctl enable-linger $USER
```

### Set up cron

```bash
crontab -e
```

Add:
```
5 * * * * cd /path/to/48208-air && .venv/bin/python manage.py fetch_aqi >> fetch_aqi.log 2>&1
```

### After changing website code (Python, templates, CSS/JS)

```bash
# If CSS or JS changed, rehash static files
python manage.py collectstatic --no-input

# Restart Gunicorn to pick up Python/template changes
systemctl --user restart 48208-air
```

Python and template changes require a Gunicorn restart. CSS/JS changes require `collectstatic` first (Whitenoise serves hashed filenames; the old hash won't match the new file).

### After changing the database (new migrations, adding stations)

```bash
python manage.py migrate           # apply any new migrations
python manage.py load_stations     # if station list changed
systemctl --user restart 48208-air
```

---

## Monitoring and logs

```bash
# Check both services at a glance
systemctl --user status 48208-air cloudflared

# Follow live Gunicorn output (requests, errors)
journalctl --user -u 48208-air -f

# Follow cloudflared tunnel output
journalctl --user -u cloudflared -f

# Check cron fetch history
tail -f /home/path/to/48208-air/fetch_aqi.log
```

---

## Testing

```bash
make check        # lint + format check + tests (full CI check)
make test         # tests only, with coverage report
make lint         # ruff linter only
make fmt          # auto-format with ruff (modifies files)
```

Tests use an in-memory SQLite database and mock all HTTP calls. Coverage is enforced at 86% minimum; `make test` fails if it drops below.

---

## Docker

Use this `docker-compose.yaml`:

```yaml
services:
  app:
    image: ghcr.io/rhowell7/48208-air:latest
    environment:
      ALLOWED_HOSTS: your-hostname
      WAQI_API_TOKEN: your-waqi-token
      CLOUDFLARED_TOKEN: your-cloudflare-tunnel-token  # optional: enables cloudflared
      TRUST_PROXY_HEADERS: "True"  # optional: set by default when cloudflared is configured
      POLL_INTERVAL_SECONDS: "3600"  # optional: defaults to hourly polling
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"  # optional: only needed for direct host access/local testing
    volumes:
      - /path/to/volume:/var/lib/postgresql/data
```

To pull and start the published image:

```bash
docker compose pull
docker compose up -d
```

To build locally from this repo instead, replace `image:` with `build: .` and run `docker compose up --build -d`.

---

## Data notes

- `station_time` is stored in UTC; convert to `America/Detroit` for display
- `unique_together = [("station", "station_time")]` makes polling idempotent; running `fetch_aqi` multiple times in the same hour is safe
- `is_wildfire_smoke_likely` on `AQIReading` is a PM2.5 + fire-season heuristic (May-Oct, AQI > 100, dominant pollutant = pm25), useful for UI flagging, not authoritative source attribution
- WAQI returns `aqi = "-"` when a station is temporarily offline; the command logs an error for that station and continues with the rest
- `dominant_pollutant` uses WAQI's field name `dominentpol` (their typo, preserved)
- Pollutant signatures to watch for construction/industrial events:
  - **PM10**: coarse dust (earthwork, demolition), distinct from PM2.5 smoke
  - **NO2**: diesel exhaust, correlates with truck traffic increases
  - **SO2**: industrial combustion, relevant for diesel generators (data centers)

---

## Baseline monitoring

The baseline period began when the primary sensor was installed. To lock in a formal pre-construction baseline snapshot:

```python
# Example: export baseline stats for PM2.5 before a given date
from django.db.models import Avg, StdDev
from aqi_tracker.models import AQIReading, Station

primary = Station.objects.get(is_primary=True)
baseline = AQIReading.objects.filter(
    station=primary,
    station_time__lt="2026-01-01",  # adjust to construction start date
).aggregate(
    avg_pm25=Avg("pm25"),
    stddev_pm25=StdDev("pm25"),
    avg_aqi=Avg("aqi"),
    stddev_aqi=StdDev("aqi"),
)
```

---

## Roadmap

- [x] **TODO 1**: Models + single-station fetch command
- [x] **TODO 2**: Multi-station `Station` model; regional network; `load_stations`
- [x] **TODO 3**: Verify and fix regional station network (20 stations, real WAQI IDs + coordinates)
- [x] **TODO 4**: Historical data import: 30,942 readings across 20 stations, back to 2014
- [x] **TODO 5**: Test suite (pytest; models, management commands)
- [x] **TODO 6**: Dashboard: stat bar, regional map with 7-day time scrubber, hourly and monthly trend charts, pollutant breakdown, station switcher dropdown
- [x] **TODO 10**: Systemd user services for Gunicorn and cloudflared; auto-start on boot via `loginctl enable-linger`
- [ ] **TODO 7**: EPA EJScreen overlay for 48208; socioeconomic context layer *(shelved - EPA shut down EJScreen data)*
- [ ] **TODO 8**: Baseline deviation alerts: notify when readings exceed pre-construction norms by >2 standard deviations on PM10, NO2, or SO2
- [ ] **TODO 9**: PurpleAir API integration: pull nearby sensors not on AQICN to fill coverage gaps (Detroit proper has many PurpleAir sensors)
- [ ] **TODO 11**: Dockerize: Dockerfile + compose for Gunicorn, cron, and static files; makes deployment to any server (VPS, Pi, cloud) repeatable
