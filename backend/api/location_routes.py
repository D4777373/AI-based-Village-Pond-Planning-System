from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Form, HTTPException

from backend.services.analysis_service import analyze_contour_file
from backend.services.contour_generation_service import generate_contours_from_dem
from backend.services.geocoding_service import geocode_place
from backend.services.opentopography_service import download_global_dem


router = APIRouter()
BASE_DIR = Path(__file__).resolve().parents[2]
GENERATED_DIR = BASE_DIR / "data" / "generated"


@router.post("/analyzeLocation")
def analyze_location(
    location_name: str = Form(...),
    analysis_radius_m: float = Form(3000.0),
    contour_interval_m: float = Form(5.0),
    resolution_m: float = Form(10.0),
    max_candidates: int = Form(20),
    rainfall_years: int = Form(5),
    runoff_coefficient: float = Form(0.30),
    pond_radius_m: float = Form(40.0),
    max_pond_depth_m: float = Form(3.0),
):
    try:
        if contour_interval_m < 1 or contour_interval_m > 50:
            raise ValueError("Contour interval must be between 1 m and 50 m.")

        place = geocode_place(location_name, analysis_radius_m)

        job_id = uuid4().hex[:12]
        job_dir = GENERATED_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        dem_path = job_dir / "source_dem.tif"
        kml_path = job_dir / "generated_contours.kml"
        geojson_path = job_dir / "generated_contours.geojson"

        dem_info = download_global_dem(
            south=place.south,
            north=place.north,
            west=place.west,
            east=place.east,
            destination=dem_path,
            dem_type="COP30",
        )

        generated = generate_contours_from_dem(
            dem_path=dem_path,
            kml_path=kml_path,
            geojson_path=geojson_path,
            contour_interval_m=contour_interval_m,
        )

        # COP30 has nominal ~30 m horizontal resolution. Do not pretend
        # the hydrology grid is finer than the source DEM.
        effective_resolution_m = max(float(resolution_m), 30.0)

        # Reuse the complete, already-working KML analysis pipeline.
        result = analyze_contour_file(
            file_bytes=kml_path.read_bytes(),
            filename=kml_path.name,
            resolution_m=effective_resolution_m,
            max_candidates=max_candidates,
            rainfall_years=rainfall_years,
            runoff_coefficient=runoff_coefficient,
            pond_radius_m=pond_radius_m,
            max_pond_depth_m=max_pond_depth_m,
        )

        result["location_search"] = {
            "query": place.query,
            "resolved_name": place.display_name,
            "latitude": place.latitude,
            "longitude": place.longitude,
            "analysis_radius_m": analysis_radius_m,
            "bounding_box": {
                "south": place.south,
                "north": place.north,
                "west": place.west,
                "east": place.east,
            },
        }

        result["source_dem"] = {
            **dem_info,
            "vertical_source": "Copernicus COP30 DSM via OpenTopography",
            "nominal_horizontal_resolution_m": 30,
            "analysis_grid_resolution_m": effective_resolution_m,
            "resolution_note": (
                "The analysis grid is not allowed to be finer than 30 m for COP30, "
                "to avoid implying spatial accuracy that the source DEM does not provide."
            ),
        }

        result["generated_contours"] = {
            "contour_interval_m": generated.contour_interval_m,
            "minimum_elevation_m": generated.minimum_elevation_m,
            "maximum_elevation_m": generated.maximum_elevation_m,
            "contour_feature_count": generated.contour_feature_count,
            "geojson": generated.geojson,
        }

        result["generated_files"] = {
            "dem_url": f"/generated/{job_id}/source_dem.tif",
            "contour_kml_url": f"/generated/{job_id}/generated_contours.kml",
            "contour_geojson_url": f"/generated/{job_id}/generated_contours.geojson",
        }

        return result

    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Location analysis failed: {exc}",
        ) from exc
