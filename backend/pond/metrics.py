from __future__ import annotations

import numpy as np
from scipy.ndimage import label


def estimate_candidate_water_metrics(
    row: int,
    col: int,
    dem: np.ndarray,
    slope_percent: np.ndarray,
    valid_mask: np.ndarray,
    resolution_m: float,
    catchment_area_m2: float,
    average_annual_rainfall_mm: float | None,
    runoff_coefficient: float = 0.30,
    pond_radius_m: float = 40.0,
    max_pond_slope_percent: float = 5.0,
    max_pond_depth_m: float = 3.0,
    shape_factor: float = 0.70,
) -> dict:
    """Calculate planning-level pond footprint, storage and runoff metrics.

    This is intentionally an *estimate*. The pond footprint is the connected
    gentle terrain around a candidate within a configurable radius. Storage is
    approximate excavation/storage geometry, not a civil-engineering design.
    """
    rows, cols = dem.shape
    radius_cells = max(1, int(np.ceil(pond_radius_m / resolution_m)))

    r0, r1 = max(0, row - radius_cells), min(rows, row + radius_cells + 1)
    c0, c1 = max(0, col - radius_cells), min(cols, col + radius_cells + 1)

    rr, cc = np.ogrid[r0:r1, c0:c1]
    distance_m = np.sqrt((rr - row) ** 2 + (cc - col) ** 2) * resolution_m

    local_valid = valid_mask[r0:r1, c0:c1]
    local_slope = slope_percent[r0:r1, c0:c1]
    eligible = (
        local_valid
        & np.isfinite(local_slope)
        & (local_slope <= max_pond_slope_percent)
        & (distance_m <= pond_radius_m)
    )

    local_row = row - r0
    local_col = col - c0
    eligible[local_row, local_col] = True

    labels, _ = label(eligible, structure=np.ones((3, 3), dtype=int))
    component_id = labels[local_row, local_col]
    footprint_mask = labels == component_id

    footprint_cells = int(footprint_mask.sum())
    cell_area_m2 = resolution_m * resolution_m
    pond_area_m2 = float(footprint_cells * cell_area_m2)

    local_dem = dem[r0:r1, c0:c1]
    footprint_elevations = local_dem[footprint_mask & np.isfinite(local_dem)]
    candidate_elevation = float(dem[row, col])

    if footprint_elevations.size:
        local_relief_m = max(0.0, float(np.nanpercentile(footprint_elevations, 90)) - candidate_elevation)
    else:
        local_relief_m = 0.0

    # Excavation depth estimate: at least 1.5 m, increased where nearby terrain
    # provides useful relief, but capped by the planning limit supplied by user.
    recommended_depth_m = float(np.clip(1.5 + local_relief_m, 1.5, max_pond_depth_m))
    storage_capacity_m3 = pond_area_m2 * recommended_depth_m * shape_factor

    annual_runoff_m3 = None
    runoff_to_storage_ratio = None
    potential_fill_percent = None
    if average_annual_rainfall_mm is not None:
        rainfall_m = average_annual_rainfall_mm / 1000.0
        annual_runoff_m3 = rainfall_m * catchment_area_m2 * runoff_coefficient
        if storage_capacity_m3 > 0:
            runoff_to_storage_ratio = annual_runoff_m3 / storage_capacity_m3
            potential_fill_percent = min(100.0, runoff_to_storage_ratio * 100.0)

    return {
        "pond_area_m2": round(pond_area_m2, 2),
        "pond_area_hectares": round(pond_area_m2 / 10_000.0, 4),
        "recommended_depth_m": round(recommended_depth_m, 2),
        "shape_factor": round(float(shape_factor), 3),
        "estimated_storage_capacity_m3": round(float(storage_capacity_m3), 2),
        "runoff_coefficient": round(float(runoff_coefficient), 3),
        "estimated_annual_runoff_m3": round(float(annual_runoff_m3), 2) if annual_runoff_m3 is not None else None,
        "runoff_to_storage_ratio": round(float(runoff_to_storage_ratio), 3) if runoff_to_storage_ratio is not None else None,
        "potential_fill_percent": round(float(potential_fill_percent), 2) if potential_fill_percent is not None else None,
        "pond_radius_used_m": round(float(pond_radius_m), 2),
        "local_relief_m": round(float(local_relief_m), 3),
    }
