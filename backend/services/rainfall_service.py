from __future__ import annotations

from datetime import date
from collections import defaultdict

import httpx


OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def get_historical_rainfall(latitude: float, longitude: float, years: int = 5) -> dict:
    """Return historical annual rainfall totals and their average.

    The last N *completed* calendar years are used so that a partial current
    year does not make the average artificially low.
    """
    years = max(1, min(int(years), 30))
    last_year = date.today().year - 1
    first_year = last_year - years + 1

    params = {
        "latitude": round(float(latitude), 6),
        "longitude": round(float(longitude), 6),
        "start_date": f"{first_year}-01-01",
        "end_date": f"{last_year}-12-31",
        "daily": "precipitation_sum",
        "timezone": "UTC",
    }

    try:
        with httpx.Client(timeout=25.0) as client:
            response = client.get(OPEN_METEO_ARCHIVE_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        times = payload.get("daily", {}).get("time", [])
        precipitation = payload.get("daily", {}).get("precipitation_sum", [])
        if not times or len(times) != len(precipitation):
            raise ValueError("Rainfall API returned no usable daily precipitation data.")

        totals: dict[int, float] = defaultdict(float)
        valid_days: dict[int, int] = defaultdict(int)

        for day, value in zip(times, precipitation):
            if value is None:
                continue
            year = int(day[:4])
            totals[year] += float(value)
            valid_days[year] += 1

        yearly = [
            {
                "year": year,
                "rainfall_mm": round(totals[year], 2),
                "valid_days": valid_days[year],
            }
            for year in sorted(totals)
            if valid_days[year] > 0
        ]
        if not yearly:
            raise ValueError("Rainfall API returned no usable precipitation values.")

        average = sum(item["rainfall_mm"] for item in yearly) / len(yearly)
        return {
            "available": True,
            "source": "Open-Meteo Historical Weather API",
            "latitude": float(latitude),
            "longitude": float(longitude),
            "period": f"{first_year}-{last_year}",
            "average_annual_rainfall_mm": round(average, 2),
            "yearly": yearly,
            "error": None,
        }

    except Exception as exc:
        # Terrain/catchment analysis should still be usable if the laptop has
        # no Internet or the public rainfall provider is temporarily down.
        return {
            "available": False,
            "source": "Open-Meteo Historical Weather API",
            "latitude": float(latitude),
            "longitude": float(longitude),
            "period": f"{first_year}-{last_year}",
            "average_annual_rainfall_mm": None,
            "yearly": [],
            "error": str(exc),
        }
