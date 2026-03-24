# aqi_tracker/migrations/0001_initial.py
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AQIReading",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("aqi", models.IntegerField()),
                ("dominant_pollutant", models.CharField(blank=True, max_length=20)),
                ("pm25", models.FloatField(blank=True, null=True)),
                ("pm10", models.FloatField(blank=True, null=True)),
                ("ozone", models.FloatField(blank=True, null=True)),
                ("no2", models.FloatField(blank=True, null=True)),
                ("so2", models.FloatField(blank=True, null=True)),
                ("co", models.FloatField(blank=True, null=True)),
                ("temperature_c", models.FloatField(blank=True, null=True)),
                ("humidity", models.FloatField(blank=True, null=True)),
                ("wind_speed", models.FloatField(blank=True, null=True)),
                ("station_time", models.DateTimeField(unique=True)),
                ("fetched_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-station_time"],
            },
        ),
        migrations.AddIndex(
            model_name="aqireading",
            index=models.Index(fields=["station_time"], name="aqi_reading_station_idx"),
        ),
    ]
