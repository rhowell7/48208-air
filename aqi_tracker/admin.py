# aqi_tracker/admin.py
from django.contrib import admin

from .models import AQIReading, Station


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "waqi_id", "wind_position", "is_primary", "active"]
    list_filter = ["wind_position", "active", "city"]
    list_editable = ["active"]
    ordering = ["wind_position", "city"]
    readonly_fields = ["waqi_id"]


@admin.register(AQIReading)
class AQIReadingAdmin(admin.ModelAdmin):
    list_display = ["station", "aqi", "dominant_pollutant", "pm25", "station_time"]
    list_filter = ["station", "dominant_pollutant"]
    date_hierarchy = "station_time"
    ordering = ["-station_time"]
    readonly_fields = ["fetched_at"]
