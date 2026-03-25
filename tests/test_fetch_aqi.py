import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from django.core.management import call_command
from io import StringIO

from aqi_tracker.models import AQIReading


GOOD_RESPONSE = {
    "status": "ok",
    "data": {
        "aqi": 42,
        "dominentpol": "pm25",
        "time": {"iso": "2025-06-15T14:00:00-04:00"},
        "iaqi": {
            "pm25": {"v": 12.5},
            "pm10": {"v": 20.0},
            "no2": {"v": 8.0},
        },
    },
}

OFFLINE_RESPONSE = {
    "status": "ok",
    "data": {
        "aqi": "-",
        "dominentpol": "",
        "time": {"iso": "2025-06-15T14:00:00-04:00"},
        "iaqi": {},
    },
}


def make_mock_response(payload):
    mock = MagicMock()
    mock.json.return_value = payload
    mock.raise_for_status.return_value = None
    return mock


@pytest.mark.django_db
class TestFetchAqi:
    def test_saves_reading(self, primary_station):
        with patch("requests.get", return_value=make_mock_response(GOOD_RESPONSE)):
            call_command(
                "fetch_aqi", station=primary_station.waqi_id, stdout=StringIO()
            )

        assert AQIReading.objects.filter(station=primary_station).count() == 1
        reading = AQIReading.objects.get(station=primary_station)
        assert reading.aqi == 42
        assert reading.dominant_pollutant == "pm25"
        assert reading.pm25 == 12.5

    def test_idempotent(self, primary_station):
        with patch("requests.get", return_value=make_mock_response(GOOD_RESPONSE)):
            call_command(
                "fetch_aqi", station=primary_station.waqi_id, stdout=StringIO()
            )
            call_command(
                "fetch_aqi", station=primary_station.waqi_id, stdout=StringIO()
            )

        assert AQIReading.objects.filter(station=primary_station).count() == 1

    def test_dry_run_does_not_save(self, primary_station):
        with patch("requests.get", return_value=make_mock_response(GOOD_RESPONSE)):
            call_command(
                "fetch_aqi",
                station=primary_station.waqi_id,
                dry_run=True,
                stdout=StringIO(),
            )

        assert AQIReading.objects.filter(station=primary_station).count() == 0

    def test_offline_station_skipped_gracefully(self, primary_station):
        out = StringIO()
        with patch("requests.get", return_value=make_mock_response(OFFLINE_RESPONSE)):
            call_command("fetch_aqi", station=primary_station.waqi_id, stdout=out)

        assert AQIReading.objects.filter(station=primary_station).count() == 0
        assert "error" in out.getvalue().lower() or "offline" in out.getvalue().lower()

    def test_station_time_stored_in_utc(self, primary_station):
        with patch("requests.get", return_value=make_mock_response(GOOD_RESPONSE)):
            call_command(
                "fetch_aqi", station=primary_station.waqi_id, stdout=StringIO()
            )

        reading = AQIReading.objects.get(station=primary_station)
        assert reading.station_time.tzinfo == timezone.utc
        assert reading.station_time == datetime(2025, 6, 15, 18, 0, tzinfo=timezone.utc)
