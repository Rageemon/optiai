"""
Resource-Constrained Project Scheduling (RCPSP) Solver
=======================================================
Uses OR-Tools CP-SAT interval variables + AddCumulative constraint.

Key features
------------
- Precedence dependencies (A must finish before B starts)
- Renewable resource capacity limits (at every time point)
- Optional time windows per activity (earliest start / latest finish)
- Minimise project makespan (critical path with resource contention)

Input schema (dict)
-------------------
{
  "activities": [
    {
      "name":       str,
      "duration":   int,            # processing time (time units)
      "predecessors": [str],        # activity names that must finish first
      "resources": {                # resource_name → units needed while active
        "workers": 3,
        "cranes":  1
      },
      "earliest_start": int | null, # optional time window
      "latest_finish":  int | null
    }
  ],
  "resources": [
    {"name": str, "capacity": int}  # maximum units available at any time
  ],
  "time_unit": str                  # descriptive label, e.g. "days" (cosmetic)
}

Output schema (dict)
--------------------
{
  "status":    str,
  "makespan":  int,
  "schedule":  [{"activity": str, "start": int, "finish": int, "duration": int}],
  "critical_path":      [str],     # activities on the critical path
  "resource_usage":     {resource: [int]},   # usage at each time unit
  "resource_capacity":  {resource: int},
  "solver_stats": {...}
}
"""

from __future__ import annotations

import logging
from typing import Any

from ortools.sat.python import cp_model

logger = logging.getLogger(__name__)


def solve_rcpsp(data: dict[str, Any]) -> dict[str, Any]:     # noqa: C901
    activities_data = data.get("activities", [])
    resources_data  = data.get("resources", [])
    time_unit       = data.get("time_unit", "time units")

    if not activities_data:
        return {"status": "INFEASIBLE", "error": "No activities provided."}

    # Map name → activity dict
    act_by_name: dict[str, dict] = {a["name"]: a for a in activities_data}
    act_names   = [a["name"] for a in activities_data]

    # Resource capacities
    resource_cap: dict[str, int] = {r["name"]: int(r["capacity"]) for r in resources_data}

    # Compute horizon: sum of all durations (safe upper bound)
    horizon = sum(max(1, int(a.get("duration", 1))) for a in activities_data) + 1

    # ------------------------------------------------------------------ #
    # Build model                                                         #
    # ------------------------------------------------------------------ #
    model = cp_model.CpModel()

    start_var: dict[str, Any]    = {}
    end_var:   dict[str, Any]    = {}
    interval:  dict[str, Any]    = {}

    for a in activities_data:
        name     = a["name"]
        duration = max(1, int(a.get("duration", 1)))
        e_start  = int(a.get("earliest_start", 0))
        l_finish = int(a.get("latest_finish", horizon))

        s = model.new_int_var(e_start, l_finish - duration, f"start_{name}")
        e = model.new_int_var(e_start + duration, l_finish, f"end_{name}")
        iv = model.new_interval_var(s, duration, e, f"iv_{name}")

        start_var[name] = s
        end_var[name]   = e
        interval[name]  = iv

    # ------------------------------------------------------------------ #
    # CONSTRAINT 1 — Precedence                                           #
    # ------------------------------------------------------------------ #
    for a in activities_data:
        name = a["name"]
        for pred_name in a.get("predecessors", []):
            if pred_name not in act_by_name:
                logger.warning("Unknown predecessor '%s' for activity '%s'", pred_name, name)
                continue
            model.add(end_var[pred_name] <= start_var[name])

    # ------------------------------------------------------------------ #
    # CONSTRAINT 2 — Cumulative resource limits                           #
    # ------------------------------------------------------------------ #
    for res_name, cap in resource_cap.items():
        res_intervals = []
        res_demands   = []
        for a in activities_data:
            demand = int(a.get("resources", {}).get(res_name, 0))
            if demand > 0:
                res_intervals.append(interval[a["name"]])
                res_demands.append(demand)
        if res_intervals:
            model.add_cumulative(res_intervals, res_demands, cap)

    # ------------------------------------------------------------------ #
    # Objective — minimise makespan                                       #
    # ------------------------------------------------------------------ #
    makespan = model.new_int_var(0, horizon, "makespan")
    model.add_max_equality(makespan, [end_var[n] for n in act_names])
    model.minimize(makespan)

    # ------------------------------------------------------------------ #
    # Solve                                                               #
    # ------------------------------------------------------------------ #
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "status": status_name,
            "error":  "No feasible schedule found. Check precedence cycles and resource capacities.",
        }

    solved_makespan = solver.value(makespan)

    # ------------------------------------------------------------------ #
    # Extract schedule                                                    #
    # ------------------------------------------------------------------ #
    schedule = []
    for a in activities_data:
        name     = a["name"]
        s_val    = solver.value(start_var[name])
        e_val    = solver.value(end_var[name])
        duration = max(1, int(a.get("duration", 1)))
        schedule.append({
            "activity": name,
            "start":    s_val,
            "finish":   e_val,
            "duration": duration,
            "resources": a.get("resources", {}),
        })
    schedule.sort(key=lambda x: x["start"])

    # ------------------------------------------------------------------ #
    # Resource usage profile                                              #
    # ------------------------------------------------------------------ #
    resource_usage: dict[str, list[int]] = {}
    for res_name, cap in resource_cap.items():
        usage = [0] * (solved_makespan + 1)
        for a in activities_data:
            demand = int(a.get("resources", {}).get(res_name, 0))
            if demand == 0:
                continue
            s_val = solver.value(start_var[a["name"]])
            e_val = solver.value(end_var[a["name"]])
            for t in range(s_val, e_val):
                if t <= solved_makespan:
                    usage[t] += demand
        resource_usage[res_name] = usage

    # ------------------------------------------------------------------ #
    # Critical path (activities with zero total float)                    #
    # ------------------------------------------------------------------ #
    # Simple heuristic: activities whose finish == makespan, or are on
    # the longest dependency chain
    critical = _find_critical(schedule, act_by_name, solved_makespan)

    return {
        "status":           status_name,
        "makespan":         solved_makespan,
        "time_unit":        time_unit,
        "schedule":         schedule,
        "critical_path":    critical,
        "resource_usage":   resource_usage,
        "resource_capacity": resource_cap,
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches":  solver.num_branches,
        },
    }


def _find_critical(
    schedule:     list[dict],
    act_by_name:  dict[str, dict],
    makespan:     int,
) -> list[str]:
    """Heuristic: activities whose finish equals makespan or chain to it."""
    sched_map = {s["activity"]: s for s in schedule}
    critical  = set()

    # Walk backwards from activities that end at makespan
    def _trace(name: str) -> None:
        if name in critical:
            return
        critical.add(name)
        for a in act_by_name.values():
            if name in a.get("predecessors", []):
                _trace(a["name"])

    for entry in schedule:
        if entry["finish"] == makespan:
            _trace(entry["activity"])

    return sorted(critical, key=lambda n: sched_map[n]["start"])
