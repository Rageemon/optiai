"""
Educational Timetabling Solver
================================
Full-complexity educational timetable using OR-Tools CP-SAT.

Handles:
- Any number of classes (e.g. "1-A", "10-D")
- Teachers with subject qualifications, max hours/week, unavailability
- Subjects with required periods/week/class + consecutive (lab) support
- Merged/combined lectures (multiple classes, one teacher, one room)
- Room assignment by capacity (post-solve greedy phase)
- Substitute teacher lookup

Input schema (dict)
-------------------
{
  "teachers": [
    {
      "name": str,
      "subjects": [str],                  # what they can teach
      "max_periods_per_week": int,        # default: days×slots
      "unavailable": [                    # hard unavailability
        {"day": str | int, "slot": int}  # day = name or 0-based index
      ],
      "preferred_slots": [                # soft: used in objective
        {"day": str | int, "slot": int}
      ]
    }
  ],
  "classes": [
    {"id": str, "strength": int}         # strength = student count
  ],
  "subjects": [
    {
      "name": str,
      "periods_per_week_per_class": int, # required lessons per class/week
      "consecutive": bool,               # must be taught in back-to-back pairs (labs)
      "mergeable_groups": [              # optional merged-lecture groups
        ["ClassA", "ClassB"]             # these classes share one teacher slot
      ]
    }
  ],
  "rooms": [                             # optional; skipped if empty
    {"name": str, "capacity": int}
  ],
  "time_config": {
    "days":          [str],              # e.g. ["Monday",...,"Friday"]
    "slots_per_day": int                 # periods per day (e.g. 8)
  },
  "substitute_pool": [str]               # teacher names allowed as subs (optional)
}

Output schema (dict)
--------------------
{
  "status":    str,
  "by_class":  {class_id: {day: [{slot, subject, teacher, room, merged_with}]}},
  "by_teacher":{teacher:  {day: [{slot, subject, class_id, room, merged_with}]}},
  "room_assignments": {class_id: {day: {slot: room}}},
  "statistics": {
    "coverage_met": bool,
    "teacher_loads": {teacher: int},
    "uncovered": [{class_id, subject, scheduled, required}]
  },
  "solver_stats": {...}
}
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from ortools.sat.python import cp_model

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def solve_timetable(data: dict[str, Any]) -> dict[str, Any]:     # noqa: C901
    teachers_data  = data.get("teachers", [])
    classes_data   = data.get("classes", [])
    subjects_data  = data.get("subjects", [])
    rooms_data     = data.get("rooms", [])
    time_cfg       = data.get("time_config", {})
    sub_pool       = set(data.get("substitute_pool", []))

    days           = time_cfg.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri"])
    slots_per_day  = int(time_cfg.get("slots_per_day", 8))
    nD, nP         = len(days), slots_per_day

    if not teachers_data or not classes_data or not subjects_data:
        return {"status": "INFEASIBLE", "error": "Must provide teachers, classes and subjects."}

    # ------------------------------------------------------------------ #
    # Pre-process teacher data                                            #
    # ------------------------------------------------------------------ #
    teacher_names = [t["name"] for t in teachers_data]

    def _day_idx(d: Any) -> int | None:
        if isinstance(d, int):
            return d if 0 <= d < nD else None
        try:
            return days.index(str(d))
        except ValueError:
            return None

    teacher_qualifies: dict[str, set[str]] = {}
    teacher_max_load: dict[str, int]       = {}
    teacher_forbidden: set[tuple]          = set()   # (name, d, p)
    teacher_preferred: set[tuple]          = set()   # (name, d, p)

    for t in teachers_data:
        name = t["name"]
        teacher_qualifies[name] = set(t.get("subjects", []))
        teacher_max_load[name]  = int(t.get("max_periods_per_week", nD * nP))
        for un in t.get("unavailable", []):
            d_idx = _day_idx(un.get("day", un.get("day_index")))
            p_idx = un.get("slot", un.get("period", un.get("slot_index")))
            if d_idx is not None and p_idx is not None:
                teacher_forbidden.add((name, d_idx, int(p_idx)))
        for pref in t.get("preferred_slots", []):
            d_idx = _day_idx(pref.get("day"))
            p_idx = pref.get("slot", pref.get("period"))
            if d_idx is not None and p_idx is not None:
                teacher_preferred.add((name, d_idx, int(p_idx)))

    # ------------------------------------------------------------------ #
    # Pre-process subject requirements                                    #
    # ------------------------------------------------------------------ #
    # req[(class_id, subject_name)] = required periods per week
    req: dict[tuple[str, str], int] = {}
    for s in subjects_data:
        ppc = int(s.get("periods_per_week_per_class", s.get("periods_per_week", 2)))
        for c in classes_data:
            # Check per-class override
            overrides = s.get("class_overrides", {})
            req[(c["id"], s["name"])] = int(overrides.get(c["id"], ppc))

    # Consecutive subjects are modeled as fixed slot pairs: (0,1), (2,3), ...
    # Therefore required periods for such subjects must be even.
    for s in subjects_data:
        if not s.get("consecutive"):
            continue
        s_name = s["name"]
        for c in classes_data:
            c_id = c["id"]
            required = req.get((c_id, s_name), 0)
            if required % 2 != 0:
                return {
                    "status": "INFEASIBLE",
                    "error": (
                        f"Consecutive subject '{s_name}' for class '{c_id}' requires an even number "
                        f"of periods, but got {required}."
                    ),
                }

    # ------------------------------------------------------------------ #
    # Build CP-SAT model                                                  #
    # ------------------------------------------------------------------ #
    model = cp_model.CpModel()

    # x[(c_id, s_name, t_name, d, p)] = 1 → teacher teaches subject to class at (d,p)
    x: dict[tuple, Any] = {}
    valid_combos: list[tuple] = []

    for c in classes_data:
        c_id = c["id"]
        for s in subjects_data:
            s_name = s["name"]
            if req.get((c_id, s_name), 0) == 0:
                continue
            for t in teachers_data:
                t_name = t["name"]
                if s_name not in teacher_qualifies.get(t_name, set()):
                    continue
                for d in range(nD):
                    for p in range(nP):
                        if (t_name, d, p) in teacher_forbidden:
                            continue
                        key = (c_id, s_name, t_name, d, p)
                        valid_combos.append(key)
                        x[key] = model.new_bool_var(f"x_{len(valid_combos)}")

    # ------------------------------------------------------------------ #
    # Merge variables: merged[(group_key, s_name, t_name, d, p)]         #
    # A merged lesson satisfies 1 period for ALL classes in the group     #
    # ------------------------------------------------------------------ #
    merge_x: dict[tuple, Any] = {}
    merge_valid: list[tuple] = []

    for s in subjects_data:
        s_name = s["name"]
        for group in s.get("mergeable_groups", []):
            group_key = tuple(sorted(group))
            # All classes in group must need this subject
            if not all(req.get((c_id, s_name), 0) > 0 for c_id in group_key):
                continue
            for t in teachers_data:
                t_name = t["name"]
                if s_name not in teacher_qualifies.get(t_name, set()):
                    continue
                for d in range(nD):
                    for p in range(nP):
                        if (t_name, d, p) in teacher_forbidden:
                            continue
                        key = (group_key, s_name, t_name, d, p)
                        merge_valid.append(key)
                        merge_x[key] = model.new_bool_var(f"mx_{len(merge_valid)}")

    # ------------------------------------------------------------------ #
    # Build lookup dicts for constraints                                  #
    # ------------------------------------------------------------------ #
    vars_cs:   dict[tuple, list] = defaultdict(list)  # (c_id, s_name)
    vars_ts:   dict[tuple, list] = defaultdict(list)  # (t_name, d, p)
    vars_cdp:  dict[tuple, list] = defaultdict(list)  # (c_id, d, p)
    vars_t:    dict[str,   list] = defaultdict(list)  # t_name

    for combo, var in x.items():
        c_id, s_name, t_name, d, p = combo
        vars_cs[(c_id, s_name)].append(var)
        vars_ts[(t_name, d, p)].append(var)
        vars_cdp[(c_id, d, p)].append(var)
        vars_t[t_name].append(var)

    metvars_cs:  dict[tuple, list] = defaultdict(list)  # (c_id, s_name) from merges
    metvars_ts:  dict[tuple, list] = defaultdict(list)  # (t_name, d, p) from merges
    metvars_cdp: dict[tuple, list] = defaultdict(list)  # (c_id, d, p)   from merges
    metvars_t:   dict[str,   list] = defaultdict(list)

    for mkey, mvar in merge_x.items():
        group_key, s_name, t_name, d, p = mkey
        for c_id in group_key:
            metvars_cs[(c_id, s_name)].append(mvar)
            metvars_cdp[(c_id, d, p)].append(mvar)
        metvars_ts[(t_name, d, p)].append(mvar)
        metvars_t[t_name].append(mvar)

    # ------------------------------------------------------------------ #
    # CONSTRAINT 1 — Subject coverage                                     #
    # ------------------------------------------------------------------ #
    for c in classes_data:
        c_id = c["id"]
        for s in subjects_data:
            s_name = s["name"]
            required = req.get((c_id, s_name), 0)
            if required == 0:
                continue
            all_cover = vars_cs.get((c_id, s_name), []) + metvars_cs.get((c_id, s_name), [])
            model.add(sum(all_cover) == required)

    # ------------------------------------------------------------------ #
    # CONSTRAINT 2 — No teacher clash per slot                            #
    # ------------------------------------------------------------------ #
    all_tdp_keys = set(vars_ts.keys()) | set(metvars_ts.keys())
    for (t_name, d, p) in all_tdp_keys:
        slot_vars = vars_ts.get((t_name, d, p), []) + metvars_ts.get((t_name, d, p), [])
        if slot_vars:
            model.add_at_most_one(slot_vars)

    # ------------------------------------------------------------------ #
    # CONSTRAINT 3 — No class clash per slot                              #
    # ------------------------------------------------------------------ #
    all_cdp_keys = set(vars_cdp.keys()) | set(metvars_cdp.keys())
    for (c_id, d, p) in all_cdp_keys:
        slot_vars = vars_cdp.get((c_id, d, p), []) + metvars_cdp.get((c_id, d, p), [])
        if slot_vars:
            model.add_at_most_one(slot_vars)

    # ------------------------------------------------------------------ #
    # CONSTRAINT 4 — Teacher max workload                                 #
    # ------------------------------------------------------------------ #
    for t_name in teacher_names:
        all_t = vars_t.get(t_name, []) + metvars_t.get(t_name, [])
        model.add(sum(all_t) <= teacher_max_load[t_name])

    # ------------------------------------------------------------------ #
    # CONSTRAINT 5 — Consecutive periods for lab subjects                 #
    # ------------------------------------------------------------------ #
    if nP < 2 and any(bool(s.get("consecutive")) for s in subjects_data):
        return {
            "status": "INFEASIBLE",
            "error": "Consecutive-period subjects require at least 2 slots per day.",
        }

    for s in subjects_data:
        if not s.get("consecutive"):
            continue
        s_name = s["name"]
        for c in classes_data:
            c_id = c["id"]
            for t in teachers_data:
                t_name = t["name"]
                if s_name not in teacher_qualifies.get(t_name, set()):
                    continue
                for d in range(nD):
                    # Pair slots consecutively: (0,1), (2,3), ...
                    for p in range(0, nP - 1, 2):
                        v1 = x.get((c_id, s_name, t_name, d, p))
                        v2 = x.get((c_id, s_name, t_name, d, p + 1))
                        if v1 is not None and v2 is not None:
                            # If one is assigned, both must be (pair constraint)
                            model.add(v1 == v2)

            # Apply the same pair rule for merged lectures on consecutive subjects.
            for group in s.get("mergeable_groups", []):
                group_key = tuple(sorted(group))
                if c_id not in group_key:
                    continue
                for t in teachers_data:
                    t_name = t["name"]
                    if s_name not in teacher_qualifies.get(t_name, set()):
                        continue
                    for d in range(nD):
                        for p in range(0, nP - 1, 2):
                            mv1 = merge_x.get((group_key, s_name, t_name, d, p))
                            mv2 = merge_x.get((group_key, s_name, t_name, d, p + 1))
                            if mv1 is not None and mv2 is not None:
                                model.add(mv1 == mv2)

    # ------------------------------------------------------------------ #
    # OBJECTIVE — maximise preference satisfaction                        #
    # ------------------------------------------------------------------ #
    pref_bonus = []
    for combo, var in x.items():
        c_id, s_name, t_name, d, p = combo
        if (t_name, d, p) in teacher_preferred:
            pref_bonus.append(var)
    if pref_bonus:
        model.maximize(sum(pref_bonus))

    # ------------------------------------------------------------------ #
    # Solve                                                               #
    # ------------------------------------------------------------------ #
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0
    solver.parameters.num_search_workers  = 4
    status = solver.solve(model)
    status_name = solver.status_name(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "status": status_name,
            "error":  (
                "No feasible timetable found. Consider: relaxing unavailability, "
                "adding more teachers or slots, or reducing required periods."
            ),
        }

    # ------------------------------------------------------------------ #
    # Extract results                                                     #
    # ------------------------------------------------------------------ #
    by_class:   dict[str, dict[str, list]] = {c["id"]: {d: [] for d in days} for c in classes_data}
    by_teacher: dict[str, dict[str, list]] = {t["name"]: {d: [] for d in days} for t in teachers_data}

    for combo, var in x.items():
        if solver.value(var) == 0:
            continue
        c_id, s_name, t_name, d, p = combo
        day_name = days[d]
        entry_c = {"slot": p, "subject": s_name, "teacher": t_name, "room": None, "merged_with": None}
        entry_t = {"slot": p, "subject": s_name, "class_id": c_id, "room": None, "merged_with": None}
        by_class[c_id][day_name].append(entry_c)
        by_teacher[t_name][day_name].append(entry_t)

    for mkey, mvar in merge_x.items():
        if solver.value(mvar) == 0:
            continue
        group_key, s_name, t_name, d, p = mkey
        day_name = days[d]
        merged_list = list(group_key)
        for c_id in group_key:
            entry_c = {"slot": p, "subject": s_name, "teacher": t_name, "room": None, "merged_with": merged_list}
            by_class[c_id][day_name].append(entry_c)
        entry_t = {"slot": p, "subject": s_name, "class_id": f"[MERGED] {', '.join(merged_list)}", "room": None, "merged_with": merged_list}
        by_teacher[t_name][day_name].append(entry_t)

    # Sort slots for readability
    for c_id in by_class:
        for day_name in by_class[c_id]:
            by_class[c_id][day_name].sort(key=lambda e: e["slot"])
    for t_name in by_teacher:
        for day_name in by_teacher[t_name]:
            by_teacher[t_name][day_name].sort(key=lambda e: e["slot"])

    # ------------------------------------------------------------------ #
    # Room assignment (greedy post-solve)                                 #
    # ------------------------------------------------------------------ #
    room_assignments: dict = {}
    if rooms_data:
        room_assignments = _assign_rooms(by_class, rooms_data, classes_data, days)
        # Inject rooms into by_class and by_teacher
        for c_id, day_slots in room_assignments.items():
            for day_name, slot_map in day_slots.items():
                for entry in by_class.get(c_id, {}).get(day_name, []):
                    entry["room"] = slot_map.get(entry["slot"])

    # ------------------------------------------------------------------ #
    # Statistics                                                          #
    # ------------------------------------------------------------------ #
    teacher_loads = {
        t_name: (
            sum(1 for (cc, ss, tn, d, p), var in x.items()
                if tn == t_name and solver.value(var) == 1)
            + sum(1 for (gk, ss, tn, d, p), mvar in merge_x.items()
                  if tn == t_name and solver.value(mvar) == 1)
        )
        for t_name in teacher_names
    }

    uncovered = []
    for c in classes_data:
        c_id = c["id"]
        for s in subjects_data:
            s_name = s["name"]
            required = req.get((c_id, s_name), 0)
            if required == 0:
                continue
            scheduled = sum(
                solver.value(v)
                for (cc, ss, tn, d, p), v in x.items()
                if cc == c_id and ss == s_name
            ) + sum(
                solver.value(v)
                for (gk, ss, tn, d, p), v in merge_x.items()
                if c_id in gk and ss == s_name
            )
            if scheduled < required:
                uncovered.append({"class_id": c_id, "subject": s_name, "scheduled": scheduled, "required": required})

    return {
        "status":      status_name,
        "by_class":    by_class,
        "by_teacher":  by_teacher,
        "room_assignments": room_assignments,
        "statistics": {
            "coverage_met":  len(uncovered) == 0,
            "teacher_loads": teacher_loads,
            "uncovered":     uncovered,
        },
        "solver_stats": {
            "wall_time":    round(solver.wall_time, 3),
            "branches":     solver.num_branches,
            "objective":    solver.objective_value if pref_bonus else None,
        },
    }


# ---------------------------------------------------------------------------
# Room assignment (greedy post-solve)
# ---------------------------------------------------------------------------

def _assign_rooms(
    by_class: dict,
    rooms_data: list,
    classes_data: list,
    days: list[str],
) -> dict:
    """Greedily assign rooms by matching class strength to room capacity."""
    class_strength = {c["id"]: c.get("strength", 0) for c in classes_data}
    rooms_sorted   = sorted(rooms_data, key=lambda r: r.get("capacity", 0))

    # room_busy[(room_name, day, slot)] = True when occupied
    room_busy: dict[tuple, bool] = {}
    assignments: dict = {c["id"]: {d: {} for d in days} for c in classes_data}

    for c_id, days_schedule in by_class.items():
        strength = class_strength.get(c_id, 0)
        for day_name, slots in days_schedule.items():
            for entry in slots:
                p = entry["slot"]
                # Find smallest room that fits and is free
                for room in rooms_sorted:
                    if room.get("capacity", 0) >= strength:
                        key = (room["name"], day_name, p)
                        if not room_busy.get(key):
                            room_busy[key] = True
                            assignments[c_id][day_name][p] = room["name"]
                            break

    return assignments


# ---------------------------------------------------------------------------
# Substitute finder (no CP needed — pure filtering)
# ---------------------------------------------------------------------------

def find_substitutes(
    timetable_result: dict[str, Any],
    absent_teacher: str,
    absent_day: str,
    teachers_data: list[dict],
) -> dict[str, Any]:
    """
    Given a solved timetable, suggest substitutes for an absent teacher on a day.

    Parameters
    ----------
    timetable_result  result from solve_timetable()
    absent_teacher    name of the absent teacher
    absent_day        day name (must match timetable_result keys)
    teachers_data     original teachers list (for qualifications)

    Returns
    -------
    {slot: {class_id, subject, candidates: [teacher_name]}}
    """
    teacher_quals = {t["name"]: set(t.get("subjects", [])) for t in teachers_data}
    teacher_forbidden_raw: dict[str, set] = {}
    days_list: list[str] = []
    for t in teachers_data:
        teacher_forbidden_raw[t["name"]] = set()
        for un in t.get("unavailable", []):
            d = un.get("day")
            if isinstance(d, str):
                teacher_forbidden_raw[t["name"]].add((d, un.get("slot", un.get("period", -1))))

    by_teacher = timetable_result.get("by_teacher", {})
    absent_slots = by_teacher.get(absent_teacher, {}).get(absent_day, [])

    if not absent_slots:
        return {"message": f"{absent_teacher} has no lessons on {absent_day}", "suggestions": {}}

    # Build "who is busy on absent_day"
    busy_on_day: dict[str, set] = defaultdict(set)
    for t_name, days_schedule in by_teacher.items():
        for entry in days_schedule.get(absent_day, []):
            busy_on_day[t_name].add(entry["slot"])

    suggestions: dict = {}
    for entry in absent_slots:
        slot    = entry["slot"]
        subject = entry["subject"]
        class_id = entry.get("class_id", "")

        candidates = []
        for t_name, quals in teacher_quals.items():
            if t_name == absent_teacher:
                continue
            if subject not in quals:
                continue
            if slot in busy_on_day.get(t_name, set()):
                continue
            if (absent_day, slot) in teacher_forbidden_raw.get(t_name, set()):
                continue
            candidates.append(t_name)

        suggestions[slot] = {
            "class_id":   class_id,
            "subject":    subject,
            "candidates": candidates,
        }

    return {"suggestions": suggestions, "absent_day": absent_day, "absent_teacher": absent_teacher}
