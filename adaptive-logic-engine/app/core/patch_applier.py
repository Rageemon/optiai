"""
Patch Applier
=============
Pure deterministic functions that apply typed patch objects to a form-level
draft dict (the same structure the frontend forms produce).

Each apply_* function:
  - Takes (draft, patch) and returns (new_draft, diff_entries).
  - deep-copies the draft before mutation — original is never modified.
  - Returns a diff list used for the "Changes Applied" preview in the frontend.

DiffEntry keys: "field", "op" ("add"|"remove"|"change"), "from", "to"

A top-level dispatcher `apply_patch(algo_id, draft, patch)` routes to the
correct function and is the only symbol that callers need to import.
"""

import copy
import random
import string
from typing import Any, Dict, List, Tuple, Optional

from app.models.patch_models import (
    JsspPatch,
    NursePatch,
    RcpspPatch,
    ShiftPatch,
    TimetablePatch,
    RoutingTspPatch,
    RoutingVrpPatch,
    RoutingCvrpPatch,
    RoutingVrptwPatch,
    RoutingPdpPatch,
    KnapsackPatch,
    BinPackingPatch,
    CuttingStockPatch,
    MapRoutingPatch,
    PoiWeightUpdate,
)

DiffEntry = Dict[str, str]  # {"field": ..., "op": ..., "from": ..., "to": ...}


def _uid() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def _parse_csv_tokens(value: str) -> List[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def _merge_group_token(class_ids: List[str]) -> str:
    return ",".join([c.strip() for c in class_ids if c.strip()])


def _resolve_teacher_ref(teachers: List[Dict[str, Any]], ref: str) -> Optional[Dict[str, Any]]:
    ref_norm = (ref or "").strip().lower()
    if not ref_norm:
        return None

    for t in teachers:
        if str(t.get("name", "")).strip().lower() == ref_norm:
            return t

    if ref_norm.endswith(" teacher"):
        subj = ref_norm[:-8].strip()
        if subj:
            matches: List[Dict[str, Any]] = []
            for t in teachers:
                subjects = [s.strip().lower() for s in str(t.get("subjects", "")).split(",") if s.strip()]
                if subj in subjects:
                    matches.append(t)
            if len(matches) == 1:
                return matches[0]

    return None


# ---------------------------------------------------------------------------
# A. Job Shop / Machine Scheduling
# ---------------------------------------------------------------------------

def apply_jssp_patch(draft: Dict[str, Any], patch: JsspPatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    # Remove jobs
    for name in patch.remove_job_names:
        before_len = len(draft.get("jobs", []))
        draft["jobs"] = [j for j in draft.get("jobs", []) if j["name"] != name]
        if len(draft.get("jobs", [])) < before_len:
            diff.append({"field": "Jobs", "op": "remove", "from": name, "to": ""})

    # Add jobs
    for job in patch.add_jobs:
        new_job = {
            "_id":      _uid(),
            "name":     job.name,
            "priority": job.priority,
            "due_date": job.due_date,
            "tasks":    [{"_id": _uid(), "machine": t.machine, "duration": t.duration} for t in job.tasks],
        }
        draft.setdefault("jobs", []).append(new_job)
        diff.append({"field": "Jobs", "op": "add", "from": "", "to": job.name})

    # Remove machines
    for name in patch.remove_machine_names:
        before_len = len(draft.get("machines", []))
        draft["machines"] = [m for m in draft.get("machines", []) if m["name"] != name]
        if len(draft.get("machines", [])) < before_len:
            diff.append({"field": "Machines", "op": "remove", "from": name, "to": ""})

    # Add machines
    for m in patch.add_machines:
        draft.setdefault("machines", []).append({"_id": _uid(), "name": m.name, "count": m.count})
        diff.append({"field": "Machines", "op": "add", "from": "", "to": f"{m.name} (×{m.count})"})

    # Objective
    if patch.set_objective:
        old = draft.get("objective", "makespan")
        draft["objective"] = patch.set_objective
        diff.append({"field": "Objective", "op": "change", "from": str(old), "to": patch.set_objective})

    return draft, diff


# ---------------------------------------------------------------------------
# B1. Shift Scheduling
# ---------------------------------------------------------------------------

def apply_shift_patch(draft: Dict[str, Any], patch: ShiftPatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    for name in patch.remove_employee_names:
        before_len = len(draft.get("employees", []))
        draft["employees"] = [e for e in draft.get("employees", []) if e["name"] != name]
        if len(draft.get("employees", [])) < before_len:
            diff.append({"field": "Employees", "op": "remove", "from": name, "to": ""})

    for name in patch.add_employee_names:
        draft.setdefault("employees", []).append({
            "_id": _uid(), "name": name, "skills": "",
            "max_shifts_per_week": 5, "max_hours_per_week": 40,
            "min_hours_per_week": 0, "requested_days_off": "", "preferred_shifts": "",
        })
        diff.append({"field": "Employees", "op": "add", "from": "", "to": name})

    for upd in patch.employee_updates:
        for emp in draft.get("employees", []):
            if emp["name"] == upd.name:
                if upd.preferred_shifts:
                    old = emp.get("preferred_shifts", "")
                    emp["preferred_shifts"] = ",".join(upd.preferred_shifts)
                    diff.append({"field": f"{upd.name} · preferred shifts", "op": "change",
                                 "from": str(old), "to": emp["preferred_shifts"]})
                if upd.requested_days_off:
                    old = emp.get("requested_days_off", "")
                    emp["requested_days_off"] = ",".join(upd.requested_days_off)
                    diff.append({"field": f"{upd.name} · days off", "op": "change",
                                 "from": str(old), "to": emp["requested_days_off"]})
                if upd.max_shifts_per_week is not None:
                    old = emp.get("max_shifts_per_week", "")
                    emp["max_shifts_per_week"] = upd.max_shifts_per_week
                    diff.append({"field": f"{upd.name} · max shifts/wk", "op": "change",
                                 "from": str(old), "to": str(upd.max_shifts_per_week)})
                if upd.max_hours_per_week is not None:
                    old = emp.get("max_hours_per_week", "")
                    emp["max_hours_per_week"] = upd.max_hours_per_week
                    diff.append({"field": f"{upd.name} · max hours/wk", "op": "change",
                                 "from": str(old), "to": str(upd.max_hours_per_week)})
                break

    for name in patch.remove_shift_names:
        before_len = len(draft.get("shifts", []))
        draft["shifts"] = [s for s in draft.get("shifts", []) if s["name"] != name]
        if len(draft.get("shifts", [])) < before_len:
            diff.append({"field": "Shifts", "op": "remove", "from": name, "to": ""})

    for s in patch.add_shifts:
        draft.setdefault("shifts", []).append({
            "_id": _uid(), "name": s.name, "start_hour": s.start_hour,
            "end_hour": s.end_hour, "required_count": s.required_count,
            "days": ",".join(s.days),
        })
        diff.append({"field": "Shifts", "op": "add", "from": "", "to": f"{s.name} ({s.start_hour:.0f}h–{s.end_hour:.0f}h)"})

    if patch.set_min_rest_hours is not None:
        old = draft.get("min_rest_hours", "")
        draft["min_rest_hours"] = patch.set_min_rest_hours
        diff.append({"field": "Min rest hours", "op": "change",
                     "from": str(old), "to": str(patch.set_min_rest_hours)})

    if patch.set_max_consecutive_days is not None:
        old = draft.get("max_consecutive_days", "")
        draft["max_consecutive_days"] = patch.set_max_consecutive_days
        diff.append({"field": "Max consecutive days", "op": "change",
                     "from": str(old), "to": str(patch.set_max_consecutive_days)})

    return draft, diff


# ---------------------------------------------------------------------------
# B2. Nurse Rostering
# ---------------------------------------------------------------------------

def apply_nurse_patch(draft: Dict[str, Any], patch: NursePatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    for name in patch.remove_nurse_names:
        before_len = len(draft.get("employees", []))
        draft["employees"] = [e for e in draft.get("employees", []) if e["name"] != name]
        if len(draft.get("employees", [])) < before_len:
            diff.append({"field": "Nurses", "op": "remove", "from": name, "to": ""})

    for name in patch.add_nurse_names:
        draft.setdefault("employees", []).append({
            "_id": _uid(), "name": name, "skills": "trainee",
            "max_shifts_per_week": 5, "max_hours_per_week": 48,
            "min_hours_per_week": 36, "requested_days_off": "", "preferred_shifts": "",
        })
        diff.append({"field": "Nurses", "op": "add", "from": "", "to": name})

    for upd in patch.nurse_skill_updates:
        for emp in draft.get("employees", []):
            if emp["name"] == upd.name:
                old = emp.get("skills", "")
                emp["skills"] = ",".join(upd.skills)
                diff.append({"field": f"{upd.name} · skills", "op": "change",
                             "from": str(old), "to": emp["skills"]})
                break

    for name in patch.remove_shift_names:
        before_len = len(draft.get("shifts", []))
        draft["shifts"] = [s for s in draft.get("shifts", []) if s["name"] != name]
        if len(draft.get("shifts", [])) < before_len:
            diff.append({"field": "Shifts", "op": "remove", "from": name, "to": ""})

    for s in patch.add_shifts:
        draft.setdefault("shifts", []).append({
            "_id": _uid(), "name": s.name, "start_hour": s.start_hour,
            "end_hour": s.end_hour, "required_count": s.required_count,
            "days": ",".join(s.days),
        })
        diff.append({"field": "Shifts", "op": "add", "from": "", "to": f"{s.name} ({s.start_hour:.0f}h–{s.end_hour:.0f}h)"})

    if patch.set_max_consecutive_days is not None:
        old = draft.get("max_consecutive_days", "")
        draft["max_consecutive_days"] = patch.set_max_consecutive_days
        diff.append({"field": "Max consecutive days", "op": "change",
                     "from": str(old), "to": str(patch.set_max_consecutive_days)})

    if patch.set_min_rest_hours is not None:
        old = draft.get("min_rest_hours", "")
        draft["min_rest_hours"] = patch.set_min_rest_hours
        diff.append({"field": "Min rest hours", "op": "change",
                     "from": str(old), "to": str(patch.set_min_rest_hours)})

    return draft, diff


# ---------------------------------------------------------------------------
# C. Educational Timetabling
# ---------------------------------------------------------------------------

def apply_timetable_patch(draft: Dict[str, Any], patch: TimetablePatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    for name in patch.remove_teacher_names:
        before_len = len(draft.get("teachers", []))
        draft["teachers"] = [t for t in draft.get("teachers", []) if t["name"] != name]
        if len(draft.get("teachers", [])) < before_len:
            diff.append({"field": "Teachers", "op": "remove", "from": name, "to": ""})

    for name in patch.add_teacher_names:
        draft.setdefault("teachers", []).append({
            "_id": _uid(), "name": name, "subjects": "",
            "max_periods_per_week": 20, "unavailable": "",
        })
        diff.append({"field": "Teachers", "op": "add", "from": "", "to": name})

    for op in patch.teacher_subject_ops:
        teacher = _resolve_teacher_ref(draft.get("teachers", []), op.teacher)
        if teacher is None:
            continue
        subjects = _parse_csv_tokens(teacher.get("subjects", ""))
        if op.op == "add" and op.subject not in subjects:
            subjects.append(op.subject)
            teacher["subjects"] = ",".join(subjects)
            diff.append({"field": f"{teacher.get('name', op.teacher)} · subjects", "op": "add",
                         "from": "", "to": op.subject})
        elif op.op == "remove" and op.subject in subjects:
            subjects.remove(op.subject)
            teacher["subjects"] = ",".join(subjects)
            diff.append({"field": f"{teacher.get('name', op.teacher)} · subjects", "op": "remove",
                         "from": op.subject, "to": ""})

    for cid in patch.remove_class_ids:
        before_len = len(draft.get("classes", []))
        draft["classes"] = [c for c in draft.get("classes", []) if c["id"] != cid]
        if len(draft.get("classes", [])) < before_len:
            diff.append({"field": "Classes", "op": "remove", "from": cid, "to": ""})

    for cid in patch.add_class_ids:
        draft.setdefault("classes", []).append({"_id": _uid(), "id": cid, "strength": 35})
        diff.append({"field": "Classes", "op": "add", "from": "", "to": cid})

    for name in patch.remove_room_names:
        before_len = len(draft.get("rooms", []))
        draft["rooms"] = [r for r in draft.get("rooms", []) if r["name"] != name]
        if len(draft.get("rooms", [])) < before_len:
            diff.append({"field": "Rooms", "op": "remove", "from": name, "to": ""})

    for room in patch.add_rooms:
        draft.setdefault("rooms", []).append({
            "_id": _uid(),
            "name": room.name,
            "capacity": room.capacity,
        })
        diff.append({"field": "Rooms", "op": "add", "from": "", "to": f"{room.name} (cap {room.capacity})"})

    for rc in patch.room_capacity_changes:
        for room in draft.get("rooms", []):
            if room["name"] == rc.room_name:
                old = room.get("capacity", "")
                room["capacity"] = rc.new_capacity
                diff.append({"field": f"{rc.room_name} · capacity", "op": "change",
                             "from": str(old), "to": str(rc.new_capacity)})
                break

    for name in patch.remove_subject_names:
        before_len = len(draft.get("subjects", []))
        draft["subjects"] = [s for s in draft.get("subjects", []) if s["name"] != name]
        if len(draft.get("subjects", [])) < before_len:
            diff.append({"field": "Subjects", "op": "remove", "from": name, "to": ""})

    for subj in patch.add_subjects:
        draft.setdefault("subjects", []).append({
            "_id": _uid(),
            "name": subj.name,
            "periods_per_week_per_class": subj.periods_per_week,
            "consecutive": subj.consecutive,
            "mergeable_groups": " | ".join(subj.mergeable_groups),
        })
        diff.append({"field": "Subjects", "op": "add", "from": "", "to": subj.name})

    for op in patch.teacher_unavail_ops:
        for teacher in draft.get("teachers", []):
            if teacher["name"] == op.teacher:
                token = f"{op.day}:{op.slot}"
                existing = [x.strip() for x in teacher.get("unavailable", "").split(",") if x.strip()]
                if op.op == "add" and token not in existing:
                    existing.append(token)
                    teacher["unavailable"] = ",".join(existing)
                    diff.append({"field": f"{op.teacher} · unavailable", "op": "add",
                                 "from": "", "to": token})
                elif op.op == "remove" and token in existing:
                    existing.remove(token)
                    teacher["unavailable"] = ",".join(existing)
                    diff.append({"field": f"{op.teacher} · unavailable", "op": "remove",
                                 "from": token, "to": ""})
                break

    for sc in patch.subject_period_changes:
        found = False
        for subj in draft.get("subjects", []):
            if subj["name"] == sc.subject_name:
                found = True
                old = subj.get("periods_per_week_per_class", "")
                subj["periods_per_week_per_class"] = sc.new_periods_per_week
                diff.append({"field": f"{sc.subject_name} · periods/week", "op": "change",
                             "from": str(old), "to": str(sc.new_periods_per_week)})
                break
        if not found:
            draft.setdefault("subjects", []).append({
                "_id": _uid(),
                "name": sc.subject_name,
                "periods_per_week_per_class": sc.new_periods_per_week,
                "consecutive": False,
                "mergeable_groups": "",
            })
            diff.append({"field": "Subjects", "op": "add", "from": "", "to": sc.subject_name})

    for cc in patch.subject_consecutive_changes:
        found = False
        for subj in draft.get("subjects", []):
            if subj["name"] == cc.subject_name:
                found = True
                old = bool(subj.get("consecutive", False))
                subj["consecutive"] = cc.new_consecutive
                diff.append({"field": f"{cc.subject_name} · consecutive", "op": "change",
                             "from": str(old), "to": str(cc.new_consecutive)})
                break
        if not found:
            draft.setdefault("subjects", []).append({
                "_id": _uid(),
                "name": cc.subject_name,
                "periods_per_week_per_class": 2,
                "consecutive": cc.new_consecutive,
                "mergeable_groups": "",
            })
            diff.append({"field": "Subjects", "op": "add", "from": "", "to": cc.subject_name})

    for mg in patch.subject_merge_group_ops:
        token = _merge_group_token(mg.class_ids)
        if not token:
            continue
        for subj in draft.get("subjects", []):
            if subj["name"] == mg.subject_name:
                existing = [x.strip() for x in str(subj.get("mergeable_groups", "")).split("|") if x.strip()]
                if mg.op == "add" and token not in existing:
                    existing.append(token)
                    subj["mergeable_groups"] = " | ".join(existing)
                    diff.append({"field": f"{mg.subject_name} · merge groups", "op": "add",
                                 "from": "", "to": token})
                elif mg.op == "remove" and token in existing:
                    existing.remove(token)
                    subj["mergeable_groups"] = " | ".join(existing)
                    diff.append({"field": f"{mg.subject_name} · merge groups", "op": "remove",
                                 "from": token, "to": ""})
                break

    time_config = dict(draft.get("time_config") or {
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "slots_per_day": 8,
    })
    time_changed = False

    if patch.set_slots_per_day is not None:
        old = time_config.get("slots_per_day", "")
        time_config["slots_per_day"] = patch.set_slots_per_day
        time_changed = True
        diff.append({"field": "Periods per day", "op": "change",
                     "from": str(old), "to": str(patch.set_slots_per_day)})

    if patch.set_days:
        old_days = ",".join(time_config.get("days", []))
        time_config["days"] = patch.set_days
        time_changed = True
        diff.append({"field": "School days", "op": "change",
                     "from": old_days, "to": ",".join(patch.set_days)})

    if time_changed:
        draft["time_config"] = time_config

    return draft, diff


# ---------------------------------------------------------------------------
# D. RCPSP Project Scheduling
# ---------------------------------------------------------------------------

def apply_rcpsp_patch(draft: Dict[str, Any], patch: RcpspPatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    for name in patch.remove_activity_names:
        before_len = len(draft.get("activities", []))
        draft["activities"] = [a for a in draft.get("activities", []) if a["name"] != name]
        if len(draft.get("activities", [])) < before_len:
            diff.append({"field": "Activities", "op": "remove", "from": name, "to": ""})

    for act in patch.add_activities:
        draft.setdefault("activities", []).append({
            "_id": _uid(), "name": act.name, "duration": act.duration,
            "predecessors": ",".join(act.predecessors), "resources": "",
        })
        diff.append({"field": "Activities", "op": "add", "from": "",
                     "to": f"{act.name} ({act.duration} units)"})

    for upd in patch.activity_updates:
        for act in draft.get("activities", []):
            if act["name"] == upd.name:
                if upd.new_duration is not None:
                    old = act.get("duration", "")
                    act["duration"] = upd.new_duration
                    diff.append({"field": f"{upd.name} · duration", "op": "change",
                                 "from": str(old), "to": str(upd.new_duration)})

                preds = [p.strip() for p in (act.get("predecessors") or "").split(",") if p.strip()]
                for p in upd.add_predecessors:
                    if p not in preds:
                        preds.append(p)
                        diff.append({"field": f"{upd.name} · predecessors", "op": "add",
                                     "from": "", "to": p})
                for p in upd.remove_predecessors:
                    if p in preds:
                        preds.remove(p)
                        diff.append({"field": f"{upd.name} · predecessors", "op": "remove",
                                     "from": p, "to": ""})
                act["predecessors"] = ",".join(preds)
                break

    for rc in patch.resource_capacity_changes:
        for res in draft.get("resources", []):
            if res["name"] == rc.resource_name:
                old = res.get("capacity", "")
                res["capacity"] = rc.new_capacity
                diff.append({"field": f"{rc.resource_name} · capacity", "op": "change",
                             "from": str(old), "to": str(rc.new_capacity)})
                break

    return draft, diff


# ---------------------------------------------------------------------------
# E. Routing
# ---------------------------------------------------------------------------

def _scale_matrix(matrix: List[List[Any]], percent: int) -> List[List[int]]:
    factor = max(1, percent) / 100.0
    return [[int(round(float(v) * factor)) for v in row] for row in matrix]


def apply_routing_tsp_patch(draft: Dict[str, Any], patch: RoutingTspPatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    if patch.set_depot is not None:
        old = draft.get("depot", 0)
        draft["depot"] = patch.set_depot
        diff.append({"field": "Depot", "op": "change", "from": str(old), "to": str(patch.set_depot)})

    if patch.set_time_limit_seconds is not None:
        old = draft.get("time_limit_seconds", "")
        draft["time_limit_seconds"] = patch.set_time_limit_seconds
        diff.append({"field": "Time limit", "op": "change", "from": str(old), "to": str(patch.set_time_limit_seconds)})

    if patch.scale_distance_percent is not None and draft.get("distance_matrix"):
        draft["distance_matrix"] = _scale_matrix(draft.get("distance_matrix", []), patch.scale_distance_percent)
        diff.append({"field": "Distance matrix", "op": "change", "from": "scaled", "to": f"{patch.scale_distance_percent}%"})

    return draft, diff


def apply_routing_vrp_patch(draft: Dict[str, Any], patch: RoutingVrpPatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    if patch.set_num_vehicles is not None:
        old = draft.get("num_vehicles", "")
        draft["num_vehicles"] = patch.set_num_vehicles
        diff.append({"field": "Vehicles", "op": "change", "from": str(old), "to": str(patch.set_num_vehicles)})

    if patch.set_depot is not None:
        old = draft.get("depot", 0)
        draft["depot"] = patch.set_depot
        diff.append({"field": "Depot", "op": "change", "from": str(old), "to": str(patch.set_depot)})

    if patch.set_max_route_distance is not None:
        old = draft.get("max_route_distance", "")
        draft["max_route_distance"] = patch.set_max_route_distance
        diff.append({"field": "Max route distance", "op": "change", "from": str(old), "to": str(patch.set_max_route_distance)})

    if patch.set_time_limit_seconds is not None:
        old = draft.get("time_limit_seconds", "")
        draft["time_limit_seconds"] = patch.set_time_limit_seconds
        diff.append({"field": "Time limit", "op": "change", "from": str(old), "to": str(patch.set_time_limit_seconds)})

    if patch.scale_distance_percent is not None and draft.get("distance_matrix"):
        draft["distance_matrix"] = _scale_matrix(draft.get("distance_matrix", []), patch.scale_distance_percent)
        diff.append({"field": "Distance matrix", "op": "change", "from": "scaled", "to": f"{patch.scale_distance_percent}%"})

    return draft, diff


def apply_routing_cvrp_patch(draft: Dict[str, Any], patch: RoutingCvrpPatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    if patch.set_num_vehicles is not None:
        old = draft.get("num_vehicles", "")
        draft["num_vehicles"] = patch.set_num_vehicles
        diff.append({"field": "Vehicles", "op": "change", "from": str(old), "to": str(patch.set_num_vehicles)})

    if patch.set_depot is not None:
        old = draft.get("depot", 0)
        draft["depot"] = patch.set_depot
        diff.append({"field": "Depot", "op": "change", "from": str(old), "to": str(patch.set_depot)})

    if patch.set_vehicle_capacities:
        old = ",".join(str(x) for x in draft.get("vehicle_capacities", []))
        draft["vehicle_capacities"] = patch.set_vehicle_capacities
        diff.append({"field": "Vehicle capacities", "op": "change", "from": old, "to": ",".join(str(x) for x in patch.set_vehicle_capacities)})

    for change in patch.demand_changes:
        demands = list(draft.get("demands", []))
        if 0 <= change.node_index < len(demands):
            old = demands[change.node_index]
            demands[change.node_index] = change.new_demand
            draft["demands"] = demands
            diff.append({"field": f"Node {change.node_index} demand", "op": "change", "from": str(old), "to": str(change.new_demand)})

    if patch.set_time_limit_seconds is not None:
        old = draft.get("time_limit_seconds", "")
        draft["time_limit_seconds"] = patch.set_time_limit_seconds
        diff.append({"field": "Time limit", "op": "change", "from": str(old), "to": str(patch.set_time_limit_seconds)})

    if patch.scale_distance_percent is not None and draft.get("distance_matrix"):
        draft["distance_matrix"] = _scale_matrix(draft.get("distance_matrix", []), patch.scale_distance_percent)
        diff.append({"field": "Distance matrix", "op": "change", "from": "scaled", "to": f"{patch.scale_distance_percent}%"})

    return draft, diff


def apply_routing_vrptw_patch(draft: Dict[str, Any], patch: RoutingVrptwPatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    if patch.set_num_vehicles is not None:
        old = draft.get("num_vehicles", "")
        draft["num_vehicles"] = patch.set_num_vehicles
        diff.append({"field": "Vehicles", "op": "change", "from": str(old), "to": str(patch.set_num_vehicles)})

    if patch.set_depot is not None:
        old = draft.get("depot", 0)
        draft["depot"] = patch.set_depot
        diff.append({"field": "Depot", "op": "change", "from": str(old), "to": str(patch.set_depot)})

    for tw in patch.time_window_changes:
        windows = list(draft.get("time_windows", []))
        if 0 <= tw.node_index < len(windows):
            old = windows[tw.node_index]
            windows[tw.node_index] = [tw.start, tw.end]
            draft["time_windows"] = windows
            diff.append({"field": f"Node {tw.node_index} time window", "op": "change", "from": str(old), "to": f"[{tw.start}, {tw.end}]"})

    for svc in patch.service_time_changes:
        services = list(draft.get("service_times", []))
        if 0 <= svc.node_index < len(services):
            old = services[svc.node_index]
            services[svc.node_index] = svc.new_demand
            draft["service_times"] = services
            diff.append({"field": f"Node {svc.node_index} service time", "op": "change", "from": str(old), "to": str(svc.new_demand)})

    if patch.set_max_waiting_time is not None:
        old = draft.get("max_waiting_time", "")
        draft["max_waiting_time"] = patch.set_max_waiting_time
        diff.append({"field": "Max waiting time", "op": "change", "from": str(old), "to": str(patch.set_max_waiting_time)})

    if patch.set_max_time_per_vehicle is not None:
        old = draft.get("max_time_per_vehicle", "")
        draft["max_time_per_vehicle"] = patch.set_max_time_per_vehicle
        diff.append({"field": "Max time/vehicle", "op": "change", "from": str(old), "to": str(patch.set_max_time_per_vehicle)})

    if patch.set_time_limit_seconds is not None:
        old = draft.get("time_limit_seconds", "")
        draft["time_limit_seconds"] = patch.set_time_limit_seconds
        diff.append({"field": "Time limit", "op": "change", "from": str(old), "to": str(patch.set_time_limit_seconds)})

    return draft, diff


def apply_routing_pdp_patch(draft: Dict[str, Any], patch: RoutingPdpPatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    if patch.set_num_vehicles is not None:
        old = draft.get("num_vehicles", "")
        draft["num_vehicles"] = patch.set_num_vehicles
        diff.append({"field": "Vehicles", "op": "change", "from": str(old), "to": str(patch.set_num_vehicles)})

    if patch.set_depot is not None:
        old = draft.get("depot", 0)
        draft["depot"] = patch.set_depot
        diff.append({"field": "Depot", "op": "change", "from": str(old), "to": str(patch.set_depot)})

    if patch.set_vehicle_capacities:
        old = ",".join(str(x) for x in draft.get("vehicle_capacities", []))
        draft["vehicle_capacities"] = patch.set_vehicle_capacities
        diff.append({"field": "Vehicle capacities", "op": "change", "from": old, "to": ",".join(str(x) for x in patch.set_vehicle_capacities)})

    for change in patch.demand_changes:
        demands = list(draft.get("demands", []))
        if 0 <= change.node_index < len(demands):
            old = demands[change.node_index]
            demands[change.node_index] = change.new_demand
            draft["demands"] = demands
            diff.append({"field": f"Node {change.node_index} demand", "op": "change", "from": str(old), "to": str(change.new_demand)})

    pairs = [list(p) for p in draft.get("pickup_delivery_pairs", [])]
    for pair in patch.add_pairs:
        candidate = [pair.pickup_index, pair.delivery_index]
        if candidate not in pairs:
            pairs.append(candidate)
            diff.append({"field": "Pickup-delivery pairs", "op": "add", "from": "", "to": str(candidate)})

    for pair in patch.remove_pairs:
        candidate = [pair.pickup_index, pair.delivery_index]
        if candidate in pairs:
            pairs.remove(candidate)
            diff.append({"field": "Pickup-delivery pairs", "op": "remove", "from": str(candidate), "to": ""})

    draft["pickup_delivery_pairs"] = pairs

    if patch.set_time_limit_seconds is not None:
        old = draft.get("time_limit_seconds", "")
        draft["time_limit_seconds"] = patch.set_time_limit_seconds
        diff.append({"field": "Time limit", "op": "change", "from": str(old), "to": str(patch.set_time_limit_seconds)})

    if patch.scale_distance_percent is not None and draft.get("distance_matrix"):
        draft["distance_matrix"] = _scale_matrix(draft.get("distance_matrix", []), patch.scale_distance_percent)
        diff.append({"field": "Distance matrix", "op": "change", "from": "scaled", "to": f"{patch.scale_distance_percent}%"})

    return draft, diff


# ---------------------------------------------------------------------------
# F. Packing & Knapsack
# ---------------------------------------------------------------------------

def apply_knapsack_patch(draft: Dict[str, Any], patch: KnapsackPatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    # Remove items
    for name in patch.remove_item_names:
        before_len = len(draft.get("items", []))
        draft["items"] = [it for it in draft.get("items", []) if it["name"] != name]
        if len(draft.get("items", [])) < before_len:
            diff.append({"field": "Items", "op": "remove", "from": name, "to": ""})

    # Add items
    for item in patch.add_items:
        draft.setdefault("items", []).append({
            "_id": _uid(),
            "name": item.name,
            "value": item.value,
            "weight": item.weight,
            "quantity": item.quantity,
        })
        diff.append({"field": "Items", "op": "add", "from": "", "to": f"{item.name} (v={item.value}, w={item.weight})"})

    # Update items
    for upd in patch.item_updates:
        for it in draft.get("items", []):
            if it["name"] == upd.name:
                if upd.new_value is not None:
                    old = it.get("value", "")
                    it["value"] = upd.new_value
                    diff.append({"field": f"{upd.name} · value", "op": "change", "from": str(old), "to": str(upd.new_value)})
                if upd.new_weight is not None:
                    old = it.get("weight", "")
                    it["weight"] = upd.new_weight
                    diff.append({"field": f"{upd.name} · weight", "op": "change", "from": str(old), "to": str(upd.new_weight)})
                if upd.new_quantity is not None:
                    old = it.get("quantity", "")
                    it["quantity"] = upd.new_quantity
                    diff.append({"field": f"{upd.name} · quantity", "op": "change", "from": str(old), "to": str(upd.new_quantity)})
                break

    if patch.set_capacity is not None:
        old = draft.get("capacity", "")
        draft["capacity"] = patch.set_capacity
        diff.append({"field": "Capacity", "op": "change", "from": str(old), "to": str(patch.set_capacity)})

    if patch.set_capacities:
        old = ",".join(str(c) for c in draft.get("capacities", []))
        draft["capacities"] = patch.set_capacities
        diff.append({"field": "Capacities", "op": "change", "from": old, "to": ",".join(str(c) for c in patch.set_capacities)})

    if patch.set_problem_type:
        old = draft.get("problem_type", "")
        draft["problem_type"] = patch.set_problem_type
        diff.append({"field": "Problem type", "op": "change", "from": str(old), "to": patch.set_problem_type})

    if patch.set_time_limit is not None:
        old = draft.get("time_limit_seconds", "")
        draft["time_limit_seconds"] = patch.set_time_limit
        diff.append({"field": "Time limit", "op": "change", "from": str(old), "to": str(patch.set_time_limit)})

    return draft, diff


def apply_binpacking_patch(draft: Dict[str, Any], patch: BinPackingPatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    # Remove items
    for name in patch.remove_item_names:
        before_len = len(draft.get("items", []))
        draft["items"] = [it for it in draft.get("items", []) if it["name"] != name]
        if len(draft.get("items", [])) < before_len:
            diff.append({"field": "Items", "op": "remove", "from": name, "to": ""})

    # Add items
    for item in patch.add_items:
        draft.setdefault("items", []).append({
            "_id": _uid(),
            "name": item.name,
            "size": item.size,
            "width": item.width,
            "height": item.height,
            "depth": item.depth,
            "quantity": item.quantity,
            "can_rotate": item.can_rotate,
        })
        diff.append({"field": "Items", "op": "add", "from": "", "to": item.name})

    # Update items
    for upd in patch.item_updates:
        for it in draft.get("items", []):
            if it["name"] == upd.name:
                if upd.new_size is not None:
                    old = it.get("size", "")
                    it["size"] = upd.new_size
                    diff.append({"field": f"{upd.name} · size", "op": "change", "from": str(old), "to": str(upd.new_size)})
                if upd.new_width is not None:
                    old = it.get("width", "")
                    it["width"] = upd.new_width
                    diff.append({"field": f"{upd.name} · width", "op": "change", "from": str(old), "to": str(upd.new_width)})
                if upd.new_height is not None:
                    old = it.get("height", "")
                    it["height"] = upd.new_height
                    diff.append({"field": f"{upd.name} · height", "op": "change", "from": str(old), "to": str(upd.new_height)})
                if upd.new_depth is not None:
                    old = it.get("depth", "")
                    it["depth"] = upd.new_depth
                    diff.append({"field": f"{upd.name} · depth", "op": "change", "from": str(old), "to": str(upd.new_depth)})
                if upd.new_quantity is not None:
                    old = it.get("quantity", "")
                    it["quantity"] = upd.new_quantity
                    diff.append({"field": f"{upd.name} · quantity", "op": "change", "from": str(old), "to": str(upd.new_quantity)})
                break

    # Remove bin types
    for name in patch.remove_bin_types:
        before_len = len(draft.get("bin_types", []))
        draft["bin_types"] = [bt for bt in draft.get("bin_types", []) if bt["name"] != name]
        if len(draft.get("bin_types", [])) < before_len:
            diff.append({"field": "Bin types", "op": "remove", "from": name, "to": ""})

    # Add bin types
    for bt in patch.add_bin_types:
        draft.setdefault("bin_types", []).append({
            "_id": _uid(),
            "name": bt.name,
            "capacity": bt.capacity,
            "cost": bt.cost,
            "available": bt.available,
        })
        diff.append({"field": "Bin types", "op": "add", "from": "", "to": f"{bt.name} (cap={bt.capacity})"})

    if patch.set_bin_capacity is not None:
        old = draft.get("bin_capacity", "")
        draft["bin_capacity"] = patch.set_bin_capacity
        diff.append({"field": "Bin capacity", "op": "change", "from": str(old), "to": str(patch.set_bin_capacity)})

    if patch.set_bin_width is not None:
        old = draft.get("bin_width", "")
        draft["bin_width"] = patch.set_bin_width
        diff.append({"field": "Bin width", "op": "change", "from": str(old), "to": str(patch.set_bin_width)})

    if patch.set_bin_height is not None:
        old = draft.get("bin_height", "")
        draft["bin_height"] = patch.set_bin_height
        diff.append({"field": "Bin height", "op": "change", "from": str(old), "to": str(patch.set_bin_height)})

    if patch.set_bin_depth is not None:
        old = draft.get("bin_depth", "")
        draft["bin_depth"] = patch.set_bin_depth
        diff.append({"field": "Bin depth", "op": "change", "from": str(old), "to": str(patch.set_bin_depth)})

    if patch.set_problem_type:
        old = draft.get("problem_type", "")
        draft["problem_type"] = patch.set_problem_type
        diff.append({"field": "Problem type", "op": "change", "from": str(old), "to": patch.set_problem_type})

    if patch.set_max_bins is not None:
        old = draft.get("max_bins", "")
        draft["max_bins"] = patch.set_max_bins
        diff.append({"field": "Max bins", "op": "change", "from": str(old), "to": str(patch.set_max_bins)})

    if patch.set_time_limit is not None:
        old = draft.get("time_limit_seconds", "")
        draft["time_limit_seconds"] = patch.set_time_limit
        diff.append({"field": "Time limit", "op": "change", "from": str(old), "to": str(patch.set_time_limit)})

    return draft, diff


def apply_cuttingstock_patch(draft: Dict[str, Any], patch: CuttingStockPatch) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    # Remove orders
    for name in patch.remove_order_names:
        before_len = len(draft.get("orders", []))
        draft["orders"] = [o for o in draft.get("orders", []) if o["name"] != name]
        if len(draft.get("orders", [])) < before_len:
            diff.append({"field": "Orders", "op": "remove", "from": name, "to": ""})

    # Add orders
    for order in patch.add_orders:
        draft.setdefault("orders", []).append({
            "_id": _uid(),
            "name": order.name,
            "length": order.length,
            "quantity": order.quantity,
        })
        diff.append({"field": "Orders", "op": "add", "from": "", "to": f"{order.name} (len={order.length}, qty={order.quantity})"})

    # Update orders
    for upd in patch.order_updates:
        for o in draft.get("orders", []):
            if o["name"] == upd.name:
                if upd.new_length is not None:
                    old = o.get("length", "")
                    o["length"] = upd.new_length
                    diff.append({"field": f"{upd.name} · length", "op": "change", "from": str(old), "to": str(upd.new_length)})
                if upd.new_quantity is not None:
                    old = o.get("quantity", "")
                    o["quantity"] = upd.new_quantity
                    diff.append({"field": f"{upd.name} · quantity", "op": "change", "from": str(old), "to": str(upd.new_quantity)})
                break

    # Remove stock types
    for name in patch.remove_stock_types:
        before_len = len(draft.get("stock_types", []))
        draft["stock_types"] = [st for st in draft.get("stock_types", []) if st["name"] != name]
        if len(draft.get("stock_types", [])) < before_len:
            diff.append({"field": "Stock types", "op": "remove", "from": name, "to": ""})

    # Add stock types
    for st in patch.add_stock_types:
        draft.setdefault("stock_types", []).append({
            "_id": _uid(),
            "name": st.name,
            "length": st.length,
            "cost": st.cost,
            "available": st.available,
        })
        diff.append({"field": "Stock types", "op": "add", "from": "", "to": f"{st.name} (len={st.length})"})

    if patch.set_stock_length is not None:
        old = draft.get("stock_length", "")
        draft["stock_length"] = patch.set_stock_length
        diff.append({"field": "Stock length", "op": "change", "from": str(old), "to": str(patch.set_stock_length)})

    if patch.set_problem_type:
        old = draft.get("problem_type", "")
        draft["problem_type"] = patch.set_problem_type
        diff.append({"field": "Problem type", "op": "change", "from": str(old), "to": patch.set_problem_type})

    if patch.set_max_stocks is not None:
        old = draft.get("max_stocks", "")
        draft["max_stocks"] = patch.set_max_stocks
        diff.append({"field": "Max stocks", "op": "change", "from": str(old), "to": str(patch.set_max_stocks)})

    if patch.set_time_limit is not None:
        old = draft.get("time_limit_seconds", "")
        draft["time_limit_seconds"] = patch.set_time_limit
        diff.append({"field": "Time limit", "op": "change", "from": str(old), "to": str(patch.set_time_limit)})

    return draft, diff


def apply_map_routing_patch(
    draft: Dict[str, Any],
    patch: MapRoutingPatch,
) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    """Apply a MapRoutingPatch to a map routing draft."""
    import copy
    draft = copy.deepcopy(draft)
    diff: List[DiffEntry] = []

    # Clear all POI weights if requested (before applying updates)
    if patch.clear_all_poi_weights:
        old = str(draft.get("poi_preferences", {}))
        draft["poi_preferences"] = {}
        diff.append({"field": "POI preferences", "op": "change", "from": old, "to": "{}"})

    # POI weight updates (add / change individual types)
    for update in patch.update_poi_weights:
        prefs = draft.setdefault("poi_preferences", {})
        old_val = prefs.get(update.poi_type, 0.0)
        new_val = max(0.0, min(1.0, update.weight))
        if new_val == 0.0 and update.poi_type in prefs:
            del prefs[update.poi_type]
            diff.append({
                "field": f"POI weight ({update.poi_type})",
                "op": "remove",
                "from": str(old_val),
                "to": "0",
            })
        else:
            prefs[update.poi_type] = new_val
            diff.append({
                "field": f"POI weight ({update.poi_type})",
                "op": "change" if old_val else "add",
                "from": str(old_val),
                "to": str(new_val),
            })

    if patch.set_distance_weight is not None:
        old = draft.get("distance_weight", "")
        draft["distance_weight"] = max(0.0, min(1.0, patch.set_distance_weight))
        diff.append({"field": "Distance weight", "op": "change", "from": str(old), "to": str(draft["distance_weight"])})

    if patch.set_avoid_highways is not None:
        old = draft.get("avoid_highways", False)
        draft["avoid_highways"] = patch.set_avoid_highways
        diff.append({"field": "Avoid highways", "op": "change", "from": str(old), "to": str(patch.set_avoid_highways)})

    if patch.set_network_type is not None:
        old = draft.get("network_type", "")
        draft["network_type"] = patch.set_network_type
        diff.append({"field": "Network type", "op": "change", "from": str(old), "to": patch.set_network_type})

    if patch.set_search_radius_m is not None:
        old = draft.get("search_radius_m", "")
        draft["search_radius_m"] = patch.set_search_radius_m
        diff.append({"field": "Search radius (m)", "op": "change", "from": str(old), "to": str(patch.set_search_radius_m)})

    if patch.set_start_address is not None:
        old = draft.get("start_address", "")
        draft["start_address"] = patch.set_start_address
        # Reset lat/lng when address changes
        draft["start_lat"] = None
        draft["start_lng"] = None
        diff.append({"field": "Start address", "op": "change", "from": old, "to": patch.set_start_address})

    if patch.set_end_address is not None:
        old = draft.get("end_address", "")
        draft["end_address"] = patch.set_end_address
        draft["end_lat"] = None
        draft["end_lng"] = None
        diff.append({"field": "End address", "op": "change", "from": old, "to": patch.set_end_address})

    if patch.set_time_limit_seconds is not None:
        old = draft.get("time_limit_seconds", "")
        draft["time_limit_seconds"] = patch.set_time_limit_seconds
        diff.append({"field": "Time limit", "op": "change", "from": str(old), "to": str(patch.set_time_limit_seconds)})

    return draft, diff


# ---------------------------------------------------------------------------
# Dispatch table & public API
# ---------------------------------------------------------------------------

_DISPATCH = {
    "scheduling_jssp":      (JsspPatch,      apply_jssp_patch),
    "scheduling_shift":     (ShiftPatch,     apply_shift_patch),
    "scheduling_nurse":     (NursePatch,     apply_nurse_patch),
    "scheduling_timetable": (TimetablePatch, apply_timetable_patch),
    "scheduling_rcpsp":     (RcpspPatch,     apply_rcpsp_patch),
    "routing_tsp":          (RoutingTspPatch,   apply_routing_tsp_patch),
    "routing_vrp":          (RoutingVrpPatch,   apply_routing_vrp_patch),
    "routing_cvrp":         (RoutingCvrpPatch,  apply_routing_cvrp_patch),
    "routing_vrptw":        (RoutingVrptwPatch, apply_routing_vrptw_patch),
    "routing_pdp":          (RoutingPdpPatch,   apply_routing_pdp_patch),
    "packing_knapsack":     (KnapsackPatch,     apply_knapsack_patch),
    "packing_binpacking":   (BinPackingPatch,   apply_binpacking_patch),
    "packing_cuttingstock":          (CuttingStockPatch,  apply_cuttingstock_patch),
    "map_routing_multiobjective":    (MapRoutingPatch,    apply_map_routing_patch),
}


def get_patch_class(algo_id: str):
    """Return the Pydantic patch model class for the given algo_id."""
    entry = _DISPATCH.get(algo_id)
    if entry is None:
        raise ValueError(f"No patch model registered for algo_id '{algo_id}'")
    return entry[0]


def apply_patch(
    algo_id: str,
    draft:   Dict[str, Any],
    patch,
) -> Tuple[Dict[str, Any], List[DiffEntry]]:
    """
    Apply a typed patch object to a form-level draft and return
    (new_draft, diff_entries).

    Raises ValueError for unknown algo_id.
    """
    entry = _DISPATCH.get(algo_id)
    if entry is None:
        raise ValueError(f"No patch applier registered for algo_id '{algo_id}'")
    _, applier_fn = entry
    return applier_fn(draft, patch)
