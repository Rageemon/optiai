"""
Abstract Base Solver — Step 3a
All domain-specific solvers inherit from this class, enforcing a uniform
interface that the dispatcher can rely on regardless of the algorithm used.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from app.models.schemas import SchedulingConstraint


class OptimizationSolver(ABC):
    """
    Abstract contract for every optimization solver in the system.

    Concrete solvers (e.g. ``SchedulingSolver``, ``RoutingSolver``) must
    implement :meth:`solve`, which accepts a list of extracted constraints
    and returns a domain-specific result dictionary.
    """

    @abstractmethod
    def solve(self, constraints: List[SchedulingConstraint]) -> Dict[str, Any]:
        """
        Execute the optimization algorithm against the supplied constraints.

        Parameters
        ----------
        constraints : list[SchedulingConstraint]
            Validated constraints produced by the LLM extraction service.

        Returns
        -------
        dict
            Domain-specific result payload.  Must at minimum contain a
            ``"status"`` key with a value of ``"SUCCESS"`` or ``"INFEASIBLE"``.
        """
        raise NotImplementedError
