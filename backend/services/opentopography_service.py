from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil

import httpx
import rasterio


OPEN_TOPOGRAPHY_URL = (
    "https://portal.opentopography.org/API/globaldem"
)

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parents[2]
)

CACHE_DIR = (
    BASE_DIR
    / "data"
    / "cache"
    / "opentopography"
)


# =========================================================
# API KEY
# =========================================================

def _get_api_key() -> str:

    api_key = (
        os.getenv(
            "OPEN_TOPOGRAPHY_API_KEY",
            "",
        )
        .strip()
    )

    if not api_key:

        raise RuntimeError(
            "OPEN_TOPOGRAPHY_API_KEY is not configured. "
            "Add it to your .env file."
        )

    return api_key


# =========================================================
# VALIDATE DOWNLOADED DEM
# =========================================================

def _validate_geotiff(
    path: Path,
) -> None:

    try:

        with rasterio.open(
            path
        ) as dataset:

            if dataset.count < 1:

                raise ValueError(
                    "DEM does not contain a raster band."
                )

            if (
                dataset.width < 2
                or
                dataset.height < 2
            ):

                raise ValueError(
                    "Downloaded DEM is too small."
                )

    except Exception as exc:

        raise RuntimeError(
            "OpenTopography response could not be "
            "opened as a GeoTIFF. "
            "Check your API key, bounding box "
            "and API quota."
        ) from exc


# =========================================================
# DOWNLOAD GLOBAL DEM
# =========================================================

def download_global_dem(
    *,
    south: float,
    north: float,
    west: float,
    east: float,
    destination: Path,
    dem_type: str = "COP30",
    use_cache: bool = True,
) -> dict:
    """
    Download a DEM GeoTIFF from OpenTopography.

    Parameters
    ----------
    use_cache:

        True
            Existing behaviour.
            Reuse/store DEM under data/cache/opentopography.

        False
            Do not read from or write to persistent cache.

            This is used by rectangle analysis so the
            downloaded DEM exists only inside its temporary
            processing directory and is automatically
            removed when analysis finishes.
    """

    if (
        south >= north
        or
        west >= east
    ):

        raise ValueError(
            "Invalid DEM bounding box."
        )

    api_key = _get_api_key()

    dem_type = (
        dem_type
        .upper()
        .strip()
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    cache_path = None

    # =====================================================
    # OPTIONAL CACHE
    # =====================================================

    if use_cache:

        CACHE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        cache_key = hashlib.sha1(
            (
                f"{dem_type}|"
                f"{south:.7f}|"
                f"{north:.7f}|"
                f"{west:.7f}|"
                f"{east:.7f}"
            ).encode(
                "utf-8"
            )
        ).hexdigest()[:20]

        cache_path = (
            CACHE_DIR
            / (
                f"{dem_type.lower()}_"
                f"{cache_key}.tif"
            )
        )

        if cache_path.exists():

            _validate_geotiff(
                cache_path
            )

            shutil.copy2(
                cache_path,
                destination,
            )

            return {
                "dataset":
                    dem_type,

                "source":
                    (
                        "OpenTopography Global DEM API "
                        "(cached)"
                    ),

                "cached":
                    True,

                "persisted":
                    True,

                "south":
                    south,

                "north":
                    north,

                "west":
                    west,

                "east":
                    east,
            }

    # =====================================================
    # DOWNLOAD
    # =====================================================

    params = {

        "demtype":
            dem_type,

        "south":
            south,

        "north":
            north,

        "west":
            west,

        "east":
            east,

        "outputFormat":
            "GTiff",

        "API_Key":
            api_key,
    }

    try:

        with httpx.Client(
            timeout=120.0,
            follow_redirects=True,
        ) as client:

            response = client.get(
                OPEN_TOPOGRAPHY_URL,
                params=params,
            )

            response.raise_for_status()

            destination.write_bytes(
                response.content
            )

    except Exception as exc:

        raise RuntimeError(
            "OpenTopography DEM download failed: "
            f"{exc}"
        ) from exc

    # =====================================================
    # VALIDATE
    # =====================================================

    _validate_geotiff(
        destination
    )

    # =====================================================
    # STORE ONLY WHEN CACHE WAS REQUESTED
    # =====================================================

    if (
        use_cache
        and
        cache_path is not None
    ):

        try:

            shutil.copy2(
                destination,
                cache_path,
            )

        except Exception:

            # Cache failure must not invalidate analysis.
            pass

    return {

        "dataset":
            dem_type,

        "source":
            "OpenTopography Global DEM API",

        "cached":
            False,

        "persisted":
            bool(
                use_cache
            ),

        "south":
            south,

        "north":
            north,

        "west":
            west,

        "east":
            east,
    }
