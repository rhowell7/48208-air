# aqi_tracker/management/commands/fetch_aqi.py
"""
Fetch the latest reading for every active station in the network
and persist to the database.

Usage:
    python manage.py fetch_aqi                    # all active stations
    python manage.py fetch_aqi --station @548659  # one specific station
    python manage.py fetch_aqi --dry-run          # print without saving

Cron (hourly):
    0 * * * * /path/to/venv/bin/python /path/to/manage.py fetch_aqi
"""

import logging
import time
import zoneinfo
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from aqi_tracker.models import AQIReading, Station

logger = logging.getLogger(__name__)

WAQI_FEED_URL = "https://api.waqi.info/feed/{}/"
INTER_REQUEST_DELAY_SECONDS = 1.5  # polite pacing between station requests


class Command(BaseCommand):
    help = "Fetch latest AQI readings for all active stations in the network."

    def add_arguments(self, parser):
        parser.add_argument(
            "--station",
            type=str,
            help="Fetch only this station (waqi_id, e.g. @548659).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and print without saving to the database.",
        )

    def handle(self, *args, **options):
        token = getattr(settings, "WAQI_API_TOKEN", None)
        if not token:
            raise CommandError(
                "WAQI_API_TOKEN not set. Get a free token at aqicn.org/api/ "
                "and add it to your settings or .env."
            )

        stations = Station.objects.filter(active=True)
        if options["station"]:
            stations = stations.filter(waqi_id=options["station"])
            if not stations.exists():
                raise CommandError(
                    f"No active station found with waqi_id={options['station']}. "
                    "Run load_stations first."
                )

        if not stations.exists():
            self.stdout.write(
                self.style.WARNING("No active stations found. Run load_stations first.")
            )
            return

        now = datetime.now(zoneinfo.ZoneInfo("America/Detroit")).strftime(
            "%Y-%m-%d %H:%M %Z"
        )
        self.stdout.write(f"\n=== fetch_aqi {now} ===")
        self.stdout.write(f"Fetching {stations.count()} station(s)...")
        results = {"saved": 0, "skipped": 0, "errors": 0}

        for i, station in enumerate(stations):
            if i > 0:
                time.sleep(INTER_REQUEST_DELAY_SECONDS)
            try:
                self._fetch_station(station, token, options["dry_run"], results)
            except Exception as e:
                results["errors"] += 1
                logger.error(f"Failed to fetch {station}: {e}")
                self.stdout.write(self.style.ERROR(f"  ERROR {station.name}: {e}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nComplete: {results['saved']} saved, "
                f"{results['skipped']} skipped (already exists), "
                f"{results['errors']} errors."
            )
        )

    def _fetch_station(self, station, token, dry_run, results):
        url = WAQI_FEED_URL.format(station.waqi_id)
        response = requests.get(url, params={"token": token}, timeout=10)
        response.raise_for_status()

        data = response.json()
        inner = data.get("data", {})
        if data.get("status") != "ok" or (
            isinstance(inner, dict) and inner.get("status") == "error"
        ):
            msg = (
                inner.get("msg")
                if isinstance(inner, dict)
                else data.get("data", "unknown")
            )
            raise ValueError(
                f"API error: {msg}. "
                "Station ID may be wrong — check waqi_id in load_stations.py."
            )

        reading = self._parse_response(station, inner)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"  DRY RUN {station.name}: {reading}")
            )
            return

        _, created = AQIReading.objects.get_or_create(
            station=station,
            station_time=reading.station_time,
            defaults={
                "aqi": reading.aqi,
                "dominant_pollutant": reading.dominant_pollutant,
                "pm25": reading.pm25,
                "pm10": reading.pm10,
                "ozone": reading.ozone,
                "no2": reading.no2,
                "so2": reading.so2,
                "co": reading.co,
                "temperature_c": reading.temperature_c,
                "humidity": reading.humidity,
                "wind_speed": reading.wind_speed,
            },
        )

        if created:
            results["saved"] += 1
            flag = " [SMOKE?]" if reading.is_wildfire_smoke_likely else ""
            self.stdout.write(
                self.style.SUCCESS(f"  Saved {station.name}: AQI {reading.aqi}{flag}")
            )
        else:
            results["skipped"] += 1
            self.stdout.write(
                f"  Skipped {station.name}: {reading.station_time} already recorded."
            )

    @staticmethod
    def _parse_response(station, data):
        def iaqi(key):
            return data.get("iaqi", {}).get(key, {}).get("v")

        aqi_raw = data.get("aqi")
        if aqi_raw == "-":
            raise ValueError("Station offline (aqi='-').")

        station_time = datetime.fromisoformat(data["time"]["iso"]).astimezone(
            timezone.utc
        )

        return AQIReading(
            station=station,
            aqi=int(aqi_raw),
            dominant_pollutant=data.get("dominentpol", ""),
            station_time=station_time,
            pm25=iaqi("pm25"),
            pm10=iaqi("pm10"),
            ozone=iaqi("o3"),
            no2=iaqi("no2"),
            so2=iaqi("so2"),
            co=iaqi("co"),
            temperature_c=iaqi("t"),
            humidity=iaqi("h"),
            wind_speed=iaqi("w"),
        )
