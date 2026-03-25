"""
Packing & Knapsack Solvers
==========================
This module provides solvers for packing and knapsack optimization problems.

Solvers:
- Knapsack: Maximize value within capacity constraints (0-1, bounded, unbounded, multiple, multidimensional)
- Bin Packing: Minimize bins needed to pack all items (1D, 2D, 3D, variable)
- Cutting Stock: Minimize waste when cutting stock material to fulfill orders
"""

from app.solvers.packing.knapsack import solve_knapsack
from app.solvers.packing.bin_packing import solve_bin_packing
from app.solvers.packing.cutting_stock import solve_cutting_stock

__all__ = [
    "solve_knapsack",
    "solve_bin_packing",
    "solve_cutting_stock",
]
