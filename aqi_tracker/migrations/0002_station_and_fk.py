# aqi_tracker/migrations/0002_station_and_fk.py
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aqi_tracker", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Station",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("waqi_id", models.CharField(max_length=20, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("city", models.CharField(max_length=50)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
                ("is_primary", models.BooleanField(default=False)),
                (
                    "wind_position",
                    models.CharField(
                        choices=[
                            ("upwind", "Upwind (early warning)"),
                            ("primary", "Primary station"),
                            ("downwind", "Downwind (plume confirmation)"),
                            ("crosswind", "Crosswind (reference)"),
                        ],
                        default="crosswind",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["wind_position", "city", "name"],
            },
        ),
        # Add nullable FK first so existing rows don't violate NOT NULL
        migrations.AddField(
            model_name="aqireading",
            name="station",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="readings",
                to="aqi_tracker.station",
            ),
        ),
        # Drop the old station_time unique constraint (replaced by unique_together)
        migrations.AlterUniqueTogether(
            name="aqireading",
            unique_together={("station", "station_time")},
        ),
        migrations.AddIndex(
            model_name="aqireading",
            index=models.Index(
                fields=["station", "station_time"],
                name="aqi_reading_station_time_idx",
            ),
        ),
    ]
