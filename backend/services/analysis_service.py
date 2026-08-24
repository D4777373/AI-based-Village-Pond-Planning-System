from __future__ import annotations

import numpy as np

from rasterio.features import shapes

from shapely.geometry import (
    mapping,
    shape,
)

from shapely.ops import (
    transform as shapely_transform,
    unary_union,
)

from backend.hydrology.catchment import (
    delineate_catchment,
)

from backend.hydrology.flow_accumulation import (
    calculate_flow_accumulation,
)

from backend.hydrology.flow_direction import (
    calculate_flow_direction,
)

from backend.hydrology.sink_fill import (
    fill_sinks_priority_flood,
)

from backend.pond.candidate import (
    find_pond_candidates,
)

from backend.pond.metrics import (
    estimate_candidate_water_metrics,
)

from backend.services.kml_service import (
    parse_contour_file,
)

from backend.services.land_service import (
    build_osm_free_land_mask,
)

from backend.services.rainfall_service import (
    get_historical_rainfall,
)

from backend.terrain.dem_generator import (
    build_dem,
)

from backend.terrain.slope import (
    calculate_slope_percent,
)


# ---------------------------------------------------------
# Convert catchment raster mask into GeoJSON
# ---------------------------------------------------------

def _mask_to_geojson(
    mask,
    transform,
    to_wgs84,
):

    geometries = []

    data = mask.astype(
        np.uint8
    )

    for geometry, value in shapes(

        data,

        mask=mask,

        transform=transform,
    ):

        if value == 1:

            geometries.append(
                shape(
                    geometry
                )
            )

    if not geometries:
        return None

    merged = unary_union(
        geometries
    )

    wgs84_geometry = (
        shapely_transform(
            to_wgs84.transform,
            merged,
        )
    )

    return mapping(
        wgs84_geometry
    )


# ---------------------------------------------------------
# MAIN ANALYSIS
# ---------------------------------------------------------

def analyze_contour_file(

    file_bytes: bytes,

    filename: str,

    resolution_m: float = 10.0,

    max_candidates: int = 20,

    rainfall_years: int = 5,

    runoff_coefficient: float = 0.30,

    pond_radius_m: float = 40.0,

    max_pond_depth_m: float = 3.0,

    max_candidate_slope_percent: float = 8.0,

    min_candidate_spacing_m: float = 100.0,

    min_accumulation_percentile: float = 85.0,

) -> dict:

    # =====================================================
    # STEP 1
    # Parse KML
    # =====================================================

    parsed = parse_contour_file(
        file_bytes,
        filename,
    )

    # =====================================================
    # STEP 2
    # Contours → DEM
    # =====================================================

    terrain = build_dem(
        parsed,
        resolution_m=
            resolution_m,
    )

    original_dem = terrain.dem

    # =====================================================
    # STEP 3
    # Fill artificial DEM sinks
    # =====================================================

    filled_dem = (
        fill_sinks_priority_flood(
            original_dem,
            terrain.valid_mask,
        )
    )

    # =====================================================
    # STEP 4
    # Calculate slope
    # =====================================================

    slope = (
        calculate_slope_percent(
            filled_dem,
            terrain.valid_mask,
            terrain.resolution_m,
        )
    )

    # =====================================================
    # STEP 5
    # D8 flow direction
    # =====================================================

    direction = (
        calculate_flow_direction(
            filled_dem,
            terrain.valid_mask,
            terrain.resolution_m,
        )
    )

    # =====================================================
    # STEP 6
    # Flow accumulation
    # =====================================================

    accumulation = (
        calculate_flow_accumulation(
            direction,
            terrain.valid_mask,
        )
    )

    # =====================================================
    # STEP 7
    # Convert analysis boundary to WGS84
    # =====================================================

    boundary_wgs84 = (
        shapely_transform(
            terrain.to_wgs84.transform,
            terrain.boundary_projected,
        )
    )

    # =====================================================
    # STEP 8
    # LAND FILTER
    #
    # Exclude:
    # rivers
    # water
    # roads
    # buildings
    #
    # IMPORTANT:
    # We do this AFTER hydrology.
    #
    # Rivers must still take part in flow calculations.
    # =====================================================

    land_filter = (
        build_osm_free_land_mask(

            terrain,

            boundary_wgs84,

            pond_radius_m=
                pond_radius_m,

            safety_buffer_m=
                10.0,
        )
    )

    # =====================================================
    # STEP 9
    # Find pond candidates ONLY on feature-clear land
    # =====================================================

    candidate_cells = (
        find_pond_candidates(

            filled_dem,

            slope,

            accumulation,

            # THIS IS THE IMPORTANT CHANGE
            land_filter.free_land_mask,

            terrain.resolution_m,

            max_candidates=
                max_candidates,

            max_slope_percent=
                max_candidate_slope_percent,

            min_candidate_spacing_m=
                min_candidate_spacing_m,

            min_accumulation_percentile=
                min_accumulation_percentile,
        )
    )

    if not candidate_cells:

        raise ValueError(
            "No pond candidates remain after "
            "excluding mapped rivers/water bodies, "
            "roads and buildings."
        )

    # =====================================================
    # STEP 10
    # Rainfall
    # =====================================================

    rain_longitude = (
        boundary_wgs84.centroid.x
    )

    rain_latitude = (
        boundary_wgs84.centroid.y
    )

    rainfall = (
        get_historical_rainfall(

            rain_latitude,

            rain_longitude,

            rainfall_years,
        )
    )

    average_rainfall_mm = (
        rainfall.get(
            "average_annual_rainfall_mm"
        )
    )

    # =====================================================
    # STEP 11
    # Calculate catchment + water information for
    # every candidate
    # =====================================================

    candidates = []

    recommended_catchment_geojson = None

    for rank, cell in enumerate(
        candidate_cells,
        start=1,
    ):

        row = cell.row
        column = cell.col

        # -------------------------------------------------
        # Catchment
        # -------------------------------------------------

        catchment_mask = (
            delineate_catchment(

                direction,

                terrain.valid_mask,

                row,

                column,
            )
        )

        cell_count = int(
            catchment_mask.sum()
        )

        area_m2 = float(

            cell_count

            * terrain.resolution_m

            * terrain.resolution_m
        )

        # -------------------------------------------------
        # Grid → longitude / latitude
        # -------------------------------------------------

        x = float(
            terrain.xs[column]
        )

        y = float(
            terrain.ys[row]
        )

        longitude, latitude = (
            terrain.to_wgs84.transform(
                x,
                y,
            )
        )

        # -------------------------------------------------
        # Water storage + runoff
        #
        # IMPORTANT:
        # Use free land mask while estimating pond
        # footprint.
        # -------------------------------------------------

        water = (
            estimate_candidate_water_metrics(

                row,

                column,

                filled_dem,

                slope,

                land_filter.free_land_mask,

                terrain.resolution_m,

                area_m2,

                average_rainfall_mm,

                runoff_coefficient=
                    runoff_coefficient,

                pond_radius_m=
                    pond_radius_m,

                max_pond_depth_m=
                    max_pond_depth_m,
            )
        )

        candidate_id = rank

        candidates.append(
            {

                "candidate_id":
                    candidate_id,

                "rank":
                    rank,

                "latitude":
                    float(latitude),

                "longitude":
                    float(longitude),

                "elevation_m":
                    round(
                        float(
                            filled_dem[
                                row,
                                column,
                            ]
                        ),
                        3,
                    ),

                "slope_percent":
                    round(
                        float(
                            slope[
                                row,
                                column,
                            ]
                        ),
                        3,
                    ),

                "flow_accumulation_cells":
                    int(
                        round(
                            float(
                                accumulation[
                                    row,
                                    column,
                                ]
                            )
                        )
                    ),

                "suitability_score":
                    round(
                        float(
                            cell.score
                        ),
                        2,
                    ),

                "catchment": {

                    "cell_count":
                        cell_count,

                    "area_m2":
                        round(
                            area_m2,
                            2,
                        ),

                    "area_hectares":
                        round(
                            area_m2
                            / 10_000.0,
                            4,
                        ),
                },

                "water":
                    water,

                "land_status": (
                    "Feature-clear according to "
                    "OpenStreetMap: candidate footprint "
                    "does not overlap mapped water/"
                    "waterways, roads or buildings. "
                    "Legal ownership still requires "
                    "official verification."
                ),
            }
        )

        # Only show top candidate catchment for now
        # to avoid filling entire map with many polygons.

        if rank == 1:

            recommended_catchment_geojson = (
                _mask_to_geojson(

                    catchment_mask,

                    terrain.transform,

                    terrain.to_wgs84,
                )
            )

    # =====================================================
    # STEP 12
    # Terrain summary
    # =====================================================

    elevations = sorted(
        {
            contour.elevation_m
            for contour
            in parsed.contours
        }
    )

    interval = min(
        (
            next_elevation
            - elevation

            for elevation,
            next_elevation

            in zip(
                elevations,
                elevations[1:],
            )

            if next_elevation
            > elevation
        ),

        default=None,
    )

    # =====================================================
    # FINAL JSON RESPONSE
    # =====================================================

    return {

        "status":
            "success",

        "filename":
            filename,

        # -------------------------------------------------
        # Terrain
        # -------------------------------------------------

        "terrain": {

            "contour_line_count":
                len(
                    parsed.contours
                ),

            "minimum_elevation_m":
                float(
                    np.nanmin(
                        original_dem
                    )
                ),

            "maximum_elevation_m":
                float(
                    np.nanmax(
                        original_dem
                    )
                ),

            "contour_interval_m":
                (
                    float(interval)
                    if interval is not None
                    else None
                ),

            "grid_resolution_m":
                round(
                    float(
                        terrain.resolution_m
                    ),
                    3,
                ),

            "grid_rows":
                int(
                    original_dem.shape[0]
                ),

            "grid_columns":
                int(
                    original_dem.shape[1]
                ),
        },

        # -------------------------------------------------
        # Rainfall
        # -------------------------------------------------

        "rainfall":
            rainfall,

        # -------------------------------------------------
        # Land filter
        # -------------------------------------------------

        "land_filter": {

            "available":
                True,

            "source":
                land_filter.source,

            "excluded_feature_counts":
                land_filter.feature_counts,

            "excluded_cell_count":
                land_filter.excluded_cell_count,

            "free_cell_count":
                land_filter.free_cell_count,

            "notes":
                land_filter.notes,
        },

        # Red polygons drawn on Leaflet
        "excluded_areas_geojson":
            land_filter.exclusion_geojson,

        # -------------------------------------------------
        # Candidates
        # -------------------------------------------------

        "candidates":
            candidates,

        "recommended_candidate_id":
            1,

        "recommended_catchment_geojson":
            recommended_catchment_geojson,

        "boundary_geojson":
            mapping(
                boundary_wgs84
            ),

        # -------------------------------------------------
        # Candidate configuration
        # -------------------------------------------------

        "candidate_generation": {

            "returned_candidates":
                len(
                    candidates
                ),

            "max_candidates_requested":
                int(
                    max_candidates
                ),

            "minimum_spacing_m":
                float(
                    min_candidate_spacing_m
                ),

            "maximum_slope_percent":
                float(
                    max_candidate_slope_percent
                ),

            "minimum_accumulation_percentile":
                float(
                    min_accumulation_percentile
                ),
        },

        # -------------------------------------------------
        # Explain methodology in API
        # -------------------------------------------------

        "method": {

            "dem":
                (
                    "Contour interpolation "
                    "(linear with nearest-edge fill)"
                ),

            "sink_handling":
                (
                    "Priority-Flood "
                    "depression filling"
                ),

            "flow_direction":
                (
                    "D8 steepest-descent"
                ),

            "flow_accumulation":
                (
                    "Upstream contributing-cell count"
                ),

            "candidate_generation":
                (
                    "Local maxima of hydrological "
                    "suitability restricted to OSM "
                    "feature-clear land, with "
                    "configurable minimum spacing"
                ),

            "land_filter":
                (
                    "OpenStreetMap/Overpass water, "
                    "waterways, roads and buildings "
                    "buffered by pond footprint radius "
                    "before candidate selection"
                ),

            "catchment":
                (
                    "Reverse traversal of D8 drainage "
                    "graph from each candidate outlet"
                ),

            "rainfall":
                (
                    "Historical daily precipitation "
                    "aggregated to annual totals using "
                    "Open-Meteo at analysis-area centroid"
                ),

            "runoff":
                (
                    "Average annual rainfall × "
                    "catchment area × runoff coefficient"
                ),

            "storage":
                (
                    "Connected gentle local footprint × "
                    "recommended excavation depth × "
                    "geometric shape factor"
                ),
        },

        # -------------------------------------------------
        # Limitations
        # -------------------------------------------------

        "limitations": [

            (
                "Candidate sites are hydrological "
                "planning candidates, not final "
                "construction approvals."
            ),

            (
                "Mapped rivers/water bodies, roads "
                "and buildings are automatically "
                "excluded using OpenStreetMap; "
                "unmapped features can still exist."
            ),

            (
                "Feature-clear land is not proof "
                "of government ownership or legal "
                "availability; official land records "
                "and field inspection are still required."
            ),

            (
                "Storage capacity is a planning-level "
                "geometric estimate and requires field "
                "survey, soil/geotechnical checks and "
                "civil-engineering design."
            ),

            (
                "Runoff volume depends on the selected "
                "runoff coefficient and should be "
                "refined with local land-cover and "
                "soil data."
            ),
        ],
    }
