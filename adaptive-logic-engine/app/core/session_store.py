"""
Session Store
=============
Thread-safe in-memory session store for the conversational optimization pipeline.

Each session persists:
  - algo_id    : The matched algorithm (str)
  - draft      : The current working form-state dict (mirrors frontend DEFAULT_VALUES format)
  - patch_log  : Ordered list of applied patches for audit / undo

Sessions expire after SESSION_TTL_SECONDS of inactivity (default 1 hour).

DEFAULT_DRAFTS mirrors the frontend DEFAULT_VALUES exactly, including `_id` keys
used for React list key tracking, so the frontend form can hydrate with zero
transformation.
"""

import time
import threading
import random
import string
from typing import Any, Dict, List, Optional

SESSION_TTL_SECONDS = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Default draft starters (mirror frontend DEFAULT_VALUES)
# ---------------------------------------------------------------------------

def _uid() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


DEFAULT_DRAFTS: Dict[str, Dict[str, Any]] = {

    "scheduling_jssp": {
        "problem_type": "jssp",
        "objective": "makespan",
        "machines": [
            {"_id": "m1", "name": "Machine A", "count": 1},
            {"_id": "m2", "name": "Machine B", "count": 1},
            {"_id": "m3", "name": "Machine C", "count": 1},
        ],
        "jobs": [
            {"_id": "j1", "name": "Job 1", "due_date": None, "priority": 1,
             "tasks": [{"_id": "t1", "machine": "Machine A", "duration": 3},
                       {"_id": "t2", "machine": "Machine B", "duration": 2},
                       {"_id": "t3", "machine": "Machine C", "duration": 2}]},
            {"_id": "j2", "name": "Job 2", "due_date": None, "priority": 1,
             "tasks": [{"_id": "t4", "machine": "Machine B", "duration": 3},
                       {"_id": "t5", "machine": "Machine A", "duration": 2},
                       {"_id": "t6", "machine": "Machine C", "duration": 4}]},
            {"_id": "j3", "name": "Job 3", "due_date": None, "priority": 1,
             "tasks": [{"_id": "t7", "machine": "Machine C", "duration": 2},
                       {"_id": "t8", "machine": "Machine A", "duration": 3},
                       {"_id": "t9", "machine": "Machine B", "duration": 3}]},
        ],
    },

    "scheduling_shift": {
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "min_rest_hours": 8,
        "max_consecutive_days": 5,
        "shifts": [
            {"_id": "s1", "name": "Morning", "start_hour": 6,  "end_hour": 14, "required_count": 2, "days": ""},
            {"_id": "s2", "name": "Evening", "start_hour": 14, "end_hour": 22, "required_count": 2, "days": ""},
            {"_id": "s3", "name": "Night",   "start_hour": 22, "end_hour": 30, "required_count": 1, "days": ""},
        ],
        "employees": [
            {"_id": "e1", "name": "Alice",  "skills": "", "max_shifts_per_week": 5, "max_hours_per_week": 40, "min_hours_per_week": 20, "requested_days_off": "Sun",     "preferred_shifts": "Morning"},
            {"_id": "e2", "name": "Bob",    "skills": "", "max_shifts_per_week": 5, "max_hours_per_week": 40, "min_hours_per_week": 20, "requested_days_off": "Sat",     "preferred_shifts": "Evening"},
            {"_id": "e3", "name": "Carol",  "skills": "", "max_shifts_per_week": 5, "max_hours_per_week": 40, "min_hours_per_week": 20, "requested_days_off": "",        "preferred_shifts": ""},
            {"_id": "e4", "name": "David",  "skills": "", "max_shifts_per_week": 4, "max_hours_per_week": 32, "min_hours_per_week": 0,  "requested_days_off": "Sun,Sat", "preferred_shifts": "Night"},
            {"_id": "e5", "name": "Eve",    "skills": "", "max_shifts_per_week": 5, "max_hours_per_week": 40, "min_hours_per_week": 20, "requested_days_off": "",        "preferred_shifts": "Morning"},
        ],
    },

    "scheduling_nurse": {
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "min_rest_hours": 10,
        "max_consecutive_days": 4,
        "shifts": [
            {"_id": "s1", "name": "Day",   "start_hour": 7,  "end_hour": 19, "required_count": 4, "days": ""},
            {"_id": "s2", "name": "Night", "start_hour": 19, "end_hour": 31, "required_count": 2, "days": ""},
        ],
        "employees": [
            {"_id": "e1", "name": "Nurse Alice",  "skills": "head_nurse",  "max_shifts_per_week": 5, "max_hours_per_week": 48, "min_hours_per_week": 36, "requested_days_off": "",        "preferred_shifts": "Day"},
            {"_id": "e2", "name": "Nurse Bob",    "skills": "trainee",     "max_shifts_per_week": 5, "max_hours_per_week": 48, "min_hours_per_week": 36, "requested_days_off": "",        "preferred_shifts": ""},
            {"_id": "e3", "name": "Nurse Carol",  "skills": "trainee",     "max_shifts_per_week": 5, "max_hours_per_week": 48, "min_hours_per_week": 36, "requested_days_off": "",        "preferred_shifts": "Day"},
            {"_id": "e4", "name": "Nurse David",  "skills": "specialist",  "max_shifts_per_week": 5, "max_hours_per_week": 48, "min_hours_per_week": 36, "requested_days_off": "Sat,Sun", "preferred_shifts": ""},
            {"_id": "e5", "name": "Nurse Eve",    "skills": "head_nurse",  "max_shifts_per_week": 4, "max_hours_per_week": 40, "min_hours_per_week": 24, "requested_days_off": "",        "preferred_shifts": "Night"},
        ],
    },

    "scheduling_timetable": {
        "time_config": {"days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "slots_per_day": 8},
        "teachers": [
            {"_id": "t1", "name": "Alice",  "subjects": "Math,Physics",      "max_periods_per_week": 20, "unavailable": ""},
            {"_id": "t2", "name": "Bob",    "subjects": "Chemistry,Biology", "max_periods_per_week": 18, "unavailable": "Monday:0"},
            {"_id": "t3", "name": "Carol",  "subjects": "English,History",   "max_periods_per_week": 16, "unavailable": ""},
            {"_id": "t4", "name": "David",  "subjects": "Math,Computer",     "max_periods_per_week": 20, "unavailable": "Friday:7"},
            {"_id": "t5", "name": "Eve",    "subjects": "Physics,Chemistry", "max_periods_per_week": 18, "unavailable": ""},
        ],
        "classes": [
            {"_id": "c1", "id": "10-A", "strength": 38},
            {"_id": "c2", "id": "10-B", "strength": 35},
            {"_id": "c3", "id": "9-A",  "strength": 40},
        ],
        "subjects": [
            {"_id": "s1", "name": "Math",      "periods_per_week_per_class": 5, "consecutive": False, "mergeable_groups": ""},
            {"_id": "s2", "name": "Physics",   "periods_per_week_per_class": 4, "consecutive": False, "mergeable_groups": "10-A,10-B"},
            {"_id": "s3", "name": "Chemistry", "periods_per_week_per_class": 3, "consecutive": True,  "mergeable_groups": ""},
            {"_id": "s4", "name": "English",   "periods_per_week_per_class": 4, "consecutive": False, "mergeable_groups": ""},
        ],
        "rooms": [
            {"_id": "r1", "name": "Room 101", "capacity": 45},
            {"_id": "r2", "name": "Room 102", "capacity": 45},
            {"_id": "r3", "name": "Lab 1",    "capacity": 40},
            {"_id": "r4", "name": "Hall",     "capacity": 80},
        ],
    },

    "routing_tsp": {
        "depot": 0,
        "time_limit_seconds": 10,
        "distance_matrix": [
            [0, 4, 8, 6, 7],
            [4, 0, 5, 3, 6],
            [8, 5, 0, 4, 3],
            [6, 3, 4, 0, 5],
            [7, 6, 3, 5, 0],
        ],
    },

    "routing_vrp": {
        "num_vehicles": 2,
        "depot": 0,
        "max_route_distance": 0,
        "time_limit_seconds": 10,
        "distance_matrix": [
            [0, 4, 8, 6, 7, 5],
            [4, 0, 5, 3, 6, 4],
            [8, 5, 0, 4, 3, 6],
            [6, 3, 4, 0, 5, 2],
            [7, 6, 3, 5, 0, 4],
            [5, 4, 6, 2, 4, 0],
        ],
    },

    "routing_cvrp": {
        "num_vehicles": 2,
        "depot": 0,
        "time_limit_seconds": 10,
        "distance_matrix": [
            [0, 4, 8, 6, 7, 5],
            [4, 0, 5, 3, 6, 4],
            [8, 5, 0, 4, 3, 6],
            [6, 3, 4, 0, 5, 2],
            [7, 6, 3, 5, 0, 4],
            [5, 4, 6, 2, 4, 0],
        ],
        "demands": [0, 4, 2, 6, 3, 5],
        "vehicle_capacities": [11, 11],
    },

    "routing_vrptw": {
        "num_vehicles": 2,
        "depot": 0,
        "time_limit_seconds": 10,
        "max_waiting_time": 30,
        "max_time_per_vehicle": 200,
        "time_matrix": [
            [0, 4, 8, 6, 7, 5],
            [4, 0, 5, 3, 6, 4],
            [8, 5, 0, 4, 3, 6],
            [6, 3, 4, 0, 5, 2],
            [7, 6, 3, 5, 0, 4],
            [5, 4, 6, 2, 4, 0],
        ],
        "service_times": [0, 2, 2, 2, 2, 2],
        "time_windows": [[0, 200], [5, 60], [10, 80], [20, 90], [30, 120], [40, 140]],
    },

    "routing_pdp": {
        "num_vehicles": 2,
        "depot": 0,
        "time_limit_seconds": 10,
        "distance_matrix": [
            [0, 4, 8, 6, 7, 5],
            [4, 0, 5, 3, 6, 4],
            [8, 5, 0, 4, 3, 6],
            [6, 3, 4, 0, 5, 2],
            [7, 6, 3, 5, 0, 4],
            [5, 4, 6, 2, 4, 0],
        ],
        "demands": [0, 3, -3, 4, -4, 0],
        "vehicle_capacities": [7, 7],
        "pickup_delivery_pairs": [[1, 2], [3, 4]],
    },

    "scheduling_rcpsp": {
        "time_unit": "days",
        "resources": [
            {"_id": "r1", "name": "Workers", "capacity": 8},
            {"_id": "r2", "name": "Cranes",  "capacity": 2},
        ],
        "activities": [
            {"_id": "a1", "name": "Foundation",    "duration": 5, "predecessors": "",                      "resources": "Workers:4,Cranes:1"},
            {"_id": "a2", "name": "Framing",       "duration": 8, "predecessors": "Foundation",             "resources": "Workers:6,Cranes:2"},
            {"_id": "a3", "name": "Electrical",    "duration": 4, "predecessors": "Framing",               "resources": "Workers:3,Cranes:0"},
            {"_id": "a4", "name": "Plumbing",      "duration": 5, "predecessors": "Framing",               "resources": "Workers:4,Cranes:0"},
            {"_id": "a5", "name": "HVAC",          "duration": 3, "predecessors": "Framing",               "resources": "Workers:2,Cranes:1"},
            {"_id": "a6", "name": "Dry Wall",      "duration": 6, "predecessors": "Electrical,Plumbing",   "resources": "Workers:5,Cranes:0"},
            {"_id": "a7", "name": "Paint & Floor", "duration": 4, "predecessors": "Dry Wall",               "resources": "Workers:4,Cranes:0"},
            {"_id": "a8", "name": "Final Inspect", "duration": 2, "predecessors": "Paint & Floor,HVAC",     "resources": "Workers:2,Cranes:0"},
        ],
    },

    # ==================================================================
    # PACKING & KNAPSACK
    # ==================================================================

    "packing_knapsack": {
        "problem_type": "0-1",
        "capacity": 50,
        "time_limit_seconds": 30,
        "items": [
            {"_id": "i1", "name": "Laptop",      "value": 500, "weight": 10, "quantity": 1},
            {"_id": "i2", "name": "Camera",      "value": 300, "weight": 5,  "quantity": 1},
            {"_id": "i3", "name": "Phone",       "value": 200, "weight": 2,  "quantity": 1},
            {"_id": "i4", "name": "Tablet",      "value": 250, "weight": 8,  "quantity": 1},
            {"_id": "i5", "name": "Headphones",  "value": 100, "weight": 3,  "quantity": 1},
            {"_id": "i6", "name": "Charger",     "value": 50,  "weight": 1,  "quantity": 1},
            {"_id": "i7", "name": "Book",        "value": 30,  "weight": 4,  "quantity": 1},
            {"_id": "i8", "name": "Water Bottle","value": 20,  "weight": 6,  "quantity": 1},
            {"_id": "i9", "name": "Snacks",      "value": 40,  "weight": 3,  "quantity": 1},
            {"_id": "i10","name": "Jacket",      "value": 80,  "weight": 12, "quantity": 1},
        ],
    },

    "packing_binpacking": {
        "problem_type": "1d",
        "bin_capacity": 100,
        "time_limit_seconds": 60,
        "items": [
            {"_id": "i1", "name": "Box A", "size": 45, "quantity": 2},
            {"_id": "i2", "name": "Box B", "size": 35, "quantity": 3},
            {"_id": "i3", "name": "Box C", "size": 25, "quantity": 4},
            {"_id": "i4", "name": "Box D", "size": 20, "quantity": 2},
            {"_id": "i5", "name": "Box E", "size": 15, "quantity": 3},
            {"_id": "i6", "name": "Box F", "size": 10, "quantity": 5},
        ],
    },

    "packing_cuttingstock": {
        "problem_type": "1d",
        "stock_length": 100,
        "time_limit_seconds": 60,
        "orders": [
            {"_id": "o1", "name": "Small Piece",  "length": 15, "quantity": 10},
            {"_id": "o2", "name": "Medium Piece", "length": 25, "quantity": 8},
            {"_id": "o3", "name": "Large Piece",  "length": 40, "quantity": 5},
            {"_id": "o4", "name": "XL Piece",     "length": 55, "quantity": 3},
        ],
    },

    # MAP ROUTING
    "map_routing_multiobjective": {
        "start_address":  "",
        "end_address":    "",
        "start_lat":      None,
        "start_lng":      None,
        "end_lat":        None,
        "end_lng":        None,
        "poi_preferences": {},
        "distance_weight":  0.5,
        "avoid_highways":   False,
        "network_type":     "drive",
        "search_radius_m":  100,
        "time_limit_seconds": 30,
    },
}


# ---------------------------------------------------------------------------
# Session class
# ---------------------------------------------------------------------------

class Session:
    __slots__ = ("session_id", "algo_id", "draft", "patch_log", "last_access")

    def __init__(self, session_id: str, algo_id: str, draft: Dict[str, Any]):
        self.session_id  = session_id
        self.algo_id     = algo_id
        self.draft       = draft
        self.patch_log:  List[Dict[str, Any]] = []
        self.last_access = time.monotonic()

    def touch(self) -> None:
        self.last_access = time.monotonic()

    def is_expired(self) -> bool:
        return (time.monotonic() - self.last_access) > SESSION_TTL_SECONDS


# ---------------------------------------------------------------------------
# Store internals
# ---------------------------------------------------------------------------

_store: Dict[str, Session] = {}
_lock  = threading.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_session(session_id: str, algo_id: str) -> Session:
    """Create (or reset) a session for session_id using the default draft for algo_id."""
    import copy
    draft = copy.deepcopy(DEFAULT_DRAFTS.get(algo_id, {}))
    with _lock:
        session = Session(session_id, algo_id, draft)
        _store[session_id] = session
        return session


def get_session(session_id: str) -> Optional[Session]:
    """Return the session if it exists and has not expired; None otherwise."""
    with _lock:
        s = _store.get(session_id)
        if s is None:
            return None
        if s.is_expired():
            del _store[session_id]
            return None
        s.touch()
        return s


def update_draft(session_id: str, new_draft: Dict[str, Any], patch_summary: str) -> bool:
    """Replace the session's draft and append to patch_log. Returns False if session missing."""
    with _lock:
        s = _store.get(session_id)
        if s is None:
            return False
        s.patch_log.append({
            "summary":   patch_summary,
            "timestamp": time.time(),
        })
        s.draft = new_draft
        s.touch()
        return True


def get_or_create(session_id: str, algo_id: str) -> Session:
    """Get existing session or create a fresh one with defaults for algo_id."""
    s = get_session(session_id)
    if s is None or s.algo_id != algo_id:
        s = create_session(session_id, algo_id)
    return s


def delete_session(session_id: str) -> None:
    with _lock:
        _store.pop(session_id, None)
