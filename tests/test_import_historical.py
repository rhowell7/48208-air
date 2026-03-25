import pytest
from pathlib import Path
from django.core.management import call_command
from io import StringIO

from aqi_tracker.models import AQIReading


# Standard AQICN data platform format (government/EPA stations)
STANDARD_CSV = """\
date, pm25, o3, no2, so2
2024/1/1, 15, 30, 8, 2
2024/1/2, 22, 25, 10, 3
2024/1/3, , 28, 7,
"""

# Direct station download format (community/PurpleAir sensors)
CONCENTRATION_CSV = """\
# Sensor Breckenridge, Detroit (AirNet)
# Daily pm25
date,min,max,median,q1,q3,stdev,count
2024-01-01T00:00:00.000Z,5.1,38.2,12.5,9.0,18.0,6.2,24
2024-01-02T00:00:00.000Z,3.0,25.0,10.0,7.0,15.0,4.1,24
"""


def write_csv(directory: Path, filename: str, content: str) -> Path:
    path = directory / filename
    path.write_text(content)
    return path


@pytest.mark.django_db
class TestImportHistorical:
    def test_standard_format_imports(self, upwind_station, tmp_path):
        write_csv(tmp_path, "ypsilanti-air-quality.csv", STANDARD_CSV)
        out = StringIO()
        call_command("import_historical", dir=tmp_path, stdout=out)

        assert AQIReading.objects.filter(station=upwind_station).count() == 3

    def test_standard_format_null_values(self, upwind_station, tmp_path):
        write_csv(tmp_path, "ypsilanti-air-quality.csv", STANDARD_CSV)
        call_command("import_historical", dir=tmp_path, stdout=StringIO())

        # Third row has blank pm25 and so2 — should still import with nulls
        from datetime import datetime, timezone

        reading = AQIReading.objects.get(
            station=upwind_station,
            station_time=datetime(2024, 1, 3, tzinfo=timezone.utc),
        )
        assert reading.pm25 is None
        assert reading.so2 is None
        assert reading.ozone is not None

    def test_concentration_format_imports(self, primary_station, tmp_path):
        write_csv(tmp_path, "detroit-breckenridge-air-quality.csv", CONCENTRATION_CSV)
        call_command("import_historical", dir=tmp_path, stdout=StringIO())

        assert AQIReading.objects.filter(station=primary_station).count() == 2

    def test_idempotent(self, upwind_station, tmp_path):
        write_csv(tmp_path, "ypsilanti-air-quality.csv", STANDARD_CSV)
        call_command("import_historical", dir=tmp_path, stdout=StringIO())
        call_command("import_historical", dir=tmp_path, stdout=StringIO())

        assert AQIReading.objects.filter(station=upwind_station).count() == 3

    def test_dry_run_does_not_save(self, upwind_station, tmp_path):
        write_csv(tmp_path, "ypsilanti-air-quality.csv", STANDARD_CSV)
        call_command("import_historical", dir=tmp_path, dry_run=True, stdout=StringIO())

        assert AQIReading.objects.filter(station=upwind_station).count() == 0

    def test_unmatched_file_skipped(self, tmp_path):
        write_csv(tmp_path, "unknown-place-air-quality.csv", STANDARD_CSV)
        out = StringIO()
        call_command("import_historical", dir=tmp_path, stdout=out)

        assert AQIReading.objects.count() == 0
