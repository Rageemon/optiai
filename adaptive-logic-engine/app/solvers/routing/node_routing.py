"""
Node-routing solvers using OR-Tools Routing API.

Implemented algorithms
----------------------
- solve_tsp   : Traveling Salesperson Problem (single vehicle)
- solve_vrp   : Multi-vehicle VRP
- solve_cvrp  : Capacitated VRP
- solve_vrptw : VRP with Time Windows
- solve_pdp   : Pickup and Delivery Problem
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ortools.constraint_solver import pywrapcp, routing_enums_pb2


def _validate_square_matrix(matrix: List[List[int]], name: str) -> None:
    if not matrix or not isinstance(matrix, list):
        raise ValueError(f"{name} must be a non-empty 2D list")
    n = len(matrix)
    for row in matrix:
        if not isinstance(row, list) or len(row) != n:
            raise ValueError(f"{name} must be square (NxN)")


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _search_params(data: Dict[str, Any]) -> pywrapcp.DefaultRoutingSearchParameters:
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = _safe_int(data.get("time_limit_seconds", 10), 10)
    return params


def _extract_routes(
    manager: pywrapcp.RoutingIndexManager,
    routing: pywrapcp.RoutingModel,
    solution: pywrapcp.Assignment,
    num_vehicles: int,
    distance_dim_name: str | None = None,
    capacity_dim_name: str | None = None,
    time_dim_name: str | None = None,
) -> Tuple[List[Dict[str, Any]], int]:
    routes: List[Dict[str, Any]] = []
    total_distance = 0

    dist_dim = routing.GetDimensionOrDie(distance_dim_name) if distance_dim_name else None
    cap_dim = routing.GetDimensionOrDie(capacity_dim_name) if capacity_dim_name else None
    time_dim = routing.GetDimensionOrDie(time_dim_name) if time_dim_name else None

    for vehicle_id in range(num_vehicles):
        index = routing.Start(vehicle_id)
        stops: List[Dict[str, Any]] = []
        route_distance = 0

        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            stop: Dict[str, Any] = {"node": node}
            if cap_dim is not None:
                stop["load"] = solution.Value(cap_dim.CumulVar(index))
            if time_dim is not None:
                stop["time"] = solution.Value(time_dim.CumulVar(index))
            stops.append(stop)

            next_index = solution.Value(routing.NextVar(index))
            route_distance += routing.GetArcCostForVehicle(index, next_index, vehicle_id)
            index = next_index

        end_node = manager.IndexToNode(index)
        end_stop: Dict[str, Any] = {"node": end_node}
        if cap_dim is not None:
            end_stop["load"] = solution.Value(cap_dim.CumulVar(index))
        if time_dim is not None:
            end_stop["time"] = solution.Value(time_dim.CumulVar(index))
        stops.append(end_stop)

        if dist_dim is not None:
            route_distance = solution.Value(dist_dim.CumulVar(index))

        total_distance += route_distance
        routes.append(
            {
                "vehicle_id": vehicle_id,
                "stops": stops,
                "distance": route_distance,
            }
        )

    return routes, total_distance


def solve_tsp(data: Dict[str, Any]) -> Dict[str, Any]:
    distance_matrix = data.get("distance_matrix", [])
    _validate_square_matrix(distance_matrix, "distance_matrix")

    n = len(distance_matrix)
    depot = _safe_int(data.get("depot", 0), 0)
    if depot < 0 or depot >= n:
        raise ValueError("depot index out of range")

    manager = pywrapcp.RoutingIndexManager(n, 1, depot)
    routing = pywrapcp.RoutingModel(manager)

    def dist_cb(from_index: int, to_index: int) -> int:
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return int(distance_matrix[f][t])

    transit = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    params = _search_params(data)
    solution = routing.SolveWithParameters(params)
    if solution is None:
        return {"status": "INFEASIBLE", "error": "No feasible TSP route found."}

    routes, total_distance = _extract_routes(manager, routing, solution, 1)
    return {
        "status": "OPTIMAL_OR_FEASIBLE",
        "problem": "tsp",
        "routes": routes,
        "total_distance": total_distance,
    }


def solve_vrp(data: Dict[str, Any]) -> Dict[str, Any]:
    distance_matrix = data.get("distance_matrix", [])
    _validate_square_matrix(distance_matrix, "distance_matrix")

    n = len(distance_matrix)
    num_vehicles = _safe_int(data.get("num_vehicles", 2), 2)
    depot = _safe_int(data.get("depot", 0), 0)
    if num_vehicles <= 0:
        raise ValueError("num_vehicles must be >= 1")
    if depot < 0 or depot >= n:
        raise ValueError("depot index out of range")

    manager = pywrapcp.RoutingIndexManager(n, num_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    def dist_cb(from_index: int, to_index: int) -> int:
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return int(distance_matrix[f][t])

    transit = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    max_route_distance = _safe_int(data.get("max_route_distance", 0), 0)
    if max_route_distance > 0:
        routing.AddDimension(transit, 0, max_route_distance, True, "Distance")

    params = _search_params(data)
    solution = routing.SolveWithParameters(params)
    if solution is None:
        return {"status": "INFEASIBLE", "error": "No feasible VRP routes found."}

    distance_dim_name = "Distance" if max_route_distance > 0 else None
    routes, total_distance = _extract_routes(manager, routing, solution, num_vehicles, distance_dim_name=distance_dim_name)
    return {
        "status": "OPTIMAL_OR_FEASIBLE",
        "problem": "vrp",
        "routes": routes,
        "total_distance": total_distance,
    }


def solve_cvrp(data: Dict[str, Any]) -> Dict[str, Any]:
    distance_matrix = data.get("distance_matrix", [])
    _validate_square_matrix(distance_matrix, "distance_matrix")

    n = len(distance_matrix)
    num_vehicles = _safe_int(data.get("num_vehicles", 2), 2)
    depot = _safe_int(data.get("depot", 0), 0)
    demands = [int(x) for x in data.get("demands", [0] * n)]
    capacities = [int(x) for x in data.get("vehicle_capacities", [15] * num_vehicles)]

    if len(demands) != n:
        raise ValueError("demands length must equal number of nodes")
    if len(capacities) != num_vehicles:
        raise ValueError("vehicle_capacities length must equal num_vehicles")

    manager = pywrapcp.RoutingIndexManager(n, num_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    def dist_cb(from_index: int, to_index: int) -> int:
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return int(distance_matrix[f][t])

    transit = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    def demand_cb(from_index: int) -> int:
        f = manager.IndexToNode(from_index)
        return demands[f]

    demand_idx = routing.RegisterUnaryTransitCallback(demand_cb)
    routing.AddDimensionWithVehicleCapacity(
        demand_idx,
        0,
        capacities,
        True,
        "Capacity",
    )

    params = _search_params(data)
    solution = routing.SolveWithParameters(params)
    if solution is None:
        return {"status": "INFEASIBLE", "error": "No feasible CVRP routes found."}

    routes, total_distance = _extract_routes(
        manager,
        routing,
        solution,
        num_vehicles,
        capacity_dim_name="Capacity",
    )
    return {
        "status": "OPTIMAL_OR_FEASIBLE",
        "problem": "cvrp",
        "routes": routes,
        "total_distance": total_distance,
    }


def solve_vrptw(data: Dict[str, Any]) -> Dict[str, Any]:
    time_matrix = data.get("time_matrix") or data.get("distance_matrix", [])
    _validate_square_matrix(time_matrix, "time_matrix")

    n = len(time_matrix)
    num_vehicles = _safe_int(data.get("num_vehicles", 2), 2)
    depot = _safe_int(data.get("depot", 0), 0)
    time_windows = data.get("time_windows", [[0, 10_000] for _ in range(n)])
    service_times = [int(x) for x in data.get("service_times", [0] * n)]
    horizon = _safe_int(data.get("max_time_per_vehicle", 10_000), 10_000)
    wait = _safe_int(data.get("max_waiting_time", 1_000), 1_000)

    if len(time_windows) != n:
        raise ValueError("time_windows length must equal number of nodes")
    if len(service_times) != n:
        raise ValueError("service_times length must equal number of nodes")

    manager = pywrapcp.RoutingIndexManager(n, num_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    def time_cb(from_index: int, to_index: int) -> int:
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return int(time_matrix[f][t]) + int(service_times[f])

    transit = routing.RegisterTransitCallback(time_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    routing.AddDimension(
        transit,
        wait,
        horizon,
        False,
        "Time",
    )
    time_dim = routing.GetDimensionOrDie("Time")

    for node in range(n):
        start, end = int(time_windows[node][0]), int(time_windows[node][1])
        index = manager.NodeToIndex(node)
        time_dim.CumulVar(index).SetRange(start, end)

    for vehicle_id in range(num_vehicles):
        start_index = routing.Start(vehicle_id)
        end_index = routing.End(vehicle_id)
        depot_start, depot_end = int(time_windows[depot][0]), int(time_windows[depot][1])
        time_dim.CumulVar(start_index).SetRange(depot_start, depot_end)
        time_dim.CumulVar(end_index).SetRange(depot_start, depot_end)

    params = _search_params(data)
    solution = routing.SolveWithParameters(params)
    if solution is None:
        return {"status": "INFEASIBLE", "error": "No feasible VRPTW routes found."}

    routes, total_distance = _extract_routes(
        manager,
        routing,
        solution,
        num_vehicles,
        time_dim_name="Time",
    )
    return {
        "status": "OPTIMAL_OR_FEASIBLE",
        "problem": "vrptw",
        "routes": routes,
        "total_time": total_distance,
    }


def solve_pdp(data: Dict[str, Any]) -> Dict[str, Any]:
    distance_matrix = data.get("distance_matrix", [])
    _validate_square_matrix(distance_matrix, "distance_matrix")

    n = len(distance_matrix)
    num_vehicles = _safe_int(data.get("num_vehicles", 2), 2)
    depot = _safe_int(data.get("depot", 0), 0)
    capacities = [int(x) for x in data.get("vehicle_capacities", [20] * num_vehicles)]
    demands = [int(x) for x in data.get("demands", [0] * n)]
    pairs = data.get("pickup_delivery_pairs", [])

    if len(demands) != n:
        raise ValueError("demands length must equal number of nodes")
    if len(capacities) != num_vehicles:
        raise ValueError("vehicle_capacities length must equal num_vehicles")

    manager = pywrapcp.RoutingIndexManager(n, num_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    def dist_cb(from_index: int, to_index: int) -> int:
        f = manager.IndexToNode(from_index)
        t = manager.IndexToNode(to_index)
        return int(distance_matrix[f][t])

    transit = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    # Capacity
    def demand_cb(from_index: int) -> int:
        f = manager.IndexToNode(from_index)
        return demands[f]

    demand_idx = routing.RegisterUnaryTransitCallback(demand_cb)
    routing.AddDimensionWithVehicleCapacity(demand_idx, 0, capacities, True, "Capacity")

    # Distance dimension for pickup-before-delivery ordering.
    routing.AddDimension(transit, 0, 10_000_000, True, "Distance")
    dist_dim = routing.GetDimensionOrDie("Distance")

    for pair in pairs:
        pickup = int(pair[0])
        delivery = int(pair[1])
        p_idx = manager.NodeToIndex(pickup)
        d_idx = manager.NodeToIndex(delivery)

        routing.AddPickupAndDelivery(p_idx, d_idx)
        routing.solver().Add(routing.VehicleVar(p_idx) == routing.VehicleVar(d_idx))
        routing.solver().Add(dist_dim.CumulVar(p_idx) <= dist_dim.CumulVar(d_idx))

    params = _search_params(data)
    solution = routing.SolveWithParameters(params)
    if solution is None:
        return {"status": "INFEASIBLE", "error": "No feasible PDP routes found."}

    routes, total_distance = _extract_routes(
        manager,
        routing,
        solution,
        num_vehicles,
        distance_dim_name="Distance",
        capacity_dim_name="Capacity",
    )
    return {
        "status": "OPTIMAL_OR_FEASIBLE",
        "problem": "pdp",
        "routes": routes,
        "total_distance": total_distance,
    }
