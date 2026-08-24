from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
import xml.etree.ElementTree as ET

import numpy as np
import rasterio
from pyproj import Transformer
from skimage import measure


KML_NS = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", KML_NS)


@dataclass
class GeneratedContours:
    kml_path: Path
    geojson_path: Path
    geojson: dict
    contour_interval_m: float
    minimum_elevation_m: float
    maximum_elevation_m: float
    contour_feature_count: int


def _wgs84_xy(transformer: Transformer, x: float, y: float):
    lon, lat = transformer.transform(x, y)
    return float(lon), float(lat)


def _raster_boundary_wgs84(dataset, transformer: Transformer):
    b = dataset.bounds
    corners_src = [
        (b.left, b.bottom),
        (b.right, b.bottom),
        (b.right, b.top),
        (b.left, b.top),
        (b.left, b.bottom),
    ]
    return [_wgs84_xy(transformer, x, y) for x, y in corners_src]


def generate_contours_from_dem(
    dem_path: Path,
    kml_path: Path,
    geojson_path: Path,
    contour_interval_m: float = 5.0,
) -> GeneratedContours:
    if contour_interval_m <= 0:
        raise ValueError("Contour interval must be greater than zero.")

    with rasterio.open(dem_path) as dataset:
        elevation = dataset.read(1, masked=True).astype("float64")
        values = elevation.filled(np.nan)
        valid = np.isfinite(values)

        if not valid.any():
            raise ValueError("DEM contains no valid elevation values.")

        minimum = float(np.nanmin(values))
        maximum = float(np.nanmax(values))

        if math.isclose(minimum, maximum):
            raise ValueError("DEM is essentially flat; contours cannot be generated.")

        source_crs = dataset.crs or "EPSG:4326"
        to_wgs84 = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)

        start_level = math.ceil(minimum / contour_interval_m) * contour_interval_m
        levels = np.arange(
            start_level,
            maximum + contour_interval_m * 0.25,
            contour_interval_m,
        )

        kml_root = ET.Element(f"{{{KML_NS}}}kml")
        document = ET.SubElement(kml_root, f"{{{KML_NS}}}Document")
        folder = ET.SubElement(document, f"{{{KML_NS}}}Folder")
        ET.SubElement(folder, f"{{{KML_NS}}}name").text = "Generated contours"

        features = []
        contour_count = 0

        for level in levels:
            paths = measure.find_contours(values, level=float(level), mask=valid)

            for path in paths:
                if len(path) < 3:
                    continue

                coords_wgs84 = []
                for row, col in path:
                    # Convert fractional raster row/column to raster CRS.
                    x, y = dataset.transform * (float(col) + 0.5, float(row) + 0.5)
                    lon, lat = _wgs84_xy(to_wgs84, x, y)
                    coords_wgs84.append((lon, lat))

                if len(coords_wgs84) < 2:
                    continue

                placemark = ET.SubElement(folder, f"{{{KML_NS}}}Placemark")
                ET.SubElement(placemark, f"{{{KML_NS}}}name").text = f"{float(level):.2f}"
                extended = ET.SubElement(placemark, f"{{{KML_NS}}}ExtendedData")
                data = ET.SubElement(extended, f"{{{KML_NS}}}Data", name="elevation_m")
                ET.SubElement(data, f"{{{KML_NS}}}value").text = f"{float(level):.2f}"

                line = ET.SubElement(placemark, f"{{{KML_NS}}}LineString")
                ET.SubElement(line, f"{{{KML_NS}}}tessellate").text = "1"
                ET.SubElement(line, f"{{{KML_NS}}}coordinates").text = " ".join(
                    f"{lon:.8f},{lat:.8f},0" for lon, lat in coords_wgs84
                )

                features.append(
                    {
                        "type": "Feature",
                        "properties": {"elevation_m": float(level)},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[lon, lat] for lon, lat in coords_wgs84],
                        },
                    }
                )
                contour_count += 1

        # Boundary polygon named "land" so the existing KML parser can reuse it.
        boundary = _raster_boundary_wgs84(dataset, to_wgs84)
        boundary_pm = ET.SubElement(folder, f"{{{KML_NS}}}Placemark")
        ET.SubElement(boundary_pm, f"{{{KML_NS}}}name").text = "land"
        polygon = ET.SubElement(boundary_pm, f"{{{KML_NS}}}Polygon")
        outer = ET.SubElement(polygon, f"{{{KML_NS}}}outerBoundaryIs")
        ring = ET.SubElement(outer, f"{{{KML_NS}}}LinearRing")
        ET.SubElement(ring, f"{{{KML_NS}}}coordinates").text = " ".join(
            f"{lon:.8f},{lat:.8f},0" for lon, lat in boundary
        )

        if contour_count == 0:
            raise ValueError(
                "No contours were produced. Try a smaller contour interval or a larger analysis area."
            )

        kml_path.parent.mkdir(parents=True, exist_ok=True)
        ET.ElementTree(kml_root).write(
            kml_path,
            encoding="utf-8",
            xml_declaration=True,
        )

        geojson = {
            "type": "FeatureCollection",
            "features": features,
        }
        geojson_path.write_text(json.dumps(geojson), encoding="utf-8")

    return GeneratedContours(
        kml_path=kml_path,
        geojson_path=geojson_path,
        geojson=geojson,
        contour_interval_m=float(contour_interval_m),
        minimum_elevation_m=minimum,
        maximum_elevation_m=maximum,
        contour_feature_count=contour_count,
    )
