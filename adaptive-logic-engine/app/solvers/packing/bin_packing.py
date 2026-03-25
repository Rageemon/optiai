"""
Bin Packing Problem Solver
==========================
Comprehensive bin packing solver using OR-Tools CP-SAT.

Handles:
- 1D Bin Packing: Pack items (by weight/size) into minimum number of bins
- 2D Bin Packing: Pack rectangular items onto 2D bins (sheet cutting, pallet loading)
- 3D Bin Packing: Pack 3D boxes into containers (container loading)
- Variable Bin Packing: Bins of different sizes/costs, minimize total cost

Key difference from Knapsack: ALL items MUST be packed. Objective is to minimize
the number of bins (or total bin cost) used.

Input schema (dict)
-------------------
{
  "problem_type": "1d" | "2d" | "3d" | "variable",
  "items": [
    {
      "name": str,
      "size": int,                    # for 1D
      "width": int, "height": int,    # for 2D
      "width": int, "height": int, "depth": int,  # for 3D
      "quantity": int,                # number of identical items (default 1)
      "can_rotate": bool              # for 2D/3D: allow rotation (default True)
    }
  ],
  "bin_capacity": int,                # for 1D: single bin capacity
  "bin_width": int, "bin_height": int,  # for 2D
  "bin_width": int, "bin_height": int, "bin_depth": int,  # for 3D
  "bin_types": [                      # for variable bin packing
    {"name": str, "capacity": int, "cost": int, "available": int}
  ],
  "max_bins": int,                    # upper bound on bins (optional)
  "time_limit_seconds": int
}

Output schema (dict)
--------------------
{
  "status": str,
  "bins_used": int,
  "total_cost": float,                # for variable bin packing
  "bin_assignments": [
    {"bin_id": int, "bin_type": str, "items": [...], "utilization_percent": float}
  ],
  "items_packed": int,
  "solver_stats": {...}
}
"""

from __future__ import annotations

import logging
from typing import Any

from ortools.sat.python import cp_model

logger = logging.getLogger(__name__)


def solve_bin_packing(data: dict[str, Any]) -> dict[str, Any]:
    """Main entry point - routes to appropriate bin packing variant solver."""
    problem_type = data.get("problem_type", "1d").lower().replace(" ", "").replace("-", "").replace("_", "")

    if problem_type in ("1d", "1dim", "onedimensional"):
        return _solve_1d_bin_packing(data)
    elif problem_type in ("2d", "2dim", "twodimensional"):
        return _solve_2d_bin_packing(data)
    elif problem_type in ("3d", "3dim", "threedimensional"):
        return _solve_3d_bin_packing(data)
    elif problem_type in ("variable", "heterogeneous", "multisize"):
        return _solve_variable_bin_packing(data)
    else:
        return {"status": "ERROR", "error": f"Unknown problem_type: {problem_type}"}


def _solve_1d_bin_packing(data: dict[str, Any]) -> dict[str, Any]:
    """
    1D Bin Packing: Pack items into minimum number of identical bins.
    Classic scenario: packing files onto disks, cutting rods, loading trucks by weight.
    """
    items = data.get("items", [])
    bin_capacity = int(data.get("bin_capacity", 0))
    max_bins = data.get("max_bins")
    time_limit = int(data.get("time_limit_seconds", 60))

    if not items:
        return {"status": "INFEASIBLE", "error": "No items provided."}
    if bin_capacity <= 0:
        return {"status": "INFEASIBLE", "error": "Bin capacity must be positive."}

    # Expand items by quantity
    expanded_items = []
    for item in items:
        qty = int(item.get("quantity", 1))
        for q in range(qty):
            expanded_items.append({
                "name": f"{item.get('name', 'Item')}_{q+1}" if qty > 1 else item.get("name", "Item"),
                "size": int(item.get("size", item.get("weight", 0))),
                "original_name": item.get("name", "Item"),
            })

    n = len(expanded_items)
    sizes = [item["size"] for item in expanded_items]
    names = [item["name"] for item in expanded_items]

    # Validate: each item must fit in a bin
    for i, size in enumerate(sizes):
        if size > bin_capacity:
            return {
                "status": "INFEASIBLE",
                "error": f"Item '{names[i]}' (size={size}) exceeds bin capacity ({bin_capacity}).",
            }

    # Upper bound on bins: at most n bins (one item per bin)
    if max_bins is None:
        max_bins = n
    else:
        max_bins = min(int(max_bins), n)

    model = cp_model.CpModel()

    # x[i][b] = 1 if item i is in bin b
    x = [[model.new_bool_var(f"x_{i}_{b}") for b in range(max_bins)] for i in range(n)]

    # y[b] = 1 if bin b is used
    y = [model.new_bool_var(f"y_{b}") for b in range(max_bins)]

    # Each item must be in exactly one bin
    for i in range(n):
        model.add_exactly_one(x[i][b] for b in range(max_bins))

    # Bin capacity constraint
    for b in range(max_bins):
        model.add(sum(sizes[i] * x[i][b] for i in range(n)) <= bin_capacity)

    # Link y[b] to x: if any item in bin b, y[b] = 1
    for b in range(max_bins):
        for i in range(n):
            model.add_implication(x[i][b], y[b])

    # Symmetry breaking: use bins in order
    for b in range(max_bins - 1):
        model.add(y[b] >= y[b + 1])

    # Objective: minimize number of bins used
    model.minimize(sum(y))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "error": "No feasible packing found."}

    # Extract solution
    bins_used = sum(solver.value(y[b]) for b in range(max_bins))
    bin_assignments = []

    for b in range(max_bins):
        if solver.value(y[b]) == 0:
            continue
        bin_items = []
        bin_load = 0
        for i in range(n):
            if solver.value(x[i][b]) == 1:
                bin_items.append({"name": names[i], "size": sizes[i]})
                bin_load += sizes[i]
        bin_assignments.append({
            "bin_id": b,
            "items": bin_items,
            "total_size": bin_load,
            "capacity": bin_capacity,
            "utilization_percent": round(100 * bin_load / bin_capacity, 2),
        })

    return {
        "status": status_name,
        "bins_used": bins_used,
        "total_items": n,
        "bin_capacity": bin_capacity,
        "bin_assignments": bin_assignments,
        "average_utilization": round(
            sum(ba["utilization_percent"] for ba in bin_assignments) / bins_used, 2
        ) if bins_used > 0 else 0,
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches": solver.num_branches,
            "objective": solver.objective_value,
        },
    }


def _solve_2d_bin_packing(data: dict[str, Any]) -> dict[str, Any]:
    """
    2D Bin Packing: Pack rectangular items onto 2D sheets/bins.
    Uses a placement model with no-overlap constraints.
    """
    items = data.get("items", [])
    bin_width = int(data.get("bin_width", 0))
    bin_height = int(data.get("bin_height", 0))
    max_bins = data.get("max_bins")
    time_limit = int(data.get("time_limit_seconds", 60))

    if not items:
        return {"status": "INFEASIBLE", "error": "No items provided."}
    if bin_width <= 0 or bin_height <= 0:
        return {"status": "INFEASIBLE", "error": "Bin dimensions must be positive."}

    # Expand items by quantity
    expanded_items = []
    for item in items:
        qty = int(item.get("quantity", 1))
        for q in range(qty):
            expanded_items.append({
                "name": f"{item.get('name', 'Item')}_{q+1}" if qty > 1 else item.get("name", "Item"),
                "width": int(item.get("width", 0)),
                "height": int(item.get("height", 0)),
                "can_rotate": item.get("can_rotate", True),
            })

    n = len(expanded_items)

    # Validate items fit in bin (with or without rotation)
    for item in expanded_items:
        w, h = item["width"], item["height"]
        fits_normal = w <= bin_width and h <= bin_height
        fits_rotated = h <= bin_width and w <= bin_height if item["can_rotate"] else False
        if not fits_normal and not fits_rotated:
            return {
                "status": "INFEASIBLE",
                "error": f"Item '{item['name']}' ({w}x{h}) cannot fit in bin ({bin_width}x{bin_height}).",
            }

    if max_bins is None:
        max_bins = n
    else:
        max_bins = min(int(max_bins), n)

    model = cp_model.CpModel()

    # Variables per item: bin assignment, position, rotation
    x_pos = [model.new_int_var(0, bin_width, f"x_{i}") for i in range(n)]
    y_pos = [model.new_int_var(0, bin_height, f"y_{i}") for i in range(n)]
    rotate = [model.new_bool_var(f"rot_{i}") if expanded_items[i]["can_rotate"] else None for i in range(n)]
    bin_assign = [model.new_int_var(0, max_bins - 1, f"bin_{i}") for i in range(n)]

    # Effective width/height after rotation
    eff_w = []
    eff_h = []
    for i in range(n):
        w, h = expanded_items[i]["width"], expanded_items[i]["height"]
        if rotate[i] is not None:
            ew = model.new_int_var(min(w, h), max(w, h), f"ew_{i}")
            eh = model.new_int_var(min(w, h), max(w, h), f"eh_{i}")
            model.add(ew == h).only_enforce_if(rotate[i])
            model.add(ew == w).only_enforce_if(rotate[i].Not())
            model.add(eh == w).only_enforce_if(rotate[i])
            model.add(eh == h).only_enforce_if(rotate[i].Not())
            eff_w.append(ew)
            eff_h.append(eh)
        else:
            eff_w.append(w)
            eff_h.append(h)

    # Item must fit within bin bounds
    for i in range(n):
        if isinstance(eff_w[i], int):
            model.add(x_pos[i] + eff_w[i] <= bin_width)
            model.add(y_pos[i] + eff_h[i] <= bin_height)
        else:
            model.add(x_pos[i] + eff_w[i] <= bin_width)
            model.add(y_pos[i] + eff_h[i] <= bin_height)

    # No overlap: for items in the same bin
    for i in range(n):
        for j in range(i + 1, n):
            same_bin = model.new_bool_var(f"same_{i}_{j}")
            model.add(bin_assign[i] == bin_assign[j]).only_enforce_if(same_bin)
            model.add(bin_assign[i] != bin_assign[j]).only_enforce_if(same_bin.Not())

            left = model.new_bool_var(f"left_{i}_{j}")
            right = model.new_bool_var(f"right_{i}_{j}")
            below = model.new_bool_var(f"below_{i}_{j}")
            above = model.new_bool_var(f"above_{i}_{j}")

            if isinstance(eff_w[i], int):
                model.add(x_pos[i] + eff_w[i] <= x_pos[j]).only_enforce_if(left)
            else:
                model.add(x_pos[i] + eff_w[i] <= x_pos[j]).only_enforce_if(left)

            if isinstance(eff_w[j], int):
                model.add(x_pos[j] + eff_w[j] <= x_pos[i]).only_enforce_if(right)
            else:
                model.add(x_pos[j] + eff_w[j] <= x_pos[i]).only_enforce_if(right)

            if isinstance(eff_h[i], int):
                model.add(y_pos[i] + eff_h[i] <= y_pos[j]).only_enforce_if(below)
            else:
                model.add(y_pos[i] + eff_h[i] <= y_pos[j]).only_enforce_if(below)

            if isinstance(eff_h[j], int):
                model.add(y_pos[j] + eff_h[j] <= y_pos[i]).only_enforce_if(above)
            else:
                model.add(y_pos[j] + eff_h[j] <= y_pos[i]).only_enforce_if(above)

            model.add(left + right + below + above >= 1).only_enforce_if(same_bin)

    # y[b] = 1 if bin b is used
    y = [model.new_bool_var(f"y_{b}") for b in range(max_bins)]
    for i in range(n):
        for b in range(max_bins):
            is_bin_b = model.new_bool_var(f"is_{i}_{b}")
            model.add(bin_assign[i] == b).only_enforce_if(is_bin_b)
            model.add(bin_assign[i] != b).only_enforce_if(is_bin_b.Not())
            model.add_implication(is_bin_b, y[b])

    model.minimize(sum(y))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "error": "No feasible 2D packing found."}

    bins_used = sum(solver.value(y[b]) for b in range(max_bins))
    bin_assignments = {b: [] for b in range(max_bins)}
    bin_area = bin_width * bin_height

    for i in range(n):
        b = solver.value(bin_assign[i])
        xp = solver.value(x_pos[i])
        yp = solver.value(y_pos[i])
        if isinstance(eff_w[i], int):
            w = eff_w[i]
            h = eff_h[i]
        else:
            w = solver.value(eff_w[i])
            h = solver.value(eff_h[i])
        rotated = rotate[i] is not None and solver.value(rotate[i]) == 1
        bin_assignments[b].append({
            "name": expanded_items[i]["name"],
            "x": xp,
            "y": yp,
            "width": w,
            "height": h,
            "rotated": rotated,
        })

    result_bins = []
    for b in range(max_bins):
        if solver.value(y[b]) == 0:
            continue
        items_in_bin = bin_assignments[b]
        total_area = sum(it["width"] * it["height"] for it in items_in_bin)
        result_bins.append({
            "bin_id": b,
            "bin_width": bin_width,
            "bin_height": bin_height,
            "items": items_in_bin,
            "total_area": total_area,
            "utilization_percent": round(100 * total_area / bin_area, 2),
        })

    return {
        "status": status_name,
        "bins_used": bins_used,
        "total_items": n,
        "bin_dimensions": {"width": bin_width, "height": bin_height},
        "bin_assignments": result_bins,
        "average_utilization": round(
            sum(ba["utilization_percent"] for ba in result_bins) / bins_used, 2
        ) if bins_used > 0 else 0,
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches": solver.num_branches,
            "objective": solver.objective_value,
        },
    }


def _solve_3d_bin_packing(data: dict[str, Any]) -> dict[str, Any]:
    """
    3D Bin Packing: Pack 3D boxes into containers.
    Uses volume-based heuristics + assignment as practical approximation.
    """
    items = data.get("items", [])
    bin_width = int(data.get("bin_width", 0))
    bin_height = int(data.get("bin_height", 0))
    bin_depth = int(data.get("bin_depth", 0))
    max_bins = data.get("max_bins")
    time_limit = int(data.get("time_limit_seconds", 60))

    if not items:
        return {"status": "INFEASIBLE", "error": "No items provided."}
    if bin_width <= 0 or bin_height <= 0 or bin_depth <= 0:
        return {"status": "INFEASIBLE", "error": "Bin dimensions must be positive."}

    bin_volume = bin_width * bin_height * bin_depth

    expanded_items = []
    for item in items:
        qty = int(item.get("quantity", 1))
        w = int(item.get("width", 0))
        h = int(item.get("height", 0))
        d = int(item.get("depth", 0))
        vol = w * h * d
        for q in range(qty):
            expanded_items.append({
                "name": f"{item.get('name', 'Item')}_{q+1}" if qty > 1 else item.get("name", "Item"),
                "width": w,
                "height": h,
                "depth": d,
                "volume": vol,
            })

    n = len(expanded_items)

    for item in expanded_items:
        dims = sorted([item["width"], item["height"], item["depth"]])
        bin_dims = sorted([bin_width, bin_height, bin_depth])
        if not all(dims[i] <= bin_dims[i] for i in range(3)):
            return {
                "status": "INFEASIBLE",
                "error": f"Item '{item['name']}' cannot fit in bin even with rotation.",
            }

    if max_bins is None:
        max_bins = n
    else:
        max_bins = min(int(max_bins), n)

    volumes = [item["volume"] for item in expanded_items]
    names = [item["name"] for item in expanded_items]

    model = cp_model.CpModel()

    x = [[model.new_bool_var(f"x_{i}_{b}") for b in range(max_bins)] for i in range(n)]
    y = [model.new_bool_var(f"y_{b}") for b in range(max_bins)]

    for i in range(n):
        model.add_exactly_one(x[i][b] for b in range(max_bins))

    effective_capacity = int(bin_volume * 0.8)
    for b in range(max_bins):
        model.add(sum(volumes[i] * x[i][b] for i in range(n)) <= effective_capacity)

    for b in range(max_bins):
        for i in range(n):
            model.add_implication(x[i][b], y[b])

    for b in range(max_bins - 1):
        model.add(y[b] >= y[b + 1])

    model.minimize(sum(y))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "error": "No feasible 3D packing found."}

    bins_used = sum(solver.value(y[b]) for b in range(max_bins))
    bin_assignments = []

    for b in range(max_bins):
        if solver.value(y[b]) == 0:
            continue
        bin_items = []
        bin_vol = 0
        for i in range(n):
            if solver.value(x[i][b]) == 1:
                bin_items.append({
                    "name": names[i],
                    "width": expanded_items[i]["width"],
                    "height": expanded_items[i]["height"],
                    "depth": expanded_items[i]["depth"],
                    "volume": volumes[i],
                })
                bin_vol += volumes[i]
        bin_assignments.append({
            "bin_id": b,
            "items": bin_items,
            "total_volume": bin_vol,
            "bin_volume": bin_volume,
            "utilization_percent": round(100 * bin_vol / bin_volume, 2),
        })

    return {
        "status": status_name,
        "bins_used": bins_used,
        "total_items": n,
        "bin_dimensions": {"width": bin_width, "height": bin_height, "depth": bin_depth},
        "bin_assignments": bin_assignments,
        "average_utilization": round(
            sum(ba["utilization_percent"] for ba in bin_assignments) / bins_used, 2
        ) if bins_used > 0 else 0,
        "note": "3D packing uses volume-based assignment (80% efficiency factor).",
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches": solver.num_branches,
            "objective": solver.objective_value,
        },
    }


def _solve_variable_bin_packing(data: dict[str, Any]) -> dict[str, Any]:
    """
    Variable Bin Packing: Multiple bin types with different capacities and costs.
    """
    items = data.get("items", [])
    bin_types = data.get("bin_types", [])
    time_limit = int(data.get("time_limit_seconds", 60))

    if not items:
        return {"status": "INFEASIBLE", "error": "No items provided."}
    if not bin_types:
        return {"status": "INFEASIBLE", "error": "No bin types provided."}

    expanded_items = []
    for item in items:
        qty = int(item.get("quantity", 1))
        for q in range(qty):
            expanded_items.append({
                "name": f"{item.get('name', 'Item')}_{q+1}" if qty > 1 else item.get("name", "Item"),
                "size": int(item.get("size", item.get("weight", 0))),
            })

    n = len(expanded_items)
    sizes = [item["size"] for item in expanded_items]
    names = [item["name"] for item in expanded_items]

    bt_names = [bt.get("name", f"Type_{i}") for i, bt in enumerate(bin_types)]
    bt_caps = [int(bt.get("capacity", 0)) for bt in bin_types]
    bt_costs = [int(bt.get("cost", 1)) for bt in bin_types]
    bt_avail = [int(bt.get("available", n)) for bt in bin_types]

    max_cap = max(bt_caps)
    for i, size in enumerate(sizes):
        if size > max_cap:
            return {
                "status": "INFEASIBLE",
                "error": f"Item '{names[i]}' (size={size}) exceeds largest bin capacity ({max_cap}).",
            }

    bin_instances = []
    for t, bt in enumerate(bin_types):
        for k in range(bt_avail[t]):
            bin_instances.append({
                "type_idx": t,
                "type_name": bt_names[t],
                "capacity": bt_caps[t],
                "cost": bt_costs[t],
            })

    m = len(bin_instances)
    if m == 0:
        return {"status": "INFEASIBLE", "error": "No bin instances available."}

    model = cp_model.CpModel()

    x = [[model.new_bool_var(f"x_{i}_{b}") for b in range(m)] for i in range(n)]
    y = [model.new_bool_var(f"y_{b}") for b in range(m)]

    for i in range(n):
        model.add_exactly_one(x[i][b] for b in range(m))

    for b in range(m):
        cap = bin_instances[b]["capacity"]
        model.add(sum(sizes[i] * x[i][b] for i in range(n)) <= cap)

    for b in range(m):
        for i in range(n):
            model.add_implication(x[i][b], y[b])

    costs = [bin_instances[b]["cost"] for b in range(m)]
    model.minimize(sum(costs[b] * y[b] for b in range(m)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "error": "No feasible packing found."}

    bins_used = sum(solver.value(y[b]) for b in range(m))
    total_cost = sum(costs[b] * solver.value(y[b]) for b in range(m))

    bin_assignments = []
    for b in range(m):
        if solver.value(y[b]) == 0:
            continue
        bin_items = []
        bin_load = 0
        for i in range(n):
            if solver.value(x[i][b]) == 1:
                bin_items.append({"name": names[i], "size": sizes[i]})
                bin_load += sizes[i]
        cap = bin_instances[b]["capacity"]
        bin_assignments.append({
            "bin_id": b,
            "bin_type": bin_instances[b]["type_name"],
            "capacity": cap,
            "cost": bin_instances[b]["cost"],
            "items": bin_items,
            "total_size": bin_load,
            "utilization_percent": round(100 * bin_load / cap, 2) if cap > 0 else 0,
        })

    return {
        "status": status_name,
        "bins_used": bins_used,
        "total_cost": total_cost,
        "total_items": n,
        "bin_assignments": bin_assignments,
        "bins_by_type": {
            bt_names[t]: sum(1 for ba in bin_assignments if ba["bin_type"] == bt_names[t])
            for t in range(len(bin_types))
        },
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches": solver.num_branches,
            "objective": solver.objective_value,
        },
    }
