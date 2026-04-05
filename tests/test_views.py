from datetime import date, datetime, timezone

import pytest

from aqi_tracker.models import AQIReading

_today = date.today()


def make_reading(
    station, aqi, *, month=_today.month, day=_today.day, hour=12, **kwargs
):
    return AQIReading.objects.create(
        station=station,
        aqi=aqi,
        station_time=datetime(_today.year, month, day, hour, 0, tzinfo=timezone.utc),
        **kwargs,
    )


@pytest.mark.django_db
class TestDashboardView:
    def test_loads_primary_station_by_default(self, client, primary_station):
        response = client.get("/")
        assert response.status_code == 200
        assert response.context["station"] == primary_station

    def test_station_switcher(self, client, primary_station, upwind_station):
        response = client.get(f"/?station={upwind_station.waqi_id}")
        assert response.status_code == 200
        assert response.context["station"] == upwind_station

    def test_invalid_station_falls_back_to_primary(self, client, primary_station):
        response = client.get("/?station=@nonexistent")
        assert response.status_code == 200
        assert response.context["station"] == primary_station

    def test_latest_reading_in_context(self, client, primary_station):
        reading = make_reading(primary_station, 42, pm25=9.4, dominant_pollutant="pm25")
        response = client.get("/")
        assert response.context["latest"] == reading

    def test_no_readings_renders_gracefully(self, client, primary_station):
        response = client.get("/")
        assert response.status_code == 200
        assert response.context["latest"] is None
        assert response.context["on_record_since"] is None

    def test_on_record_since_uses_earliest_reading(self, client, primary_station):
        make_reading(primary_station, 50, month=1, day=1)  # later reading first
        AQIReading.objects.create(
            station=primary_station,
            aqi=45,
            station_time=datetime(2014, 6, 1, 12, tzinfo=timezone.utc),
        )
        response = client.get("/")
        assert response.context["on_record_since"] == "Jun 2014"

    def test_unhealthy_days_counts_qualifying_days(self, client, primary_station):
        # Counts: any AQI > 100, any pollutant, any month in current year
        make_reading(primary_station, 150, month=3, day=1)
        make_reading(primary_station, 150, month=7, day=4)
        # Does not count: AQI too low
        make_reading(primary_station, 80, month=7, day=5)
        response = client.get("/")
        assert response.context["unhealthy_days"] == 2

    def test_unhealthy_days_counts_distinct_days_not_readings(
        self, client, primary_station
    ):
        # Two readings on the same day should count as one unhealthy day
        make_reading(primary_station, 150, month=7, day=4, hour=6)
        make_reading(primary_station, 160, month=7, day=4, hour=18)
        response = client.get("/")
        assert response.context["unhealthy_days"] == 1

    def test_map_contains_all_active_stations(
        self, client, primary_station, upwind_station
    ):
        response = client.get("/")
        stations = response.context["stations_map"]
        waqi_ids = {s["waqi_id"] for s in stations}
        assert primary_station.waqi_id in waqi_ids
        assert upwind_station.waqi_id in waqi_ids

    def test_map_selected_station_flagged(
        self, client, primary_station, upwind_station
    ):
        response = client.get(f"/?station={upwind_station.waqi_id}")
        stations = response.context["stations_map"]
        selected = [s for s in stations if s["is_selected"]]
        assert len(selected) == 1
        assert selected[0]["waqi_id"] == upwind_station.waqi_id

    def test_map_includes_aqi_and_color(self, client, primary_station):
        make_reading(primary_station, 42)
        response = client.get("/")
        stations = response.context["stations_map"]
        primary = next(s for s in stations if s["waqi_id"] == primary_station.waqi_id)
        assert primary["aqi"] == 42
        assert primary["color"].startswith("#")

    def test_weekly_data_is_individual_readings(self, client, primary_station):
        # weekly_data passes every reading to Chart.js as {x: ISO timestamp, y: aqi}
        make_reading(primary_station, 40, hour=6)
        make_reading(primary_station, 60, hour=18)
        response = client.get("/")
        weekly = response.context["weekly_data"]
        assert len(weekly) == 2
        assert all("x" in d and "y" in d for d in weekly)
        assert weekly[0]["y"] == 40
        assert weekly[1]["y"] == 60

    def test_yearly_data_is_daily_averages(self, client, primary_station):
        # Two readings on the same day should be averaged into one {x, y} entry
        make_reading(primary_station, 40, month=1, day=10, hour=6)
        make_reading(primary_station, 60, month=1, day=10, hour=18)
        make_reading(primary_station, 80, month=1, day=11)
        response = client.get("/")
        yearly = response.context["yearly_data"]
        assert all("x" in d and "y" in d for d in yearly)
        jan10 = next(d for d in yearly if d["x"] == "2026-01-10")
        assert jan10["y"] == 50  # average of 40 and 60
        jan11 = next(d for d in yearly if d["x"] == "2026-01-11")
        assert jan11["y"] == 80

    def test_pollutants_list_has_five_entries(self, client, primary_station):
        make_reading(primary_station, 50, pm25=9.4, pm10=18.0, no2=12.0)
        response = client.get("/")
        assert len(response.context["pollutants"]) == 5

    def test_pollutant_pct_clamped_at_100(self, client, primary_station):
        make_reading(primary_station, 300, pm25=9999.0)
        response = client.get("/")
        pm25 = next(p for p in response.context["pollutants"] if p[0] == "PM2.5")
        assert pm25[3] == 100

    def test_pollutant_pct_none_when_value_missing(self, client, primary_station):
        make_reading(primary_station, 50)  # no pollutant values
        response = client.get("/")
        pm25 = next(p for p in response.context["pollutants"] if p[0] == "PM2.5")
        assert pm25[3] is None

    def test_no_pollutants_when_no_latest(self, client, primary_station):
        response = client.get("/")
        assert response.context["pollutants"] == []
