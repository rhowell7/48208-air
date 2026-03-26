import pytest
from datetime import datetime, timezone
from aqi_tracker.models import AQIReading, Station


@pytest.mark.django_db
class TestStation:
    def test_str_primary(self, primary_station):
        assert str(primary_station) == "Detroit - Breckenridge (A548659) [PRIMARY]"

    def test_str_non_primary(self, upwind_station):
        assert str(upwind_station) == "Ypsilanti (@5335)"

    def test_only_one_primary(self, primary_station, upwind_station):
        assert Station.objects.filter(is_primary=True).count() == 1


@pytest.mark.django_db
class TestAQIReadingCategory:
    def _reading(self, station, aqi):
        return AQIReading(
            station=station,
            aqi=aqi,
            station_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

    def test_good(self, primary_station):
        assert self._reading(primary_station, 50).category == "Good"

    def test_moderate(self, primary_station):
        assert self._reading(primary_station, 51).category == "Moderate"

    def test_sensitive_groups(self, primary_station):
        assert (
            self._reading(primary_station, 101).category
            == "Unhealthy for Sensitive Groups"
        )

    def test_unhealthy(self, primary_station):
        assert self._reading(primary_station, 151).category == "Unhealthy"

    def test_very_unhealthy(self, primary_station):
        assert self._reading(primary_station, 201).category == "Very Unhealthy"

    def test_hazardous(self, primary_station):
        assert self._reading(primary_station, 301).category == "Hazardous"


@pytest.mark.django_db
class TestWildFireSmokeHeuristic:
    def _reading(self, station, aqi, month, pollutant="pm25"):
        return AQIReading(
            station=station,
            aqi=aqi,
            dominant_pollutant=pollutant,
            station_time=datetime(2025, month, 1, tzinfo=timezone.utc),
        )

    def test_smoke_likely(self, primary_station):
        assert (
            self._reading(primary_station, 150, month=7).is_wildfire_smoke_likely
            is True
        )

    def test_aqi_too_low(self, primary_station):
        assert (
            self._reading(primary_station, 99, month=7).is_wildfire_smoke_likely
            is False
        )

    def test_wrong_pollutant(self, primary_station):
        assert (
            self._reading(
                primary_station, 150, month=7, pollutant="o3"
            ).is_wildfire_smoke_likely
            is False
        )

    def test_outside_fire_season(self, primary_station):
        assert (
            self._reading(primary_station, 150, month=1).is_wildfire_smoke_likely
            is False
        )

    def test_boundary_month_may(self, primary_station):
        assert (
            self._reading(primary_station, 150, month=5).is_wildfire_smoke_likely
            is True
        )

    def test_boundary_month_october(self, primary_station):
        assert (
            self._reading(primary_station, 150, month=10).is_wildfire_smoke_likely
            is True
        )
