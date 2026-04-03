# aqi_tracker/views.py
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from django.shortcuts import render

from .models import AQIReading, Station

DETROIT_TZ = ZoneInfo("America/Detroit")

# EPA standard AQI color scale
AQI_COLORS = {
    "Good": "#00e400",
    "Moderate": "#ffff00",
    "Unhealthy for Sensitive Groups": "#ff7e00",
    "Unhealthy": "#ff0000",
    "Very Unhealthy": "#8f3f97",
    "Hazardous": "#7e0023",
}

# Max values used to normalize pollutant bar widths (not EPA thresholds, just visual scale)
POLLUTANT_MAXES = {
    "PM2.5": 150,
    "PM10": 350,
    "Ozone": 200,
    "NO₂": 200,
    "SO₂": 300,
}


def _weekly_readings(readings_qs, days=7):
    """Individual readings for the last N days as {x: UTC ISO, y: aqi} for the time-scale chart."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [
        {"x": r.station_time.isoformat(), "y": r.aqi}
        for r in readings_qs.filter(station_time__gte=cutoff).order_by("station_time")
    ]


def _night_bands(tz, days=7):
    """
    Night periods (9 PM–6 AM local) for the last N days, as UTC ISO strings.
    Generates enough bands to cover chart edges.
    """
    today = date.today()
    bands = []
    for i in range(-1, days + 1):
        day = today - timedelta(days=i)
        next_day = day + timedelta(days=1)
        night_start = datetime(day.year, day.month, day.day, 21, 0, tzinfo=tz)
        night_end = datetime(
            next_day.year, next_day.month, next_day.day, 6, 0, tzinfo=tz
        )
        bands.append(
            {
                "from": night_start.astimezone(timezone.utc).isoformat(),
                "to": night_end.astimezone(timezone.utc).isoformat(),
            }
        )
    return bands


def _timeline_frames(tz, days=7):
    """
    Returns a chronologically-ordered list of hourly frames for the map scrubber.
    Each frame: {ts, label, stations: {waqi_id: {aqi, category, color}}}.
    Readings are bucketed by truncating station_time to the hour; the last
    reading within each hour wins (most up-to-date value).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    qs = (
        AQIReading.objects.filter(station__active=True, station_time__gte=cutoff)
        .select_related("station")
        .order_by("station_time")
    )

    # {hour_dt: {waqi_id: {aqi, category, color}}}
    buckets = defaultdict(dict)
    for r in qs:
        hour = r.station_time.replace(minute=0, second=0, microsecond=0)
        category = r.category
        buckets[hour][r.station.waqi_id] = {
            "aqi": r.aqi,
            "category": category,
            "color": AQI_COLORS.get(category, "#aaaaaa"),
        }

    frames = []
    for hour in sorted(buckets):
        frames.append(
            {
                "ts": hour.isoformat(),
                "label": hour.astimezone(tz).strftime("%b %-d, %-I:%M %p ET"),
                "stations": buckets[hour],
            }
        )
    return frames


def _yearly_daily_maxes(readings_qs, tz):
    """Daily peak AQI for the past year as {x: date ISO, y: max_aqi}.

    Companion to _yearly_daily_averages. Shows the worst single reading each
    day, which is more sensitive to short-duration events (garbage burning,
    passing trucks, industrial incidents) than the daily average.
    """
    cutoff = date.today() - timedelta(days=365)
    buckets = defaultdict(list)
    for r in readings_qs.filter(station_time__date__gte=cutoff).order_by(
        "station_time"
    ):
        key = r.station_time.astimezone(tz).date().isoformat()
        buckets[key].append(r.aqi)
    return [{"x": k, "y": max(v)} for k, v in sorted(buckets.items())]


def _yearly_daily_averages(readings_qs, tz):
    """Daily averages for the past year as {x: date ISO, y: avg_aqi}.

    Uses the same {x, y} format as _weekly_readings so both charts share the
    same Chart.js time-axis configuration. Daily granularity preserves smoke
    spikes that monthly averaging would hide.
    """
    cutoff = date.today() - timedelta(days=365)
    buckets = defaultdict(list)
    for r in readings_qs.filter(station_time__date__gte=cutoff).order_by(
        "station_time"
    ):
        key = r.station_time.astimezone(tz).date().isoformat()
        buckets[key].append(r.aqi)
    return [{"x": k, "y": round(sum(v) / len(v))} for k, v in sorted(buckets.items())]


def dashboard(request):
    waqi_id = request.GET.get("station")
    station = None
    if waqi_id:
        station = Station.objects.filter(waqi_id=waqi_id, active=True).first()
    if not station:
        station = Station.objects.filter(is_primary=True).first()

    readings = station.readings
    latest = readings.first()

    earliest = (
        readings.order_by("station_time").values_list("station_time", flat=True).first()
    )
    on_record_since = (
        earliest.astimezone(DETROIT_TZ).strftime("%b %Y") if earliest else None
    )

    current_year = date.today().year
    unhealthy_days = (
        readings.filter(
            station_time__year=current_year,
            aqi__gt=100,
        )
        .dates("station_time", "day")
        .count()
    )

    weekly_data = _weekly_readings(readings, 7)
    yearly_data = _yearly_daily_averages(readings, DETROIT_TZ)
    night_bands = _night_bands(DETROIT_TZ)

    stations_map = []
    for s in Station.objects.filter(active=True):
        r = s.readings.first()
        category = r.category if r else "No data"
        stations_map.append(
            {
                "waqi_id": s.waqi_id,
                "name": s.name,
                "lat": s.latitude,
                "lng": s.longitude,
                "aqi": r.aqi if r else None,
                "category": category,
                "color": AQI_COLORS.get(category, "#aaaaaa"),
                "is_selected": s.waqi_id == station.waqi_id,
            }
        )

    pollutants = []
    if latest:
        raw = [
            ("PM2.5", latest.pm25, "µg/m³"),
            ("PM10", latest.pm10, "µg/m³"),
            ("Ozone", latest.ozone, "ppb"),
            ("NO₂", latest.no2, "ppb"),
            ("SO₂", latest.so2, "ppb"),
        ]
        for label, value, unit in raw:
            max_val = POLLUTANT_MAXES[label]
            pct = min(100, round(value / max_val * 100)) if value is not None else None
            pollutants.append((label, value, unit, pct))

    context = {
        "station": station,
        "latest": latest,
        "on_record_since": on_record_since,
        "unhealthy_days": unhealthy_days,
        "current_year": current_year,
        "weekly_data": weekly_data,
        "yearly_data": yearly_data,
        "peak_data": _yearly_daily_maxes(readings, DETROIT_TZ),
        "night_bands": night_bands,
        "stations_map": stations_map,
        "timeline_frames": _timeline_frames(DETROIT_TZ),
        "all_stations": Station.objects.filter(active=True).order_by("name"),
        "pollutants": pollutants,
    }
    return render(request, "aqi_tracker/dashboard.html", context)
