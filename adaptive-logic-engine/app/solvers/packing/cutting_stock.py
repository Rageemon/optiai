"""
Cutting Stock Problem Solver
============================
Comprehensive cutting stock solver using OR-Tools CP-SAT.

Handles:
- 1D Cutting Stock: Cut raw materials (rods, rolls, pipes) to fulfill orders
- Multi-stock Cutting: Different stock sizes available with different costs
- Pattern-based Cutting: Generate and select optimal cutting patterns

Key difference from Bin Packing: We have standard-sized raw materials (stock) and
must cut them to produce specific quantities of required pieces while minimizing
waste (or the number of stock units used).

Input schema (dict)
-------------------
{
  "problem_type": "1d" | "multi-stock",
  "stock_length": int,               # length of raw stock (for 1d)
  "stock_types": [                   # for multi-stock
    {"name": str, "length": int, "cost": int, "available": int}
  ],
  "orders": [
    {
      "name": str,
      "length": int,                 # piece length to cut
      "quantity": int                # number of pieces needed
    }
  ],
  "max_stocks": int,                 # optional upper bound
  "time_limit_seconds": int
}

Output schema (dict)
--------------------
{
  "status": str,
  "stocks_used": int,
  "total_cost": float,
  "total_waste": int,
  "waste_percent": float,
  "cutting_plan": [
    {
      "stock_id": int,
      "stock_type": str,
      "stock_length": int,
      "cuts": [{"name": str, "length": int, "count": int}],
      "waste": int
    }
  ],
  "order_fulfillment": {
    "order_name": {"required": int, "fulfilled": int}
  },
  "solver_stats": {...}
}
"""

from __future__ import annotations

import logging
from typing import Any
from collections import defaultdict

from ortools.sat.python import cp_model

logger = logging.getLogger(__name__)


def solve_cutting_stock(data: dict[str, Any]) -> dict[str, Any]:
    """Main entry point - routes to appropriate cutting stock variant solver."""
    problem_type = data.get("problem_type", "1d").lower().replace(" ", "").replace("-", "").replace("_", "")

    if problem_type in ("1d", "1dim", "onedimensional", "single"):
        return _solve_1d_cutting_stock(data)
    elif problem_type in ("multistock", "multi", "variable", "heterogeneous"):
        return _solve_multi_stock_cutting(data)
    else:
        return {"status": "ERROR", "error": f"Unknown problem_type: {problem_type}"}


def _solve_1d_cutting_stock(data: dict[str, Any]) -> dict[str, Any]:
    """
    1D Cutting Stock: Cut identical stock pieces to fulfill orders.
    Classic scenario: cutting steel rods, paper rolls, wooden beams.
    """
    orders = data.get("orders", [])
    stock_length = int(data.get("stock_length", 0))
    max_stocks = data.get("max_stocks")
    time_limit = int(data.get("time_limit_seconds", 60))

    if not orders:
        return {"status": "INFEASIBLE", "error": "No orders provided."}
    if stock_length <= 0:
        return {"status": "INFEASIBLE", "error": "Stock length must be positive."}

    # Prepare orders
    order_names = [o.get("name", f"Order_{i}") for i, o in enumerate(orders)]
    order_lengths = [int(o.get("length", 0)) for o in orders]
    order_quantities = [int(o.get("quantity", 1)) for o in orders]

    # Validate orders
    for i, length in enumerate(order_lengths):
        if length > stock_length:
            return {
                "status": "INFEASIBLE",
                "error": f"Order '{order_names[i]}' (length={length}) exceeds stock length ({stock_length}).",
            }
        if length <= 0:
            return {
                "status": "INFEASIBLE",
                "error": f"Order '{order_names[i]}' has invalid length ({length}).",
            }

    # Expand orders into individual pieces
    pieces = []
    for i, order in enumerate(orders):
        for q in range(order_quantities[i]):
            pieces.append({
                "order_idx": i,
                "name": order_names[i],
                "length": order_lengths[i],
            })

    n = len(pieces)
    lengths = [p["length"] for p in pieces]

    # Upper bound on stocks needed (worst case: one piece per stock)
    if max_stocks is None:
        max_stocks = n
    else:
        max_stocks = min(int(max_stocks), n)

    model = cp_model.CpModel()

    # x[p][s] = 1 if piece p is cut from stock s
    x = [[model.new_bool_var(f"x_{p}_{s}") for s in range(max_stocks)] for p in range(n)]

    # y[s] = 1 if stock s is used
    y = [model.new_bool_var(f"y_{s}") for s in range(max_stocks)]

    # Each piece must be cut from exactly one stock
    for p in range(n):
        model.add_exactly_one(x[p][s] for s in range(max_stocks))

    # Stock capacity: total length of pieces from stock s <= stock_length
    for s in range(max_stocks):
        model.add(sum(lengths[p] * x[p][s] for p in range(n)) <= stock_length)

    # Link y[s] to x: if any piece from stock s, y[s] = 1
    for s in range(max_stocks):
        for p in range(n):
            model.add_implication(x[p][s], y[s])

    # Symmetry breaking: use stocks in order
    for s in range(max_stocks - 1):
        model.add(y[s] >= y[s + 1])

    # Objective: minimize number of stocks used
    model.minimize(sum(y))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "error": "No feasible cutting plan found."}

    # Extract solution
    stocks_used = sum(solver.value(y[s]) for s in range(max_stocks))
    cutting_plan = []
    total_waste = 0
    order_fulfillment = {name: {"required": order_quantities[i], "fulfilled": 0}
                        for i, name in enumerate(order_names)}

    for s in range(max_stocks):
        if solver.value(y[s]) == 0:
            continue

        stock_pieces = []
        stock_used_length = 0

        for p in range(n):
            if solver.value(x[p][s]) == 1:
                stock_pieces.append(pieces[p])
                stock_used_length += lengths[p]
                order_fulfillment[pieces[p]["name"]]["fulfilled"] += 1

        waste = stock_length - stock_used_length
        total_waste += waste

        # Aggregate cuts by order name
        cuts_agg = defaultdict(lambda: {"length": 0, "count": 0})
        for piece in stock_pieces:
            cuts_agg[piece["name"]]["length"] = piece["length"]
            cuts_agg[piece["name"]]["count"] += 1

        cuts_list = [
            {"name": name, "length": info["length"], "count": info["count"]}
            for name, info in cuts_agg.items()
        ]

        cutting_plan.append({
            "stock_id": s,
            "stock_length": stock_length,
            "cuts": cuts_list,
            "used_length": stock_used_length,
            "waste": waste,
            "waste_percent": round(100 * waste / stock_length, 2),
        })

    total_stock_length = stocks_used * stock_length
    overall_waste_percent = round(100 * total_waste / total_stock_length, 2) if total_stock_length > 0 else 0

    return {
        "status": status_name,
        "stocks_used": stocks_used,
        "stock_length": stock_length,
        "total_stock_length": total_stock_length,
        "total_waste": total_waste,
        "waste_percent": overall_waste_percent,
        "material_utilization": round(100 - overall_waste_percent, 2),
        "cutting_plan": cutting_plan,
        "order_fulfillment": order_fulfillment,
        "all_orders_fulfilled": all(
            v["fulfilled"] >= v["required"] for v in order_fulfillment.values()
        ),
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches": solver.num_branches,
            "objective": solver.objective_value,
        },
    }


def _solve_multi_stock_cutting(data: dict[str, Any]) -> dict[str, Any]:
    """
    Multi-Stock Cutting: Multiple stock sizes with different costs.
    Objective: minimize total cost while fulfilling all orders.
    """
    orders = data.get("orders", [])
    stock_types = data.get("stock_types", [])
    time_limit = int(data.get("time_limit_seconds", 60))

    if not orders:
        return {"status": "INFEASIBLE", "error": "No orders provided."}
    if not stock_types:
        return {"status": "INFEASIBLE", "error": "No stock types provided."}

    # Prepare orders
    order_names = [o.get("name", f"Order_{i}") for i, o in enumerate(orders)]
    order_lengths = [int(o.get("length", 0)) for o in orders]
    order_quantities = [int(o.get("quantity", 1)) for o in orders]

    # Prepare stock types
    st_names = [st.get("name", f"Stock_{i}") for i, st in enumerate(stock_types)]
    st_lengths = [int(st.get("length", 0)) for st in stock_types]
    st_costs = [int(st.get("cost", 1)) for st in stock_types]
    st_available = [int(st.get("available", 1000)) for st in stock_types]

    max_stock_length = max(st_lengths)

    # Validate orders fit in at least one stock type
    for i, length in enumerate(order_lengths):
        if length > max_stock_length:
            return {
                "status": "INFEASIBLE",
                "error": f"Order '{order_names[i]}' (length={length}) exceeds all stock lengths.",
            }

    # Expand orders into pieces
    pieces = []
    for i in range(len(orders)):
        for q in range(order_quantities[i]):
            pieces.append({
                "order_idx": i,
                "name": order_names[i],
                "length": order_lengths[i],
            })

    n = len(pieces)
    lengths = [p["length"] for p in pieces]

    # Create stock instances
    stock_instances = []
    for t in range(len(stock_types)):
        for k in range(st_available[t]):
            stock_instances.append({
                "type_idx": t,
                "type_name": st_names[t],
                "length": st_lengths[t],
                "cost": st_costs[t],
            })

    m = len(stock_instances)
    if m == 0:
        return {"status": "INFEASIBLE", "error": "No stock instances available."}

    model = cp_model.CpModel()

    # x[p][s] = 1 if piece p is cut from stock instance s
    # But piece can only go in stocks long enough
    x = {}
    for p in range(n):
        for s in range(m):
            if stock_instances[s]["length"] >= lengths[p]:
                x[(p, s)] = model.new_bool_var(f"x_{p}_{s}")

    # y[s] = 1 if stock s is used
    y = [model.new_bool_var(f"y_{s}") for s in range(m)]

    # Each piece in exactly one stock
    for p in range(n):
        feasible_stocks = [x[(p, s)] for s in range(m) if (p, s) in x]
        if not feasible_stocks:
            return {
                "status": "INFEASIBLE",
                "error": f"Piece '{pieces[p]['name']}' (length={lengths[p]}) cannot fit in any stock.",
            }
        model.add_exactly_one(feasible_stocks)

    # Stock capacity
    for s in range(m):
        pieces_in_s = [lengths[p] * x[(p, s)] for p in range(n) if (p, s) in x]
        if pieces_in_s:
            model.add(sum(pieces_in_s) <= stock_instances[s]["length"])

    # Link y to x
    for s in range(m):
        for p in range(n):
            if (p, s) in x:
                model.add_implication(x[(p, s)], y[s])

    # Minimize total cost
    model.minimize(sum(stock_instances[s]["cost"] * y[s] for s in range(m)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status_name, "error": "No feasible cutting plan found."}

    # Extract solution
    stocks_used = sum(solver.value(y[s]) for s in range(m))
    total_cost = sum(stock_instances[s]["cost"] * solver.value(y[s]) for s in range(m))
    total_waste = 0
    cutting_plan = []
    order_fulfillment = {name: {"required": order_quantities[i], "fulfilled": 0}
                        for i, name in enumerate(order_names)}

    for s in range(m):
        if solver.value(y[s]) == 0:
            continue

        stock_pieces = []
        stock_used_length = 0

        for p in range(n):
            if (p, s) in x and solver.value(x[(p, s)]) == 1:
                stock_pieces.append(pieces[p])
                stock_used_length += lengths[p]
                order_fulfillment[pieces[p]["name"]]["fulfilled"] += 1

        waste = stock_instances[s]["length"] - stock_used_length
        total_waste += waste

        cuts_agg = defaultdict(lambda: {"length": 0, "count": 0})
        for piece in stock_pieces:
            cuts_agg[piece["name"]]["length"] = piece["length"]
            cuts_agg[piece["name"]]["count"] += 1

        cuts_list = [
            {"name": name, "length": info["length"], "count": info["count"]}
            for name, info in cuts_agg.items()
        ]

        cutting_plan.append({
            "stock_id": s,
            "stock_type": stock_instances[s]["type_name"],
            "stock_length": stock_instances[s]["length"],
            "stock_cost": stock_instances[s]["cost"],
            "cuts": cuts_list,
            "used_length": stock_used_length,
            "waste": waste,
            "waste_percent": round(100 * waste / stock_instances[s]["length"], 2),
        })

    total_stock_length = sum(cp["stock_length"] for cp in cutting_plan)
    overall_waste_percent = round(100 * total_waste / total_stock_length, 2) if total_stock_length > 0 else 0

    # Count stocks by type
    stocks_by_type = defaultdict(int)
    for cp in cutting_plan:
        stocks_by_type[cp["stock_type"]] += 1

    return {
        "status": status_name,
        "stocks_used": stocks_used,
        "total_cost": total_cost,
        "total_waste": total_waste,
        "waste_percent": overall_waste_percent,
        "material_utilization": round(100 - overall_waste_percent, 2),
        "cutting_plan": cutting_plan,
        "stocks_by_type": dict(stocks_by_type),
        "order_fulfillment": order_fulfillment,
        "all_orders_fulfilled": all(
            v["fulfilled"] >= v["required"] for v in order_fulfillment.values()
        ),
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches": solver.num_branches,
            "objective": solver.objective_value,
        },
    }
