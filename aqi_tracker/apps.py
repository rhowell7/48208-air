# aqi_tracker/apps.py
from django.apps import AppConfig


class AqiTrackerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "aqi_tracker"
    verbose_name = "AQI Tracker"
