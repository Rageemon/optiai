"""
Knapsack Problem Solver
=======================
Comprehensive knapsack solver using OR-Tools CP-SAT.

Handles:
- 0-1 Knapsack: Select items (take or leave) to maximize value within capacity
- Bounded Knapsack: Each item has limited quantity available
- Unbounded Knapsack: Unlimited quantity of each item type
- Multiple Knapsack: Multiple containers with different capacities
- Multi-dimensional Knapsack: Items have multiple resource dimensions

Input schema (dict)
-------------------
{
  "problem_type": "0-1" | "bounded" | "unbounded" | "multiple" | "multidimensional",
  "items": [
    {
      "name": str,
      "value": int | float,
      "weight": int | float,
      "quantity": int,               # for bounded (default 1)
      "dimensions": {                # for multidimensional
        "weight": int,
        "volume": int,
        ...
      }
    }
  ],
  "capacity": int | float,           # single knapsack capacity
  "capacities": [int],               # multiple knapsack capacities
  "dimension_capacities": {          # for multidimensional
    "weight": int,
    "volume": int,
    ...
  },
  "time_limit_seconds": int
}

Output schema (dict)
--------------------
{
  "status": str,
  "total_value": float,
  "total_weight": float,
  "selected_items": [...],
  "knapsack_contents": {...},
  "capacity_usage": {...},
  "solver_stats": {...}
}
"""

from __future__ import annotations

import logging
from typing import Any

from ortools.sat.python import cp_model

logger = logging.getLogger(__name__)


def solve_knapsack(data: dict[str, Any]) -> dict[str, Any]:
    """Main entry point - routes to appropriate knapsack variant solver."""
    problem_type = data.get("problem_type", "0-1").lower().replace(" ", "-").replace("_", "-")

    if problem_type in ("0-1", "01", "binary"):
        return _solve_01_knapsack(data)
    elif problem_type == "bounded":
        return _solve_bounded_knapsack(data)
    elif problem_type == "unbounded":
        return _solve_unbounded_knapsack(data)
    elif problem_type == "multiple":
        return _solve_multiple_knapsack(data)
    elif problem_type in ("multidimensional", "multi-dimensional", "mdkp"):
        return _solve_multidimensional_knapsack(data)
    else:
        return {"status": "ERROR", "error": f"Unknown problem_type: {problem_type}"}


def _solve_01_knapsack(data: dict[str, Any]) -> dict[str, Any]:
    """0-1 Knapsack: Each item can be taken at most once."""
    items = data.get("items", [])
    capacity = int(data.get("capacity", 0))
    time_limit = int(data.get("time_limit_seconds", 30))

    if not items:
        return {"status": "INFEASIBLE", "error": "No items provided."}
    if capacity <= 0:
        return {"status": "INFEASIBLE", "error": "Capacity must be positive."}

    model = cp_model.CpModel()

    n = len(items)
    x = [model.new_bool_var(f"x_{i}") for i in range(n)]

    values = [int(item.get("value", 0)) for item in items]
    weights = [int(item.get("weight", 0)) for item in items]
    names = [item.get("name", f"Item_{i}") for i, item in enumerate(items)]

    model.add(sum(weights[i] * x[i] for i in range(n)) <= capacity)
    model.maximize(sum(values[i] * x[i] for i in range(n)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "error": "No feasible solution found."}

    selected = []
    total_value = 0
    total_weight = 0

    for i in range(n):
        if solver.value(x[i]) == 1:
            selected.append({
                "name": names[i],
                "quantity": 1,
                "value": values[i],
                "weight": weights[i],
            })
            total_value += values[i]
            total_weight += weights[i]

    return {
        "status": status_name,
        "total_value": total_value,
        "total_weight": total_weight,
        "selected_items": selected,
        "items_not_selected": [
            {"name": names[i], "value": values[i], "weight": weights[i]}
            for i in range(n) if solver.value(x[i]) == 0
        ],
        "capacity_usage": {
            "used": total_weight,
            "total": capacity,
            "utilization_percent": round(100 * total_weight / capacity, 2) if capacity > 0 else 0,
        },
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches": solver.num_branches,
            "objective": solver.objective_value,
        },
    }


def _solve_bounded_knapsack(data: dict[str, Any]) -> dict[str, Any]:
    """Bounded Knapsack: Each item has a limited quantity available."""
    items = data.get("items", [])
    capacity = int(data.get("capacity", 0))
    time_limit = int(data.get("time_limit_seconds", 30))

    if not items:
        return {"status": "INFEASIBLE", "error": "No items provided."}
    if capacity <= 0:
        return {"status": "INFEASIBLE", "error": "Capacity must be positive."}

    model = cp_model.CpModel()

    n = len(items)
    values = [int(item.get("value", 0)) for item in items]
    weights = [int(item.get("weight", 0)) for item in items]
    quantities = [int(item.get("quantity", 1)) for item in items]
    names = [item.get("name", f"Item_{i}") for i, item in enumerate(items)]

    x = [model.new_int_var(0, quantities[i], f"x_{i}") for i in range(n)]

    model.add(sum(weights[i] * x[i] for i in range(n)) <= capacity)
    model.maximize(sum(values[i] * x[i] for i in range(n)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "error": "No feasible solution found."}

    selected = []
    total_value = 0
    total_weight = 0

    for i in range(n):
        qty = solver.value(x[i])
        if qty > 0:
            item_value = values[i] * qty
            item_weight = weights[i] * qty
            selected.append({
                "name": names[i],
                "quantity": qty,
                "value": item_value,
                "weight": item_weight,
                "unit_value": values[i],
                "unit_weight": weights[i],
            })
            total_value += item_value
            total_weight += item_weight

    return {
        "status": status_name,
        "total_value": total_value,
        "total_weight": total_weight,
        "selected_items": selected,
        "capacity_usage": {
            "used": total_weight,
            "total": capacity,
            "utilization_percent": round(100 * total_weight / capacity, 2) if capacity > 0 else 0,
        },
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches": solver.num_branches,
            "objective": solver.objective_value,
        },
    }


def _solve_unbounded_knapsack(data: dict[str, Any]) -> dict[str, Any]:
    """Unbounded Knapsack: Unlimited quantity of each item type."""
    items = data.get("items", [])
    capacity = int(data.get("capacity", 0))
    time_limit = int(data.get("time_limit_seconds", 30))

    if not items:
        return {"status": "INFEASIBLE", "error": "No items provided."}
    if capacity <= 0:
        return {"status": "INFEASIBLE", "error": "Capacity must be positive."}

    model = cp_model.CpModel()

    n = len(items)
    values = [int(item.get("value", 0)) for item in items]
    weights = [int(item.get("weight", 1)) for item in items]
    names = [item.get("name", f"Item_{i}") for i, item in enumerate(items)]

    upper_bounds = [capacity // max(1, weights[i]) for i in range(n)]
    x = [model.new_int_var(0, upper_bounds[i], f"x_{i}") for i in range(n)]

    model.add(sum(weights[i] * x[i] for i in range(n)) <= capacity)
    model.maximize(sum(values[i] * x[i] for i in range(n)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "error": "No feasible solution found."}

    selected = []
    total_value = 0
    total_weight = 0

    for i in range(n):
        qty = solver.value(x[i])
        if qty > 0:
            item_value = values[i] * qty
            item_weight = weights[i] * qty
            selected.append({
                "name": names[i],
                "quantity": qty,
                "value": item_value,
                "weight": item_weight,
                "unit_value": values[i],
                "unit_weight": weights[i],
            })
            total_value += item_value
            total_weight += item_weight

    return {
        "status": status_name,
        "total_value": total_value,
        "total_weight": total_weight,
        "selected_items": selected,
        "capacity_usage": {
            "used": total_weight,
            "total": capacity,
            "utilization_percent": round(100 * total_weight / capacity, 2) if capacity > 0 else 0,
        },
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches": solver.num_branches,
            "objective": solver.objective_value,
        },
    }


def _solve_multiple_knapsack(data: dict[str, Any]) -> dict[str, Any]:
    """Multiple Knapsack: Assign items to multiple knapsacks with different capacities."""
    items = data.get("items", [])
    capacities = data.get("capacities", [])
    time_limit = int(data.get("time_limit_seconds", 30))

    if not items:
        return {"status": "INFEASIBLE", "error": "No items provided."}
    if not capacities:
        return {"status": "INFEASIBLE", "error": "No knapsack capacities provided."}

    model = cp_model.CpModel()

    n = len(items)
    k = len(capacities)

    values = [int(item.get("value", 0)) for item in items]
    weights = [int(item.get("weight", 0)) for item in items]
    names = [item.get("name", f"Item_{i}") for i, item in enumerate(items)]

    x = [[model.new_bool_var(f"x_{i}_{j}") for j in range(k)] for i in range(n)]

    for i in range(n):
        model.add_at_most_one(x[i][j] for j in range(k))

    for j in range(k):
        model.add(sum(weights[i] * x[i][j] for i in range(n)) <= capacities[j])

    model.maximize(sum(values[i] * x[i][j] for i in range(n) for j in range(k)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "error": "No feasible solution found."}

    selected = []
    knapsack_contents: dict[int, list] = {j: [] for j in range(k)}
    knapsack_weights = [0] * k
    total_value = 0
    total_weight = 0

    for i in range(n):
        for j in range(k):
            if solver.value(x[i][j]) == 1:
                selected.append({
                    "name": names[i],
                    "quantity": 1,
                    "value": values[i],
                    "weight": weights[i],
                    "knapsack_id": j,
                })
                knapsack_contents[j].append({
                    "name": names[i],
                    "value": values[i],
                    "weight": weights[i],
                })
                knapsack_weights[j] += weights[i]
                total_value += values[i]
                total_weight += weights[i]

    knapsack_stats = []
    for j in range(k):
        knapsack_stats.append({
            "knapsack_id": j,
            "capacity": capacities[j],
            "used": knapsack_weights[j],
            "utilization_percent": round(100 * knapsack_weights[j] / capacities[j], 2) if capacities[j] > 0 else 0,
            "items_count": len(knapsack_contents[j]),
        })

    return {
        "status": status_name,
        "total_value": total_value,
        "total_weight": total_weight,
        "selected_items": selected,
        "knapsack_contents": knapsack_contents,
        "knapsack_stats": knapsack_stats,
        "items_not_selected": [
            {"name": names[i], "value": values[i], "weight": weights[i]}
            for i in range(n)
            if all(solver.value(x[i][j]) == 0 for j in range(k))
        ],
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches": solver.num_branches,
            "objective": solver.objective_value,
        },
    }


def _solve_multidimensional_knapsack(data: dict[str, Any]) -> dict[str, Any]:
    """Multi-dimensional Knapsack: Items have multiple resource dimensions."""
    items = data.get("items", [])
    dimension_capacities = data.get("dimension_capacities", {})
    time_limit = int(data.get("time_limit_seconds", 30))

    if not items:
        return {"status": "INFEASIBLE", "error": "No items provided."}
    if not dimension_capacities:
        return {"status": "INFEASIBLE", "error": "No dimension capacities provided."}

    model = cp_model.CpModel()

    n = len(items)
    dimensions = list(dimension_capacities.keys())

    values = [int(item.get("value", 0)) for item in items]
    names = [item.get("name", f"Item_{i}") for i, item in enumerate(items)]

    item_dimensions: list[dict] = []
    for item in items:
        dims = dict(item.get("dimensions", {}))
        if "weight" in dimension_capacities and "weight" not in dims:
            dims["weight"] = int(item.get("weight", 0))
        item_dimensions.append(dims)

    x = [model.new_bool_var(f"x_{i}") for i in range(n)]

    for dim in dimensions:
        cap = int(dimension_capacities[dim])
        model.add(
            sum(int(item_dimensions[i].get(dim, 0)) * x[i] for i in range(n)) <= cap
        )

    model.maximize(sum(values[i] * x[i] for i in range(n)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "error": "No feasible solution found."}

    selected = []
    total_value = 0
    dimension_usage: dict[str, int] = {dim: 0 for dim in dimensions}

    for i in range(n):
        if solver.value(x[i]) == 1:
            selected.append({
                "name": names[i],
                "quantity": 1,
                "value": values[i],
                "dimensions": item_dimensions[i],
            })
            total_value += values[i]
            for dim in dimensions:
                dimension_usage[dim] += int(item_dimensions[i].get(dim, 0))

    dimension_stats = {}
    for dim in dimensions:
        cap = int(dimension_capacities[dim])
        used = dimension_usage[dim]
        dimension_stats[dim] = {
            "used": used,
            "total": cap,
            "utilization_percent": round(100 * used / cap, 2) if cap > 0 else 0,
        }

    return {
        "status": status_name,
        "total_value": total_value,
        "selected_items": selected,
        "dimension_usage": dimension_stats,
        "items_not_selected": [
            {"name": names[i], "value": values[i], "dimensions": item_dimensions[i]}
            for i in range(n) if solver.value(x[i]) == 0
        ],
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches": solver.num_branches,
            "objective": solver.objective_value,
        },
    }
