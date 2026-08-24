from __future__ import annotations

import numpy as np

# D8 directions: N, NE, E, SE, S, SW, W, NW
DR = np.array([-1, -1, 0, 1, 1, 1, 0, -1], dtype=int)
DC = np.array([0, 1, 1, 1, 0, -1, -1, -1], dtype=int)
DIST = np.array([1.0, 2**0.5, 1.0, 2**0.5, 1.0, 2**0.5, 1.0, 2**0.5])


def calculate_flow_direction(dem: np.ndarray, valid_mask: np.ndarray, resolution_m: float) -> np.ndarray:
    rows, cols = dem.shape
    direction = np.full((rows, cols), -1, dtype=np.int8)

    for r in range(rows):
        for c in range(cols):
            if not valid_mask[r, c]:
                continue
            current = dem[r, c]
            best_dir = -1
            best_slope = 0.0
            for d in range(8):
                rr, cc = r + DR[d], c + DC[d]
                if not (0 <= rr < rows and 0 <= cc < cols):
                    continue
                if not valid_mask[rr, cc]:
                    continue
                drop = current - dem[rr, cc]
                if drop <= 0:
                    continue
                slope = drop / (resolution_m * DIST[d])
                if slope > best_slope:
                    best_slope = slope
                    best_dir = d
            direction[r, c] = best_dir
    return direction


def downstream_cell(r: int, c: int, direction: np.ndarray):
    d = int(direction[r, c])
    if d < 0:
        return None
    return r + int(DR[d]), c + int(DC[d])
