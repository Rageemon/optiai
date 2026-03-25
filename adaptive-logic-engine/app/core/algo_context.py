"""
Algorithm Registry — algo_context.py
Single source of truth describing every algorithm the engine can run.

This file is read by the LLM service and sent to Gemini so it can answer:
  "Does any algorithm here solve the user's problem?"

To add a new algorithm:
  1. Add an entry to ALGORITHM_REGISTRY below.
  2. Implement the solver in app/solvers/.
  3. Register the solver id in app/core/dispatcher.py.

Data contract per algorithm
---------------------------
id            : str   — snake_case unique key, used as URL slug (/solve/{id})
name          : str   — Human-readable name
domain        : str   — High-level category shown to the user
description   : str   — 2-3 sentence plain-English explanation
capabilities  : list  — What kinds of problems it solves (bullet points for the UI)
variables     : dict  — Decision variables the user must supply as inputs
constraints   : list  — Constraint types the solver understands
objective     : str   — What the solver optimises for
limitations   : list  — Known hard limits / things it cannot do
input_schema  : dict  — JSON schema fragment driving the dynamic input form
"""

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALGORITHM_REGISTRY: List[Dict[str, Any]] = [

    # ==================================================================
    # A. MACHINE & PRODUCTION SCHEDULING
    # ==================================================================

    # ------------------------------------------------------------------
    # A1. Job Shop / Flow Shop / Parallel Machine Scheduling
    # ------------------------------------------------------------------
    {
        "id": "scheduling_jssp",
        "name": "Job Shop & Machine Scheduling Solver",
        "domain": "Machine & Production Scheduling",
        "description": (
            "Schedules jobs on machines to minimise makespan (total completion time) "
            "or weighted tardiness. Handles Job Shop (each job has its own machine "
            "sequence), Flow Shop (all jobs share the same machine order), and "
            "Parallel Machine (independent tasks on multiple identical/heterogeneous "
            "machines). Uses CP-SAT NoOverlap interval constraints."
        ),
        "capabilities": [
            "Job Shop Scheduling Problem (JSSP) — unique machine sequences per job",
            "Flow Shop Scheduling Problem (FSSP) — same machine order for all jobs",
            "Parallel machine scheduling — independent tasks, multiple machines",
            "Weighted tardiness minimisation with due dates and job priorities",
            "Machine utilisation analysis and Gantt chart output",
            "Parallel (identical or heterogeneous) machine capacity support",
        ],
        "variables": {
            "jobs":     "List of jobs, each with an ordered list of (machine, duration) tasks",
            "machines": "Optional machine list; auto-detected from jobs if omitted",
            "objective": "'makespan' (default) or 'weighted_tardiness'",
            "horizon":   "Maximum time horizon (auto-computed if not given)",
        },
        "constraints": [
            "no_overlap       — two tasks cannot run on the same machine simultaneously",
            "precedence       — tasks within a job must run in their defined order",
            "due_date         — job must finish by deadline (soft or hard)",
            "machine_count    — parallel: set count > 1 for identical machine copies",
        ],
        "objective": "Minimise makespan (default) or weighted sum of job tardiness",
        "limitations": [
            "Preemption not supported (tasks run to completion once started)",
            "Setup times between tasks not yet modelled",
            "Very large instances (>50 jobs × 20 machines) may time out",
        ],
        "input_schema": {
            "problem_type": {"type": "string", "enum": ["jssp", "fssp", "parallel"]},
            "objective":    {"type": "string", "enum": ["makespan", "weighted_tardiness"]},
            "jobs": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name":     {"type": "string"},
                    "priority": {"type": "integer"},
                    "due_date": {"type": ["integer", "null"]},
                    "tasks":    {"type": "array", "items": {
                        "type": "object",
                        "properties": {
                            "machine":  {"type": "string"},
                            "duration": {"type": "integer"},
                        },
                    }},
                },
            }},
            "machines": {"type": "array", "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "count": {"type": "integer"}},
            }},
        },
    },

    # ==================================================================
    # B. PERSONNEL & WORKFORCE SCHEDULING
    # ==================================================================

    # ------------------------------------------------------------------
    # B1. Employee Shift Scheduling
    # ------------------------------------------------------------------
    {
        "id": "scheduling_shift",
        "name": "Employee Shift Scheduling Solver",
        "domain": "Personnel & Workforce Scheduling",
        "description": (
            "Assigns employees to working shifts over a scheduling horizon (days). "
            "Enforces legal rest periods between shifts, maximum consecutive working "
            "days, coverage requirements per shift, and respects employee hard "
            "unavailability and soft preferences. Uses CP-SAT Boolean assignment variables."
        ),
        "capabilities": [
            "Weekly or monthly employee shift scheduling",
            "Multiple shift types (Morning, Afternoon, Night, etc.)",
            "Minimum staffing coverage requirements per shift per day",
            "Minimum rest period between consecutive shifts",
            "Maximum consecutive working days constraint",
            "Employee preferred-shift and day-off request handling (soft)",
            "Min/max working hours per week per employee",
        ],
        "variables": {
            "employees": "List of employees with skills, hours constraints, preferences",
            "shifts":    "Shift definitions with start/end hours and required headcount",
            "days":      "Scheduling horizon (list of day names, default Mon–Sun)",
        },
        "constraints": [
            "min_rest_hours         — minimum gap between any two shifts (default 8h)",
            "max_consecutive_days   — max working days in a row (default 5)",
            "required_count         — minimum workers per shift per day",
            "max_shifts_per_week    — upper bound on shifts assigned to one employee",
            "requested_days_off     — soft: avoid scheduling on these days",
            "preferred_shifts       — soft: prefer these shift types when possible",
        ],
        "objective": "Maximise preference satisfaction while meeting all coverage requirements",
        "limitations": [
            "Does not model intra-shift breaks or meal periods",
            "Skill-level matching requires separately using nurse rostering variant",
            "Maximum practical scale: ~100 employees × 7 days × 5 shift types",
        ],
        "input_schema": {
            "employees": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "max_shifts_per_week": {"type": "integer"},
                    "max_hours_per_week":  {"type": "number"},
                    "min_hours_per_week":  {"type": "number"},
                    "requested_days_off":  {"type": "array", "items": {"type": "string"}},
                    "preferred_shifts":    {"type": "array", "items": {"type": "string"}},
                },
            }},
            "shifts": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name":           {"type": "string"},
                    "start_hour":     {"type": "number"},
                    "end_hour":       {"type": "number"},
                    "days":           {"type": "array", "items": {"type": "string"}},
                    "required_count": {"type": "integer"},
                },
            }},
            "days":                 {"type": "array", "items": {"type": "string"}},
            "min_rest_hours":       {"type": "number"},
            "max_consecutive_days": {"type": "integer"},
        },
    },

    # ------------------------------------------------------------------
    # B2. Nurse Rostering
    # ------------------------------------------------------------------
    {
        "id": "scheduling_nurse",
        "name": "Nurse Rostering Solver",
        "domain": "Personnel & Workforce Scheduling",
        "description": (
            "Specialised shift scheduling for healthcare settings. Extends basic shift "
            "scheduling with skill-level coverage (e.g. 1 head nurse + 2 trainees per "
            "shift), maximum consecutive night shifts, fatigue tracking, and strict "
            "fairness in workload distribution across nursing staff."
        ),
        "capabilities": [
            "Multi-skill-level staffing requirements (head nurse, trainee, specialist)",
            "Consecutive night shift limits",
            "Workload fairness across all nurses",
            "Request-off and preferred-pattern support",
            "All features of employee shift scheduling",
        ],
        "variables": {
            "nurses":  "List of nurses with skill levels (head, trainee)", 
            "shifts":  "Shift definitions including required skill counts",
            "days":    "Rostering horizon",
        },
        "constraints": [
            "required_skills   — {skill: count} minimum per shift per day",
            "max_night_shifts  — max consecutive night shifts (default 3)",
            "All constraints from employee shift scheduling apply",
        ],
        "objective": "Meet all skill-level requirements while maximising staff preferences",
        "limitations": [
            "Long rostering horizons (>30 days) may require reducing nurse count",
            "Does not model floating nurses across departments",
        ],
        "input_schema": {
            "employees": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name":   {"type": "string"},
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "max_shifts_per_week": {"type": "integer"},
                },
            }},
            "shifts": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name":            {"type": "string"},
                    "start_hour":      {"type": "number"},
                    "end_hour":        {"type": "number"},
                    "required_count":  {"type": "integer"},
                    "required_skills": {
                        "type": "object",
                        "additionalProperties": {"type": "integer"},
                    },
                },
            }},
        },
    },

    # ==================================================================
    # C. EDUCATIONAL TIMETABLING
    # ==================================================================
    {
        "id": "scheduling_timetable",
        "name": "Educational Timetabling Solver",
        "domain": "Timetabling",
        "description": (
            "Generates a conflict-free weekly school or university timetable. "
            "Handles any number of classes (e.g. 1-A through 10-D), teachers with "
            "subject qualifications and hard unavailability, merged/combined lectures "
            "for multiple classes, room assignment by capacity, consecutive-period "
            "requirements for lab sessions, and a substitute-teacher lookup tool for "
            "absent staff. Uses CP-SAT Boolean assignment variables."
        ),
        "capabilities": [
            "Any number of classes and divisions (1-A, 1-B … 10-D etc.)",
            "Teacher qualification matching (teacher only teaches their subjects)",
            "Hard teacher unavailability and soft preferred-slot support",
            "Merged/combined lectures — multiple classes in one room with one teacher",
            "Lab subjects requiring back-to-back consecutive periods",
            "Room assignment by student headcount and room capacity",
            "Teacher maximum hours per week enforcement",
            "Substitute teacher lookup when someone is absent",
            "Class view and teacher view output for the full week",
            "Sports scheduling (rooms as courts, teachers as referees)",
        ],
        "variables": {
            "teachers":     "Names, subject qualifications, max hours, unavailability",
            "classes":      "Class IDs (e.g. '10-A') and student headcount",
            "subjects":     "Subject names, periods/week/class, consecutive flag, merge groups",
            "rooms":        "Room names and capacities (optional but recommended)",
            "time_config":  "Days list and slots_per_day",
        },
        "constraints": [
            "teacher_unavailable   — hard block on specific day/slot for a teacher",
            "no_teacher_clash      — teacher cannot be in two places at once",
            "no_class_clash        — class cannot have two lessons simultaneously",
            "subject_coverage      — each class must get required periods of each subject",
            "teacher_max_load      — total periods cannot exceed teacher's weekly limit",
            "room_capacity         — room must fit all students in the class",
            "consecutive_periods   — lab/double periods must appear back-to-back",
            "merged_lecture        — specified classes share a teacher in one time slot",
        ],
        "objective": "Maximise teacher preference satisfaction while meeting all hard constraints",
        "limitations": [
            "Very large schools (>40 classes, >50 teachers) may time out at 60s",
            "Does not model student-elective groupings across streams",
            "Sports scheduling: travel time between venues not modelled",
        ],
        "input_schema": {
            "teachers": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name":                   {"type": "string"},
                    "subjects":               {"type": "array", "items": {"type": "string"}},
                    "max_periods_per_week":   {"type": "integer"},
                    "unavailable": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"day": {"type": "string"}, "slot": {"type": "integer"}},
                    }},
                    "preferred_slots": {"type": "array", "items": {
                        "type": "object",
                        "properties": {"day": {"type": "string"}, "slot": {"type": "integer"}},
                    }},
                },
            }},
            "classes": {"type": "array", "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "strength": {"type": "integer"}},
            }},
            "subjects": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name":                       {"type": "string"},
                    "periods_per_week_per_class":  {"type": "integer"},
                    "consecutive":                {"type": "boolean"},
                    "mergeable_groups":           {"type": "array", "items": {
                        "type": "array", "items": {"type": "string"},
                    }},
                },
            }},
            "rooms": {"type": "array", "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "capacity": {"type": "integer"}},
            }},
            "time_config": {
                "type": "object",
                "properties": {
                    "days":          {"type": "array", "items": {"type": "string"}},
                    "slots_per_day": {"type": "integer"},
                },
            },
        },
    },

    # ==================================================================
    # D. PROJECT MANAGEMENT (RCPSP)
    # ==================================================================
    {
        "id": "scheduling_rcpsp",
        "name": "Resource-Constrained Project Scheduling (RCPSP)",
        "domain": "Project Management",
        "description": (
            "Schedules project activities with precedence dependencies and limited "
            "renewable resources to minimise total project duration (makespan). "
            "Uses CP-SAT cumulative resource constraints — the gold standard for "
            "construction projects, software releases, event planning, and any "
            "task-network with shared resource pools."
        ),
        "capabilities": [
            "Precedence / dependency constraints (A must finish before B starts)",
            "Multiple renewable resource types with simultaneous capacity limits",
            "Optional time windows per activity (earliest start, latest finish)",
            "Critical path identification",
            "Resource usage profile over time",
            "Project duration minimisation under resource contention",
        ],
        "variables": {
            "activities": "List of tasks with duration, predecessor names, and resource demands",
            "resources":  "Global renewable resource pools with max capacities",
        },
        "constraints": [
            "precedence        — activity ordering (finish-to-start)",
            "resource_capacity — total units of each resource at any time ≤ capacity",
            "time_window       — earliest_start and latest_finish per activity",
        ],
        "objective": "Minimise project makespan (critical path with resource contention)",
        "limitations": [
            "Non-renewable resources (budget, materials) not yet modelled",
            "Multiple project portfolios require manual horizon adjustment",
            "Max practical scale: ~200 activities, 10 resource types",
        ],
        "input_schema": {
            "activities": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name":           {"type": "string"},
                    "duration":       {"type": "integer"},
                    "predecessors":   {"type": "array", "items": {"type": "string"}},
                    "resources":      {"type": "object", "additionalProperties": {"type": "integer"}},
                    "earliest_start": {"type": ["integer", "null"]},
                    "latest_finish":  {"type": ["integer", "null"]},
                },
            }},
            "resources": {"type": "array", "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "capacity": {"type": "integer"}},
            }},
        },
    },

    # ------------------------------------------------------------------
    # 2. ROUTING (Node-routing with OR-Tools)
    # ------------------------------------------------------------------
    {
        "id": "routing_tsp",
        "name": "Traveling Salesperson Problem (TSP)",
        "domain": "Routing",
        "description": (
            "Single-vehicle closed tour that starts at a depot, visits every node "
            "exactly once, and returns to the depot while minimising total travel cost."
        ),
        "capabilities": [
            "Single-vehicle shortest closed tour",
            "Exact depot control",
            "Distance-matrix based optimization",
        ],
        "variables": {
            "distance_matrix": "NxN travel matrix (distance/time/cost)",
            "depot": "Start/end node index",
        },
        "constraints": [
            "visit_once — every non-depot node visited exactly once",
            "single_vehicle — one route only",
            "return_to_depot — tour ends at origin",
        ],
        "objective": "Minimise total tour cost",
        "limitations": [
            "Assumes static matrix (no live traffic updates)",
            "Performance depends on matrix size and time limit",
        ],
        "input_schema": {
            "distance_matrix": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
            "depot": {"type": "integer"},
            "time_limit_seconds": {"type": "integer"},
        },
    },
    {
        "id": "routing_vrp",
        "name": "Vehicle Routing Problem (VRP)",
        "domain": "Routing",
        "description": (
            "Multi-vehicle extension of TSP where a fleet serves all nodes from a central depot."
        ),
        "capabilities": [
            "Fleet routing from one depot",
            "Automatic customer allocation to vehicles",
            "Optional max route distance per vehicle",
        ],
        "variables": {
            "distance_matrix": "NxN travel matrix",
            "num_vehicles": "Number of vehicles",
            "depot": "Common depot index",
            "max_route_distance": "Optional upper bound per vehicle route",
        },
        "constraints": [
            "visit_once — each node visited exactly once",
            "fleet_size — fixed number of vehicles",
            "route_distance_cap — optional per-vehicle distance limit",
        ],
        "objective": "Minimise aggregate fleet travel cost",
        "limitations": [
            "Single depot in this version",
            "No per-vehicle heterogenous costs in this base variant",
        ],
        "input_schema": {
            "distance_matrix": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
            "num_vehicles": {"type": "integer"},
            "depot": {"type": "integer"},
            "max_route_distance": {"type": "integer"},
            "time_limit_seconds": {"type": "integer"},
        },
    },
    {
        "id": "routing_cvrp",
        "name": "Capacitated Vehicle Routing Problem (CVRP)",
        "domain": "Routing",
        "description": (
            "VRP with vehicle capacity constraints where each node has demand and "
            "route load must never exceed vehicle capacity."
        ),
        "capabilities": [
            "Per-node demand handling",
            "Per-vehicle capacity limits",
            "Load-aware routing and assignment",
        ],
        "variables": {
            "distance_matrix": "NxN travel matrix",
            "demands": "Demand per node (depot usually 0)",
            "vehicle_capacities": "Capacity for each vehicle",
            "num_vehicles": "Fleet size",
            "depot": "Depot index",
        },
        "constraints": [
            "capacity — cumulative load per route <= vehicle capacity",
            "visit_once — each customer served once",
            "fleet_size — fixed number of routes",
        ],
        "objective": "Minimise travel cost while satisfying capacity",
        "limitations": [
            "Single commodity demand",
            "Single depot in this version",
        ],
        "input_schema": {
            "distance_matrix": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
            "demands": {"type": "array", "items": {"type": "integer"}},
            "vehicle_capacities": {"type": "array", "items": {"type": "integer"}},
            "num_vehicles": {"type": "integer"},
            "depot": {"type": "integer"},
            "time_limit_seconds": {"type": "integer"},
        },
    },
    {
        "id": "routing_vrptw",
        "name": "Vehicle Routing Problem with Time Windows (VRPTW)",
        "domain": "Routing",
        "description": (
            "VRP with per-node service time windows. Vehicles must arrive within "
            "allowed intervals while minimizing total route time/cost."
        ),
        "capabilities": [
            "Per-location earliest/latest service windows",
            "Waiting-time aware routing",
            "Service-time aware travel",
        ],
        "variables": {
            "time_matrix": "NxN travel-time matrix",
            "time_windows": "[start,end] window per node",
            "service_times": "Service duration per node",
            "num_vehicles": "Fleet size",
            "depot": "Depot index",
        },
        "constraints": [
            "time_window — serve each node inside its window",
            "max_waiting_time — bound idle waiting",
            "max_time_per_vehicle — horizon limit per route",
        ],
        "objective": "Minimise route time while respecting all windows",
        "limitations": [
            "Single depot in this version",
            "No break scheduling in this variant",
        ],
        "input_schema": {
            "time_matrix": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
            "time_windows": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
            "service_times": {"type": "array", "items": {"type": "integer"}},
            "num_vehicles": {"type": "integer"},
            "depot": {"type": "integer"},
            "max_waiting_time": {"type": "integer"},
            "max_time_per_vehicle": {"type": "integer"},
            "time_limit_seconds": {"type": "integer"},
        },
    },
    {
        "id": "routing_pdp",
        "name": "Pickup and Delivery Problem (PDP)",
        "domain": "Routing",
        "description": (
            "Handles pickup-delivery pairs with precedence (pickup before drop), "
            "same-vehicle coupling, and capacity limits."
        ),
        "capabilities": [
            "Pickup-before-delivery precedence",
            "Same-vehicle pickup and drop coupling",
            "Capacity-aware paired transportation",
        ],
        "variables": {
            "distance_matrix": "NxN travel matrix",
            "pickup_delivery_pairs": "List of [pickup_index, delivery_index] pairs",
            "demands": "Signed node demands (pickup positive, delivery negative)",
            "vehicle_capacities": "Per-vehicle capacities",
            "num_vehicles": "Fleet size",
            "depot": "Depot index",
        },
        "constraints": [
            "pickup_before_delivery — precedence for each pair",
            "same_vehicle_pair — pickup and delivery done by same vehicle",
            "capacity — route load bounds across full trip",
        ],
        "objective": "Minimise total route cost while honoring pair constraints",
        "limitations": [
            "Single depot in this version",
            "No explicit rider ride-time constraints yet",
        ],
        "input_schema": {
            "distance_matrix": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
            "pickup_delivery_pairs": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}},
            "demands": {"type": "array", "items": {"type": "integer"}},
            "vehicle_capacities": {"type": "array", "items": {"type": "integer"}},
            "num_vehicles": {"type": "integer"},
            "depot": {"type": "integer"},
            "time_limit_seconds": {"type": "integer"},
        },
    },

    # ==================================================================
    # E. PACKING & KNAPSACK PROBLEMS
    # ==================================================================

    # ------------------------------------------------------------------
    # E1. Knapsack Problem
    # ------------------------------------------------------------------
    {
        "id": "packing_knapsack",
        "name": "Knapsack Problem Solver",
        "domain": "Packing & Knapsack",
        "description": (
            "Selects items to maximize total value while staying within capacity constraints. "
            "Handles 0-1 knapsack (take or leave each item), bounded knapsack (limited quantity "
            "per item), unbounded knapsack (unlimited copies), multiple knapsack (multiple "
            "containers), and multi-dimensional knapsack (weight + volume constraints). "
            "Uses CP-SAT for optimal or near-optimal solutions."
        ),
        "capabilities": [
            "0-1 Knapsack — take or leave each unique item",
            "Bounded Knapsack — limited quantity of each item type available",
            "Unbounded Knapsack — unlimited copies of each item type",
            "Multiple Knapsack — assign items to multiple bags/containers",
            "Multi-dimensional Knapsack — multiple resource constraints (weight, volume, etc.)",
            "Budget optimization, investment selection, resource allocation",
        ],
        "variables": {
            "items": "List of items with name, value, weight, and optional quantity/dimensions",
            "capacity": "Total capacity of knapsack (for single knapsack problems)",
            "capacities": "List of capacities (for multiple knapsack)",
            "dimension_capacities": "Dict of resource_name → capacity (for multi-dimensional)",
            "problem_type": "'0-1', 'bounded', 'unbounded', 'multiple', or 'multidimensional'",
        },
        "constraints": [
            "capacity — total weight/size of selected items ≤ knapsack capacity",
            "quantity — respect available quantity per item (bounded knapsack)",
            "assignment — each item assigned to at most one knapsack (multiple knapsack)",
            "multi_dim — all dimension constraints satisfied simultaneously",
        ],
        "objective": "Maximize total value of selected items within capacity limits",
        "limitations": [
            "Very large instances (>1000 items) may require longer solve times",
            "Fractional selection not supported (use LP for continuous relaxation)",
            "All values and weights must be non-negative integers",
        ],
        "input_schema": {
            "problem_type": {"type": "string", "enum": ["0-1", "bounded", "unbounded", "multiple", "multidimensional"]},
            "items": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "integer"},
                    "weight": {"type": "integer"},
                    "quantity": {"type": "integer"},
                    "dimensions": {"type": "object", "additionalProperties": {"type": "integer"}},
                },
            }},
            "capacity": {"type": "integer"},
            "capacities": {"type": "array", "items": {"type": "integer"}},
            "dimension_capacities": {"type": "object", "additionalProperties": {"type": "integer"}},
            "time_limit_seconds": {"type": "integer"},
        },
    },

    # ------------------------------------------------------------------
    # E2. Bin Packing Problem
    # ------------------------------------------------------------------
    {
        "id": "packing_binpacking",
        "name": "Bin Packing Problem Solver",
        "domain": "Packing & Knapsack",
        "description": (
            "Packs ALL items into the minimum number of bins (containers). Unlike knapsack, "
            "every item MUST be packed — the goal is minimizing containers used. Handles "
            "1D bin packing (by weight/size), 2D bin packing (rectangular items on sheets), "
            "3D bin packing (boxes in containers), and variable bin packing (different bin "
            "types with different costs). Uses CP-SAT with symmetry-breaking for efficiency."
        ),
        "capabilities": [
            "1D Bin Packing — pack items by single dimension (weight, length, size)",
            "2D Bin Packing — pack rectangles with rotation support",
            "3D Bin Packing — pack boxes into containers (volume-based)",
            "Variable Bin Packing — multiple bin types with different sizes and costs",
            "File backup to disks, pallet loading, container loading, memory allocation",
        ],
        "variables": {
            "items": "List of items with size (1D) or width/height/depth (2D/3D)",
            "bin_capacity": "Single bin capacity (1D)",
            "bin_width/bin_height/bin_depth": "Bin dimensions (2D/3D)",
            "bin_types": "List of bin types with capacity, cost, available quantity",
            "problem_type": "'1d', '2d', '3d', or 'variable'",
        },
        "constraints": [
            "bin_capacity — sum of item sizes in each bin ≤ bin capacity",
            "no_overlap — 2D/3D items cannot overlap within a bin",
            "all_packed — every item must be assigned to exactly one bin",
            "bin_available — cannot use more bins than available (variable)",
        ],
        "objective": "Minimize number of bins used (or total cost for variable bins)",
        "limitations": [
            "2D packing with many small items (>50) may have longer solve times",
            "3D packing uses volume-based approximation for feasibility",
            "Items must fit in at least one bin type",
        ],
        "input_schema": {
            "problem_type": {"type": "string", "enum": ["1d", "2d", "3d", "variable"]},
            "items": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "size": {"type": "integer"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "depth": {"type": "integer"},
                    "quantity": {"type": "integer"},
                    "can_rotate": {"type": "boolean"},
                },
            }},
            "bin_capacity": {"type": "integer"},
            "bin_width": {"type": "integer"},
            "bin_height": {"type": "integer"},
            "bin_depth": {"type": "integer"},
            "bin_types": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "capacity": {"type": "integer"},
                    "cost": {"type": "integer"},
                    "available": {"type": "integer"},
                },
            }},
            "max_bins": {"type": "integer"},
            "time_limit_seconds": {"type": "integer"},
        },
    },

    # ------------------------------------------------------------------
    # E3. Cutting Stock Problem
    # ------------------------------------------------------------------
    {
        "id": "packing_cuttingstock",
        "name": "Cutting Stock Problem Solver",
        "domain": "Packing & Knapsack",
        "description": (
            "Cuts standard-sized raw materials (stock) to fulfill orders for specific piece "
            "sizes while minimizing waste or cost. Essential for manufacturing: cutting steel "
            "rods, paper rolls, wooden beams, fabric, glass sheets. Handles single stock size "
            "and multi-stock (different stock lengths with different costs). Uses CP-SAT for "
            "optimal cutting patterns."
        ),
        "capabilities": [
            "1D Cutting Stock — cut linear stock (rods, rolls, beams) into ordered pieces",
            "Multi-Stock Cutting — multiple stock sizes with different costs",
            "Order fulfillment — produce exact quantities of each ordered piece size",
            "Waste minimization — minimize leftover scrap material",
            "Steel cutting, paper roll cutting, lumber cutting, pipe cutting",
        ],
        "variables": {
            "orders": "List of orders with piece length and required quantity",
            "stock_length": "Length of raw stock material (single stock)",
            "stock_types": "List of stock types with length, cost, available quantity",
            "problem_type": "'1d' or 'multi-stock'",
        },
        "constraints": [
            "stock_length — sum of cut pieces ≤ stock length",
            "order_fulfillment — produce at least requested quantity of each piece",
            "piece_validity — each piece length ≤ stock length",
            "stock_available — cannot use more stock than available",
        ],
        "objective": "Minimize number of stock units used (or total cost for multi-stock)",
        "limitations": [
            "Assumes 1D cutting (kerf/blade width not modeled)",
            "All piece lengths must be positive integers ≤ stock length",
            "Large orders (>500 pieces) may require longer solve times",
        ],
        "input_schema": {
            "problem_type": {"type": "string", "enum": ["1d", "multi-stock"]},
            "orders": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "length": {"type": "integer"},
                    "quantity": {"type": "integer"},
                },
            }},
            "stock_length": {"type": "integer"},
            "stock_types": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "length": {"type": "integer"},
                    "cost": {"type": "integer"},
                    "available": {"type": "integer"},
                },
            }},
            "max_stocks": {"type": "integer"},
            "time_limit_seconds": {"type": "integer"},
        },
    },

    # ------------------------------------------------------------------
    # 3. Task / Resource Assignment (planned)
    # ------------------------------------------------------------------
    {
        "id": "assignment",
        "name": "Task Assignment Solver",
        "domain": "Resource Assignment",
        "description": (
            "Optimally assigns workers, machines, or agents to tasks/projects "
            "minimising total cost or maximising total utility. Solves the classic "
            "Hungarian-algorithm-style linear assignment problem and its variants "
            "using OR-Tools linear solver."
        ),
        "capabilities": [
            "Project-to-team assignment",
            "Job-shop machine scheduling",
            "PCB component placement optimisation",
            "Supply chain demand allocation",
            "Any one-to-one or many-to-many matching problem",
        ],
        "variables": {
            "agents":   "Workers, machines, or resources",
            "tasks":    "Jobs, projects, or demand nodes",
            "cost_matrix": "Agent × Task cost/benefit matrix",
        },
        "constraints": [
            "one_to_one   — each agent handles at most one task",
            "capacity     — agent can handle up to N tasks",
            "skill_match  — agent can only be assigned to compatible tasks",
            "budget       — total cost must not exceed a given budget",
        ],
        "objective": "Minimise total assignment cost (or maximise total utility)",
        "limitations": [
            "Requires a cost/utility matrix",
            "Does not model multi-stage pipelines natively",
        ],
        "input_schema": {
            "agents":       {"type": "array", "items": {"type": "string"}},
            "tasks":        {"type": "array", "items": {"type": "string"}},
            "cost_matrix":  {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
        },
        "status": "planned",
    },

    # -----------------------------------------------------------------------
    # F. MAP ROUTING — Multi-Objective Real-World Navigation
    # -----------------------------------------------------------------------
    {
        "id": "map_routing_multiobjective",
        "name": "Multi-Objective Map Routing",
        "domain": "map_routing",
        "description": (
            "Real-world route planning on OpenStreetMap data that balances multiple objectives "
            "simultaneously — e.g. shortest path vs. passing through restaurant-dense streets. "
            "Uses a dynamic cost function: road segments near your desired POIs are made "
            "artificially 'cheaper', so the pathfinder naturally routes through those areas. "
            "Powered by OSMnx + NetworkX. No API key required."
        ),
        "capabilities": [
            "Route between any two real-world addresses or coordinates",
            "Multi-objective: balance distance against POI density (restaurants, cafes, parks, etc.)",
            "Real OpenStreetMap street network — drive, walk, or bike modes",
            "Returns optimised route + pure-distance baseline for comparison",
            "Shows all POIs along the chosen route",
            "Clickable map: set start/end points directly",
        ],
        "variables": {
            "poi_preferences":  "Dict of per-POI-type weights (0–1), e.g. {'restaurant': 0.9, 'cafe': 0.4}",
            "distance_weight":  "How much to penalise longer roads (0 = ignore distance, 1 = shortest only)",
            "network_type":     "Travel mode: 'drive' | 'walk' | 'bike'",
            "avoid_highways":   "Exclude motorways and trunk roads (true/false)",
            "search_radius_m":  "POI attraction radius around each road segment in metres",
            "start_address":    "Origin address or place name",
            "end_address":      "Destination address or place name",
        },
        "constraints": [
            "Start and end must be reachable within the same road network",
            "Both points must be within the same bounding box download area",
            "Each POI type weight must be between 0.0 and 1.0",
        ],
        "objective": (
            "Find the path from start to end that minimises the custom edge cost "
            "(weighted sum of road length and POI scarcity)."
        ),
        "limitations": [
            "First solve for a new area downloads OSM data — takes 15–60 seconds; cached afterwards",
            "Works best for intra-city routes (≤ 10 km); very large bounding boxes slow downloads",
            "POI data depends on OpenStreetMap completeness in the area",
            "Rate limited to Nominatim (geocoding) 1 req/s and Overpass (POI) 1 req/2s",
        ],
        "input_schema": {
            "start_address":    {"type": "string",  "description": "Origin address or place name"},
            "end_address":      {"type": "string",  "description": "Destination address or place name"},
            "start_lat":        {"type": "number",  "description": "Origin latitude (overrides start_address)"},
            "start_lng":        {"type": "number",  "description": "Origin longitude (overrides start_address)"},
            "end_lat":          {"type": "number",  "description": "Destination latitude (overrides end_address)"},
            "end_lng":          {"type": "number",  "description": "Destination longitude (overrides end_address)"},
            "poi_preferences":  {"type": "object",  "description": "POI type → weight (0.0–1.0)"},
            "distance_weight":  {"type": "number",  "description": "Distance penalty weight (0.0–1.0, default 0.5)"},
            "avoid_highways":   {"type": "boolean", "description": "Exclude motorways and trunk roads"},
            "network_type":     {"type": "string",  "description": "drive | walk | bike"},
            "search_radius_m":  {"type": "integer", "description": "POI attraction radius in metres (default 100)"},
            "time_limit_seconds": {"type": "integer", "description": "Unused; kept for API consistency"},
        },
        "status": "active",
    },
]

# ---------------------------------------------------------------------------
# Helpers used by the LLM service
# ---------------------------------------------------------------------------

# Quick id → metadata lookup
ALGO_BY_ID: Dict[str, Dict[str, Any]] = {a["id"]: a for a in ALGORITHM_REGISTRY}


def get_algo_summary_for_llm() -> str:
    """
    Return a compact, token-efficient text block describing every algorithm.
    This is injected into the Gemini prompt so it can match the user's problem.
    """
    lines = ["AVAILABLE ALGORITHMS\n" + "=" * 40]
    for algo in ALGORITHM_REGISTRY:
        status = algo.get("status", "available")
        lines.append(
            f"\nID: {algo['id']}  |  STATUS: {status}\n"
            f"Name: {algo['name']}\n"
            f"Domain: {algo['domain']}\n"
            f"Description: {algo['description']}\n"
            f"Capabilities: {', '.join(algo['capabilities'])}\n"
            f"Constraints supported: {', '.join(algo['constraints'])}\n"
            f"Objective: {algo['objective']}\n"
            f"Limitations: {', '.join(algo['limitations'])}"
        )
    lines.append("\n" + "=" * 40)
    return "\n".join(lines)
