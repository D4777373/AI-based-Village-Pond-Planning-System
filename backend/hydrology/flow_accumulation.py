from __future__ import annotations

from collections import deque
import numpy as np

from backend.hydrology.flow_direction import downstream_cell


def calculate_flow_accumulation(direction: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    rows, cols = direction.shape
    indegree = np.zeros((rows, cols), dtype=np.int32)
    accumulation = np.zeros((rows, cols), dtype=np.float64)
    accumulation[valid_mask] = 1.0

    for r in range(rows):
        for c in range(cols):
            if not valid_mask[r, c]:
                continue
            dst = downstream_cell(r, c, direction)
            if dst is None:
                continue
            rr, cc = dst
            if 0 <= rr < rows and 0 <= cc < cols and valid_mask[rr, cc]:
                indegree[rr, cc] += 1

    q = deque((r, c) for r in range(rows) for c in range(cols)
              if valid_mask[r, c] and indegree[r, c] == 0)

    processed = 0
    while q:
        r, c = q.popleft()
        processed += 1
        dst = downstream_cell(r, c, direction)
        if dst is None:
            continue
        rr, cc = dst
        if not (0 <= rr < rows and 0 <= cc < cols) or not valid_mask[rr, cc]:
            continue
        accumulation[rr, cc] += accumulation[r, c]
        indegree[rr, cc] -= 1
        if indegree[rr, cc] == 0:
            q.append((rr, cc))

    # In strict downhill D8 there should be no cycles. Keep invalid cells NaN for clarity.
    accumulation[~valid_mask] = np.nan
    return accumulation
