from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pyproj import CRS, Transformer
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from scipy.interpolate import griddata
from shapely.geometry import Polygon, mapping
from shapely.ops import transform as shapely_transform

from backend.services.kml_service import ParsedContourMap


@dataclass
class TerrainGrid:
    dem: np.ndarray
    valid_mask: np.ndarray
    transform: object
    resolution_m: float
    xs: np.ndarray
    ys: np.ndarray
    to_wgs84: Transformer
    to_projected: Transformer
    boundary_projected: Polygon


def _utm_crs(lon: float, lat: float) -> CRS:
    zone = int((lon + 180) // 6) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def _sample_contour_points(parsed: ParsedContourMap, max_points: int = 60000):
    lons, lats, zs = [], [], []
    total = sum(len(c.coordinates) for c in parsed.contours)
    stride = max(1, total // max_points)

    counter = 0
    for contour in parsed.contours:
        for lon, lat in contour.coordinates:
            if counter % stride == 0:
                lons.append(lon)
                lats.append(lat)
                zs.append(contour.elevation_m)
            counter += 1
    return np.asarray(lons), np.asarray(lats), np.asarray(zs)


def build_dem(
    parsed: ParsedContourMap,
    resolution_m: float = 10.0,
    max_cells: int = 250_000,
) -> TerrainGrid:
    boundary_wgs84 = Polygon(parsed.boundary)
    if not boundary_wgs84.is_valid:
        boundary_wgs84 = boundary_wgs84.buffer(0)

    centroid = boundary_wgs84.centroid
    projected_crs = _utm_crs(centroid.x, centroid.y)
    to_projected = Transformer.from_crs("EPSG:4326", projected_crs, always_xy=True)
    to_wgs84 = Transformer.from_crs(projected_crs, "EPSG:4326", always_xy=True)

    boundary_projected = shapely_transform(to_projected.transform, boundary_wgs84)
    minx, miny, maxx, maxy = boundary_projected.bounds

    width = maxx - minx
    height = maxy - miny
    estimated_cells = max(1, int(width / resolution_m) * int(height / resolution_m))
    if estimated_cells > max_cells:
        scale = (estimated_cells / max_cells) ** 0.5
        resolution_m *= scale

    cols = max(1, int(np.ceil(width / resolution_m)))
    rows = max(1, int(np.ceil(height / resolution_m)))
    transform = from_origin(minx, maxy, resolution_m, resolution_m)

    xs = minx + (np.arange(cols) + 0.5) * resolution_m
    ys = maxy - (np.arange(rows) + 0.5) * resolution_m
    grid_x, grid_y = np.meshgrid(xs, ys)

    valid_mask = geometry_mask(
        [mapping(boundary_projected)],
        out_shape=(rows, cols),
        transform=transform,
        invert=True,
        all_touched=False,
    )

    lons, lats, zs = _sample_contour_points(parsed)
    px, py = to_projected.transform(lons, lats)
    points = np.column_stack([px, py])

    # Linear interpolation preserves terrain variation between contour lines.
    dem = griddata(points, zs, (grid_x, grid_y), method="linear")

    # Linear interpolation can be empty near polygon edges, so use nearest there.
    missing_inside = valid_mask & np.isnan(dem)
    if missing_inside.any():
        nearest = griddata(points, zs, (grid_x[missing_inside], grid_y[missing_inside]), method="nearest")
        dem[missing_inside] = nearest

    dem[~valid_mask] = np.nan

    if np.all(np.isnan(dem[valid_mask])):
        raise ValueError("DEM interpolation failed for this contour map.")

    return TerrainGrid(
        dem=dem,
        valid_mask=valid_mask,
        transform=transform,
        resolution_m=float(resolution_m),
        xs=xs,
        ys=ys,
        to_wgs84=to_wgs84,
        to_projected=to_projected,
        boundary_projected=boundary_projected,
    )
