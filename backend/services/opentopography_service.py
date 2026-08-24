from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil

import httpx
import rasterio


OPEN_TOPOGRAPHY_URL = "https://portal.opentopography.org/API/globaldem"

BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_DIR = BASE_DIR / "data" / "cache" / "opentopography"


def _get_api_key() -> str:
    api_key = os.getenv("OPEN_TOPOGRAPHY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OPEN_TOPOGRAPHY_API_KEY is not configured. Add it to your .env file."
        )
    return api_key


def _validate_geotiff(path: Path) -> None:
    try:
        with rasterio.open(path) as dataset:
            if dataset.count < 1:
                raise ValueError("DEM does not contain a raster band.")
            if dataset.width < 2 or dataset.height < 2:
                raise ValueError("Downloaded DEM is too small.")
    except Exception as exc:
        raise RuntimeError(
            "OpenTopography response could not be opened as a GeoTIFF. "
            "Check your API key, bounding box and API quota."
        ) from exc


def download_global_dem(
    *,
    south: float,
    north: float,
    west: float,
    east: float,
    destination: Path,
    dem_type: str = "COP30",
) -> dict:
    """Download a DEM GeoTIFF from OpenTopography, with a local cache."""
    if south >= north or west >= east:
        raise ValueError("Invalid DEM bounding box.")

    api_key = _get_api_key()
    dem_type = dem_type.upper().strip()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)

    cache_key = hashlib.sha1(
        f"{dem_type}|{south:.7f}|{north:.7f}|{west:.7f}|{east:.7f}".encode("utf-8")
    ).hexdigest()[:20]
    cache_path = CACHE_DIR / f"{dem_type.lower()}_{cache_key}.tif"

    if cache_path.exists():
        _validate_geotiff(cache_path)
        shutil.copy2(cache_path, destination)
        return {
            "dataset": dem_type,
            "source": "OpenTopography Global DEM API (cached)",
            "cached": True,
            "south": south,
            "north": north,
            "west": west,
            "east": east,
        }

    params = {
        "demtype": dem_type,
        "south": south,
        "north": north,
        "west": west,
        "east": east,
        "outputFormat": "GTiff",
        "API_Key": api_key,
    }

    try:
        with httpx.Client(timeout=90.0, follow_redirects=True) as client:
            response = client.get(OPEN_TOPOGRAPHY_URL, params=params)
            response.raise_for_status()
            destination.write_bytes(response.content)
    except Exception as exc:
        raise RuntimeError(f"OpenTopography DEM download failed: {exc}") from exc

    _validate_geotiff(destination)
    shutil.copy2(destination, cache_path)

    return {
        "dataset": dem_type,
        "source": "OpenTopography Global DEM API",
        "cached": False,
        "south": south,
        "north": north,
        "west": west,
        "east": east,
    }

