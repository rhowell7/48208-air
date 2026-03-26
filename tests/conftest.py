import pytest
from aqi_tracker.models import Station


@pytest.fixture
def primary_station(db):
    return Station.objects.create(
        waqi_id="A548659",
        name="Detroit - Breckenridge",
        city="Detroit",
        latitude=42.3565,
        longitude=-83.0942,
        is_primary=True,
        wind_position=Station.WindPosition.PRIMARY,
    )


@pytest.fixture
def upwind_station(db):
    return Station.objects.create(
        waqi_id="@5335",
        name="Ypsilanti",
        city="Ypsilanti",
        latitude=42.2400,
        longitude=-83.5997,
        wind_position=Station.WindPosition.UPWIND,
    )
