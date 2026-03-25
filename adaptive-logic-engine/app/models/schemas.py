"""
Pydantic Data Models
Defines the strict schema contract between the LLM and the solver pipeline,
plus models for the multi-step conversational chat flow.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Domain Enum
# ---------------------------------------------------------------------------

class ProblemDomain(str, Enum):
    """
    Classifies the type of optimization problem detected in the user's text.
    Using `str` as a mixin keeps JSON serialization clean (emits string value,
    not {"value": "SCHEDULING", "name": "SCHEDULING"}).
    """
    SCHEDULING = "SCHEDULING"
    ROUTING    = "ROUTING"
    ASSIGNMENT = "ASSIGNMENT"


# ---------------------------------------------------------------------------
# Constraint Models
# ---------------------------------------------------------------------------

class SchedulingConstraint(BaseModel):
    """
    A single constraint extracted from the user's natural-language input.

    Fields
    ------
    constraint_type : str
        Semantic category of the constraint.
        Supported values: ``"unavailable"`` | ``"required"`` | ``"preferred"``.
    teacher : str
        Name of the teacher this constraint applies to.
    day : Optional[str]
        Day-of-week (e.g. "Monday").  ``None`` means *all days*.
    time_slot : Optional[str]
        Time slot label (e.g. "9AM", "12PM", "3PM").  ``None`` means *all slots*.
    """
    constraint_type: str = Field(
        ...,
        description="Type of constraint: 'unavailable', 'required', or 'preferred'.",
    )
    teacher: str = Field(
        ...,
        description="Full name of the teacher the constraint targets.",
    )
    day: Optional[str] = Field(
        default=None,
        description="Day of the week (e.g. 'Monday'). Null means all days.",
    )
    time_slot: Optional[str] = Field(
        default=None,
        description="Time slot label (e.g. '9AM', '12PM', '3PM'). Null means all slots.",
    )


# ---------------------------------------------------------------------------
# Request / Response wrappers
# ---------------------------------------------------------------------------

class OptimizationRequest(BaseModel):
    """
    The inbound payload sent by the API consumer.

    Fields
    ------
    text : str
        Raw, unconstrained natural-language description of the scheduling
        problem (e.g. "Alice can't teach on Mondays. Bob must cover the 9 AM
        slot on Wednesdays.").
    """
    text: str = Field(
        ...,
        min_length=10,
        description="Natural-language description of the optimization problem.",
        examples=[
            "Alice is unavailable on Monday at 9AM. "
            "Bob must teach the 12PM slot on Wednesday."
        ],
    )


class LLMExtractionResult(BaseModel):
    """
    The structured payload that the LLM **must** return.

    The Gemini SDK's ``response_schema`` parameter enforces this structure,
    ensuring deterministic downstream parsing with no hallucinated fields.

    Fields
    ------
    domain      : ProblemDomain   — Detected problem category.
    constraints : list[SchedulingConstraint] — All extracted rules.
    """
    domain: ProblemDomain = Field(
        ...,
        description="The detected optimization domain.",
    )
    constraints: List[SchedulingConstraint] = Field(
        default_factory=list,
        description="Ordered list of constraints extracted from the user text.",
    )


# ===========================================================================
# Chat / Conversational Flow Models
# ===========================================================================

class ChatRequest(BaseModel):
    """Inbound payload for the /api/chat endpoint."""
    message: str = Field(
        ...,
        min_length=3,
        description="The user's natural-language message.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Opaque session token so the frontend can maintain state.",
    )
    # Phase context sent back by the frontend after the first turn
    algo_id: Optional[str] = Field(
        default=None,
        description="Algorithm id if the user has already been shown a match.",
    )
    phase: Optional[str] = Field(
        default=None,
        description=(
            "Conversation phase: 'match' | 'confirm' | 'modify' | 'solve'. "
            "None means first message."
        ),
    )


class AlgoMatchResult(BaseModel):
    """LLM-structured response for the problem → algorithm matching step."""
    matched: bool = Field(
        ...,
        description="True if at least one algorithm can solve this problem.",
    )
    algo_id: Optional[str] = Field(
        default=None,
        description="The id of the best matching algorithm, or null if none.",
    )
    confidence: Optional[str] = Field(
        default=None,
        description="'high' | 'medium' | 'low' — how confident the match is.",
    )
    reasoning: str = Field(
        ...,
        description=(
            "1-2 sentence plain-English explanation of why this algorithm matches "
            "(or why no algorithm is available)."
        ),
    )


class SmartChatResult(BaseModel):
    """
    LLM response for the intelligent conversational chat handler.

    Gemini detects the user's intent and generates an appropriate response.
    For algorithm problems it also sets matched/algo_id/confidence.
    """
    intent: str = Field(
        ...,
        description=(
            "Intent category: 'algorithm_problem' | 'app_overview' | 'algo_list' | "
            "'greeting' | 'unrelated' | 'general_chat'"
        ),
    )
    matched: bool = Field(
        default=False,
        description="True only when intent='algorithm_problem' AND a matching algorithm exists.",
    )
    algo_id: Optional[str] = Field(
        default=None,
        description="Best matching algorithm id — set only when matched=true.",
    )
    confidence: Optional[str] = Field(
        default=None,
        description="'high' | 'medium' | 'low' — only set when matched=true.",
    )
    message: str = Field(
        ...,
        description=(
            "The full conversational response to show the user. "
            "For algorithm_problem+matched=true: write only a 1-2 sentence natural intro "
            "(the structured algorithm card will be appended automatically). "
            "For all other cases: write the complete, helpful response."
        ),
    )


class AlgoModification(BaseModel):
    """
    Legacy modification envelope kept for backwards-compat; also used by
    routes.py as the serialisable wrapper around typed patch summaries.
    """
    modified_constraints: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Updated constraint objects.",
    )
    modified_variables: Dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value pairs of algorithm variables changed.",
    )
    summary: str = Field(
        ...,
        description="Human-readable, one-sentence summary of what was changed.",
    )


class PatchDiffEntry(BaseModel):
    """One line in the structured diff displayed to the user after a modify step."""
    field: str = Field(..., description="Name of the field or entity that changed.")
    op:    str = Field(..., description="'add' | 'remove' | 'change'")
    from_: str = Field(..., alias="from", description="Previous value (empty string for add).")
    to:    str = Field(...,               description="New value (empty string for remove).")

    model_config = {"populate_by_name": True}



class ChatResponse(BaseModel):
    """Unified response envelope for all /api/chat turns."""
    phase: str = Field(
        ...,
        description=(
            "Current pipeline phase: "
            "'no_match' | 'algo_found' | 'modified' | 'ready_to_solve'."
        ),
    )
    message: str = Field(
        ...,
        description="The assistant reply shown in the chat bubble.",
    )
    algo_id:        Optional[str]              = None
    algo_details:   Optional[Dict[str, Any]]   = None   # Full algo metadata
    modification:   Optional[Dict[str, Any]]   = None   # Legacy summary dict
    patch_diff:     Optional[List[Dict[str, str]]] = None  # Structured diff entries for UI
    effective_draft: Optional[Dict[str, Any]]  = None   # Updated form-state after patch applied
    session_id:     Optional[str]              = None
