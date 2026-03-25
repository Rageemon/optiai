"""
Scheduling Solvers Package
--------------------------
Each module handles one family of scheduling problems using OR-Tools CP-SAT.

Modules
-------
job_shop   — Job Shop / Flow Shop / Parallel Machine Scheduling
workforce  — Employee Shift Scheduling and Nurse Rostering
timetable  — Educational Timetabling (school/university)
project    — Resource-Constrained Project Scheduling (RCPSP)
"""
from .job_shop  import solve_job_shop
from .workforce import solve_shift_scheduling, solve_nurse_rostering
from .timetable import solve_timetable, find_substitutes
from .project   import solve_rcpsp

__all__ = [
    "solve_job_shop",
    "solve_shift_scheduling",
    "solve_nurse_rostering",
    "solve_timetable",
    "find_substitutes",
    "solve_rcpsp",
]
