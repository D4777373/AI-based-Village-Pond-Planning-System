from typing import Any

from pydantic import BaseModel, Field


# =========================================================
# Terrain
# =========================================================

class TerrainSummary(BaseModel):
    contour_line_count: int
    minimum_elevation_m: float
    maximum_elevation_m: float
    contour_interval_m: float | None
    grid_resolution_m: float
    grid_rows: int
    grid_columns: int


# =========================================================
# Rainfall
# =========================================================

class RainfallYear(BaseModel):
    year: int
    rainfall_mm: float
    valid_days: int


class RainfallSummary(BaseModel):
    available: bool
    source: str
    latitude: float
    longitude: float
    period: str
    average_annual_rainfall_mm: float | None
    yearly: list[RainfallYear]
    error: str | None


# =========================================================
# Land Filter
# =========================================================

class LandFilterSummary(BaseModel):
    available: bool
    source: str
    excluded_feature_counts: dict[str, int]
    excluded_cell_count: int
    free_cell_count: int
    notes: list[str]


# =========================================================
# Catchment
# =========================================================

class CatchmentSummary(BaseModel):
    cell_count: int
    area_m2: float
    area_hectares: float


# =========================================================
# Pond / Water Calculation
# =========================================================

class WaterMetrics(BaseModel):
    pond_area_m2: float
    pond_area_hectares: float
    recommended_depth_m: float
    shape_factor: float

    estimated_storage_capacity_m3: float

    runoff_coefficient: float

    estimated_annual_runoff_m3: float | None

    runoff_to_storage_ratio: float | None

    potential_fill_percent: float | None

    pond_radius_used_m: float
    local_relief_m: float


# =========================================================
# Candidate
# =========================================================

class PondCandidate(BaseModel):
    candidate_id: int
    rank: int

    latitude: float
    longitude: float

    elevation_m: float
    slope_percent: float

    flow_accumulation_cells: int

    suitability_score: float = Field(
        ge=0,
        le=100,
    )

    catchment: CatchmentSummary

    water: WaterMetrics

    land_status: str


# =========================================================
# Candidate Generation Summary
# =========================================================

class CandidateGenerationSummary(BaseModel):
    returned_candidates: int
    max_candidates_requested: int
    minimum_spacing_m: float
    maximum_slope_percent: float
    minimum_accumulation_percentile: float


# =========================================================
# Full API Response
# =========================================================

class AnalysisResponse(BaseModel):
    status: str
    filename: str

    terrain: TerrainSummary

    rainfall: RainfallSummary

    land_filter: LandFilterSummary

    excluded_areas_geojson: dict[str, Any] | None

    candidates: list[PondCandidate]

    recommended_candidate_id: int

    recommended_catchment_geojson: dict[str, Any] | None

    boundary_geojson: dict[str, Any]

    candidate_generation: CandidateGenerationSummary

    method: dict[str, str]

    limitations: list[str]
