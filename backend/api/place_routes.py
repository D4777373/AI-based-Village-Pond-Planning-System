from __future__ import annotations

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Response,
)

from backend.services.place_search_service import (
    search_places,
)


router = APIRouter()


# =========================================================
# SEARCH PLACE NAMES
# =========================================================

@router.get(
    "/searchPlaces"
)
def search_map_places(
    response: Response,

    q: str = Query(
        ...,
        min_length=2,
        max_length=120,
    ),

    lat: float | None = Query(
        None
    ),

    lon: float | None = Query(
        None
    ),

    zoom: int | None = Query(
        None,
        ge=1,
        le=18,
    ),
):
    """
    Search Indian OpenStreetMap locations using Photon.

    Results are returned only for the current request.

    This application does not persist place-search results.
    """

    # Explicitly tell browsers/proxies that these
    # autocomplete responses are not to be cached.
    response.headers[
        "Cache-Control"
    ] = "no-store"

    response.headers[
        "Pragma"
    ] = "no-cache"

    try:

        items = search_places(

            query=q,

            limit=8,

            latitude=lat,

            longitude=lon,

            zoom=zoom,
        )

        return {

            "query":
                q,

            "count":
                len(
                    items
                ),

            "items":
                items,
        }

    except RuntimeError as exc:

        raise HTTPException(
            status_code=503,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Unexpected place-search error: "
                f"{exc}"
            ),
        ) from exc
