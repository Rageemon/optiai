"""
Routing Solver — Placeholder
Reserved for future graph-based routing algorithms (e.g. Vehicle Routing
Problem, Shortest Path, Travelling Salesman) using OR-Tools' routing library.

To add routing support:
    1. Define ``RoutingConstraint`` in ``app/models/schemas.py``.
    2. Implement ``solve()`` using ``ortools.constraint_solver.routing_enums_pb2``
       and ``ortools.constraint_solver.pywraprouting``.
    3. Register the solver in ``app/core/dispatcher.py``.
"""

from typing import Any, Dict, List

from app.models.schemas import SchedulingConstraint
from app.solvers.base_solver import OptimizationSolver


class RoutingSolver(OptimizationSolver):
    """Stub — raises ``NotImplementedError`` until the domain is built out."""

    def solve(self, constraints: List[SchedulingConstraint]) -> Dict[str, Any]:
        raise NotImplementedError(
            "RoutingSolver is not yet implemented. "
            "This solver is reserved for a future sprint."
        )
