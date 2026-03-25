"""
Multi-Objective OSM Router
============================
Main solver for map_routing_multiobjective.

Instead of a precomputed distance matrix, this solver downloads real
OpenStreetMap road data and dynamically modifies edge weights before
pathfinding — making roads that pass near desired POIs (restaurants, cafes,
parks …) appear cheaper to the Dijkstra algorithm. The result is a route that
naturally gravitates toward those areas while still respecting the overall
distance penalty.

Input dict → see algo_context.py input_schema for the canonical spec.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# Average travel speeds used for ETA estimation
_SPEED_KMH: dict[str, float] = {"drive": 35.0, "walk": 5.0, "bike": 15.0}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def solve_map_routing(data: dict[str, Any]) -> dict[str, Any]:
    """
    Solve a multi-objective map routing problem using OSM data.

    Parameters (flat dict)
    ----------------------
    start_address  : str   — human-readable start (used when lat/lng absent)
    end_address    : str   — human-readable destination
    start_lat/lng  : float — direct coordinates (override address geocoding)
    end_lat/lng    : float — direct coordinates
    poi_preferences: dict  — {poi_type: weight 0–1}  e.g. {"restaurant": 0.8}
    distance_weight: float — 0–1, how strongly to penalise longer edges
    avoid_highways : bool  — exclude motorways/trunk roads
    network_type   : str   — "drive" | "walk" | "bike"
    search_radius_m: int   — metres around edge midpoint to count POIs (def 100)
    time_limit_seconds: int — unused (kept for API consistency)

    Returns
    -------
    {
      "status": "OPTIMAL" | "INFEASIBLE" | "ERROR",
      "route": {
        "coordinates": [[lat,lng], ...],
        "total_distance_m": float,
        "total_distance_km": float,
        "estimated_time_min": float,
        "node_count": int
      },
      "pois_along_route": [{"name":str,"type":str,"lat":float,"lng":float}, ...],
      "alternative_route": {same shape as route} | null,   # pure-distance baseline
      "stats": {
        "pois_found": int,
        "optimized_route_pois": int,
        "baseline_route_pois": int,
        "distance_overhead_pct": float,
        "weights_used": dict
      }
    }
    """
    try:
        return _solve(data)
    except Exception as exc:
        logger.error("solve_map_routing failed: %s", exc, exc_info=True)
        return {"status": "ERROR", "error": str(exc)}


# ---------------------------------------------------------------------------
# Core implementation
# ---------------------------------------------------------------------------

def _solve(data: dict[str, Any]) -> dict[str, Any]:
    from app.solvers.map_routing.nominatim_client import geocode
    from app.solvers.map_routing.overpass_client import fetch_pois
    from app.solvers.map_routing.graph_builder import (
        build_weighted_graph,
        get_nearest_node,
        extract_route_coordinates,
    )
    import networkx as nx  # transitive dep of osmnx — always available

    # ------------------------------------------------------------------
    # 1. Resolve start / end coordinates
    # ------------------------------------------------------------------
    start_lat = _opt_float(data.get("start_lat"))
    start_lng = _opt_float(data.get("start_lng"))
    end_lat   = _opt_float(data.get("end_lat"))
    end_lng   = _opt_float(data.get("end_lng"))

    if start_lat is None or start_lng is None:
        addr = str(data.get("start_address", "")).strip()
        if not addr:
            return {"status": "INFEASIBLE",
                    "error": "Provide start_address or start_lat + start_lng."}
        start_lat, start_lng = geocode(addr)

    if end_lat is None or end_lng is None:
        addr = str(data.get("end_address", "")).strip()
        if not addr:
            return {"status": "INFEASIBLE",
                    "error": "Provide end_address or end_lat + end_lng."}
        end_lat, end_lng = geocode(addr)

    logger.info("Route: (%.5f,%.5f) → (%.5f,%.5f)", start_lat, start_lng, end_lat, end_lng)

    # ------------------------------------------------------------------
    # 2. Bounding box  (start↔end + buffer big enough for detour routes)
    # ------------------------------------------------------------------
    search_radius_m  = float(data.get("search_radius_m", 100))
    # expand bbox so routes with moderate detours still fit inside
    bbox_buffer_m = max(search_radius_m, 800.0)
    north, south, east, west = _bbox(start_lat, start_lng, end_lat, end_lng, bbox_buffer_m)

    # ------------------------------------------------------------------
    # 3. Parse parameters
    # ------------------------------------------------------------------
    raw_prefs: dict = data.get("poi_preferences") or {}
    poi_prefs: dict[str, float] = {
        k: max(0.0, min(1.0, float(v)))
        for k, v in raw_prefs.items()
        if _opt_float(v) is not None and float(v) > 0
    }
    distance_weight = max(0.0, min(1.0, float(data.get("distance_weight", 0.5))))
    avoid_highways  = bool(data.get("avoid_highways", False))
    network_type    = str(data.get("network_type", "drive"))

    # ------------------------------------------------------------------
    # 4. Fetch POIs (only when preferences are set)
    # ------------------------------------------------------------------
    all_pois: list[dict[str, Any]] = []
    if poi_prefs:
        all_pois = fetch_pois(north, south, east, west, list(poi_prefs.keys()))

    # ------------------------------------------------------------------
    # 5. Build custom-weighted graph
    # ------------------------------------------------------------------
    weights = {"distance": distance_weight, **poi_prefs}
    G, _nodes = build_weighted_graph(
        north=north, south=south, east=east, west=west,
        poi_list=all_pois,
        weights=weights,
        search_radius_m=search_radius_m,
        avoid_highways=avoid_highways,
        network_type=network_type,
    )

    # ------------------------------------------------------------------
    # 6. Snap start/end to nearest graph nodes
    # ------------------------------------------------------------------
    orig = get_nearest_node(G, start_lat, start_lng)
    dest = get_nearest_node(G, end_lat,   end_lng)
    if orig == dest:
        return {"status": "INFEASIBLE",
                "error": "Start and end resolve to the same network node. "
                         "Try locations further apart."}

    # ------------------------------------------------------------------
    # 7. Optimised route  (custom_weight penalises distance, rewards POIs)
    # ------------------------------------------------------------------
    try:
        opt_nodes = nx.shortest_path(G, orig, dest, weight="custom_weight")
    except nx.NetworkXNoPath:
        return {"status": "INFEASIBLE",
                "error": "No connected route found between the given points."}

    opt_coords   = extract_route_coordinates(G, opt_nodes)
    opt_dist_m   = _path_length(G, opt_nodes)

    # ------------------------------------------------------------------
    # 8. Baseline route  (pure distance — for side-by-side comparison)
    # ------------------------------------------------------------------
    base_nodes: list[int] | None = None
    base_coords: list[tuple[float, float]] = []
    base_dist_m = 0.0
    try:
        base_nodes  = nx.shortest_path(G, orig, dest, weight="length")
        base_coords = extract_route_coordinates(G, base_nodes)
        base_dist_m = _path_length(G, base_nodes)
    except nx.NetworkXNoPath:
        pass

    # ------------------------------------------------------------------
    # 9. POIs along each route
    # ------------------------------------------------------------------
    opt_route_pois  = _filter_pois_near_route(opt_coords,  all_pois, search_radius_m)
    base_route_pois = _filter_pois_near_route(base_coords, all_pois, search_radius_m)

    # ------------------------------------------------------------------
    # 10. Build output
    # ------------------------------------------------------------------
    speed = _SPEED_KMH.get(network_type, 35.0)
    opt_eta  = (opt_dist_m  / 1000.0) / speed * 60.0
    base_eta = (base_dist_m / 1000.0) / speed * 60.0

    overhead_pct = 0.0
    if base_dist_m > 0:
        overhead_pct = round((opt_dist_m - base_dist_m) / base_dist_m * 100.0, 1)

    return {
        "status": "OPTIMAL",
        "route": {
            "coordinates":        [[lat, lng] for lat, lng in opt_coords],
            "total_distance_m":   round(opt_dist_m, 1),
            "total_distance_km":  round(opt_dist_m / 1000.0, 3),
            "estimated_time_min": round(opt_eta, 1),
            "node_count":         len(opt_nodes),
        },
        "pois_along_route": opt_route_pois,
        "alternative_route": {
            "coordinates":        [[lat, lng] for lat, lng in base_coords],
            "total_distance_m":   round(base_dist_m, 1),
            "total_distance_km":  round(base_dist_m / 1000.0, 3),
            "estimated_time_min": round(base_eta, 1),
            "poi_count":          len(base_route_pois),
        } if base_nodes else None,
        "stats": {
            "pois_found":            len(all_pois),
            "optimized_route_pois":  len(opt_route_pois),
            "baseline_route_pois":   len(base_route_pois),
            "distance_overhead_pct": overhead_pct,
            "weights_used":          weights,
        },
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _opt_float(val: Any) -> float | None:
    try:
        f = float(val)  # type: ignore[arg-type]
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _bbox(
    lat1: float, lng1: float,
    lat2: float, lng2: float,
    buffer_m: float,
) -> tuple[float, float, float, float]:
    """Return (north, south, east, west) bounding box enclosing both points + buffer."""
    lat_deg = buffer_m / 111_320.0
    avg_lat = (lat1 + lat2) / 2.0
    lng_deg = buffer_m / max(1.0, 111_320.0 * math.cos(math.radians(avg_lat)))
    return (
        max(lat1, lat2) + lat_deg,   # north
        min(lat1, lat2) - lat_deg,   # south
        max(lng1, lng2) + lng_deg,   # east
        min(lng1, lng2) - lng_deg,   # west
    )


def _path_length(G: Any, nodes: list[int]) -> float:
    """Sum edge 'length' attributes (metres) along a node sequence."""
    total = 0.0
    for u, v in zip(nodes[:-1], nodes[1:]):
        edata = G.get_edge_data(u, v)
        if edata:
            total += edata[min(edata)].get("length", 0.0)
    return total


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((phi2 - phi1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians((lng2 - lng1) / 2)) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(a))


def _filter_pois_near_route(
    coords: list[tuple[float, float]],
    pois: list[dict[str, Any]],
    radius_m: float,
) -> list[dict[str, Any]]:
    """Return POIs within radius_m of any route coordinate (deduped)."""
    if not coords or not pois:
        return []
    result: list[dict[str, Any]] = []
    seen: set[tuple[float, float]] = set()
    for poi in pois:
        key = (poi["lat"], poi["lng"])
        if key in seen:
            continue
        for rlat, rlng in coords:
            if _haversine(rlat, rlng, poi["lat"], poi["lng"]) <= radius_m:
                result.append(poi)
                seen.add(key)
                break
    return result
