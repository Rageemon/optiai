"""
Scheduling Solver — Step 3b
Uses Google OR-Tools CP-SAT to produce a conflict-free weekly timetable.

Static domain
-------------
Teachers : Alice, Bob, Charlie
Days     : Monday – Friday  (5 days)
Slots    : 9AM, 12PM, 3PM   (3 time slots per day)

Decision variables
------------------
``shifts[(t, d, s)]`` — BoolVar that is 1 when teacher *t* is scheduled
on day *d* at slot *s*, and 0 otherwise.

Hard constraints (always applied)
----------------------------------
1. **No double-booking** — At most one teacher per (day, slot) pair.
2. **Single slot per day** — Each teacher teaches at most one slot per day
   (prevents the solver from over-assigning a teacher in the same day).

Soft / dynamic constraints (injected from LLM output)
------------------------------------------------------
* ``"unavailable"``  → teacher CANNOT be assigned to the given (day, slot).
  If only day is specified, blocked for all slots that day.
  If only slot is specified, blocked for that slot across all days.
* ``"required"``     → teacher MUST be assigned to the exact (day, slot).
* ``"preferred"``    → treated as a soft hint: adds to the objective
  function with a positive weight so the solver favours it without a hard
  commitment (avoids INFEASIBLE results for contradictory soft hints).

Objective
---------
Maximise total assignments + preferred-slot bonuses.
"""

import logging
from typing import Any, Dict, List

from ortools.sat.python import cp_model

from app.models.schemas import SchedulingConstraint
from app.solvers.base_solver import OptimizationSolver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static domain data
# ---------------------------------------------------------------------------

TEACHERS: List[str] = ["Alice", "Bob", "Charlie"]
DAYS: List[str]     = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
SLOTS: List[str]    = ["9AM", "12PM", "3PM"]

_TEACHER_INDEX: Dict[str, int] = {t.lower(): i for i, t in enumerate(TEACHERS)}
_DAY_INDEX:     Dict[str, int] = {d.lower(): i for i, d in enumerate(DAYS)}
_SLOT_INDEX:    Dict[str, int] = {s.lower(): i for i, s in enumerate(SLOTS)}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _lookup(mapping: Dict[str, int], key: str | None) -> int | None:
    """Return the integer index for *key* or ``None`` if unknown/unspecified."""
    if key is None:
        return None
    return mapping.get(key.lower())


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

class SchedulingSolver(OptimizationSolver):
    """
    CP-SAT–based weekly timetable solver.

    The solver builds a Boolean variable matrix, applies static hard
    constraints, injects dynamic LLM-derived constraints, then maximises
    coverage via OR-Tools' CP-SAT engine.
    """

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def solve(self, constraints: List[SchedulingConstraint]) -> Dict[str, Any]:
        """
        Build and solve the CP-SAT model.

        Parameters
        ----------
        constraints : list[SchedulingConstraint]
            Validated constraint objects produced by the LLM service.

        Returns
        -------
        dict with keys:
            - ``status``        : "SUCCESS" | "INFEASIBLE" | "UNKNOWN"
            - ``solver_status`` : raw OR-Tools status string
            - ``schedule``      : nested dict  { day → { slot → teacher | null } }
            - ``stats``         : wall-clock time and number of assignments
        """
        model  = cp_model.CpModel()
        solver = cp_model.CpSolver()

        T, D, S = len(TEACHERS), len(DAYS), len(SLOTS)

        # ---- Decision variables -----------------------------------------
        # shifts[(t, d, s)] ∈ {0, 1}
        shifts: Dict[tuple, Any] = {
            (t, d, s): model.new_bool_var(f"shift_t{t}_d{d}_s{s}")
            for t in range(T)
            for d in range(D)
            for s in range(S)
        }

        # ---- Hard constraint 1: no double-booking -----------------------
        # For every (day, slot), at most ONE teacher is present.
        for d in range(D):
            for s in range(S):
                model.add_at_most_one(shifts[(t, d, s)] for t in range(T))

        # ---- Hard constraint 2: single slot per teacher per day ----------
        # Each teacher teaches at most one slot per day.
        for t in range(T):
            for d in range(D):
                model.add_at_most_one(shifts[(t, d, s)] for s in range(S))

        # ---- Dynamic constraint injection from LLM output ---------------
        # Collect preferred-slot bonus terms for the objective function.
        preferred_terms: List[Any] = []
        skipped = 0

        for constraint in constraints:
            t_idx = _lookup(_TEACHER_INDEX, constraint.teacher)
            if t_idx is None:
                logger.warning(
                    "Constraint references unknown teacher '%s' — skipping.",
                    constraint.teacher,
                )
                skipped += 1
                continue

            d_idx = _lookup(_DAY_INDEX,  constraint.day)
            s_idx = _lookup(_SLOT_INDEX, constraint.time_slot)

            ctype = constraint.constraint_type.lower()

            if ctype == "unavailable":
                # Block teacher from specific (day, slot), all slots that day,
                # or all days in that slot — depending on what was specified.
                if d_idx is not None and s_idx is not None:
                    model.add(shifts[(t_idx, d_idx, s_idx)] == 0)
                elif d_idx is not None:
                    for s in range(S):
                        model.add(shifts[(t_idx, d_idx, s)] == 0)
                elif s_idx is not None:
                    for d in range(D):
                        model.add(shifts[(t_idx, d, s_idx)] == 0)
                else:
                    # "unavailable" with no day/slot → block entirely
                    for d in range(D):
                        for s in range(S):
                            model.add(shifts[(t_idx, d, s)] == 0)

            elif ctype == "required":
                # Hard-pin teacher to the specific (day, slot) if both given.
                if d_idx is not None and s_idx is not None:
                    model.add(shifts[(t_idx, d_idx, s_idx)] == 1)
                else:
                    logger.warning(
                        "Constraint type 'required' for teacher '%s' needs both "
                        "day and time_slot — skipping (got day=%s, slot=%s).",
                        constraint.teacher, constraint.day, constraint.time_slot,
                    )
                    skipped += 1

            elif ctype == "preferred":
                # Soft preference: add to objective with a weight of 1
                # so the solver favours this assignment without mandating it.
                if d_idx is not None and s_idx is not None:
                    preferred_terms.append(shifts[(t_idx, d_idx, s_idx)])
                else:
                    logger.info(
                        "Preferred constraint for '%s' needs both day+slot — ignoring.",
                        constraint.teacher,
                    )
            else:
                logger.warning("Unknown constraint_type '%s' — skipping.", ctype)
                skipped += 1

        if skipped:
            logger.info("%d constraint(s) were skipped due to missing/unknown fields.", skipped)

        # ---- Objective: maximise total assignments + preferred bonuses ---
        # Base score: 1 point per assigned shift.
        # Bonus score: 2 extra points per preferred shift that is assigned.
        base_score = sum(
            shifts[(t, d, s)]
            for t in range(T)
            for d in range(D)
            for s in range(S)
        )
        bonus_score = sum(preferred_terms) * 2 if preferred_terms else 0
        model.maximize(base_score + bonus_score)

        # ---- Solve -------------------------------------------------------
        logger.info("Invoking CP-SAT solver …")
        status_code = solver.solve(model)
        status_name = solver.status_name(status_code)
        wall_time   = round(solver.wall_time, 4)

        logger.info("CP-SAT finished — status=%s, wall_time=%.4fs", status_name, wall_time)

        if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            schedule: Dict[str, Dict[str, str | None]] = {}
            total_assigned = 0

            for d, day in enumerate(DAYS):
                schedule[day] = {}
                for s, slot in enumerate(SLOTS):
                    assigned_teacher = None
                    for t, teacher in enumerate(TEACHERS):
                        if solver.value(shifts[(t, d, s)]) == 1:
                            assigned_teacher = teacher
                            total_assigned  += 1
                            break
                    schedule[day][slot] = assigned_teacher

            return {
                "status":        "SUCCESS",
                "solver_status": status_name,
                "schedule":      schedule,
                "stats": {
                    "total_assigned_slots": total_assigned,
                    "wall_time_seconds":    wall_time,
                    "constraints_applied":  len(constraints) - skipped,
                    "constraints_skipped":  skipped,
                },
            }

        # INFEASIBLE / UNKNOWN
        return {
            "status":        "INFEASIBLE",
            "solver_status": status_name,
            "schedule":      {},
            "stats": {
                "total_assigned_slots": 0,
                "wall_time_seconds":    wall_time,
                "constraints_applied":  len(constraints) - skipped,
                "constraints_skipped":  skipped,
            },
            "detail": (
                "No valid schedule exists that satisfies all hard constraints. "
                "Check for conflicting 'required' or over-restrictive 'unavailable' rules."
            ),
        }
