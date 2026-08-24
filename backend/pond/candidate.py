from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import binary_erosion, maximum_filter


@dataclass(frozen=True)
class CandidateCell:
    row: int
    col: int
    score: float


def _candidate_score_grid(
    dem: np.ndarray,
    slope_percent: np.ndarray,
    accumulation: np.ndarray,
    valid_mask: np.ndarray,
    resolution_m: float,
    max_slope_percent: float,
    min_boundary_distance_m: float,
    min_accumulation_percentile: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Build a 0..1 suitability score grid for hydrological pond candidates."""
    valid = valid_mask & np.isfinite(dem) & np.isfinite(accumulation) & np.isfinite(slope_percent)

    iterations = max(1, int(round(min_boundary_distance_m / resolution_m)))
    interior = binary_erosion(valid, iterations=iterations, border_value=0)
    if not interior.any():
        interior = valid

    # Keep gentle terrain and meaningful drainage cells. The percentile makes
    # the method scale to maps of different sizes rather than hard-coding a
    # particular accumulation count from the sample KML.
    acc_values = accumulation[interior & np.isfinite(accumulation)]
    if acc_values.size == 0:
        raise ValueError("No valid flow-accumulation cells are available for candidate selection.")

    accumulation_threshold = float(np.nanpercentile(acc_values, min_accumulation_percentile))
    candidate_mask = (
        interior
        & (slope_percent <= max_slope_percent)
        & (accumulation >= accumulation_threshold)
    )

    # Relax only the accumulation threshold if the terrain is unusual.
    if not candidate_mask.any():
        candidate_mask = interior & (slope_percent <= max_slope_percent)
    if not candidate_mask.any():
        candidate_mask = interior

    acc = np.where(candidate_mask, accumulation, np.nan)
    elev = np.where(candidate_mask, dem, np.nan)
    slope = np.where(candidate_mask, slope_percent, np.nan)

    log_acc = np.log1p(acc)
    amin, amax = np.nanmin(log_acc), np.nanmax(log_acc)
    acc_score = (log_acc - amin) / (amax - amin + 1e-12)

    emin, emax = np.nanmin(elev), np.nanmax(elev)
    low_elev_score = 1.0 - (elev - emin) / (emax - emin + 1e-12)

    slope_score = 1.0 - np.clip(slope / max_slope_percent, 0, 1)

    # Phase-2 hydrological score. Land-use, road/building and ownership checks
    # are intentionally separate future filters.
    score = 0.65 * acc_score + 0.20 * slope_score + 0.15 * low_elev_score
    score[~candidate_mask] = np.nan
    return score, candidate_mask


def find_pond_candidates(
    dem: np.ndarray,
    slope_percent: np.ndarray,
    accumulation: np.ndarray,
    valid_mask: np.ndarray,
    resolution_m: float,
    max_candidates: int = 20,
    max_slope_percent: float = 8.0,
    min_boundary_distance_m: float = 30.0,
    min_candidate_spacing_m: float = 100.0,
    min_accumulation_percentile: float = 85.0,
) -> list[CandidateCell]:
    """
    Return multiple distinct hydrologically suitable pond positions.

    We select local maxima of the suitability score and enforce a minimum
    spacing so one drainage channel does not create dozens of near-duplicate
    markers. Nothing is hard-coded to the supplied contour map.
    """
    score, candidate_mask = _candidate_score_grid(
        dem,
        slope_percent,
        accumulation,
        valid_mask,
        resolution_m,
        max_slope_percent,
        min_boundary_distance_m,
        min_accumulation_percentile,
    )

    spacing_cells = max(1, int(round(min_candidate_spacing_m / resolution_m)))
    window = max(3, 2 * spacing_cells + 1)

    safe_score = np.where(np.isfinite(score), score, -np.inf)
    local_max = safe_score == maximum_filter(safe_score, size=window, mode="constant", cval=-np.inf)
    peak_mask = candidate_mask & local_max & np.isfinite(score)

    peak_indices = np.argwhere(peak_mask)
    if peak_indices.size == 0:
        index = int(np.nanargmax(score))
        r, c = np.unravel_index(index, score.shape)
        return [CandidateCell(int(r), int(c), float(score[r, c] * 100.0))]

    peak_indices = sorted(
        peak_indices,
        key=lambda rc: float(score[int(rc[0]), int(rc[1])]),
        reverse=True,
    )

    selected: list[CandidateCell] = []
    min_distance_cells = min_candidate_spacing_m / resolution_m

    for rr, cc in peak_indices:
        r, c = int(rr), int(cc)
        if any(
            ((r - p.row) ** 2 + (c - p.col) ** 2) ** 0.5 < min_distance_cells
            for p in selected
        ):
            continue

        selected.append(CandidateCell(r, c, float(score[r, c] * 100.0)))
        if len(selected) >= max_candidates:
            break

    return selected


def choose_pond_candidate(
    dem: np.ndarray,
    slope_percent: np.ndarray,
    accumulation: np.ndarray,
    valid_mask: np.ndarray,
    resolution_m: float,
    max_slope_percent: float = 8.0,
    min_boundary_distance_m: float = 30.0,
) -> tuple[int, int, float]:
    """Backward-compatible helper that returns the highest-ranked site."""
    best = find_pond_candidates(
        dem,
        slope_percent,
        accumulation,
        valid_mask,
        resolution_m,
        max_candidates=1,
        max_slope_percent=max_slope_percent,
        min_boundary_distance_m=min_boundary_distance_m,
    )[0]
    return best.row, best.col, best.score
