# 48208-air

A Django app that collects and visualizes air quality data across a regional
sensor network centered on Detroit's Core City neighborhood (ZIP 48208) — one
of Michigan's highest pollution-burden communities.

The primary sensor (`@548659`, GAIA A12) is located on Breckenridge St and
feeds into the [World Air Quality Index](https://aqicn.org) global network.
It is currently the **only community air sensor in Detroit proper**.

The network also tracks upwind stations (Ann Arbor, Ypsilanti) for early
wildfire smoke warning, and downwind stations (Windsor, Grosse Pointe) for
plume confirmation — based on the region's prevailing SW→NE winds.

A recurring theme in the data: dramatic PM2.5 spikes during Canadian wildfire
season (May–October), visible as AQI readings above 100 dominated by fine
particulate matter drifting southeast across the Great Lakes into Detroit.

A secondary purpose of this project is **pre-construction baseline documentation**
for a proposed large industrial facility nearby. Readings are timestamped and
archived so that post-construction air quality can be compared against a
statistically sound pre-construction baseline across PM2.5, PM10, NO2, and SO2.

---

## Regional station network

Stations are seeded via `load_stations` and organized by wind relationship to
the primary sensor:

| Wind position | Stations | Purpose |
|---|---|---|
| **Upwind** | Ann Arbor, Ypsilanti | Early warning — smoke arrives here before 48208 |
| **Primary** | Breckenridge, Detroit | Home sensor — baseline + real-time |
| **Crosswind** | Dearborn, Hamtramck (×4) | Industrial comparison reference |
| **Downwind** | Windsor (×2), Grosse Pointe | Plume confirmation; wind reversal detection |

The Hamtramck cluster (4 sensors) was placed around the GM Factory ZERO EV
assembly plant — a useful EJ monitoring comparison for 48208's cumulative
industrial burden.

Note: non-primary station IDs in `load_stations.py` are approximate and must
be verified. See **Verifying station IDs** below.

---

## Setup

### 1. Create virtual environment and Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate.fish  # `deactivate` when finished
pip install django requests django-apscheduler
```

### 2. Get a WAQI API token

Free token at: https://aqicn.org/api/  
Tokens are issued immediately via email. The free tier allows 1,000
requests/day — well above the hourly polling rate for 11 stations (264/day).

### 3. Configure settings

```python
# settings.py
import os

WAQI_API_TOKEN = os.environ.get("WAQI_API_TOKEN")  # recommended

INSTALLED_APPS = [
    ...
    "aqi_tracker",
    "django_apscheduler",  # optional, for in-process scheduling
]
```

### 4. Run migrations and seed stations

```bash
python manage.py migrate
python manage.py load_stations
```

### 5. Verify non-primary station IDs

The station IDs for all non-primary stations need to be confirmed before
live polling. The easiest method:

1. Go to [aqicn.org/map/](https://aqicn.org/map/) and zoom to Detroit
2. Click each sensor — the URL reveals the station name
3. Run the verification helper:

```bash
python manage.py load_stations --verify-ids
```

This prints an API URL for each non-primary station. A valid station returns
`"status": "ok"`; an invalid ID returns `"status": "error"`. Update the IDs
in `load_stations.py` and re-run to correct them.

### 6. Test and go live

```bash
# Dry run first — fetches all stations but doesn't save
python manage.py fetch_aqi --dry-run

# Fetch a single station by ID
python manage.py fetch_aqi --station @548659

# Fetch all active stations
python manage.py fetch_aqi
```

---

## Scheduling

### cron (recommended for production)

```
# /etc/cron.d/48208-air  — fetch all stations every hour
0 * * * * www-data /path/to/venv/bin/python /path/to/manage.py fetch_aqi >> /var/log/48208-air.log 2>&1
```

### django-apscheduler (dev / single-process deployments)

```python
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django.core.management import call_command

def fetch_aqi_job():
    call_command("fetch_aqi")

scheduler = BackgroundScheduler()
scheduler.add_jobstore(DjangoJobStore(), "default")
scheduler.add_job(
    fetch_aqi_job,
    "interval",
    hours=1,
    id="fetch_aqi",
    replace_existing=True,
)
scheduler.start()
```

---

## Data notes

- `station_time` is stored in UTC; convert to `America/Detroit` for display
- `unique_together = [("station", "station_time")]` makes polling idempotent —
  running `fetch_aqi` multiple times in the same hour is safe
- `is_wildfire_smoke_likely` on `AQIReading` is a PM2.5 + fire-season heuristic
  (May–Oct, AQI > 100, dominant pollutant = pm25) — useful for UI flagging,
  not authoritative source attribution
- WAQI returns `aqi = "-"` when a station is temporarily offline; the command
  logs an error for that station and continues with the rest
- `dominant_pollutant` uses WAQI's field name `dominentpol` (their typo, preserved)
- Pollutant signatures to watch for construction/industrial events:
  - **PM10** — coarse dust (earthwork, demolition); distinct from PM2.5 smoke
  - **NO2** — diesel exhaust; correlates with truck traffic increases
  - **SO2** — industrial combustion; relevant for diesel generators (data centers)

---

## Baseline monitoring

The baseline period began when the primary sensor was installed. To lock in a
formal pre-construction baseline snapshot:

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

- [x] **TODO 1** — Models + single-station fetch command
- [x] **TODO 2** — Multi-station `Station` model; regional network; `load_stations`
- [x] **TODO 3** — Verify and fix regional station network (18 stations, real WAQI IDs + coordinates)
- [ ] **TODO 4** — Historical backfill via WAQI data platform (lock in full baseline archive)
- [ ] **TODO 5** — Test suite (pytest; models, management commands)
- [ ] **TODO 6** — Dashboard: current AQI, 7-day trend, wildfire smoke highlighting,
      station dropdown, upwind/downwind comparison view
- [ ] **TODO 7** — EPA EJScreen overlay for 48208; socioeconomic context layer
- [ ] **TODO 8** — Baseline deviation alerts: notify when readings exceed
      pre-construction norms by >2σ on PM10, NO2, or SO2
