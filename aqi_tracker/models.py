# aqi_tracker/models.py
from django.db import models


class Station(models.Model):
    """
    A WAQI monitoring station in the Detroit regional network.
    Seed these via the load_stations management command or Django admin.
    """

    waqi_id = models.CharField(max_length=20, unique=True)  # e.g. "@548659"
    name = models.CharField(max_length=100)  # e.g. "Detroit - Breckenridge"
    city = models.CharField(max_length=50)
    latitude = models.FloatField()
    longitude = models.FloatField()

    # Our backyard sensor — drives the "home" view and baseline tracking
    is_primary = models.BooleanField(default=False)

    # Rough wind relationship to primary station, for UI labeling
    class WindPosition(models.TextChoices):
        UPWIND = "upwind", "Upwind (early warning)"
        PRIMARY = "primary", "Primary station"
        DOWNWIND = "downwind", "Downwind (plume confirmation)"
        CROSSWIND = "crosswind", "Crosswind (reference)"

    wind_position = models.CharField(
        max_length=20,
        choices=WindPosition.choices,
        default=WindPosition.CROSSWIND,
    )

    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["wind_position", "city", "name"]

    def __str__(self):
        marker = " [PRIMARY]" if self.is_primary else ""
        return f"{self.name} ({self.waqi_id}){marker}"


class AQIReading(models.Model):
    """
    A single hourly reading from any station in the network.
    """

    station = models.ForeignKey(
        Station,
        on_delete=models.CASCADE,
        related_name="readings",
    )

    aqi = models.IntegerField()
    dominant_pollutant = models.CharField(max_length=20, blank=True)

    pm25 = models.FloatField(null=True, blank=True)
    pm10 = models.FloatField(null=True, blank=True)
    ozone = models.FloatField(null=True, blank=True)
    no2 = models.FloatField(null=True, blank=True)
    so2 = models.FloatField(null=True, blank=True)
    co = models.FloatField(null=True, blank=True)

    temperature_c = models.FloatField(null=True, blank=True)
    humidity = models.FloatField(null=True, blank=True)
    wind_speed = models.FloatField(null=True, blank=True)

    station_time = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-station_time"]
        # One reading per station per timestamp — idempotent polling
        unique_together = [("station", "station_time")]
        indexes = [
            models.Index(fields=["station", "station_time"]),
            models.Index(fields=["station_time"]),
        ]

    def __str__(self):
        return (
            f"AQI {self.aqi} @ {self.station.name} "
            f"{self.station_time:%Y-%m-%d %H:%M} ({self.dominant_pollutant})"
        )

    @property
    def category(self):
        if self.aqi <= 50:
            return "Good"
        if self.aqi <= 100:
            return "Moderate"
        if self.aqi <= 150:
            return "Unhealthy for Sensitive Groups"
        if self.aqi <= 200:
            return "Unhealthy"
        if self.aqi <= 300:
            return "Very Unhealthy"
        return "Hazardous"

    @property
    def is_wildfire_smoke_likely(self):
        """
        PM2.5-dominant reading above AQI 100 during Canadian fire season.
        Especially meaningful on upwind stations (Ann Arbor, Ypsilanti)
        where it can serve as a leading indicator for 48208.
        """
        return (
            self.dominant_pollutant == "pm25"
            and self.aqi > 100
            and self.station_time.month in range(5, 11)
        )
