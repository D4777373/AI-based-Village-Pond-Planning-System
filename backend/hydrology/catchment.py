from __future__ import annotations

from collections import deque
import numpy as np

from backend.hydrology.flow_direction import downstream_cell


def delineate_catchment(
    direction: np.ndarray,
    valid_mask: np.ndarray,
    outlet_row: int,
    outlet_col: int,
) -> np.ndarray:
    rows, cols = direction.shape
    catchment = np.zeros((rows, cols), dtype=bool)
    catchment[outlet_row, outlet_col] = True
    q = deque([(outlet_row, outlet_col)])

    while q:
        r, c = q.popleft()
        r0, r1 = max(0, r - 1), min(rows, r + 2)
        c0, c1 = max(0, c - 1), min(cols, c + 2)

        for rr in range(r0, r1):
            for cc in range(c0, c1):
                if catchment[rr, cc] or not valid_mask[rr, cc]:
                    continue
                if downstream_cell(rr, cc, direction) == (r, c):
                    catchment[rr, cc] = True
                    q.append((rr, cc))

    return catchment
