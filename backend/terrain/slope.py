import numpy as np


def calculate_slope_percent(dem: np.ndarray, valid_mask: np.ndarray, resolution_m: float) -> np.ndarray:
    # Fill outside cells only for gradient calculation; output will still be masked.
    filled = dem.copy()
    mean_value = float(np.nanmean(filled))
    filled[~np.isfinite(filled)] = mean_value

    dz_dy, dz_dx = np.gradient(filled, resolution_m, resolution_m)
    slope = np.sqrt(dz_dx ** 2 + dz_dy ** 2) * 100.0
    slope[~valid_mask] = np.nan
    return slope
