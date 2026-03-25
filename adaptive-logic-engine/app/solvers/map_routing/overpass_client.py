"""
Overpass API POI Fetcher
=========================
Fetches Points of Interest (POIs) from OpenStreetMap via the Overpass API.

This module maps friendly POI type names to OSM tags and queries the
Overpass API for all matching features within a bounding box.

Usage
-----
    from app.solvers.map_routing.overpass_client import fetch_pois

    pois = fetch_pois(
        north=40.78, south=40.75, east=-73.97, west=-74.00,
        poi_types=["restaurant", "cafe"]
    )
    # Returns list of {"name": str, "type": str, "lat": float, "lng": float}
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_HEADERS = {"User-Agent": "OptimAI-MapRouting/1.0 (optimization-engine)"}

# Map friendly names → OSM amenity/leisure/shop tags
_POI_TAG_MAP: dict[str, dict[str, str]] = {
    "restaurant":   {"amenity": "restaurant"},
    "cafe":         {"amenity": "cafe"},
    "fast_food":    {"amenity": "fast_food"},
    "bar":          {"amenity": "bar"},
    "pub":          {"amenity": "pub"},
    "park":         {"leisure": "park"},
    "garden":       {"leisure": "garden"},
    "museum":       {"tourism": "museum"},
    "gallery":      {"tourism": "gallery"},
    "hotel":        {"tourism": "hotel"},
    "hospital":     {"amenity": "hospital"},
    "pharmacy":     {"amenity": "pharmacy"},
    "supermarket":  {"shop": "supermarket"},
    "school":       {"amenity": "school"},
    "bank":         {"amenity": "bank"},
    "atm":          {"amenity": "atm"},
    "parking":      {"amenity": "parking"},
    "fuel":         {"amenity": "fuel"},
    "church":       {"amenity": "place_of_worship"},
    "cinema":       {"amenity": "cinema"},
    "theatre":      {"amenity": "theatre"},
}

_LAST_CALL: list[float] = [0.0]   # list to allow mutation in nested functions


def _build_overpass_query(
    north: float, south: float, east: float, west: float,
    poi_types: list[str],
) -> str:
    """Build an Overpass QL query for the given bbox and POI types."""
    bbox = f"{south},{west},{north},{east}"
    filters = []
    for poi_type in poi_types:
        tags = _POI_TAG_MAP.get(poi_type)
        if not tags:
            continue
        for key, val in tags.items():
            # nodes
            filters.append(f'node["{key}"="{val}"]({bbox});')
            # way centroids
            filters.append(f'way["{key}"="{val}"]({bbox});')

    if not filters:
        return ""

    union_body = "\n".join(f"  {f}" for f in filters)
    return f"""
[out:json][timeout:30];
(
{union_body}
);
out center tags;
""".strip()


def fetch_pois(
    north: float,
    south: float,
    east: float,
    west: float,
    poi_types: list[str],
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """
    Fetch POIs of the requested types within the bounding box.

    Returns
    -------
    List of dicts: {"name": str, "type": str, "lat": float, "lng": float}
    """
    # Rate limit: 1 req / 2 seconds for Overpass
    elapsed = time.monotonic() - _LAST_CALL[0]
    if elapsed < 2.0:
        time.sleep(2.0 - elapsed)

    # Filter to known types only
    known_types = [t for t in poi_types if t in _POI_TAG_MAP]
    if not known_types:
        logger.warning("No recognised POI types in %s — returning empty list.", poi_types)
        return []

    query = _build_overpass_query(north, south, east, west, known_types)
    if not query:
        return []

    logger.info("Fetching POIs for types: %s in bbox (%s,%s,%s,%s)", known_types, north, south, east, west)

    try:
        resp = requests.post(
            _OVERPASS_URL,
            data={"data": query},
            headers=_HEADERS,
            timeout=timeout,
        )
        _LAST_CALL[0] = time.monotonic()
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Overpass API error: %s — returning empty POI list.", exc)
        return []

    elements = resp.json().get("elements", [])
    pois: list[dict[str, Any]] = []

    for el in elements:
        tags = el.get("tags", {})

        # Determine type from tags
        poi_type = _infer_type(tags)
        if poi_type is None:
            continue

        # Resolve coordinates (node → lat/lon; way → center)
        if el["type"] == "node":
            lat, lng = el.get("lat"), el.get("lon")
        else:
            center = el.get("center", {})
            lat, lng = center.get("lat"), center.get("lon")

        if lat is None or lng is None:
            continue

        name = tags.get("name") or tags.get("name:en") or f"Unnamed {poi_type.capitalize()}"
        pois.append({"name": name, "type": poi_type, "lat": float(lat), "lng": float(lng)})

    logger.info("Fetched %d POIs.", len(pois))
    return pois


def _infer_type(tags: dict[str, str]) -> str | None:
    """Reverse-map OSM tags → friendly POI type name."""
    for friendly, osm_tags in _POI_TAG_MAP.items():
        for key, val in osm_tags.items():
            if tags.get(key) == val:
                return friendly
    return None


def known_poi_types() -> list[str]:
    """Return list of all supported POI type names."""
    return list(_POI_TAG_MAP.keys())
