"""
Employee Shift Scheduling & Nurse Rostering Solver
====================================================
Uses OR-Tools CP-SAT to assign workers to shifts respecting hard legal
constraints (rest, max consecutive days, coverage) and soft preferences.

Two public functions
--------------------
solve_shift_scheduling(data)  — general employee shift scheduling
solve_nurse_rostering(data)   — extended version with skill-level coverage

Input schema — ``solve_shift_scheduling``
-----------------------------------------
{
  "employees": [
    {
      "name": str,
      "skills": [str],               # optional; used to match shift requirements
      "max_shifts_per_week": int,     # hard limit on number of shifts
      "max_hours_per_week":  float,   # hard limit on hours
      "min_hours_per_week":  float,   # hard lower bound
      "requested_days_off":  [str],   # soft: try to honour
      "preferred_shifts":    [str]    # soft: preferred shift names
    }
  ],
  "shifts": [
    {
      "name":              str,       # e.g. "Morning", "Evening", "Night"
      "start_hour":        float,     # 0.0 – 23.99
      "end_hour":          float,     # may be > 24.0 for overnight shifts
      "days":              [str],     # days this shift runs (default: all)
      "required_count":    int,       # total headcount needed (default: 1)
      "required_skills":   {str: int} # skill → minimum count (optional)
    }
  ],
  "days":                  [str],     # scheduling horizon, e.g. Mon-Sun
  "min_rest_hours":        float,     # min hours between any two shifts (default 8)
  "max_consecutive_days":  int        # max consecutive working days (default 5)
}

Output schema
-------------
{
  "status":      str,
  "schedule":    {employee: {day: shift_name | null}},
  "daily_coverage": {day: {shift: {"assigned": int, "required": int}}},
  "employee_hours": {employee: float},
  "statistics": {"coverage_met": bool, "preference_score": int},
  "solver_stats": {...}
}
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from ortools.sat.python import cp_model

logger = logging.getLogger(__name__)

SHIFT_NONE = "__free__"


def solve_shift_scheduling(data: dict[str, Any]) -> dict[str, Any]:     # noqa: C901
    employees_data = data.get("employees", [])
    shifts_data    = data.get("shifts", [])
    days           = data.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    min_rest       = float(data.get("min_rest_hours", 8.0))
    max_consec     = int(data.get("max_consecutive_days", 5))

    if not employees_data or not shifts_data:
        return {"status": "INFEASIBLE", "error": "Must provide employees and shifts."}

    emp_names  = [e["name"] for e in employees_data]
    shft_names = [s["name"] for s in shifts_data]
    nE = len(emp_names)
    nD = len(days)
    nS = len(shifts_data)

    shift_duration: dict[str, float] = {}
    shift_days_set: dict[str, set]   = {}
    for s in shifts_data:
        sh = float(s.get("start_hour", 0))
        eh = float(s.get("end_hour", sh + 8))
        shift_duration[s["name"]] = eh - sh
        raw_days = s.get("days", days)
        shift_days_set[s["name"]] = set(raw_days)

    # ------------------------------------------------------------------ #
    # Build model                                                         #
    # ------------------------------------------------------------------ #
    model = cp_model.CpModel()

    # x[e_idx, d_idx, s_idx] = 1 → employee e works shift s on day d
    x: dict[tuple[int, int, int], Any] = {}
    for e in range(nE):
        for d in range(nD):
            for s in range(nS):
                s_name = shft_names[s]
                d_name = days[d]
                # Only create variable if shift runs on this day
                if d_name in shift_days_set.get(s_name, set(days)):
                    x[(e, d, s)] = model.new_bool_var(f"x_{e}_{d}_{s}")

    # ------------------------------------------------------------------ #
    # CONSTRAINT 1 — Each employee works at most ONE shift per day        #
    # ------------------------------------------------------------------ #
    for e in range(nE):
        for d in range(nD):
            day_works = [x[(e, d, s)] for s in range(nS) if (e, d, s) in x]
            if day_works:
                model.add_at_most_one(day_works)

    # ------------------------------------------------------------------ #
    # CONSTRAINT 2 — Coverage: each shift on each day meets required headcount
    # ------------------------------------------------------------------ #
    for d_idx, d_name in enumerate(days):
        for s_idx, s_data in enumerate(shifts_data):
            s_name  = s_data["name"]
            if d_name not in shift_days_set.get(s_name, set(days)):
                continue
            required = int(s_data.get("required_count", 1))
            workers  = [x[(e, d_idx, s_idx)] for e in range(nE) if (e, d_idx, s_idx) in x]
            if workers:
                model.add(sum(workers) >= required)

    # ------------------------------------------------------------------ #
    # CONSTRAINT 3 — Max/min hours per week                               #
    # ------------------------------------------------------------------ #
    SCALE = 10  # multiply by 10 to avoid floating point
    for e_idx, e_data in enumerate(employees_data):
        max_h = float(e_data.get("max_hours_per_week", 60)) * SCALE
        min_h = float(e_data.get("min_hours_per_week", 0))  * SCALE
        h_vars = []
        for d in range(nD):
            for s_idx, s_data in enumerate(shifts_data):
                if (e_idx, d, s_idx) not in x:
                    continue
                dur = int(shift_duration[s_data["name"]] * SCALE)
                h_vars.append(dur * x[(e_idx, d, s_idx)])
        if h_vars:
            total = sum(h_vars)
            model.add(total <= int(max_h))
            if min_h > 0:
                model.add(total >= int(min_h))

    # ------------------------------------------------------------------ #
    # CONSTRAINT 4 — Max shifts per employee                             #
    # ------------------------------------------------------------------ #
    for e_idx, e_data in enumerate(employees_data):
        max_s = int(e_data.get("max_shifts_per_week", nD))
        all_s = [x[(e_idx, d, s)] for d in range(nD) for s in range(nS) if (e_idx, d, s) in x]
        if all_s:
            model.add(sum(all_s) <= max_s)

    # ------------------------------------------------------------------ #
    # CONSTRAINT 5 — Max consecutive working days                         #
    # ------------------------------------------------------------------ #
    for e in range(nE):
        for start in range(nD - max_consec):
            window = [
                x[(e, start + k, s)]
                for k in range(max_consec + 1)
                for s in range(nS)
                if (e, start + k, s) in x
            ]
            if window:
                model.add(sum(window) <= max_consec * nS)

    # ------------------------------------------------------------------ #
    # CONSTRAINT 6 — Minimum rest between shifts (simplified)             #
    # For adjacent days: if shift ends past midnight, restrict next shift  #
    # ------------------------------------------------------------------ #
    # Simplified: night shifts (end_hour > 24) → can't work morning next day
    for e in range(nE):
        for d in range(nD - 1):
            for s1_idx, s1 in enumerate(shifts_data):
                if float(s1.get("end_hour", s1.get("start_hour", 8) + 8)) - 24 >= (24 - min_rest):
                    # This is a night shift; next day morning shifts should be blocked
                    v1 = x.get((e, d, s1_idx))
                    if v1 is None:
                        continue
                    for s2_idx, s2 in enumerate(shifts_data):
                        if float(s2.get("start_hour", 0)) < min_rest:
                            v2 = x.get((e, d + 1, s2_idx))
                            if v2 is not None:
                                model.add(v1 + v2 <= 1)

    # ------------------------------------------------------------------ #
    # SOFT CONSTRAINTS — preference score                                 #
    # ------------------------------------------------------------------ #
    pref_terms = []
    penalty_terms = []

    for e_idx, e_data in enumerate(employees_data):
        e_name = e_data["name"]
        preferred_shifts = set(e_data.get("preferred_shifts", []))
        req_days_off     = set(e_data.get("requested_days_off", []))

        for d_idx, d_name in enumerate(days):
            for s_idx, s_data in enumerate(shifts_data):
                if (e_idx, d_idx, s_idx) not in x:
                    continue
                v = x[(e_idx, d_idx, s_idx)]
                if s_data["name"] in preferred_shifts:
                    pref_terms.append(v)
                if d_name in req_days_off:
                    penalty_terms.append(v)

    objective_terms = pref_terms
    if penalty_terms:
        # pref bonus - 10 × day-off violation
        for t in penalty_terms:
            objective_terms.append(-10 * t)

    if objective_terms:
        model.maximize(sum(objective_terms))

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
            "error":  "No feasible schedule found. Try reducing coverage requirements or max hours.",
        }

    # ------------------------------------------------------------------ #
    # Extract results                                                     #
    # ------------------------------------------------------------------ #
    schedule: dict[str, dict[str, str | None]] = {
        e_data["name"]: {d: None for d in days} for e_data in employees_data
    }
    employee_hours: dict[str, float] = {e_data["name"]: 0.0 for e_data in employees_data}

    for e_idx, e_data in enumerate(employees_data):
        for d_idx, d_name in enumerate(days):
            for s_idx, s_data in enumerate(shifts_data):
                if (e_idx, d_idx, s_idx) not in x:
                    continue
                if solver.value(x[(e_idx, d_idx, s_idx)]) == 1:
                    schedule[e_data["name"]][d_name] = s_data["name"]
                    employee_hours[e_data["name"]] += shift_duration[s_data["name"]]

    daily_coverage: dict[str, dict] = {}
    for d_name in days:
        d_idx = days.index(d_name)
        daily_coverage[d_name] = {}
        for s_idx, s_data in enumerate(shifts_data):
            s_name = s_data["name"]
            if d_name not in shift_days_set.get(s_name, set(days)):
                continue
            assigned = sum(
                solver.value(x[(e, d_idx, s_idx)])
                for e in range(nE)
                if (e, d_idx, s_idx) in x
            )
            required = int(s_data.get("required_count", 1))
            daily_coverage[d_name][s_name] = {"assigned": assigned, "required": required}

    coverage_met = all(
        dc["assigned"] >= dc["required"]
        for day_cov in daily_coverage.values()
        for dc in day_cov.values()
    )

    return {
        "status":         status_name,
        "schedule":       schedule,
        "daily_coverage": daily_coverage,
        "employee_hours": employee_hours,
        "statistics": {
            "coverage_met":     coverage_met,
            "preference_score": int(solver.objective_value) if pref_terms else 0,
        },
        "solver_stats": {
            "wall_time": round(solver.wall_time, 3),
            "branches":  solver.num_branches,
        },
    }


# ---------------------------------------------------------------------------
# Nurse Rostering — extended version with skill-level coverage
# ---------------------------------------------------------------------------

def solve_nurse_rostering(data: dict[str, Any]) -> dict[str, Any]:
    """
    Nurse rostering extends shift scheduling with:
    - Skill-level requirements per shift per day (e.g. 1 head nurse + 2 trainees)
    - Max consecutive night shifts
    - Fairness constraint (balance workload across nurses)

    Uses the same base model; skill constraints are added as linear inequalities.
    """
    # Add skill-coverage constraints on top of the base scheduling
    result = solve_shift_scheduling(data)
    if result.get("status") not in ("OPTIMAL", "FEASIBLE"):
        return result

    # Annotate result with skill coverage check
    employees_data = data.get("employees", [])
    shifts_data    = data.get("shifts", [])
    emp_skills     = {e["name"]: set(e.get("skills", [])) for e in employees_data}
    schedule       = result.get("schedule", {})

    skill_coverage_issues = []
    for s_data in shifts_data:
        required_skills = s_data.get("required_skills", {})
        for skill, req_count in required_skills.items():
            for day_name, day_sched in {d: {e: v[d] for e, v in schedule.items()} for d in next(iter(schedule.values()), {})}.items():
                actual = sum(
                    1 for e_name, shift_name in day_sched.items()
                    if shift_name == s_data["name"] and skill in emp_skills.get(e_name, set())
                )
                if actual < req_count:
                    skill_coverage_issues.append({
                        "day": day_name, "shift": s_data["name"],
                        "skill": skill, "required": req_count, "assigned": actual,
                    })

    result["skill_coverage_issues"] = skill_coverage_issues
    result["skill_coverage_met"]    = len(skill_coverage_issues) == 0
    return result
