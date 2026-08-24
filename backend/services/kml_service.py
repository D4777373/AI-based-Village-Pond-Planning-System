from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import MultiPoint, Polygon

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


@dataclass
class ContourLine:
    elevation_m: float
    coordinates: list[tuple[float, float]]  # (lon, lat)


@dataclass
class ParsedContourMap:
    contours: list[ContourLine]
    boundary: list[tuple[float, float]]


def _extract_kml_bytes(file_bytes: bytes, filename: str) -> bytes:
    ext = Path(filename).suffix.lower()
    if ext == ".kml":
        return file_bytes
    if ext == ".kmz":
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".kml")]
            if not names:
                raise ValueError("KMZ does not contain a KML file.")
            return archive.read(names[0])
    raise ValueError("Only .kml and .kmz files are supported.")


def _parse_coordinates(text: str | None) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    if not text:
        return points
    for token in text.split():
        values = token.split(",")
        if len(values) < 2:
            continue
        try:
            points.append((float(values[0]), float(values[1])))
        except ValueError:
            pass
    return points


def parse_contour_file(file_bytes: bytes, filename: str) -> ParsedContourMap:
    raw = _extract_kml_bytes(file_bytes, filename)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("Uploaded file is not valid KML/XML.") from exc

    contours: list[ContourLine] = []
    boundary: list[tuple[float, float]] | None = None
    all_contour_points: list[tuple[float, float]] = []

    for placemark in root.findall(".//kml:Placemark", KML_NS):
        name_node = placemark.find("kml:name", KML_NS)
        name = name_node.text.strip() if name_node is not None and name_node.text else ""

        line = placemark.find(".//kml:LineString", KML_NS)
        if line is not None:
            try:
                elevation = float(name)
            except ValueError:
                elevation = None
            if elevation is not None:
                coords_node = line.find("kml:coordinates", KML_NS)
                coords = _parse_coordinates(coords_node.text if coords_node is not None else None)
                if len(coords) >= 2:
                    contours.append(ContourLine(elevation, coords))
                    all_contour_points.extend(coords)

        polygon = placemark.find(".//kml:Polygon", KML_NS)
        if polygon is not None:
            coords_node = polygon.find(
                ".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", KML_NS
            )
            coords = _parse_coordinates(coords_node.text if coords_node is not None else None)
            if len(coords) >= 3:
                boundary = coords

    if not contours:
        raise ValueError("No numeric contour LineStrings were found in the file.")

    if boundary is None:
        hull = MultiPoint(all_contour_points).convex_hull
        if not isinstance(hull, Polygon):
            raise ValueError("Could not derive an analysis boundary from contour data.")
        boundary = list(hull.exterior.coords)

    return ParsedContourMap(contours=contours, boundary=boundary)
