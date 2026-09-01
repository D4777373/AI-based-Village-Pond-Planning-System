from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import time

import httpx
import numpy as np

from rasterio.features import geometry_mask

from shapely.geometry import (
    GeometryCollection,
    LineString,
    Polygon,
    mapping,
)

from shapely.ops import (
    polygonize,
    transform as shapely_transform,
    unary_union,
)


# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parents[2]

CACHE_DIR = (
    BASE_DIR
    / "data"
    / "cache"
    / "osm"
)


# ---------------------------------------------------------
# Public Overpass servers
# ---------------------------------------------------------
#
# private.coffee was previously known as:
#
#     overpass.kumi.systems
#
# Do NOT use the old kumi hostname anymore.
#
# The official overpass-api.de server is kept as a final
# fallback because it can sometimes be overloaded.
# ---------------------------------------------------------

OVERPASS_ENDPOINTS = (
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)


# Timeout used INSIDE the Overpass query.
OVERPASS_QUERY_TIMEOUT_SECONDS = 90


# HTTP timeout used by Python/httpx.
HTTP_TIMEOUT_SECONDS = 120.0


# How long connection establishment may take.
HTTP_CONNECT_TIMEOUT_SECONDS = 15.0


# We only tile roads/buildings once.
#
# One large bbox:
#
#       +-------------------+
#       |                   |
#       |                   |
#       +-------------------+
#
# becomes:
#
#       +---------+---------+
#       |    3    |    4    |
#       +---------+---------+
#       |    1    |    2    |
#       +---------+---------+
#
# We deliberately do NOT recursively produce 16, 64, ...
# requests because that caused the long retry storm seen
# in the earlier implementation.
MAX_TILE_DEPTH = 1


CACHE_VERSION = "osm-exclusions-v3"


# =========================================================
# CUSTOM ERROR
# =========================================================


class OverpassRequestError(RuntimeError):
    """
    Error raised after every configured Overpass instance
    failed.

    had_http_response:
        True means at least one server was reachable and
        returned an HTTP error such as 500/502/504.

        False means every attempt failed before receiving an
        HTTP response, for example "Network is unreachable".

    Tiling only makes sense in the first case.
    """

    def __init__(
        self,
        message: str,
        *,
        had_http_response: bool,
    ):
        super().__init__(message)

        self.had_http_response = (
            had_http_response
        )


# =========================================================
# RESULT OBJECT
# =========================================================


@dataclass
class LandFilterResult:
    """
    Result of the OpenStreetMap land suitability filter.
    """

    free_land_mask: np.ndarray

    # Geometry displayed as red exclusion area on frontend.
    exclusion_geojson: dict | None

    source: str

    feature_counts: dict[str, int]

    excluded_cell_count: int

    free_cell_count: int

    notes: list[str]


# =========================================================
# OSM FEATURE CLASSIFICATION
# =========================================================


def _category(
    tags: dict,
) -> str | None:
    """
    Convert OpenStreetMap tags into the exclusion categories
    understood by this application.

    Possible return values:

        water
        waterway
        road
        building
    """

    # -----------------------------------------------------
    # Buildings
    # -----------------------------------------------------

    if tags.get("building"):
        return "building"

    # -----------------------------------------------------
    # Roads
    # -----------------------------------------------------

    if tags.get("highway"):
        return "road"

    # -----------------------------------------------------
    # Water areas
    # -----------------------------------------------------

    if tags.get("natural") in {
        "water",
        "wetland",
    }:
        return "water"

    if tags.get("landuse") in {
        "reservoir",
        "basin",
    }:
        return "water"

    if tags.get("water"):
        return "water"

    if tags.get("waterway") == "riverbank":
        return "water"

    # -----------------------------------------------------
    # Linear waterways
    # -----------------------------------------------------

    if tags.get("waterway") in {
        "river",
        "stream",
        "canal",
        "drain",
        "ditch",
    }:
        return "waterway"

    return None


# =========================================================
# OVERPASS GEOMETRY HELPERS
# =========================================================


def _coords_from_geometry(
    items: list[dict] | None,
) -> list[tuple[float, float]]:
    """
    Convert an Overpass geometry array into Shapely-style
    coordinate pairs:

        (longitude, latitude)
    """

    if not items:
        return []

    coordinates: list[
        tuple[
            float,
            float,
        ]
    ] = []

    for point in items:

        if (
            "lon" not in point
            or "lat" not in point
        ):
            continue

        try:

            lon = float(
                point["lon"]
            )

            lat = float(
                point["lat"]
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        coordinates.append(
            (
                lon,
                lat,
            )
        )

    return coordinates


# =========================================================
# WAY -> SHAPELY
# =========================================================


def _way_geometry(
    element: dict,
    category: str,
):
    """
    Convert an OSM way returned with `out geom` into a
    Shapely geometry.
    """

    coordinates = (
        _coords_from_geometry(
            element.get(
                "geometry"
            )
        )
    )

    if len(coordinates) < 2:
        return None

    # Water bodies and buildings are commonly represented
    # by closed polygons.
    area_like = (
        category
        in {
            "water",
            "building",
        }
    )

    if (
        area_like
        and len(coordinates) >= 4
        and coordinates[0]
        == coordinates[-1]
    ):

        polygon = Polygon(
            coordinates
        )

        if not polygon.is_valid:

            try:
                polygon = polygon.buffer(
                    0
                )

            except Exception:
                return None

        if polygon.is_empty:
            return None

        return polygon

    # Roads, rivers, streams, canals etc. are normally
    # represented as line geometries.
    try:

        return LineString(
            coordinates
        )

    except Exception:
        return None


# =========================================================
# RELATION -> SHAPELY
# =========================================================


def _relation_geometry(
    element: dict,
    category: str,
):
    """
    Convert an OSM relation into a Shapely geometry.

    This is mainly useful for:

        lakes
        wetlands
        reservoirs
        riverbanks
        multipolygon water bodies
    """

    lines = []

    polygons = []

    members = element.get(
        "members",
        [],
    )

    for member in members:

        coordinates = (
            _coords_from_geometry(
                member.get(
                    "geometry"
                )
            )
        )

        if len(coordinates) < 2:
            continue

        # -------------------------------------------------
        # Closed member
        # -------------------------------------------------

        if (
            len(coordinates) >= 4
            and coordinates[0]
            == coordinates[-1]
        ):

            try:

                polygon = Polygon(
                    coordinates
                )

                if not polygon.is_valid:
                    polygon = (
                        polygon.buffer(
                            0
                        )
                    )

                if not polygon.is_empty:
                    polygons.append(
                        polygon
                    )

            except Exception:
                continue

        # -------------------------------------------------
        # Open member
        # -------------------------------------------------

        else:

            try:

                lines.append(
                    LineString(
                        coordinates
                    )
                )

            except Exception:
                continue

    # -----------------------------------------------------
    # Water/building multipolygons
    # -----------------------------------------------------

    if category in {
        "water",
        "building",
    }:

        if lines:

            try:

                merged = unary_union(
                    lines
                )

                generated_polygons = list(
                    polygonize(
                        merged
                    )
                )

                polygons.extend(
                    generated_polygons
                )

            except Exception:
                pass

        if polygons:

            try:

                return unary_union(
                    polygons
                )

            except Exception:
                pass

    # -----------------------------------------------------
    # Fallback to line geometry
    # -----------------------------------------------------

    if lines:

        try:

            return unary_union(
                lines
            )

        except Exception:
            return None

    if polygons:

        try:

            return unary_union(
                polygons
            )

        except Exception:
            return None

    return None


# =========================================================
# BOUNDING BOX HELPERS
# =========================================================


def _normalise_bounds(
    bounds,
) -> tuple[
    float,
    float,
    float,
    float,
]:
    """
    Return:

        min_lon
        min_lat
        max_lon
        max_lat
    """

    (
        min_lon,
        min_lat,
        max_lon,
        max_lat,
    ) = bounds

    return (
        float(min_lon),
        float(min_lat),
        float(max_lon),
        float(max_lat),
    )


def _bbox_string(
    bounds: tuple[
        float,
        float,
        float,
        float,
    ],
) -> str:
    """
    Convert Shapely bbox order:

        min_lon, min_lat, max_lon, max_lat

    into Overpass bbox order:

        south, west, north, east
    """

    (
        min_lon,
        min_lat,
        max_lon,
        max_lat,
    ) = bounds

    return (
        f"{min_lat:.7f},"
        f"{min_lon:.7f},"
        f"{max_lat:.7f},"
        f"{max_lon:.7f}"
    )


def _split_bounds(
    bounds: tuple[
        float,
        float,
        float,
        float,
    ],
) -> list[
    tuple[
        float,
        float,
        float,
        float,
    ]
]:
    """
    Split one bbox into four tiles.
    """

    (
        min_lon,
        min_lat,
        max_lon,
        max_lat,
    ) = bounds

    middle_lon = (
        min_lon
        + max_lon
    ) / 2.0

    middle_lat = (
        min_lat
        + max_lat
    ) / 2.0

    return [

        # South-west
        (
            min_lon,
            min_lat,
            middle_lon,
            middle_lat,
        ),

        # South-east
        (
            middle_lon,
            min_lat,
            max_lon,
            middle_lat,
        ),

        # North-west
        (
            min_lon,
            middle_lat,
            middle_lon,
            max_lat,
        ),

        # North-east
        (
            middle_lon,
            middle_lat,
            max_lon,
            max_lat,
        ),
    ]


# =========================================================
# CACHE
# =========================================================


def _cache_file(
    group: str,
    bounds: tuple[
        float,
        float,
        float,
        float,
    ],
) -> Path:

    CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    bbox = _bbox_string(
        bounds
    )

    raw_key = (
        f"{CACHE_VERSION}|"
        f"{group}|"
        f"{bbox}"
    )

    key = hashlib.sha1(
        raw_key.encode(
            "utf-8"
        )
    ).hexdigest()[:20]

    return (
        CACHE_DIR
        / (
            f"osm_"
            f"{group}_"
            f"{key}.json"
        )
    )


def _read_cache(
    path: Path,
) -> list[dict] | None:

    if not path.exists():
        return None

    try:

        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        elements = payload.get(
            "elements",
            [],
        )

        if not isinstance(
            elements,
            list,
        ):
            return None

        return elements

    except Exception:

        return None


def _write_cache(
    path: Path,
    elements: list[dict],
) -> None:

    try:

        payload = {
            "version":
                CACHE_VERSION,

            "elements":
                elements,
        }

        path.write_text(
            json.dumps(
                payload
            ),
            encoding="utf-8",
        )

    except Exception:

        # Cache problems must not fail the actual analysis.
        pass


# =========================================================
# REMOVE DUPLICATES
# =========================================================


def _deduplicate_elements(
    elements: list[dict],
) -> list[dict]:
    """
    Remove repeated OSM features.

    This is needed when a way crosses two tiles.
    """

    unique = {}

    anonymous_index = 0

    for element in elements:

        element_type = str(
            element.get(
                "type",
                "unknown",
            )
        )

        element_id = (
            element.get(
                "id"
            )
        )

        if element_id is None:

            anonymous_index += 1

            key = (
                "anonymous",
                anonymous_index,
            )

        else:

            key = (
                element_type,
                str(
                    element_id
                ),
            )

        unique[key] = element

    return list(
        unique.values()
    )


# =========================================================
# BUILD OVERPASS QUERY
# =========================================================


def _build_query(
    group: str,
    bounds: tuple[
        float,
        float,
        float,
        float,
    ],
) -> str:

    bbox = _bbox_string(
        bounds
    )

    # -----------------------------------------------------
    # WATER
    # -----------------------------------------------------

    if group == "water":

        return f"""
[out:json][timeout:{OVERPASS_QUERY_TIMEOUT_SECONDS}];
(
  way["natural"="water"]({bbox});
  relation["natural"="water"]({bbox});

  way["natural"="wetland"]({bbox});
  relation["natural"="wetland"]({bbox});

  way["water"]({bbox});
  relation["water"]({bbox});

  way["waterway"="riverbank"]({bbox});
  relation["waterway"="riverbank"]({bbox});

  way["waterway"~"^(river|stream|canal|drain|ditch)$"]({bbox});

  way["landuse"~"^(reservoir|basin)$"]({bbox});
  relation["landuse"~"^(reservoir|basin)$"]({bbox});
);
out geom qt;
"""

    # -----------------------------------------------------
    # ROADS
    # -----------------------------------------------------

    if group == "roads":

        return f"""
[out:json][timeout:{OVERPASS_QUERY_TIMEOUT_SECONDS}];
(
  way["highway"]({bbox});
);
out geom qt;
"""

    # -----------------------------------------------------
    # BUILDINGS
    # -----------------------------------------------------

    if group == "buildings":

        return f"""
[out:json][timeout:{OVERPASS_QUERY_TIMEOUT_SECONDS}];
(
  way["building"]({bbox});
);
out geom qt;
"""

    raise ValueError(
        f"Unknown OSM query group: "
        f"{group}"
    )


# =========================================================
# HTTP OVERPASS REQUEST
# =========================================================


def _request_overpass(
    query: str,
    group: str,
) -> tuple[
    list[dict],
    str,
]:
    """
    Try each configured Overpass server exactly once.

    Important:

    We do NOT repeatedly retry the same unhealthy public
    server.

    Example:

        private.coffee
              ↓ fail

        maps.mail.ru
              ↓ fail

        overpass-api.de
              ↓ fail

        raise error

    This prevents the huge retry storm that happened in the
    previous implementation.
    """

    errors: list[str] = []

    had_http_response = False

    timeout = httpx.Timeout(
        HTTP_TIMEOUT_SECONDS,
        connect=
            HTTP_CONNECT_TIMEOUT_SECONDS,
    )

    headers = {
        "User-Agent": (
            "VillagePondPlanningStudentProject/1.0 "
            "(academic geospatial project)"
        ),

        "Accept":
            "application/json",
    }

    for endpoint in (
        OVERPASS_ENDPOINTS
    ):

        print(
            "[land-service] "
            f"Querying {group} from "
            f"{endpoint}"
        )

        try:

            with httpx.Client(
                timeout=timeout,
                headers=headers,
                follow_redirects=True,
            ) as client:

                response = client.post(
                    endpoint,
                    data={
                        "data": query
                    },
                )

            had_http_response = True

            # ---------------------------------------------
            # Successful response
            # ---------------------------------------------

            if response.status_code == 200:

                try:

                    payload = (
                        response.json()
                    )

                except Exception as exc:

                    errors.append(
                        f"{endpoint}: "
                        f"invalid JSON response "
                        f"({exc})"
                    )

                    continue

                elements = payload.get(
                    "elements",
                    [],
                )

                if not isinstance(
                    elements,
                    list,
                ):

                    errors.append(
                        f"{endpoint}: "
                        "response does not contain "
                        "a valid elements array"
                    )

                    continue

                print(
                    "[land-service] "
                    f"{group}: received "
                    f"{len(elements)} "
                    f"OSM element(s)"
                )

                return (
                    elements,
                    endpoint,
                )

            # ---------------------------------------------
            # HTTP error
            # ---------------------------------------------

            status = (
                response.status_code
            )

            print(
                "[land-service] "
                f"{endpoint} returned "
                f"HTTP {status}; "
                "trying next server."
            )

            errors.append(
                f"{endpoint}: "
                f"HTTP {status}"
            )

            # Be slightly polite if a public endpoint
            # explicitly rate-limits us.
            if status == 429:

                retry_after = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                try:

                    wait_seconds = min(
                        float(
                            retry_after
                        ),
                        10.0,
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    wait_seconds = 2.0

                time.sleep(
                    max(
                        0.0,
                        wait_seconds,
                    )
                )

        # -------------------------------------------------
        # Network / DNS / routing errors
        # -------------------------------------------------

        except httpx.RequestError as exc:

            message = (
                f"{endpoint}: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            errors.append(
                message
            )

            print(
                "[land-service] "
                f"Cannot reach {endpoint}: "
                f"{exc}"
            )

            print(
                "[land-service] "
                "Trying next Overpass server."
            )

            continue

        # -------------------------------------------------
        # Unexpected error
        # -------------------------------------------------

        except Exception as exc:

            errors.append(
                f"{endpoint}: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            print(
                "[land-service] "
                f"Unexpected error from "
                f"{endpoint}: "
                f"{exc}"
            )

            continue

    error_message = (
        "All configured Overpass "
        f"servers failed for '{group}'. "
        + " | ".join(
            errors
        )
    )

    raise OverpassRequestError(
        error_message,
        had_http_response=
            had_http_response,
    )


# =========================================================
# FETCH ONE FEATURE GROUP
# =========================================================


def _fetch_group(
    *,
    group: str,
    bounds: tuple[
        float,
        float,
        float,
        float,
    ],
    depth: int = 0,
) -> tuple[
    list[dict],
    str,
]:
    """
    Fetch one OpenStreetMap feature category.

    Flow:

        cache
          ↓

        complete bbox query
          ↓

        success → cache → return

    If the query fails:

        NETWORK UNREACHABLE
        → do NOT tile

        every server unavailable
        → do NOT tile

        server returned actual HTTP errors
        + group is roads/buildings
        → optionally split into 4 tiles once
    """

    cache_path = _cache_file(
        group,
        bounds,
    )

    cached = _read_cache(
        cache_path
    )

    # -----------------------------------------------------
    # Cached data exists
    # -----------------------------------------------------

    if cached is not None:

        print(
            "[land-service] "
            f"Using cached {group} data: "
            f"{cache_path.name}"
        )

        return (
            cached,
            (
                "local-cache:"
                f"{cache_path.name}"
            ),
        )

    # -----------------------------------------------------
    # Direct request
    # -----------------------------------------------------

    query = _build_query(
        group,
        bounds,
    )

    try:

        elements, endpoint = (
            _request_overpass(
                query,
                group,
            )
        )

        elements = (
            _deduplicate_elements(
                elements
            )
        )

        _write_cache(
            cache_path,
            elements,
        )

        return (
            elements,
            endpoint,
        )

    except OverpassRequestError as exc:

        # -------------------------------------------------
        # DO NOT TILE WATER
        #
        # Water queries are normally much lighter than
        # building/road queries.
        # -------------------------------------------------

        may_tile = (
            group
            in {
                "roads",
                "buildings",
            }
            and
            exc.had_http_response
            and
            depth
            < MAX_TILE_DEPTH
        )

        if not may_tile:

            raise

        # -------------------------------------------------
        # Try four smaller areas
        # -------------------------------------------------

        print(
            "[land-service] "
            f"{group} query failed after "
            "reaching the servers. "
            "Trying four smaller tiles."
        )

        tiles = _split_bounds(
            bounds
        )

        combined: list[
            dict
        ] = []

        sources: list[
            str
        ] = []

        for index, tile in enumerate(
            tiles,
            start=1,
        ):

            print(
                "[land-service] "
                f"Fetching {group} tile "
                f"{index}/4"
            )

            tile_elements, tile_source = (
                _fetch_group(
                    group=group,
                    bounds=tile,
                    depth=depth + 1,
                )
            )

            combined.extend(
                tile_elements
            )

            sources.append(
                tile_source
            )

        combined = (
            _deduplicate_elements(
                combined
            )
        )

        _write_cache(
            cache_path,
            combined,
        )

        return (
            combined,
            (
                "tiled-overpass:"
                + ",".join(
                    sorted(
                        set(
                            sources
                        )
                    )
                )
            ),
        )


# =========================================================
# DOWNLOAD ALL EXCLUSION DATA
# =========================================================


def _download_osm_elements(
    boundary_wgs84,
) -> tuple[
    list[dict],
    str,
]:
    """
    Download mapped features that make land unsuitable for
    constructing a new pond.

    We intentionally query three groups separately:

        water
        roads
        buildings

    This avoids a very large monolithic Overpass request.
    """

    bounds = _normalise_bounds(
        boundary_wgs84.bounds
    )

    all_elements: list[
        dict
    ] = []

    source_details: dict[
        str,
        str,
    ] = {}

    # -----------------------------------------------------
    # WATER FIRST
    # -----------------------------------------------------

    groups = (
        "water",
        "roads",
        "buildings",
    )

    failures = []

    for group in groups:

        try:

            elements, source = (
                _fetch_group(
                    group=group,
                    bounds=bounds,
                )
            )

            all_elements.extend(
                elements
            )

            source_details[
                group
            ] = source

        except Exception as exc:

            failures.append(
                f"{group}: {exc}"
            )

            print(
                "[land-service] "
                f"Unable to retrieve "
                f"{group}: {exc}"
            )

    # -----------------------------------------------------
    # SAFETY:
    #
    # Never silently treat missing OSM data as free land.
    # -----------------------------------------------------

    if failures:

        raise RuntimeError(
            "OpenStreetMap land-suitability "
            "information could not be retrieved "
            "completely. "
            "Pond analysis was stopped rather than "
            "incorrectly treating unverified land as "
            "available. "
            "Check network connectivity or try again "
            "later. "
            "Details: "
            + " | ".join(
                failures
            )
        )

    all_elements = (
        _deduplicate_elements(
            all_elements
        )
    )

    source = (
        "OpenStreetMap via Overpass; "
        f"water={source_details.get('water')}; "
        f"roads={source_details.get('roads')}; "
        f"buildings={source_details.get('buildings')}"
    )

    print(
        "[land-service] "
        f"Total unique OSM exclusion "
        f"elements: "
        f"{len(all_elements)}"
    )

    return (
        all_elements,
        source,
    )


# =========================================================
# PROJECT AND BUFFER FEATURE
# =========================================================


def _project_and_buffer(
    geometry,
    category: str,
    tags: dict,
    to_projected,
    pond_radius_m: float,
    safety_buffer_m: float,
):
    """
    Convert WGS84 OSM geometry into projected metre
    coordinates and apply the pond-footprint safety buffer.

    This ensures not only the pond centre, but the estimated
    entire pond footprint stays clear of the obstacle.
    """

    try:

        projected = (
            shapely_transform(
                to_projected.transform,
                geometry,
            )
        )

    except Exception:

        return None

    if projected.is_empty:
        return None

    # -----------------------------------------------------
    # EXISTING WATER BODY
    # -----------------------------------------------------

    if category == "water":

        distance = (
            pond_radius_m
            + safety_buffer_m
        )

    # -----------------------------------------------------
    # BUILDING
    # -----------------------------------------------------

    elif category == "building":

        distance = (
            pond_radius_m
            + max(
                5.0,
                safety_buffer_m,
            )
        )

    # -----------------------------------------------------
    # ROAD
    # -----------------------------------------------------

    elif category == "road":

        # OSM roads are usually centre lines, not full road
        # polygons, so reserve a little additional width.
        distance = (
            pond_radius_m
            + max(
                6.0,
                safety_buffer_m,
            )
        )

    # -----------------------------------------------------
    # LINEAR WATERWAY
    # -----------------------------------------------------

    elif category == "waterway":

        waterway_type = (
            tags.get(
                "waterway"
            )
        )

        # Approximate half-width where OSM only provides
        # the waterway centre line.
        half_width = {

            "river":
                20.0,

            "canal":
                8.0,

            "stream":
                4.0,

            "drain":
                3.0,

            "ditch":
                2.0,

        }.get(
            waterway_type,
            5.0,
        )

        distance = (
            pond_radius_m
            + safety_buffer_m
            + half_width
        )

    else:

        distance = (
            pond_radius_m
            + safety_buffer_m
        )

    try:

        buffered = (
            projected.buffer(
                distance
            )
        )

    except Exception:

        return None

    if buffered.is_empty:
        return None

    return buffered


# =========================================================
# MAIN PUBLIC FUNCTION
# =========================================================


def build_osm_free_land_mask(
    terrain,
    boundary_wgs84,
    pond_radius_m: float,
    safety_buffer_m: float = 10.0,
) -> LandFilterResult:
    """
    Create a DEM-sized boolean mask containing terrain cells
    that are clear of mapped:

        rivers
        streams
        canals
        drains
        ditches
        lakes
        reservoirs
        wetlands
        roads
        buildings

    IMPORTANT
    ---------

    "free land" in this module ONLY means:

        no mapped OpenStreetMap exclusion obstacle

    It does NOT prove that the land is:

        government-owned
        public
        legally available
        construction-approved

    Official land ownership/cadastral information would be
    required for that decision.
    """

    # -----------------------------------------------------
    # Download OpenStreetMap exclusion features
    # -----------------------------------------------------

    elements, source = (
        _download_osm_elements(
            boundary_wgs84
        )
    )

    feature_counts = {

        "water":
            0,

        "waterway":
            0,

        "road":
            0,

        "building":
            0,
    }

    exclusion_geometries = []

    # =====================================================
    # OSM OBJECT -> BUFFERED EXCLUSION POLYGON
    # =====================================================

    for element in elements:

        tags = element.get(
            "tags",
            {},
        )

        category = _category(
            tags
        )

        if category is None:
            continue

        element_type = (
            element.get(
                "type"
            )
        )

        # -------------------------------------------------
        # Convert geometry
        # -------------------------------------------------

        if element_type == "way":

            geometry = (
                _way_geometry(
                    element,
                    category,
                )
            )

        elif element_type == "relation":

            geometry = (
                _relation_geometry(
                    element,
                    category,
                )
            )

        else:

            geometry = None

        if (
            geometry is None
            or geometry.is_empty
        ):
            continue

        # -------------------------------------------------
        # Project + safety buffer
        # -------------------------------------------------

        buffered = (
            _project_and_buffer(
                geometry=
                    geometry,

                category=
                    category,

                tags=
                    tags,

                to_projected=
                    terrain.to_projected,

                pond_radius_m=
                    float(
                        pond_radius_m
                    ),

                safety_buffer_m=
                    float(
                        safety_buffer_m
                    ),
            )
        )

        if (
            buffered is None
            or buffered.is_empty
        ):
            continue

        # -------------------------------------------------
        # Keep only geometry inside our analysis boundary.
        # -------------------------------------------------

        try:

            clipped = (
                buffered.intersection(
                    terrain
                    .boundary_projected
                )
            )

        except Exception:

            try:

                repaired = (
                    buffered.buffer(
                        0
                    )
                )

                clipped = (
                    repaired.intersection(
                        terrain
                        .boundary_projected
                    )
                )

            except Exception:

                continue

        if clipped.is_empty:
            continue

        exclusion_geometries.append(
            clipped
        )

        feature_counts[
            category
        ] += 1

    # =====================================================
    # MERGE EXCLUSION GEOMETRIES
    # =====================================================

    if exclusion_geometries:

        try:

            exclusion_union = (
                unary_union(
                    exclusion_geometries
                )
            )

        except Exception:

            # Repair individual geometries and retry.
            repaired = []

            for geometry in (
                exclusion_geometries
            ):

                try:

                    clean = (
                        geometry.buffer(
                            0
                        )
                    )

                    if not clean.is_empty:

                        repaired.append(
                            clean
                        )

                except Exception:

                    continue

            if repaired:

                exclusion_union = (
                    unary_union(
                        repaired
                    )
                )

            else:

                exclusion_union = (
                    GeometryCollection()
                )

    else:

        exclusion_union = (
            GeometryCollection()
        )

    # =====================================================
    # RASTERISE EXCLUSION AREA
    # =====================================================

    if not exclusion_union.is_empty:

        exclusion_mask = (
            geometry_mask(
                [
                    mapping(
                        exclusion_union
                    )
                ],

                out_shape=
                    terrain
                    .valid_mask
                    .shape,

                transform=
                    terrain
                    .transform,

                invert=True,

                all_touched=True,
            )
        )

    else:

        exclusion_mask = (
            np.zeros_like(
                terrain.valid_mask,
                dtype=bool,
            )
        )

    # =====================================================
    # FREE LAND MASK
    # =====================================================
    #
    # Free land =
    #
    #     valid DEM cell
    #           AND
    #     not inside an OSM exclusion
    # =====================================================

    free_land_mask = (
        terrain.valid_mask
        & ~exclusion_mask
    )

    if not free_land_mask.any():

        raise ValueError(
            "Land-suitability filtering removed "
            "the entire analysis area. "
            "This may happen in a dense urban area or "
            "when the pond radius/safety buffer is too "
            "large. Try reducing the pond radius or "
            "analysis region."
        )

    # =====================================================
    # CONVERT EXCLUSION AREA BACK TO LAT/LON FOR FRONTEND
    # =====================================================

    exclusion_geojson = None

    if not exclusion_union.is_empty:

        try:

            wgs84_exclusion = (
                shapely_transform(
                    terrain
                    .to_wgs84
                    .transform,

                    exclusion_union,
                )
            )

            exclusion_geojson = (
                mapping(
                    wgs84_exclusion
                )
            )

        except Exception:

            # Mapping failure should not invalidate the
            # actual raster land filtering.
            exclusion_geojson = None

    # =====================================================
    # CELL COUNTS
    # =====================================================

    excluded_cells = int(
        (
            terrain.valid_mask
            & exclusion_mask
        ).sum()
    )

    free_cells = int(
        free_land_mask.sum()
    )

    # =====================================================
    # RESULT
    # =====================================================

    return LandFilterResult(

        free_land_mask=
            free_land_mask,

        exclusion_geojson=
            exclusion_geojson,

        source=
            source,

        feature_counts=
            feature_counts,

        excluded_cell_count=
            excluded_cells,

        free_cell_count=
            free_cells,

        notes=[
            (
                "Mapped water bodies, waterways, roads "
                "and buildings are excluded from pond "
                "candidate locations."
            ),
            (
                "Existing waterways remain part of the "
                "hydrological terrain calculation and "
                "are excluded only when selecting new "
                "pond locations."
            ),
            (
                "The exclusion geometry is buffered by "
                "the proposed pond radius so the full "
                "estimated pond footprint remains clear "
                "of mapped obstacles."
            ),
            (
                "OpenStreetMap queries are separated "
                "into water, road and building requests "
                "to reduce load on public Overpass "
                "servers."
            ),
            (
                "Multiple public Overpass instances are "
                "used as fallbacks when one service is "
                "unavailable."
            ),
            (
                "Road and building requests may be "
                "divided into four smaller geographic "
                "tiles when the complete request reaches "
                "a server but fails."
            ),
            (
                "OSM feature-clear land is not proof of "
                "government ownership, legal land "
                "availability or construction approval."
            ),
        ],
    )
