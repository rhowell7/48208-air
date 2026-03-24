# aqi_tracker/management/commands/import_historical.py
"""
Import historical AQI data from CSV files downloaded from aqicn.org.

Usage:
    python manage.py import_historical
    python manage.py import_historical --dir /path/to/csvs
    python manage.py import_historical --dry-run

Two CSV formats are supported:

  Standard (aqicn.org data platform):
    Columns: date, pm25[, pm10, o3, no2, so2, co]
    Date format: YYYY/M/D
    Values are AQI sub-index values (0–500 scale).
    Overall AQI = max sub-index; dominant pollutant = which drove it.

  Breckenridge (direct station download from aqicn.org/station/@548659/):
    Columns: date, min, max, median, q1, q3, stdev, count
    Date format: ISO 8601
    Values are PM2.5 concentrations (µg/m³) — converted to AQI via EPA breakpoints.
    Median is used as the representative daily value.

All readings are stored at midnight UTC. Idempotent: safe to re-run.
Data sourced from the World Air Quality Index Project (waqi.info) and
originating EPA agencies. Data is unvalidated and subject to change.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from aqi_tracker.models import AQIReading, Station

# Maps CSV filename → Station.waqi_id
FILE_TO_WAQI_ID = {
    "allen-park-air-quality.csv":                          "@5322",
    "ann-arbor-northside-air-quality.csv":                 "A563443",
    "ann-arbor-sugarbush-park-air-quality.csv":            "A554191",
    "ann-arbor-veterans-memorial-park-air-quality.csv":    "A490177",
    "ann-arbor-wastewater-treatment-plant-air-quality.csv":"A554200",
    "ann-arbor-water-treatment-plant-air-quality.csv":     "A554188",
    "dearborn-air-quality.csv":                            "@5324",
    "detroit-breckenridge-air-quality.csv":                "A548659",
    "detroit-southwest-air-quality.csv":                   "@12851",
    "detroit-w-lafayette-air-quality.csv":                 "@5325",
    "grosse-pointe-air-quality.csv":                       "A547657",
    "hamtramck-east-air-quality.csv":                      "A1089652",
    "hamtramck-north-air-quality.csv":                     "A1089643",
    "hamtramck-south-air-quality.csv":                     "A1089649",
    "hamtramck-west-air-quality.csv":                      "A1089646",
    "oak-park-air-quality.csv":                            "A500233",
    "windsor-air-quality.csv":                             "@5915",
    "windsor-downtown-air-quality.csv":                    "@38",
    "windsor-west-air-quality.csv":                        "@39",
    "ypsilanti-air-quality.csv":                           "@5335",
}

# EPA PM2.5 24-hour AQI breakpoints: (conc_lo, conc_hi, aqi_lo, aqi_hi)
_PM25_BREAKPOINTS = [
    (0.0,   12.0,  0,   50),
    (12.1,  35.4,  51,  100),
    (35.5,  55.4,  101, 150),
    (55.5,  150.4, 151, 200),
    (150.5, 250.4, 201, 300),
    (250.5, 350.4, 301, 400),
    (350.5, 500.4, 401, 500),
]


def pm25_to_aqi(concentration: float) -> int:
    """Convert PM2.5 concentration (µg/m³) to AQI using EPA linear interpolation."""
    for bp_lo, bp_hi, aqi_lo, aqi_hi in _PM25_BREAKPOINTS:
        if bp_lo <= concentration <= bp_hi:
            return round(
                (aqi_hi - aqi_lo) / (bp_hi - bp_lo) * (concentration - bp_lo) + aqi_lo
            )
    return 500  # cap at top of hazardous range


def _float(value: str):
    """Parse a CSV cell to float, returning None for blank/invalid values."""
    try:
        return float(value.strip()) if value.strip() else None
    except ValueError:
        return None


class Command(BaseCommand):
    help = "Import historical AQI data from aqicn.org CSV files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dir",
            type=Path,
            default=Path(settings.BASE_DIR) / "historical_data",
            help="Directory containing the CSV files (default: BASE_DIR/historical_data).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and count rows without writing to the database.",
        )

    def handle(self, *args, **options):
        data_dir: Path = options["dir"]
        dry_run: bool = options["dry_run"]

        if not data_dir.exists():
            self.stdout.write(self.style.ERROR(f"Directory not found: {data_dir}"))
            return

        stations = {s.waqi_id: s for s in Station.objects.all()}
        total_saved = total_skipped = total_errors = 0

        for filename, waqi_id in FILE_TO_WAQI_ID.items():
            path = data_dir / filename
            if not path.exists():
                self.stdout.write(self.style.WARNING(f"  Missing: {filename}"))
                continue

            station = stations.get(waqi_id)
            if not station:
                self.stdout.write(
                    self.style.WARNING(f"  No station for {waqi_id} — run load_stations first.")
                )
                continue

            saved, skipped, errors = self._import_file(path, station, dry_run)
            total_saved += saved
            total_skipped += skipped
            total_errors += errors
            label = "DRY RUN " if dry_run else ""
            self.stdout.write(
                f"  {label}{station.name}: {saved} saved, {skipped} skipped, {errors} errors"
            )

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {total_saved} saved, {total_skipped} skipped, {total_errors} errors."
        ))

    def _import_file(self, path: Path, station: Station, dry_run: bool):
        saved = skipped = errors = 0

        with open(path, newline="", encoding="utf-8") as f:
            lines = [line for line in f if not line.startswith("#")]

        reader = csv.DictReader(lines)
        # Detect format from column headers: concentration format has 'median',
        # standard platform format has pollutant columns (pm25, o3, etc.)
        is_concentration_format = "median" in (reader.fieldnames or [])

        for row in reader:
            try:
                row = {k.strip(): v.strip() for k, v in row.items()}
                if is_concentration_format:
                    reading = self._parse_breckenridge(row, station)
                else:
                    reading = self._parse_standard(row, station)

                if reading is None:
                    skipped += 1
                    continue

                if dry_run:
                    saved += 1
                    continue

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
                    },
                )
                saved += 1 if created else 0
                skipped += 0 if created else 1

            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f"    Row error ({e}): {dict(row)}"))

        return saved, skipped, errors

    @staticmethod
    def _parse_standard(row: dict, station: Station):
        """
        Parse aqicn.org data platform format.
        Values on the 0–500 AQI sub-index scale; overall AQI = highest sub-index.
        """
        date_str = row.get("date", "")
        if not date_str:
            return None

        station_time = datetime.strptime(date_str, "%Y/%m/%d").replace(tzinfo=timezone.utc)

        pollutants = {
            "pm25":  _float(row.get("pm25", "")),
            "pm10":  _float(row.get("pm10", "")),
            "ozone": _float(row.get("o3", "")),
            "no2":   _float(row.get("no2", "")),
            "so2":   _float(row.get("so2", "")),
            "co":    _float(row.get("co", "")),
        }

        non_null = {k: v for k, v in pollutants.items() if v is not None}
        if not non_null:
            return None

        dominant = max(non_null, key=lambda k: non_null[k])
        aqi = int(max(non_null.values()))

        return AQIReading(station=station, station_time=station_time,
                          aqi=aqi, dominant_pollutant=dominant, **pollutants)

    @staticmethod
    def _parse_breckenridge(row: dict, station: Station):
        """
        Parse direct station download format (PM2.5 concentrations in µg/m³).
        Uses daily median as the representative value; converts to AQI.
        """
        date_str = row.get("date", "")
        if not date_str:
            return None

        station_time = (
            datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            .astimezone(timezone.utc)
        )

        median_pm25 = _float(row.get("median", ""))
        if median_pm25 is None:
            return None

        return AQIReading(
            station=station,
            station_time=station_time,
            aqi=pm25_to_aqi(median_pm25),
            dominant_pollutant="pm25",
            pm25=median_pm25,
        )