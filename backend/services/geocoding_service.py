from __future__ import annotations

from dataclasses import dataclass

import httpx
from pyproj import Geod


NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"


@dataclass
class GeocodedPlace:
    query: str
    display_name: str
    latitude: float
    longitude: float
    south: float
    north: float
    west: float
    east: float


def _bbox_from_center(latitude: float, longitude: float, radius_m: float):
    """Create an approximately square WGS84 bounding box around a point."""
    geod = Geod(ellps="WGS84")

    east_lon, _, _ = geod.fwd(longitude, latitude, 90.0, radius_m)
    west_lon, _, _ = geod.fwd(longitude, latitude, 270.0, radius_m)
    _, north_lat, _ = geod.fwd(longitude, latitude, 0.0, radius_m)
    _, south_lat, _ = geod.fwd(longitude, latitude, 180.0, radius_m)

    return south_lat, north_lat, west_lon, east_lon


def geocode_place(query: str, radius_m: float = 3000.0) -> GeocodedPlace:
    query = query.strip()
    if not query:
        raise ValueError("Location name cannot be empty.")

    if radius_m < 500 or radius_m > 20000:
        raise ValueError("Analysis radius must be between 500 m and 20,000 m.")

    headers = {
        "User-Agent": "VillagePondPlanningStudentProject/1.0 (academic project)"
    }
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
        "accept-language": "en",
    }

    try:
        with httpx.Client(timeout=20.0, headers=headers) as client:
            response = client.get(NOMINATIM_SEARCH_URL, params=params)
            response.raise_for_status()
            results = response.json()
    except Exception as exc:
        raise RuntimeError(f"Location geocoding failed: {exc}") from exc

    if not results:
        raise ValueError(
            f"Location '{query}' was not found. Try a more complete name, for example "
            "'IIT Bhilai, Kutelabhata, Chhattisgarh, India'."
        )

    result = results[0]
    latitude = float(result["lat"])
    longitude = float(result["lon"])

    south, north, west, east = _bbox_from_center(
        latitude=latitude,
        longitude=longitude,
        radius_m=radius_m,
    )

    return GeocodedPlace(
        query=query,
        display_name=result.get("display_name", query),
        latitude=latitude,
        longitude=longitude,
        south=south,
        north=north,
        west=west,
        east=east,
    )
