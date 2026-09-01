from __future__ import annotations

import httpx


# =========================================================
# PHOTON GEOCODING
# =========================================================
#
# Photon:
#
# - uses OpenStreetMap data
# - supports search-as-you-type
# - supports location bias
# - supports country filtering
#
# The public demo service is suitable for reasonable
# academic/demo usage.
# =========================================================

PHOTON_SEARCH_URL = (
    "https://photon.komoot.io/api/"
)


# =========================================================
# BUILD HUMAN-READABLE LABEL
# =========================================================

def _build_label(
    properties: dict,
) -> str:
    """
    Create a readable label for a Photon search result.

    Example:

        Chandigarh,
        Chandigarh,
        India
    """

    possible_parts = [

        properties.get(
            "name"
        ),

        properties.get(
            "street"
        ),

        properties.get(
            "locality"
        ),

        properties.get(
            "district"
        ),

        properties.get(
            "city"
        ),

        properties.get(
            "county"
        ),

        properties.get(
            "state"
        ),

        properties.get(
            "postcode"
        ),

        properties.get(
            "country"
        ),
    ]

    result = []

    seen = set()

    for part in possible_parts:

        if not part:
            continue

        text = str(
            part
        ).strip()

        if not text:
            continue

        lower = (
            text.lower()
        )

        # Avoid labels such as:
        #
        # Chandigarh, Chandigarh, Chandigarh
        #
        if lower in seen:
            continue

        seen.add(
            lower
        )

        result.append(
            text
        )

    return ", ".join(
        result
    )


# =========================================================
# SEARCH PLACES
# =========================================================

def search_places(
    *,
    query: str,
    limit: int = 8,
    latitude: float | None = None,
    longitude: float | None = None,
    zoom: int | None = None,
) -> list[dict]:
    """
    Search OpenStreetMap place names through Photon.

    No result is persisted by this service.

    Parameters
    ----------
    query:
        User-entered text.

    latitude / longitude:
        Optional current map centre used only as
        a ranking bias.

    countrycode:
        Restricted to India because this pond-planning
        application currently targets Indian locations.
    """

    query = (
        query
        .strip()
    )

    if len(query) < 2:

        return []

    limit = max(
        1,
        min(
            int(
                limit
            ),
            10,
        ),
    )

    params = {

        "q":
            query,

        "limit":
            limit,

        "lang":
            "en",

        # Restrict suggestions to India.
        "countrycode":
            "IN",
    }

    # =====================================================
    # OPTIONAL MAP LOCATION BIAS
    # =====================================================
    #
    # This does NOT restrict results to the current screen.
    #
    # It only ranks nearby locations slightly higher.
    # =====================================================

    if (
        latitude is not None
        and
        longitude is not None
    ):

        params[
            "lat"
        ] = latitude

        params[
            "lon"
        ] = longitude

        params[
            "location_bias_scale"
        ] = 0.25

        if zoom is not None:

            params[
                "zoom"
            ] = max(
                1,
                min(
                    int(
                        zoom
                    ),
                    18,
                ),
            )

    headers = {

        "User-Agent":
            (
                "AI-Based-Village-Pond-Planning-System/"
                "1.0 academic-project"
            ),

        "Accept":
            "application/json",
    }

    try:

        with httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers=headers,
        ) as client:

            response = client.get(
                PHOTON_SEARCH_URL,
                params=params,
            )

            response.raise_for_status()

            payload = (
                response.json()
            )

    except httpx.HTTPError as exc:

        raise RuntimeError(
            "Place-search service is temporarily "
            f"unavailable: {exc}"
        ) from exc

    except Exception as exc:

        raise RuntimeError(
            "Place search failed: "
            f"{exc}"
        ) from exc

    features = payload.get(
        "features",
        [],
    )

    if not isinstance(
        features,
        list,
    ):

        return []

    results = []

    for feature in features:

        geometry = (
            feature.get(
                "geometry"
            )
            or
            {}
        )

        coordinates = (
            geometry.get(
                "coordinates"
            )
        )

        if (
            not isinstance(
                coordinates,
                list,
            )
            or
            len(coordinates) < 2
        ):

            continue

        try:

            longitude_value = float(
                coordinates[0]
            )

            latitude_value = float(
                coordinates[1]
            )

        except (
            TypeError,
            ValueError,
        ):

            continue

        properties = (
            feature.get(
                "properties"
            )
            or
            {}
        )

        label = (
            _build_label(
                properties
            )
        )

        if not label:

            continue

        # =================================================
        # PHOTON MAY RETURN FEATURE EXTENT
        # =================================================
        #
        # extent:
        #
        # [
        #     min_lon,
        #     max_lat,
        #     max_lon,
        #     min_lat
        # ]
        #
        # We pass it to frontend when present so Leaflet
        # can zoom to a large place/building correctly.
        # =================================================

        extent = (
            properties.get(
                "extent"
            )
        )

        results.append({

            "name":
                properties.get(
                    "name"
                )
                or
                label,

            "label":
                label,

            "latitude":
                latitude_value,

            "longitude":
                longitude_value,

            "state":
                properties.get(
                    "state"
                ),

            "county":
                properties.get(
                    "county"
                ),

            "city":
                properties.get(
                    "city"
                ),

            "district":
                properties.get(
                    "district"
                ),

            "postcode":
                properties.get(
                    "postcode"
                ),

            "country":
                properties.get(
                    "country"
                ),

            "country_code":
                properties.get(
                    "countrycode"
                ),

            "osm_key":
                properties.get(
                    "osm_key"
                ),

            "osm_value":
                properties.get(
                    "osm_value"
                ),

            "osm_type":
                properties.get(
                    "osm_type"
                ),

            "osm_id":
                properties.get(
                    "osm_id"
                ),

            "extent":
                extent,
        })

    return results
