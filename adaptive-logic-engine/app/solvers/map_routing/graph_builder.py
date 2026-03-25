"""
OSM Graph Builder & Weight Modifier
=====================================
Downloads, caches, and post-processes OpenStreetMap road graphs.

Key responsibilities:
1. Download road network for a bounding box via OSMnx (cached to disk).
2. Associate POIs with nearby road edges (spatial join).
3. Build a custom-weighted copy of the graph based on the user's
   multi-objective preferences:

       cost(edge) = distance_weight × length_m
                  − Σ (poi_weight_i × edge_poi_count_i)

   This makes roads that pass near many desired POIs "cheaper" for
   NetworkX pathfinding, naturally producing routes through those areas.

Usage
-----
    from app.solvers.map_routing.graph_builder import build_weighted_graph

    G, node_lookup = build_weighted_graph(
        north=40.78, south=40.75, east=-73.97, west=-74.00,
        poi_list=[{"lat": 40.76, "lng": -73.98, "type": "restaurant"}, ...],
        weights={"distance": 0.5, "restaurant": 0.8, "cafe": 0.3},
        avoid_highways=False,
        network_type="drive",
    )
"""

from __future__ import annotations

import copy
import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# OSMnx is a heavy dependency — import lazily so the module can be imported
# even before osmnx is installed (gives a clear ImportError only on use).
try:
    import osmnx as ox
    import networkx as nx
    _OSMNX_AVAILABLE = True
except ImportError:
    _OSMNX_AVAILABLE = False


_EARTH_RADIUS_M = 6_371_000.0


def _check_deps() -> None:
    if not _OSMNX_AVAILABLE:
        raise RuntimeError(
            "osmnx is not installed. Run: pip install 'osmnx>=1.9.0'"
        )


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance in metres between two lat/lng points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _edge_midpoint(G: Any, u: int, v: int, k: int) -> tuple[float, float]:
    """Return the geographic midpoint of an OSMnx edge (u, v, k)."""
    u_data = G.nodes[u]
    v_data = G.nodes[v]
    return (
        (u_data["y"] + v_data["y"]) / 2.0,
        (u_data["x"] + v_data["x"]) / 2.0,
    )


def _poi_counts_per_edge(
    G: Any,
    poi_list: list[dict[str, Any]],
    search_radius_m: float,
) -> dict[tuple[int, int, int], dict[str, int]]:
    """
    For each graph edge, count how many POIs of each type fall within
    `search_radius_m` metres of the edge midpoint.

    Returns
    -------
    dict mapping (u, v, k) → {"restaurant": 3, "cafe": 1, ...}
    """
    counts: dict[tuple[int, int, int], dict[str, int]] = {}
    if not poi_list:
        return counts

    edges = list(G.edges(keys=True))
    for u, v, k in edges:
        mid_lat, mid_lng = _edge_midpoint(G, u, v, k)
        type_counts: dict[str, int] = {}
        for poi in poi_list:
            dist = _haversine_m(mid_lat, mid_lng, poi["lat"], poi["lng"])
            if dist <= search_radius_m:
                poi_type = poi.get("type", "unknown")
                type_counts[poi_type] = type_counts.get(poi_type, 0) + 1
        if type_counts:
            counts[(u, v, k)] = type_counts

    return counts


def download_graph(
    north: float,
    south: float,
    east: float,
    west: float,
    network_type: str = "drive",
    avoid_highways: bool = False,
) -> Any:
    """
    Download (or load from cache) the OSMnx road graph for the bounding box.

    Parameters
    ----------
    north/south/east/west : float
        Bounding box in decimal degrees.
    network_type : str
        "drive" | "walk" | "bike" — filters OSM highway types.
    avoid_highways : bool
        When True, adds a custom filter to exclude motorways and trunk roads.

    Returns
    -------
    NetworkX MultiDiGraph (OSMnx format).
    """
    _check_deps()

    # OSMnx caches graphs automatically via its local cache dir.
    ox.settings.use_cache = True
    ox.settings.log_console = False

    custom_filter = None
    if avoid_highways and network_type == "drive":
        custom_filter = (
            '["highway"!~"motorway|motorway_link|trunk|trunk_link"]'
            '["access"!~"private"]'
        )

    logger.info(
        "Downloading %s graph for bbox N=%s S=%s E=%s W=%s …",
        network_type, north, south, east, west,
    )

    G = ox.graph_from_bbox(
        bbox=(west, south, east, north),
        network_type=network_type,
        custom_filter=custom_filter,
        simplify=True,
        retain_all=False,
    )

    # Add 'length' attribute (metres) to every edge if not already present
    G = ox.distance.add_edge_lengths(G)
    logger.info("Graph downloaded: %d nodes, %d edges.", G.number_of_nodes(), G.number_of_edges())
    return G


def build_weighted_graph(
    north: float,
    south: float,
    east: float,
    west: float,
    poi_list: list[dict[str, Any]],
    weights: dict[str, float],
    search_radius_m: float = 100.0,
    avoid_highways: bool = False,
    network_type: str = "drive",
) -> tuple[Any, dict[int, dict[str, Any]]]:
    """
    Download graph + compute custom multi-objective edge weights.

    The custom weight for each edge is:

        w = max(1, distance_weight × length_m
                 − poi_bonus × Σ (poi_weight_i × count_i))

    where poi_bonus = 1000 (a normalisation scalar so a single POI near a
    short edge can meaningfully reduce its cost relative to other edges).

    Parameters
    ----------
    weights : dict
        {"distance": 0.5, "restaurant": 0.8, "cafe": 0.3, ...}
        Keys other than "distance" are treated as POI type weights.

    Returns
    -------
    (G_weighted, node_lookup)
        G_weighted : copy of G with a "custom_weight" attribute on every edge.
        node_lookup : {node_id: {"lat": float, "lng": float}} for frontend rendering.
    """
    G = download_graph(north, south, east, west, network_type, avoid_highways)

    distance_weight = float(weights.get("distance", 0.5))
    poi_weights = {k: float(v) for k, v in weights.items() if k != "distance" and v > 0}

    # Compute per-edge POI counts only when POI weights are requested
    edge_poi_counts: dict[tuple[int, int, int], dict[str, int]] = {}
    if poi_weights and poi_list:
        logger.info("Associating %d POIs with graph edges (radius=%.0fm) …", len(poi_list), search_radius_m)
        edge_poi_counts = _poi_counts_per_edge(G, poi_list, search_radius_m)

    # Build a modified copy with custom_weight attribute
    G_weighted = G.copy()
    poi_bonus_scale = 1000.0   # tuned so 1 POI ≈ reduces cost by ~1000m equivalent

    for u, v, k, data in G_weighted.edges(keys=True, data=True):
        length_m = data.get("length", 1.0)
        base_cost = distance_weight * length_m

        # POI bonus: sum of (poi_weight × count)
        bonus = 0.0
        if poi_weights:
            edge_counts = edge_poi_counts.get((u, v, k), {})
            for poi_type, poi_w in poi_weights.items():
                count = edge_counts.get(poi_type, 0)
                bonus += poi_w * count * poi_bonus_scale

        G_weighted[u][v][k]["custom_weight"] = max(1.0, base_cost - bonus)

    # Build node lookup for frontend
    node_lookup = {
        node: {"lat": data["y"], "lng": data["x"]}
        for node, data in G_weighted.nodes(data=True)
    }

    return G_weighted, node_lookup


def get_nearest_node(G: Any, lat: float, lng: float) -> int:
    """Return the graph node ID nearest to (lat, lng)."""
    _check_deps()
    return ox.nearest_nodes(G, X=lng, Y=lat)


def extract_route_coordinates(
    G: Any,
    node_sequence: list[int],
) -> list[tuple[float, float]]:
    """
    Convert a list of OSMnx node IDs to [[lat, lng], ...] coordinates.
    Includes intermediate geometry waypoints if available.
    """
    coords: list[tuple[float, float]] = []
    for i, node in enumerate(node_sequence):
        node_data = G.nodes[node]
        lat = node_data["y"]
        lng = node_data["x"]

        # If there's geometry on the edge, include intermediate points
        if i < len(node_sequence) - 1:
            next_node = node_sequence[i + 1]
            edge_data = G.get_edge_data(node, next_node)
            if edge_data:
                best_key = min(edge_data.keys())
                geom = edge_data[best_key].get("geometry")
                if geom is not None:
                    # shapely LineString
                    coords.append((lat, lng))
                    for x, y in list(geom.coords)[1:-1]:
                        coords.append((y, x))  # Shapely uses (lng, lat) order
                    continue

        coords.append((lat, lng))

    # Append final node
    if node_sequence:
        last = G.nodes[node_sequence[-1]]
        if not coords or coords[-1] != (last["y"], last["x"]):
            coords.append((last["y"], last["x"]))

    return coords
