"""
Dispatcher
==========
Routes requests to the correct domain-specific solver.

Two public functions
--------------------
execute_optimization(extraction_result)  — legacy LLM-extraction path
execute_solve(algo_id, inputs)           — new structured-input path (POST /api/solve)

Adding a new solver
-------------------
1. Create a solver module under ``app/solvers/scheduling/`` (or another domain).
2. Add a branch in ``execute_solve`` below.
3. Register the algorithm in ``algo_context.py``.
"""

import logging
from typing import Any, Dict

from fastapi import HTTPException

from app.models.schemas import LLMExtractionResult, ProblemDomain
from app.solvers.scheduling_solver import SchedulingSolver
from app.solvers.scheduling.job_shop  import solve_job_shop
from app.solvers.scheduling.workforce import solve_shift_scheduling, solve_nurse_rostering
from app.solvers.scheduling.timetable import solve_timetable, find_substitutes
from app.solvers.scheduling.project   import solve_rcpsp
from app.solvers.routing import (
    solve_tsp,
    solve_vrp,
    solve_cvrp,
    solve_vrptw,
    solve_pdp,
)
from app.solvers.packing import (
    solve_knapsack,
    solve_bin_packing,
    solve_cutting_stock,
)
from app.solvers.map_routing import solve_map_routing

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# New path: structured inputs (POST /api/solve)
# ---------------------------------------------------------------------------

def execute_solve(algo_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatch a structured solve request to the right solver.

    Parameters
    ----------
    algo_id : str    — matches ALGO_BY_ID keys in algo_context.py
    inputs  : dict   — validated JSON payload from the frontend form

    Returns
    -------
    dict — solver result payload
    """
    logger.info("execute_solve: algo_id=%s", algo_id)

    if algo_id == "scheduling_jssp":
        return solve_job_shop(inputs)

    if algo_id == "scheduling_shift":
        return solve_shift_scheduling(inputs)

    if algo_id == "scheduling_nurse":
        return solve_nurse_rostering(inputs)

    if algo_id == "scheduling_timetable":
        return solve_timetable(inputs)

    if algo_id == "scheduling_rcpsp":
        return solve_rcpsp(inputs)

    if algo_id == "routing_tsp":
        return solve_tsp(inputs)

    if algo_id == "routing_vrp":
        return solve_vrp(inputs)

    if algo_id == "routing_cvrp":
        return solve_cvrp(inputs)

    if algo_id == "routing_vrptw":
        return solve_vrptw(inputs)

    if algo_id == "routing_pdp":
        return solve_pdp(inputs)

    # Packing & Knapsack solvers
    if algo_id == "packing_knapsack":
        return solve_knapsack(inputs)

    if algo_id == "packing_binpacking":
        return solve_bin_packing(inputs)

    if algo_id == "packing_cuttingstock":
        return solve_cutting_stock(inputs)

    # Map Routing solvers
    if algo_id == "map_routing_multiobjective":
        return solve_map_routing(inputs)

    # Substitute lookup (not a solver — utility endpoint)
    if algo_id == "scheduling_timetable_substitute":
        timetable_result = inputs.get("timetable_result", {})
        absent_teacher   = inputs.get("absent_teacher", "")
        absent_day       = inputs.get("absent_day", "")
        teachers_data    = inputs.get("teachers_data", [])
        return find_substitutes(timetable_result, absent_teacher, absent_day, teachers_data)

    raise HTTPException(
        status_code=501,
        detail=f"Solver for '{algo_id}' is not yet implemented.",
    )


# ---------------------------------------------------------------------------
# Legacy path: LLM-extraction → solver (kept for /api/optimize compatibility)
# ---------------------------------------------------------------------------

def execute_optimization(extraction_result: LLMExtractionResult) -> Dict[str, Any]:
    """
    Instantiate the appropriate solver for the detected domain and execute it.

    Parameters
    ----------
    extraction_result : LLMExtractionResult
        The fully-validated output of the LLM extraction service, containing
        both the ``domain`` classification and the list of ``constraints``.

    Returns
    -------
    dict
        The solver's result payload, which at minimum contains ``"status"``
        and ``"schedule"`` keys (for the SCHEDULING domain).

    Raises
    ------
    HTTPException(501)
        If the detected domain maps to a solver that is not yet implemented.
    HTTPException(400)
        If the domain value is unrecognised (should not occur given enum
        validation, but included as a defensive guard).
    """
    domain = extraction_result.domain
    logger.info("Dispatcher received domain=%s with %d constraint(s).",
                domain, len(extraction_result.constraints))

    # ------------------------------------------------------------------ #
    # SCHEDULING — fully implemented                                       #
    # ------------------------------------------------------------------ #
    if domain == ProblemDomain.SCHEDULING:
        solver = SchedulingSolver()
        logger.info("Dispatching to SchedulingSolver …")
        return solver.solve(extraction_result.constraints)

    # ------------------------------------------------------------------ #
    # ROUTING & ASSIGNMENT — stubs (future sprints)                        #
    # ------------------------------------------------------------------ #
    if domain in (ProblemDomain.ROUTING, ProblemDomain.ASSIGNMENT):
        raise HTTPException(
            status_code=501,
            detail=(
                f"The '{domain.value}' solver has not been implemented yet. "
                "This domain is planned for a future release. "
                "Only SCHEDULING is supported in this MVP."
            ),
        )

    # Defensive fallback — unreachable with current Pydantic enum validation
    raise HTTPException(
        status_code=400,
        detail=f"Unknown optimization domain: '{domain}'. "
               f"Valid domains are: {[d.value for d in ProblemDomain]}.",
    )
