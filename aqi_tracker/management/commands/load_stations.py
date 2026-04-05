# aqi_tracker/management/commands/load_stations.py
"""
Seeds the Station table with the Detroit regional monitoring network.

Run once after initial migration:
    python manage.py load_stations

Safe to re-run — uses update_or_create so existing records are updated,
not duplicated. Set a station's active=False in the admin to stop polling it
without losing its historical readings.

Wind positions are relative to 48208 with prevailing SW→NE winds:
  UPWIND    = west/northwest — Ann Arbor (5 sensors), Ypsilanti
  PRIMARY   = our backyard sensor
  CROSSWIND = roughly N/S — Dearborn, Allen Park, Oak Park, Hamtramck cluster
  DOWNWIND  = east/southeast — Windsor (3 sensors), Grosse Pointe

Note on WAQI IDs: government/EPA stations use @numeric IDs; community/
PurpleAir sensors use A-prefix IDs (e.g. A547657). Both are supported by
the WAQI API feed endpoint.

All IDs and coordinates verified against the WAQI API, March 2026.
"""

from django.core.management.base import BaseCommand

from aqi_tracker.models import Station

STATIONS = [
    # ── Primary ──────────────────────────────────────────────────────────────
    {
        "waqi_id": "A548659",
        "name": "Detroit - Core City",
        "city": "Detroit",
        "latitude": 42.3565,
        "longitude": -83.0942,
        "is_primary": True,
        "wind_position": Station.WindPosition.PRIMARY,
        "notes": "Backyard GAIA A12 sensor, Core City neighborhood, 48208. "
        "Only community air sensor in Detroit proper.",
    },
    # ── Upwind (early warning — smoke arrives here before 48208) ─────────────
    {
        "waqi_id": "@5335",
        "name": "Ypsilanti",
        "city": "Ypsilanti",
        "latitude": 42.2400,
        "longitude": -83.5997,
        "is_primary": False,
        "wind_position": Station.WindPosition.UPWIND,
        "notes": "~25mi upwind. Eastern Michigan University area.",
    },
    {
        "waqi_id": "A554191",
        "name": "Ann Arbor - Sugarbush Park",
        "city": "Ann Arbor",
        "latitude": 42.3148,
        "longitude": -83.6975,
        "is_primary": False,
        "wind_position": Station.WindPosition.UPWIND,
        "notes": "~45mi upwind. Community PurpleAir sensor.",
    },
    {
        "waqi_id": "A563443",
        "name": "Ann Arbor - Northside",
        "city": "Ann Arbor",
        "latitude": 42.2983,
        "longitude": -83.7347,
        "is_primary": False,
        "wind_position": Station.WindPosition.UPWIND,
        "notes": "Northside Community Center. ~45mi upwind.",
    },
    {
        "waqi_id": "A490177",
        "name": "Ann Arbor - Veterans Memorial Park",
        "city": "Ann Arbor",
        "latitude": 42.2812,
        "longitude": -83.7778,
        "is_primary": False,
        "wind_position": Station.WindPosition.UPWIND,
        "notes": "~45mi upwind.",
    },
    {
        "waqi_id": "A554188",
        "name": "Ann Arbor - Water Treatment Plant",
        "city": "Ann Arbor",
        "latitude": 42.2963,
        "longitude": -83.7623,
        "is_primary": False,
        "wind_position": Station.WindPosition.UPWIND,
        "notes": "~45mi upwind. Municipal infrastructure site.",
    },
    {
        "waqi_id": "A554200",
        "name": "Ann Arbor - Wastewater Treatment Plant",
        "city": "Ann Arbor",
        "latitude": 42.2699,
        "longitude": -83.6632,
        "is_primary": False,
        "wind_position": Station.WindPosition.UPWIND,
        "notes": "~40mi upwind. Municipal infrastructure site.",
    },
    # ── Crosswind (industrial comparison reference) ──────────────────────────
    {
        "waqi_id": "@5324",
        "name": "Dearborn",
        "city": "Dearborn",
        "latitude": 42.3075,
        "longitude": -83.1500,
        "is_primary": False,
        "wind_position": Station.WindPosition.CROSSWIND,
        "notes": "Near Ford Rouge Complex. Heavy industrial baseline — useful "
        "for separating regional smoke events from local industrial sources.",
    },
    {
        "waqi_id": "@5322",
        "name": "Allen Park",
        "city": "Allen Park",
        "latitude": 42.2283,
        "longitude": -83.2092,
        "is_primary": False,
        "wind_position": Station.WindPosition.CROSSWIND,
        "notes": "South of Dearborn, near industrial corridor.",
    },
    {
        "waqi_id": "A500233",
        "name": "Oak Park",
        "city": "Oak Park",
        "latitude": 42.4631,
        "longitude": -83.1833,
        "is_primary": False,
        "wind_position": Station.WindPosition.CROSSWIND,
        "notes": "North of Detroit. Community PurpleAir sensor.",
    },
    {
        "waqi_id": "A1089643",
        "name": "Hamtramck - North",
        "city": "Hamtramck",
        "latitude": 42.4218,
        "longitude": -83.0670,
        "is_primary": False,
        "wind_position": Station.WindPosition.CROSSWIND,
        "notes": "One of 4 sensors placed around Factory ZERO (GM EV assembly). "
        "Community EJ monitoring cluster. Compare with 48208 for "
        "cumulative industrial burden picture.",
    },
    {
        "waqi_id": "A1089649",
        "name": "Hamtramck - South",
        "city": "Hamtramck",
        "latitude": 42.4185,
        "longitude": -83.0682,
        "is_primary": False,
        "wind_position": Station.WindPosition.CROSSWIND,
        "notes": "Factory ZERO monitoring cluster — south sensor.",
    },
    {
        "waqi_id": "A1089652",
        "name": "Hamtramck - East",
        "city": "Hamtramck",
        "latitude": 42.4196,
        "longitude": -83.0652,
        "is_primary": False,
        "wind_position": Station.WindPosition.CROSSWIND,
        "notes": "Factory ZERO monitoring cluster — east sensor.",
    },
    {
        "waqi_id": "A1089646",
        "name": "Hamtramck - West",
        "city": "Hamtramck",
        "latitude": 42.4193,
        "longitude": -83.0711,
        "is_primary": False,
        "wind_position": Station.WindPosition.CROSSWIND,
        "notes": "Factory ZERO monitoring cluster — west sensor.",
    },
    # ── Downwind (plume confirmation — smoke arrives here after 48208) ────────
    {
        "waqi_id": "@39",
        "name": "Windsor - West",
        "city": "Windsor, ON",
        "latitude": 42.2929,
        "longitude": -83.0731,
        "is_primary": False,
        "wind_position": Station.WindPosition.DOWNWIND,
        "notes": "Cross-border. Prevailing winds carry Detroit plumes SE into Windsor. "
        "If Windsor spikes BEFORE 48208, wind has reversed — notable event.",
    },
    {
        "waqi_id": "@5915",
        "name": "Windsor",
        "city": "Windsor, ON",
        "latitude": 42.3149,
        "longitude": -83.0364,
        "is_primary": False,
        "wind_position": Station.WindPosition.DOWNWIND,
        "notes": "Central Windsor station.",
    },
    {
        "waqi_id": "@38",
        "name": "Windsor - Downtown",
        "city": "Windsor, ON",
        "latitude": 42.3158,
        "longitude": -83.0437,
        "is_primary": False,
        "wind_position": Station.WindPosition.DOWNWIND,
        "notes": "Downtown Windsor. Directly across from Detroit.",
    },
    {
        "waqi_id": "A547657",
        "name": "Grosse Pointe",
        "city": "Grosse Pointe",
        "latitude": 42.3686,
        "longitude": -82.9657,
        "is_primary": False,
        "wind_position": Station.WindPosition.DOWNWIND,
        "notes": "Wealthy suburb directly downwind. Useful as socioeconomic "
        "comparison — does a higher-income community to the east show "
        "lower burden? (Likely yes, due to less local industry.)",
    },
    # ── Extended regional network ────────────────────────────────────────────
    # Upwind (farther west/southwest — regional smoke origin tracking)
    {
        "waqi_id": "@5334",
        "name": "Tecumseh",
        "city": "Tecumseh",
        "latitude": 42.0028,
        "longitude": -83.9443,
        "is_primary": False,
        "wind_position": Station.WindPosition.UPWIND,
        "notes": "~50mi SW of 48208. Useful for tracking regional pollution "
        "moving NE before it reaches the Detroit metro.",
    },
    {
        "waqi_id": "@5326",
        "name": "Flint",
        "city": "Flint",
        "latitude": 43.0125,
        "longitude": -83.6875,
        "is_primary": False,
        "wind_position": Station.WindPosition.UPWIND,
        "notes": "~65mi NW of 48208. Northwest approach for smoke plumes; "
        "also an EJ reference city for industrial air quality comparison.",
    },
    {
        "waqi_id": "@5330",
        "name": "Lansing",
        "city": "Lansing",
        "latitude": 42.7325,
        "longitude": -84.5555,
        "is_primary": False,
        "wind_position": Station.WindPosition.UPWIND,
        "notes": "~90mi WNW of 48208. Far upwind reference; state capital.",
    },
    # Downwind (farther east/northeast — plume confirmation beyond Windsor)
    {
        "waqi_id": "A493741",
        "name": "New Haven",
        "city": "New Haven",
        "latitude": 42.7294,
        "longitude": -82.8027,
        "is_primary": False,
        "wind_position": Station.WindPosition.DOWNWIND,
        "notes": "Macomb County, ~35mi NE of 48208. Michigan DEQ sensor. "
        "Confirms plumes that have passed through the Detroit metro.",
    },
    {
        "waqi_id": "@5331",
        "name": "Port Huron",
        "city": "Port Huron",
        "latitude": 42.9706,
        "longitude": -82.4249,
        "is_primary": False,
        "wind_position": Station.WindPosition.DOWNWIND,
        "notes": "~60mi NE of 48208 at Lake Huron. Far downwind terminus "
        "for tracking plume extent.",
    },
    {
        "waqi_id": "@28",
        "name": "Sarnia",
        "city": "Sarnia, ON",
        "latitude": 42.9745,
        "longitude": -82.4060,
        "is_primary": False,
        "wind_position": Station.WindPosition.DOWNWIND,
        "notes": "Ontario, directly across the St. Clair River from Port Huron. "
        "Home to Chemical Valley — one of Canada's largest petrochemical "
        "clusters. SO2 and NO2 here can be locally sourced, not just "
        "Detroit plumes; interpret with care.",
    },
    {
        "waqi_id": "@5",
        "name": "Chatham",
        "city": "Chatham, ON",
        "latitude": 42.4048,
        "longitude": -82.1910,
        "is_primary": False,
        "wind_position": Station.WindPosition.DOWNWIND,
        "notes": "Ontario, ~65mi ESE of 48208. Far downwind; useful for "
        "confirming whether Detroit plumes are reaching rural SW Ontario.",
    },
    # ── Historical only (offline EPA/DEQ stations — do not poll) ─────────────
    # Together these form a continuous official record for SW Detroit: 2018–2025.
    # Import their data via import_historical; leave active=False.
    {
        "waqi_id": "@5325",
        "name": "Detroit - W Lafayette",
        "city": "Detroit",
        "latitude": 42.3206,
        "longitude": -83.0747,
        "is_primary": False,
        "active": False,
        "wind_position": Station.WindPosition.PRIMARY,
        "notes": "Michigan DEQ station, offline since Feb 2020. "
        "Historical data: Oct 2018 – Feb 2020. "
        "Succeeded by Detroit Southwest (@12851).",
    },
    {
        "waqi_id": "@12851",
        "name": "Detroit - Southwest",
        "city": "Detroit",
        "latitude": 42.3042,
        "longitude": -83.1072,
        "is_primary": False,
        "active": False,
        "wind_position": Station.WindPosition.PRIMARY,
        "notes": "Michigan DEQ station, offline since Jun 2025. "
        "Historical data: Nov 2020 – Apr 2025. "
        "Preceded by Detroit W Lafayette (@5325).",
    },
]


class Command(BaseCommand):
    help = "Seed the Station table with the Detroit regional monitoring network."

    def add_arguments(self, parser):
        parser.add_argument(
            "--verify-ids",
            action="store_true",
            help="After loading, print WAQI API URLs to verify each station ID.",
        )

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for data in STATIONS:
            notes = data.pop("notes", "")
            obj, created = Station.objects.update_or_create(
                waqi_id=data["waqi_id"],
                defaults={**data, "notes": notes},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created: {obj}"))
            else:
                updated_count += 1
                self.stdout.write(f"  Updated: {obj}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {created_count} created, {updated_count} updated."
            )
        )

        if options["verify_ids"]:
            self._print_verify_urls()

    def _print_verify_urls(self):
        self.stdout.write("\nStation verification URLs (check each in browser):")
        for station in Station.objects.exclude(
            wind_position=Station.WindPosition.PRIMARY
        ):
            self.stdout.write(
                f"  {station.name}: "
                f"https://api.waqi.info/feed/{station.waqi_id}/?token=YOUR_TOKEN"
            )
