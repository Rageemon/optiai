"""
Job Shop / Flow Shop / Parallel Machine Scheduling Solver
=========================================================
Uses OR-Tools CP-SAT interval variables with NoOverlap constraints.

Supported problem types (``data["problem_type"]``)
---------------------------------------------------
jssp      — each job defines its OWN ordered sequence of machines
fssp      — ALL jobs share the SAME machine order (flow shop)
parallel  — tasks are independent; multiple identical/heterogeneous machines

Input schema (dict)
-------------------
{
  "problem_type": "jssp" | "fssp" | "parallel",   # default: jssp
  "objective":    "makespan" | "weighted_tardiness",  # default: makespan
  "horizon":      int | null,                    # auto-computed when null
  "jobs": [
    {
      "name":     str,
      "priority": int,        # weight for weighted_tardiness (default 1)
      "due_date": int | null, # for tardiness objective
      "tasks": [
        {"machine": str, "duration": int}
      ]
    }
  ],
  "machines": [               # optional; auto-detected from tasks if omitted
    {"name": str, "count": int}  # count > 1 → parallel copies of machine
  ]
}

Output schema (dict)
--------------------
{
  "status":             str,   # OPTIMAL | FEASIBLE | INFEASIBLE | UNKNOWN
  "makespan":           int,
  "schedule": [
    {
      "job":   str,
      "tasks": [{"machine": str, "start": int, "end": int, "duration": int}]
    }
  ],
  "machine_timelines": {machine: [{"job": str, "start": int, "end": int}]},
  "machine_utilization": {machine: float},
  "solver_stats": {"wall_time": float, "branches": int}
}
"""

from __future__ import annotations

import logging
from typing import Any

from ortools.sat.python import cp_model

logger = logging.getLogger(__name__)


def solve_job_shop(data: dict[str, Any]) -> dict[str, Any]:
    problem_type  = data.get("problem_type", "jssp").lower()
    objective_type = data.get("objective", "makespan").lower()
    jobs_data     = data.get("jobs", [])

    if not jobs_data:
        return {"status": "INFEASIBLE", "error": "No jobs provided."}

    # ------------------------------------------------------------------ #
    # Build machine list (auto-detect + explicit)                         #
    # ------------------------------------------------------------------ #
    machine_names: list[str] = []
    for job in jobs_data:
        for task in job.get("tasks", []):
            m = str(task.get("machine", "")).strip()
            if m and m not in machine_names:
                machine_names.append(m)

    machine_count: dict[str, int] = {}
    for m_info in data.get("machines", []):
        name  = m_info if isinstance(m_info, str) else m_info.get("name", "")
        count = 1 if isinstance(m_info, str) else int(m_info.get("count", 1))
        if name:
            if name not in machine_names:
                machine_names.append(name)
            machine_count[name] = count

    if not machine_names:
        return {"status": "INFEASIBLE", "error": "No machines detected."}

    # For FSSP: override job task sequences so all jobs use machine_names in order
    if problem_type == "fssp":
        for job in jobs_data:
            dur_by_machine: dict[str, int] = {
                t["machine"]: t.get("duration", 1)
                for t in job.get("tasks", [])
            }
            job["tasks"] = [
                {"machine": m, "duration": dur_by_machine.get(m, 0)}
                for m in machine_names
            ]

    # ------------------------------------------------------------------ #
    # Horizon                                                             #
    # ------------------------------------------------------------------ #
    horizon: int = data.get("horizon") or (
        sum(
            sum(max(1, int(t.get("duration", 1))) for t in j.get("tasks", []))
            for j in jobs_data
        ) * 2 + 1
    )

    # ------------------------------------------------------------------ #
    # Build CP-SAT model                                                  #
    # ------------------------------------------------------------------ #
    model = cp_model.CpModel()

    all_tasks: dict[tuple[int, int], dict[str, Any]] = {}
    # machine → list of intervals (for NoOverlap); parallel count > 1 → NoOverlap2D trick
    machine_to_intervals: dict[str, list] = {m: [] for m in machine_names}

    for j_idx, job in enumerate(jobs_data):
        tasks = job.get("tasks", [])
        for t_idx, task in enumerate(tasks):
            duration = max(1, int(task.get("duration", 1)))
            machine  = str(task.get("machine", machine_names[0])).strip()
            # Skip zero-duration tasks (common in FSSP where machine not used)
            if duration == 0:
                continue

            s_var = model.new_int_var(0, horizon, f"s_{j_idx}_{t_idx}")
            e_var = model.new_int_var(0, horizon, f"e_{j_idx}_{t_idx}")
            i_var = model.new_interval_var(s_var, duration, e_var, f"i_{j_idx}_{t_idx}")

            all_tasks[(j_idx, t_idx)] = {
                "start":    s_var,
                "end":      e_var,
                "interval": i_var,
                "machine":  machine,
                "duration": duration,
            }
            if machine in machine_to_intervals:
                machine_to_intervals[machine].append(i_var)

    # No-overlap per machine (parallel machines → NoOverlap2D or disjunctive)
    for machine, intervals in machine_to_intervals.items():
        count = machine_count.get(machine, 1)
        if len(intervals) > count:
            if count == 1:
                model.add_no_overlap(intervals)
            else:
                # For parallel identical machines, use cumulative with demand=1 capacity=count
                durations = [
                    t["duration"]
                    for t in all_tasks.values()
                    if t["machine"] == machine
                ]
                demands = [1] * len(intervals)
                model.add_cumulative(intervals, demands, count)

    # Precedence: task order within each job
    for j_idx, job in enumerate(jobs_data):
        prev_end = None
        for t_idx, task in enumerate(job.get("tasks", [])):
            if (j_idx, t_idx) not in all_tasks:
                continue
            if prev_end is not None:
                model.add(prev_end <= all_tasks[(j_idx, t_idx)]["start"])
            prev_end = all_tasks[(j_idx, t_idx)]["end"]

    # ------------------------------------------------------------------ #
    # Objective                                                           #
    # ------------------------------------------------------------------ #
    makespan = model.new_int_var(0, horizon, "makespan")
    all_ends = [t["end"] for t in all_tasks.values()]
    if all_ends:
        model.add_max_equality(makespan, all_ends)

    if objective_type in ("tardiness", "weighted_tardiness"):
        penalty_terms = []
        for j_idx, job in enumerate(jobs_data):
            due_date = job.get("due_date")
            priority = int(job.get("priority", 1))
            tasks    = job.get("tasks", [])
            if due_date is None:
                continue
            # Find last task of this job that was actually modelled
            last_end = None
            for t_idx in range(len(tasks) - 1, -1, -1):
                if (j_idx, t_idx) in all_tasks:
                    last_end = all_tasks[(j_idx, t_idx)]["end"]
                    break
            if last_end is None:
                continue
            tard  = model.new_int_var(0, horizon, f"tard_{j_idx}")
            zero  = model.new_constant(0)
            delay = model.new_int_var(-horizon, horizon, f"delay_{j_idx}")
            model.add(delay == last_end - int(due_date))
            model.add_max_equality(tard, [delay, zero])
            penalty_terms.append(priority * tard)

        if penalty_terms:
            model.minimize(sum(penalty_terms))
        else:
            model.minimize(makespan)
    else:
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
            "error":  "No feasible schedule found. Verify constraints and horizon.",
        }

    # ------------------------------------------------------------------ #
    # Extract results                                                     #
    # ------------------------------------------------------------------ #
    solved_makespan = solver.value(makespan)
    schedule: list[dict] = []
    machine_timelines: dict[str, list] = {m: [] for m in machine_names}

    for j_idx, job in enumerate(jobs_data):
        job_entry: dict[str, Any] = {
            "job":   job.get("name", f"Job-{j_idx + 1}"),
            "tasks": [],
        }
        for t_idx, task in enumerate(job.get("tasks", [])):
            if (j_idx, t_idx) not in all_tasks:
                continue
            td = all_tasks[(j_idx, t_idx)]
            s, e = solver.value(td["start"]), solver.value(td["end"])
            machine = td["machine"]
            job_entry["tasks"].append({
                "machine":  machine,
                "start":    s,
                "end":      e,
                "duration": td["duration"],
            })
            if machine in machine_timelines:
                machine_timelines[machine].append({
                    "job":   job.get("name", f"Job-{j_idx + 1}"),
                    "start": s,
                    "end":   e,
                })
        schedule.append(job_entry)

    for m in machine_timelines:
        machine_timelines[m].sort(key=lambda x: x["start"])

    utilization = {
        m: round(sum(t["end"] - t["start"] for t in tl) / max(solved_makespan, 1), 3)
        for m, tl in machine_timelines.items()
    }

    return {
        "status":              status_name,
        "makespan":            solved_makespan,
        "schedule":            schedule,
        "machine_timelines":   machine_timelines,
        "machine_utilization": utilization,
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches":  solver.num_branches,
        },
    }
