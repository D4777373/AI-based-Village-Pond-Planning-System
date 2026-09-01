from __future__ import annotations

import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import (
    APIRouter,
    Form,
    HTTPException,
)

from pyproj import Geod

from backend.services.analysis_service import (
    analyze_contour_file,
)

from backend.services.contour_generation_service import (
    generate_contours_from_dem,
)

from backend.services.opentopography_service import (
    download_global_dem,
)


router = APIRouter()

GEOD = Geod(
    ellps="WGS84"
)


# =========================================================
# RECTANGLE CONFIGURATION
# =========================================================

# A very tiny rectangle is not useful with COP30.
MIN_SIDE_M = 300.0


# ---------------------------------------------------------
# IMPORTANT
#
# There is NO longer a 25 km² normal-analysis limit.
#
# The user chooses the desired rectangle.
#
# We instead automatically increase analysis resolution
# when a large rectangle would create too many grid cells.
# ---------------------------------------------------------

MAX_ANALYSIS_GRID_CELLS = int(
    os.getenv(
        "MAX_ANALYSIS_GRID_CELLS",
        "1000000",
    )
)


# ---------------------------------------------------------
# Emergency deployment ceiling
#
# This protects the server from somebody accidentally
# selecting a state-sized region.
#
# It is configuration, not a fixed application rule.
#
# Example:
#
# MAX_DRAWN_AREA_KM2=5000
#
# in .env if your server can handle more.
# ---------------------------------------------------------

MAX_DRAWN_AREA_KM2 = float(
    os.getenv(
        "MAX_DRAWN_AREA_KM2",
        "2500",
    )
)


# COP30 nominal horizontal resolution.
SOURCE_DEM_RESOLUTION_M = 30.0


# =========================================================
# AREA DIMENSIONS
# =========================================================

def _calculate_area_dimensions(
    *,
    south: float,
    north: float,
    west: float,
    east: float,
) -> dict:

    if not (
        -90 <= south <= 90
        and
        -90 <= north <= 90
    ):

        raise ValueError(
            "Latitude must be between -90 and 90."
        )

    if not (
        -180 <= west <= 180
        and
        -180 <= east <= 180
    ):

        raise ValueError(
            "Longitude must be between -180 and 180."
        )

    if south >= north:

        raise ValueError(
            "South latitude must be smaller "
            "than north latitude."
        )

    if west >= east:

        raise ValueError(
            "West longitude must be smaller "
            "than east longitude."
        )

    center_latitude = (
        south
        +
        north
    ) / 2.0

    center_longitude = (
        west
        +
        east
    ) / 2.0

    # Width.
    _, _, width_m = GEOD.inv(
        west,
        center_latitude,
        east,
        center_latitude,
    )

    # Height.
    _, _, height_m = GEOD.inv(
        center_longitude,
        south,
        center_longitude,
        north,
    )

    width_m = abs(
        float(
            width_m
        )
    )

    height_m = abs(
        float(
            height_m
        )
    )

    area_m2 = (
        width_m
        *
        height_m
    )

    area_km2 = (
        area_m2
        /
        1_000_000.0
    )

    area_hectares = (
        area_m2
        /
        10_000.0
    )

    # Tiny selections do not make sense with COP30.
    if (
        width_m < MIN_SIDE_M
        or
        height_m < MIN_SIDE_M
    ):

        raise ValueError(
            "Selected rectangle is too small. "
            f"Each side must be at least "
            f"{MIN_SIDE_M:.0f} m."
        )

    # Emergency server protection only.
    if (
        MAX_DRAWN_AREA_KM2 > 0
        and
        area_km2 > MAX_DRAWN_AREA_KM2
    ):

        raise ValueError(
            "The selected area is larger than the "
            "current server safety limit. "
            f"Selected area: {area_km2:.2f} km². "
            f"Current server limit: "
            f"{MAX_DRAWN_AREA_KM2:.2f} km². "
            "Increase MAX_DRAWN_AREA_KM2 in .env "
            "if this deployment has enough resources."
        )

    return {

        "center_latitude":
            center_latitude,

        "center_longitude":
            center_longitude,

        "width_m":
            width_m,

        "height_m":
            height_m,

        "area_m2":
            area_m2,

        "area_km2":
            area_km2,

        "area_hectares":
            area_hectares,
    }


# =========================================================
# ADAPTIVE GRID RESOLUTION
# =========================================================

def _calculate_effective_resolution(
    *,
    area_m2: float,
    requested_resolution_m: float,
) -> float:
    """
    Automatically make the grid coarser for large areas.

    Example:

    Small rectangle:
        requested 30 m
        -> 30 m

    Very large rectangle:
        30 m would produce millions of cells
        -> automatically use 45 m / 60 m / etc.

    This lets the USER choose a larger geographical area
    without creating an unbounded RAM requirement.
    """

    minimum_resolution = max(
        float(
            requested_resolution_m
        ),
        SOURCE_DEM_RESOLUTION_M,
    )

    # Number of square cells approximately equals:
    #
    #     area / resolution²
    #
    # So:
    #
    #     resolution = sqrt(area / max_cells)
    #

    required_resolution = math.sqrt(
        area_m2
        /
        max(
            MAX_ANALYSIS_GRID_CELLS,
            1,
        )
    )

    effective_resolution = max(
        minimum_resolution,
        required_resolution,
    )

    # Keep a sensible decimal value.
    return round(
        effective_resolution,
        2,
    )


# =========================================================
# POST /api/analyzeArea
# =========================================================

@router.post(
    "/analyzeArea"
)
def analyze_area(

    south: float = Form(...),

    north: float = Form(...),

    west: float = Form(...),

    east: float = Form(...),

    contour_interval_m: float = Form(
        5.0
    ),

    resolution_m: float = Form(
        30.0
    ),

    max_candidates: int = Form(
        20
    ),

    rainfall_years: int = Form(
        5
    ),

    runoff_coefficient: float = Form(
        0.30
    ),

    pond_radius_m: float = Form(
        40.0
    ),

    max_pond_depth_m: float = Form(
        3.0
    ),
):

    """
    Analyze exactly the rectangle drawn by the user.

    IMPORTANT:

    Rectangle analysis is TEMPORARY.

    The backend does NOT permanently save:

        downloaded DEM
        generated KML
        generated GeoJSON
        returned analysis result

    DEM and contour files live inside TemporaryDirectory()
    only while this request is executing.

    If the user wants the result, the frontend allows them
    to explicitly download the returned JSON.
    """

    try:

        # =================================================
        # INPUT VALIDATION
        # =================================================

        if not (
            1.0
            <= contour_interval_m
            <= 100.0
        ):

            raise ValueError(
                "Contour interval must be "
                "between 1 m and 100 m."
            )

        if not (
            1.0
            <= resolution_m
            <= 1000.0
        ):

            raise ValueError(
                "Requested analysis resolution must be "
                "between 1 m and 1000 m."
            )

        if not (
            1
            <= max_candidates
            <= 100
        ):

            raise ValueError(
                "Maximum candidates must be "
                "between 1 and 100."
            )

        if not (
            1
            <= rainfall_years
            <= 30
        ):

            raise ValueError(
                "Rainfall history must be "
                "between 1 and 30 years."
            )

        if not (
            0.0
            <= runoff_coefficient
            <= 1.0
        ):

            raise ValueError(
                "Runoff coefficient must be "
                "between 0 and 1."
            )

        if not (
            5.0
            <= pond_radius_m
            <= 500.0
        ):

            raise ValueError(
                "Pond radius must be "
                "between 5 m and 500 m."
            )

        if not (
            0.5
            <= max_pond_depth_m
            <= 20.0
        ):

            raise ValueError(
                "Maximum pond depth must be "
                "between 0.5 m and 20 m."
            )

        # =================================================
        # AREA
        # =================================================

        area = (
            _calculate_area_dimensions(

                south=
                    float(
                        south
                    ),

                north=
                    float(
                        north
                    ),

                west=
                    float(
                        west
                    ),

                east=
                    float(
                        east
                    ),
            )
        )

        # =================================================
        # ADAPTIVE ANALYSIS RESOLUTION
        # =================================================

        effective_resolution_m = (
            _calculate_effective_resolution(

                area_m2=
                    area[
                        "area_m2"
                    ],

                requested_resolution_m=
                    float(
                        resolution_m
                    ),
            )
        )

        estimated_grid_cells = int(
            area[
                "area_m2"
            ]
            /
            (
                effective_resolution_m
                *
                effective_resolution_m
            )
        )

        # =================================================
        # TEMPORARY PROCESSING DIRECTORY
        # =================================================
        #
        # Everything downloaded/generated in this block
        # disappears automatically after the request.
        # =================================================

        with TemporaryDirectory(
            prefix=
                "pond_rectangle_"
        ) as temp_directory:

            work_dir = Path(
                temp_directory
            )

            dem_path = (
                work_dir
                /
                "source_dem.tif"
            )

            kml_path = (
                work_dir
                /
                "generated_contours.kml"
            )

            geojson_path = (
                work_dir
                /
                "generated_contours.geojson"
            )

            # =============================================
            # DOWNLOAD DEM WITHOUT PERSISTENT CACHE
            # =============================================

            dem_info = (
                download_global_dem(

                    south=
                        float(
                            south
                        ),

                    north=
                        float(
                            north
                        ),

                    west=
                        float(
                            west
                        ),

                    east=
                        float(
                            east
                        ),

                    destination=
                        dem_path,

                    dem_type=
                        "COP30",

                    use_cache=
                        False,
                )
            )

            # =============================================
            # DEM -> CONTOURS
            # =============================================

            generated = (
                generate_contours_from_dem(

                    dem_path=
                        dem_path,

                    kml_path=
                        kml_path,

                    geojson_path=
                        geojson_path,

                    contour_interval_m=
                        float(
                            contour_interval_m
                        ),
                )
            )

            # =============================================
            # EXISTING HYDROLOGY PIPELINE
            # =============================================

            result = (
                analyze_contour_file(

                    file_bytes=
                        kml_path.read_bytes(),

                    filename=
                        "temporary_rectangle_contours.kml",

                    resolution_m=
                        effective_resolution_m,

                    max_candidates=
                        int(
                            max_candidates
                        ),

                    rainfall_years=
                        int(
                            rainfall_years
                        ),

                    runoff_coefficient=
                        float(
                            runoff_coefficient
                        ),

                    pond_radius_m=
                        float(
                            pond_radius_m
                        ),

                    max_pond_depth_m=
                        float(
                            max_pond_depth_m
                        ),
                )
            )

            # At this point all required information has
            # been converted to regular Python dictionaries.
            #
            # The TemporaryDirectory can safely disappear
            # after this function returns.

            # =============================================
            # ADD RECTANGLE METADATA
            # =============================================

            result[
                "analysis_mode"
            ] = (
                "drawn_rectangle"
            )

            result[
                "area_selection"
            ] = {

                "center_latitude":
                    area[
                        "center_latitude"
                    ],

                "center_longitude":
                    area[
                        "center_longitude"
                    ],

                "width_m":
                    round(
                        area[
                            "width_m"
                        ],
                        2,
                    ),

                "height_m":
                    round(
                        area[
                            "height_m"
                        ],
                        2,
                    ),

                "area_m2":
                    round(
                        area[
                            "area_m2"
                        ],
                        2,
                    ),

                "area_km2":
                    round(
                        area[
                            "area_km2"
                        ],
                        4,
                    ),

                "area_hectares":
                    round(
                        area[
                            "area_hectares"
                        ],
                        4,
                    ),

                "bounding_box": {

                    "south":
                        float(
                            south
                        ),

                    "north":
                        float(
                            north
                        ),

                    "west":
                        float(
                            west
                        ),

                    "east":
                        float(
                            east
                        ),
                },
            }

            # =============================================
            # SOURCE DEM METADATA ONLY
            # =============================================

            result[
                "source_dem"
            ] = {

                **dem_info,

                "vertical_source":
                    (
                        "Copernicus COP30 DSM "
                        "via OpenTopography"
                    ),

                "nominal_horizontal_resolution_m":
                    SOURCE_DEM_RESOLUTION_M,

                "requested_analysis_resolution_m":
                    float(
                        resolution_m
                    ),

                "analysis_grid_resolution_m":
                    effective_resolution_m,

                "estimated_grid_cells":
                    estimated_grid_cells,

                "adaptive_resolution":
                    (
                        effective_resolution_m
                        >
                        max(
                            float(
                                resolution_m
                            ),
                            SOURCE_DEM_RESOLUTION_M,
                        )
                    ),

                "resolution_note":
                    (
                        "Large selections automatically "
                        "use a coarser analysis grid to "
                        "control memory and processing "
                        "requirements."
                    ),
            }

            # =============================================
            # GENERATED CONTOURS
            # =============================================
            #
            # GeoJSON is copied into response memory.
            # No KML/GeoJSON file is kept on disk.
            # =============================================

            result[
                "generated_contours"
            ] = {

                "contour_interval_m":
                    generated
                    .contour_interval_m,

                "minimum_elevation_m":
                    generated
                    .minimum_elevation_m,

                "maximum_elevation_m":
                    generated
                    .maximum_elevation_m,

                "contour_feature_count":
                    generated
                    .contour_feature_count,

                "geojson":
                    generated
                    .geojson,
            }

            # =============================================
            # STORAGE POLICY
            # =============================================

            result[
                "storage_policy"
            ] = {

                "server_result_saved":
                    False,

                "dem_saved":
                    False,

                "generated_contour_files_saved":
                    False,

                "temporary_processing":
                    True,

                "message":
                    (
                        "This rectangle analysis was "
                        "processed temporarily. The "
                        "server did not persist the DEM, "
                        "generated contour files or "
                        "analysis result. Use the Save "
                        "Result button in the browser if "
                        "you want to keep the returned "
                        "result."
                    ),
            }

            return result

    except (
        ValueError,
        RuntimeError,
    ) as exc:

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Rectangle-area analysis failed: "
                f"{exc}"
            ),
        ) from exc
