"""
Typed Patch Models — one closed schema per algorithm type.

These are the ONLY schemas sent to the Gemini API for structured output in the
'modify' phase. Every field is fully typed (str, int, float, bool, List[T] where
T is also a closed model) — no Dict[str, Any], no additionalProperties. This
guarantees zero Gemini schema-validation errors.

Each patch model has:
  - Explicit list fields for additions/removals/updates.
  - Optional scalar fields for global setting changes.
  - A mandatory 'summary' string (one plain-English sentence).

Each model maps 1-to-1 with an apply_* function in patch_applier.py.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# ===========================================================================
# Shared sub-models
# ===========================================================================

class ShiftDef(BaseModel):
    """A shift definition usable by both ShiftPatch and NursePatch."""
    name:           str        = Field(..., description="Shift name e.g. 'Morning'")
    start_hour:     float      = Field(..., description="Start hour 0-23 (e.g. 6.0)")
    end_hour:       float      = Field(..., description="End hour, may exceed 23 for overnight shifts (e.g. 30.0 = 6 AM next day)")
    required_count: int        = Field(1,   description="Minimum staff required per day for this shift")
    days:           List[str]  = Field(default_factory=list, description="Days this shift applies to; empty list means every day")


# ===========================================================================
# A. Job Shop / Machine Scheduling (scheduling_jssp)
# ===========================================================================

class JsspJobTask(BaseModel):
    machine:  str = Field(..., description="Machine name that performs this task")
    duration: int = Field(..., description="Processing time in time units (must be >= 1)")


class JsspJobDef(BaseModel):
    name:     str               = Field(..., description="Unique job name")
    priority: int               = Field(1,    description="Priority weight — higher means more important")
    due_date: Optional[int]     = Field(None, description="Deadline in time units; null if no deadline")
    tasks:    List[JsspJobTask] = Field(...,   description="Ordered list of (machine, duration) operations")


class JsspMachineDef(BaseModel):
    name:  str = Field(..., description="Unique machine name")
    count: int = Field(1,   description="Number of identical parallel copies of this machine")


class JsspPatch(BaseModel):
    """Patch for the Job Shop & Machine Scheduling solver."""
    add_jobs:             List[JsspJobDef]    = Field(default_factory=list, description="New jobs to add to the schedule")
    remove_job_names:     List[str]           = Field(default_factory=list, description="Names of existing jobs to remove")
    add_machines:         List[JsspMachineDef] = Field(default_factory=list, description="New machines to add")
    remove_machine_names: List[str]           = Field(default_factory=list, description="Names of existing machines to remove")
    set_objective:        Optional[str]       = Field(None, description="New objective: 'makespan' or 'weighted_tardiness'; null means no change")
    summary:              str                 = Field(..., description="One plain-English sentence describing all changes made")


# ===========================================================================
# B1. Employee Shift Scheduling (scheduling_shift)
# ===========================================================================

class ShiftEmployeeUpdate(BaseModel):
    """Preference or constraint update for an existing employee."""
    name:                str        = Field(..., description="Exact name of the employee to update")
    preferred_shifts:    List[str]  = Field(default_factory=list, description="New preferred shift names; empty list means no change to preferences")
    requested_days_off:  List[str]  = Field(default_factory=list, description="New requested days off; empty list means no change")
    max_shifts_per_week: Optional[int]   = Field(None, description="New maximum shifts per week for this employee; null means no change")
    max_hours_per_week:  Optional[float] = Field(None, description="New maximum hours per week; null means no change")


class ShiftPatch(BaseModel):
    """Patch for the Employee Shift Scheduling solver."""
    add_employee_names:      List[str]                 = Field(default_factory=list, description="Names of new employees to add with default settings")
    remove_employee_names:   List[str]                 = Field(default_factory=list, description="Names of employees to remove completely")
    add_shifts:              List[ShiftDef]            = Field(default_factory=list, description="New shift types to add to the schedule")
    remove_shift_names:      List[str]                 = Field(default_factory=list, description="Shift names to remove completely")
    employee_updates:        List[ShiftEmployeeUpdate] = Field(default_factory=list, description="Preference or constraint updates for existing employees")
    set_min_rest_hours:      Optional[float]           = Field(None, description="New minimum rest hours required between any two consecutive shifts; null means no change")
    set_max_consecutive_days: Optional[int]            = Field(None, description="New maximum consecutive working days per employee; null means no change")
    summary:                 str                       = Field(..., description="One plain-English sentence describing all changes made")


# ===========================================================================
# B2. Nurse Rostering (scheduling_nurse)
# ===========================================================================

class NurseSkillUpdate(BaseModel):
    """Update the skill list for an existing nurse."""
    name:   str       = Field(..., description="Exact name of the nurse to update")
    skills: List[str] = Field(..., description="Complete new skill list replacing the old one (e.g. ['head_nurse', 'specialist'])")


class NursePatch(BaseModel):
    """Patch for the Nurse Rostering solver."""
    add_nurse_names:          List[str]             = Field(default_factory=list, description="Names of new nurses to add with trainee skill level")
    remove_nurse_names:       List[str]             = Field(default_factory=list, description="Names of nurses to remove from the roster")
    add_shifts:               List[ShiftDef]        = Field(default_factory=list, description="New shift types to add")
    remove_shift_names:       List[str]             = Field(default_factory=list, description="Shift names to remove")
    nurse_skill_updates:      List[NurseSkillUpdate] = Field(default_factory=list, description="Update skills for existing nurses")
    set_max_consecutive_days: Optional[int]         = Field(None, description="New maximum consecutive shifts; null means no change")
    set_min_rest_hours:       Optional[float]       = Field(None, description="New minimum rest hours between shifts; null means no change")
    summary:                  str                   = Field(..., description="One plain-English sentence describing all changes made")


# ===========================================================================
# C. Educational Timetabling (scheduling_timetable)
# ===========================================================================

class TeacherUnavailOp(BaseModel):
    """Add or remove a specific unavailability block for a teacher."""
    teacher: str = Field(..., description="Exact teacher name")
    op:      str = Field(..., description="'add' to mark this slot unavailable, 'remove' to make this slot available again")
    day:     str = Field(..., description="Full day name with capital first letter e.g. 'Monday', 'Tuesday'")
    slot:    int = Field(..., description="0-indexed period number (0 = first period of the day)")


class SubjectPeriodChange(BaseModel):
    """Change the number of periods per week per class for a subject."""
    subject_name:         str = Field(..., description="Exact subject name to modify")
    new_periods_per_week: int = Field(..., description="New number of periods per week per class (must be >= 1)")


class TeacherSubjectOp(BaseModel):
    """Add/remove a single subject qualification for a teacher."""
    teacher: str = Field(..., description="Exact teacher name")
    op:      str = Field(..., description="'add' to add qualification, 'remove' to remove qualification")
    subject: str = Field(..., description="Exact subject name")


class RoomDef(BaseModel):
    """Room definition used when adding new rooms."""
    name:     str = Field(..., description="Unique room name")
    capacity: int = Field(..., description="Maximum room capacity")


class RoomCapacityChange(BaseModel):
    """Change capacity for an existing room."""
    room_name:    str = Field(..., description="Exact room name")
    new_capacity: int = Field(..., description="New room capacity")


class SubjectConsecutiveChange(BaseModel):
    """Set whether a subject must be scheduled in consecutive periods."""
    subject_name:    str  = Field(..., description="Exact subject name")
    new_consecutive: bool = Field(..., description="True if subject needs consecutive periods")


class SubjectMergeGroupOp(BaseModel):
    """Add/remove one merge group for a subject."""
    subject_name: str       = Field(..., description="Exact subject name")
    op:           str       = Field(..., description="'add' to add group, 'remove' to remove group")
    class_ids:    List[str] = Field(default_factory=list, description="Class IDs in this merge group (e.g. ['10-A','10-B'])")


class SubjectDef(BaseModel):
    """Subject definition used for subject additions."""
    name:                  str       = Field(..., description="Unique subject name")
    periods_per_week:      int       = Field(..., description="Required periods per week per class")
    consecutive:           bool      = Field(False, description="Whether periods must be back-to-back")
    mergeable_groups:      List[str] = Field(default_factory=list, description="Optional class-merge groups encoded as comma-joined tokens, e.g. ['10-A,10-B']")


class TimetablePatch(BaseModel):
    """Patch for the Educational Timetabling solver."""
    add_teacher_names:      List[str]                  = Field(default_factory=list, description="New teacher names to add (empty subject list — must be set in the form)")
    remove_teacher_names:   List[str]                  = Field(default_factory=list, description="Teacher names to remove completely")
    teacher_subject_ops:    List[TeacherSubjectOp]     = Field(default_factory=list, description="Add/remove teacher subject qualifications")
    add_class_ids:          List[str]                  = Field(default_factory=list, description="New class IDs to add e.g. '11-A', '10-D'")
    remove_class_ids:       List[str]                  = Field(default_factory=list, description="Class IDs to remove completely")
    teacher_unavail_ops:    List[TeacherUnavailOp]     = Field(default_factory=list, description="Add or remove specific unavailability slots for teachers")
    add_rooms:              List[RoomDef]              = Field(default_factory=list, description="New rooms to add")
    remove_room_names:      List[str]                  = Field(default_factory=list, description="Room names to remove")
    room_capacity_changes:  List[RoomCapacityChange]   = Field(default_factory=list, description="Capacity changes for existing rooms")
    add_subjects:           List[SubjectDef]           = Field(default_factory=list, description="New subjects to add")
    remove_subject_names:   List[str]                  = Field(default_factory=list, description="Subject names to remove")
    subject_period_changes: List[SubjectPeriodChange]  = Field(default_factory=list, description="Change periods/week for specific subjects")
    subject_consecutive_changes: List[SubjectConsecutiveChange] = Field(default_factory=list, description="Set consecutive-period requirement for subjects")
    subject_merge_group_ops: List[SubjectMergeGroupOp] = Field(default_factory=list, description="Add/remove merge groups for subjects")
    set_slots_per_day:      Optional[int]              = Field(None, description="New number of periods per school day; null means no change")
    set_days:               List[str]                  = Field(default_factory=list, description="Completely replace the list of school days; empty list means no change")
    summary:                str                        = Field(..., description="One plain-English sentence describing all changes made")


# ===========================================================================
# D. Routing
# ===========================================================================

class NodeDemandChange(BaseModel):
    node_index: int = Field(..., description="0-based node index")
    new_demand: int = Field(..., description="Updated demand at this node")


class TimeWindowChange(BaseModel):
    node_index: int = Field(..., description="0-based node index")
    start:      int = Field(..., description="Earliest arrival time")
    end:        int = Field(..., description="Latest arrival time")


class PickupDeliveryPairDef(BaseModel):
    pickup_index:   int = Field(..., description="Pickup node index")
    delivery_index: int = Field(..., description="Delivery node index")


class RoutingTspPatch(BaseModel):
    set_depot:              Optional[int]  = Field(None, description="New depot node index")
    set_time_limit_seconds: Optional[int]  = Field(None, description="Solver time limit in seconds")
    scale_distance_percent: Optional[int]  = Field(None, description="Scale all matrix costs by this percent")
    summary:                str            = Field(..., description="One plain-English sentence describing all changes made")


class RoutingVrpPatch(BaseModel):
    set_num_vehicles:       Optional[int]  = Field(None, description="New number of vehicles")
    set_depot:              Optional[int]  = Field(None, description="New depot node index")
    set_max_route_distance: Optional[int]  = Field(None, description="Per-vehicle route distance cap")
    set_time_limit_seconds: Optional[int]  = Field(None, description="Solver time limit in seconds")
    scale_distance_percent: Optional[int]  = Field(None, description="Scale all matrix costs by this percent")
    summary:                str            = Field(..., description="One plain-English sentence describing all changes made")


class RoutingCvrpPatch(BaseModel):
    set_num_vehicles:       Optional[int]           = Field(None, description="New number of vehicles")
    set_depot:              Optional[int]           = Field(None, description="New depot node index")
    set_vehicle_capacities: List[int]               = Field(default_factory=list, description="Replace all vehicle capacities")
    demand_changes:         List[NodeDemandChange]  = Field(default_factory=list, description="Per-node demand updates")
    set_time_limit_seconds: Optional[int]           = Field(None, description="Solver time limit in seconds")
    scale_distance_percent: Optional[int]           = Field(None, description="Scale all matrix costs by this percent")
    summary:                str                     = Field(..., description="One plain-English sentence describing all changes made")


class RoutingVrptwPatch(BaseModel):
    set_num_vehicles:         Optional[int]           = Field(None, description="New number of vehicles")
    set_depot:                Optional[int]           = Field(None, description="New depot node index")
    time_window_changes:      List[TimeWindowChange]  = Field(default_factory=list, description="Per-node time-window updates")
    service_time_changes:     List[NodeDemandChange]  = Field(default_factory=list, description="Per-node service-time updates (reuse new_demand as new service time)")
    set_max_waiting_time:     Optional[int]           = Field(None, description="Maximum waiting time")
    set_max_time_per_vehicle: Optional[int]           = Field(None, description="Maximum route horizon per vehicle")
    set_time_limit_seconds:   Optional[int]           = Field(None, description="Solver time limit in seconds")
    summary:                  str                     = Field(..., description="One plain-English sentence describing all changes made")


class RoutingPdpPatch(BaseModel):
    set_num_vehicles:       Optional[int]                = Field(None, description="New number of vehicles")
    set_depot:              Optional[int]                = Field(None, description="New depot node index")
    set_vehicle_capacities: List[int]                    = Field(default_factory=list, description="Replace all vehicle capacities")
    demand_changes:         List[NodeDemandChange]       = Field(default_factory=list, description="Per-node demand updates")
    add_pairs:              List[PickupDeliveryPairDef]  = Field(default_factory=list, description="Pickup-delivery pairs to add")
    remove_pairs:           List[PickupDeliveryPairDef]  = Field(default_factory=list, description="Pickup-delivery pairs to remove")
    set_time_limit_seconds: Optional[int]                = Field(None, description="Solver time limit in seconds")
    scale_distance_percent: Optional[int]                = Field(None, description="Scale all matrix costs by this percent")
    summary:                str                          = Field(..., description="One plain-English sentence describing all changes made")


# ===========================================================================
# E. RCPSP — Resource-Constrained Project Scheduling (scheduling_rcpsp)
# ===========================================================================

class RcpspActivityDef(BaseModel):
    """A new project activity to add."""
    name:         str       = Field(..., description="Unique activity name")
    duration:     int       = Field(..., description="Duration in time units (must be >= 1)")
    predecessors: List[str] = Field(default_factory=list, description="Names of activities that must complete before this one starts")


class RcpspActivityUpdate(BaseModel):
    """Update properties of an existing project activity."""
    name:                str       = Field(..., description="Exact activity name to update")
    new_duration:        Optional[int] = Field(None, description="New duration if changing it; null means keep current")
    add_predecessors:    List[str] = Field(default_factory=list, description="Activity names to add as new predecessors")
    remove_predecessors: List[str] = Field(default_factory=list, description="Activity names to remove from predecessors")


class RcpspResourceCapacityChange(BaseModel):
    """Change the maximum capacity of a shared resource."""
    resource_name: str = Field(..., description="Exact resource name e.g. 'Workers', 'Cranes'")
    new_capacity:  int = Field(..., description="New maximum simultaneous units of this resource")


class RcpspPatch(BaseModel):
    """Patch for the RCPSP Project Scheduling solver."""
    add_activities:            List[RcpspActivityDef]           = Field(default_factory=list, description="New project activities to add")
    remove_activity_names:     List[str]                        = Field(default_factory=list, description="Activity names to remove")
    activity_updates:          List[RcpspActivityUpdate]        = Field(default_factory=list, description="Duration or precedence changes for existing activities")
    resource_capacity_changes: List[RcpspResourceCapacityChange] = Field(default_factory=list, description="Change capacity limits for existing resources")
    summary:                   str                              = Field(..., description="One plain-English sentence describing all changes made")


# ===========================================================================
# F. Packing & Knapsack
# ===========================================================================

# ---------------------------------------------------------------------------
# F1. Knapsack Problem (packing_knapsack)
# ---------------------------------------------------------------------------

class KnapsackItemDef(BaseModel):
    """Definition of an item to add to knapsack problem."""
    name:     str           = Field(..., description="Unique item name")
    value:    int           = Field(..., description="Value/profit of item")
    weight:   int           = Field(..., description="Weight/size of item")
    quantity: int           = Field(1, description="Available quantity (for bounded knapsack)")


class KnapsackItemUpdate(BaseModel):
    """Update properties of an existing item."""
    name:         str           = Field(..., description="Exact item name to update")
    new_value:    Optional[int] = Field(None, description="New value; null means no change")
    new_weight:   Optional[int] = Field(None, description="New weight; null means no change")
    new_quantity: Optional[int] = Field(None, description="New quantity; null means no change")


class KnapsackPatch(BaseModel):
    """Patch for the Knapsack Problem solver."""
    add_items:           List[KnapsackItemDef]    = Field(default_factory=list, description="New items to add")
    remove_item_names:   List[str]                = Field(default_factory=list, description="Item names to remove")
    item_updates:        List[KnapsackItemUpdate] = Field(default_factory=list, description="Value/weight/quantity changes for existing items")
    set_capacity:        Optional[int]            = Field(None, description="New knapsack capacity; null means no change")
    set_capacities:      List[int]                = Field(default_factory=list, description="Replace all knapsack capacities (for multiple knapsack); empty means no change")
    set_problem_type:    Optional[str]            = Field(None, description="Change problem type: '0-1', 'bounded', 'unbounded', 'multiple', 'multidimensional'")
    set_time_limit:      Optional[int]            = Field(None, description="New solver time limit in seconds")
    summary:             str                      = Field(..., description="One plain-English sentence describing all changes made")


# ---------------------------------------------------------------------------
# F2. Bin Packing Problem (packing_binpacking)
# ---------------------------------------------------------------------------

class BinPackingItemDef(BaseModel):
    """Definition of an item to add to bin packing problem."""
    name:       str  = Field(..., description="Unique item name")
    size:       int  = Field(0, description="Item size (for 1D)")
    width:      int  = Field(0, description="Item width (for 2D/3D)")
    height:     int  = Field(0, description="Item height (for 2D/3D)")
    depth:      int  = Field(0, description="Item depth (for 3D)")
    quantity:   int  = Field(1, description="Number of identical items")
    can_rotate: bool = Field(True, description="Whether item can be rotated (2D/3D)")


class BinPackingItemUpdate(BaseModel):
    """Update properties of an existing item."""
    name:         str           = Field(..., description="Exact item name to update")
    new_size:     Optional[int] = Field(None, description="New size (1D); null means no change")
    new_width:    Optional[int] = Field(None, description="New width (2D/3D); null means no change")
    new_height:   Optional[int] = Field(None, description="New height (2D/3D); null means no change")
    new_depth:    Optional[int] = Field(None, description="New depth (3D); null means no change")
    new_quantity: Optional[int] = Field(None, description="New quantity; null means no change")


class BinTypeDef(BaseModel):
    """Definition of a bin type for variable bin packing."""
    name:      str = Field(..., description="Bin type name")
    capacity:  int = Field(..., description="Bin capacity")
    cost:      int = Field(1, description="Cost per bin of this type")
    available: int = Field(100, description="Number of bins available")


class BinPackingPatch(BaseModel):
    """Patch for the Bin Packing Problem solver."""
    add_items:           List[BinPackingItemDef]   = Field(default_factory=list, description="New items to add")
    remove_item_names:   List[str]                 = Field(default_factory=list, description="Item names to remove")
    item_updates:        List[BinPackingItemUpdate] = Field(default_factory=list, description="Size/dimension changes for existing items")
    add_bin_types:       List[BinTypeDef]          = Field(default_factory=list, description="New bin types to add (variable bin packing)")
    remove_bin_types:    List[str]                 = Field(default_factory=list, description="Bin type names to remove")
    set_bin_capacity:    Optional[int]             = Field(None, description="New bin capacity (1D); null means no change")
    set_bin_width:       Optional[int]             = Field(None, description="New bin width (2D/3D); null means no change")
    set_bin_height:      Optional[int]             = Field(None, description="New bin height (2D/3D); null means no change")
    set_bin_depth:       Optional[int]             = Field(None, description="New bin depth (3D); null means no change")
    set_problem_type:    Optional[str]             = Field(None, description="Change problem type: '1d', '2d', '3d', 'variable'")
    set_max_bins:        Optional[int]             = Field(None, description="New upper bound on bins")
    set_time_limit:      Optional[int]             = Field(None, description="New solver time limit in seconds")
    summary:             str                       = Field(..., description="One plain-English sentence describing all changes made")


# ---------------------------------------------------------------------------
# F3. Cutting Stock Problem (packing_cuttingstock)
# ---------------------------------------------------------------------------

class CuttingStockOrderDef(BaseModel):
    """Definition of an order for cutting stock problem."""
    name:     str = Field(..., description="Order/piece name")
    length:   int = Field(..., description="Required piece length")
    quantity: int = Field(1, description="Quantity needed")


class CuttingStockOrderUpdate(BaseModel):
    """Update properties of an existing order."""
    name:         str           = Field(..., description="Exact order name to update")
    new_length:   Optional[int] = Field(None, description="New piece length; null means no change")
    new_quantity: Optional[int] = Field(None, description="New quantity needed; null means no change")


class StockTypeDef(BaseModel):
    """Definition of a stock type for multi-stock cutting."""
    name:      str = Field(..., description="Stock type name")
    length:    int = Field(..., description="Stock length")
    cost:      int = Field(1, description="Cost per stock unit")
    available: int = Field(100, description="Units available")


class CuttingStockPatch(BaseModel):
    """Patch for the Cutting Stock Problem solver."""
    add_orders:          List[CuttingStockOrderDef]   = Field(default_factory=list, description="New orders to add")
    remove_order_names:  List[str]                    = Field(default_factory=list, description="Order names to remove")
    order_updates:       List[CuttingStockOrderUpdate] = Field(default_factory=list, description="Length/quantity changes for existing orders")
    add_stock_types:     List[StockTypeDef]           = Field(default_factory=list, description="New stock types to add (multi-stock)")
    remove_stock_types:  List[str]                    = Field(default_factory=list, description="Stock type names to remove")
    set_stock_length:    Optional[int]                = Field(None, description="New stock length (single stock); null means no change")
    set_problem_type:    Optional[str]                = Field(None, description="Change problem type: '1d', 'multi-stock'")
    set_max_stocks:      Optional[int]                = Field(None, description="New upper bound on stocks")
    set_time_limit:      Optional[int]                = Field(None, description="New solver time limit in seconds")
    summary:             str                          = Field(..., description="One plain-English sentence describing all changes made")


# ---------------------------------------------------------------------------
# F. MAP ROUTING — Multi-Objective Real-World Navigation
# ---------------------------------------------------------------------------

class PoiWeightUpdate(BaseModel):
    """Update the weight for a single POI type in the map routing problem."""
    poi_type: str   = Field(..., description="POI type name (e.g. 'restaurant', 'cafe', 'park')")
    weight:   float = Field(..., description="New weight value between 0.0 (ignore) and 1.0 (strongly prefer)")


class MapRoutingPatch(BaseModel):
    """Patch for the Multi-Objective Map Routing solver."""
    update_poi_weights:     List[PoiWeightUpdate]      = Field(
        default_factory=list,
        description=(
            "Set or update POI type weights. Each entry sets the weight for one POI type. "
            "To add restaurants and cafes, use: [{poi_type:'restaurant', weight:0.8}, {poi_type:'cafe', weight:0.5}]. "
            "Available types: restaurant, cafe, park, museum, hospital, bar, pub, fast_food, "
            "supermarket, pharmacy, school, bank, hotel, cinema, theatre, fuel, parking. "
            "Weight 0.0 = ignore, 1.0 = strongly prefer. Set weight to 0 to remove a POI type."
        ),
    )
    clear_all_poi_weights:  bool                       = Field(
        False,
        description="Set to true to clear ALL existing POI preferences before applying update_poi_weights. Use when replacing all POI types."
    )
    set_distance_weight:    Optional[float]            = Field(
        None,
        description="New distance penalty (0.0 = ignore distance, 1.0 = shortest path only)"
    )
    set_avoid_highways:     Optional[bool]             = Field(
        None,
        description="True to exclude motorways and trunk roads, False to allow"
    )
    set_network_type:       Optional[str]              = Field(
        None,
        description="Change travel mode: 'drive' | 'walk' | 'bike'"
    )
    set_search_radius_m:    Optional[int]              = Field(
        None,
        description="New POI attraction radius in metres"
    )
    set_start_address:      Optional[str]              = Field(
        None,
        description="New origin address or place name"
    )
    set_end_address:        Optional[str]              = Field(
        None,
        description="New destination address or place name"
    )
    set_time_limit_seconds: Optional[int]              = Field(
        None,
        description="New solver time limit in seconds"
    )
    summary:                str                        = Field(
        ...,
        description="One plain-English sentence describing all changes made"
    )

