"""
FastAPI Routes
Defines the full HTTP API surface for the optimization engine.

Endpoints
---------
POST /api/chat             — Main conversational pipeline (multi-phase)
POST /api/solve            — Structured solver invocation (primary solve path)
POST /api/solve/substitute — Find substitute teachers for an absent staff member
POST /api/optimize         — Legacy single-shot optimization (kept for compatibility)
GET  /api/health           — Health check
"""

import logging
import time
import uuid
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.dispatcher import execute_optimization, execute_solve
from app.core.llm_service import extract_constraints, smart_chat, parse_modification
from app.core.algo_context import ALGO_BY_ID
from app.core.session_store import create_session, get_session, get_or_create, update_draft
from app.core.patch_applier import apply_patch
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    OptimizationRequest,
)


class SolveRequest(BaseModel):
    algo_id: str
    inputs: Dict[str, Any]


class SubstituteRequest(BaseModel):
    timetable_result: Dict[str, Any]
    absent_teacher:   str
    absent_day:       str
    teachers_data:    list


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Optimization"])


# ===========================================================================
# POST /api/chat  — Conversational pipeline (the main endpoint)
# ===========================================================================

@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Multi-phase conversational optimization pipeline",
    status_code=status.HTTP_200_OK,
)
async def chat(request: ChatRequest):
    """
    **Conversational optimization pipeline — all phases handled here.**

    ### Phases
    | phase (sent by client) | What happens |
    |------------------------|--------------|
    | `None` (first message) | Gemini matches problem to an algorithm |
    | `confirm`              | User confirmed the algo → returns ready_to_solve |
    | `modify`               | User wants to tweak → Gemini parses modifications |

    ### Phase flow
    ```
    User sends problem
        └─► Gemini matches → no_match  (sorry message) or algo_found (show capabilities)
    User says "yes" / "looks good"
        └─► [phase=confirm] → ready_to_solve (frontend navigates to /solve/{algo_id})
    User says "change X to Y"
        └─► [phase=modify]  → modified   (show updated capabilities, ask for confirm)
    ```
    """
    session_id = request.session_id or str(uuid.uuid4())

    # -----------------------------------------------------------------------
    # Phase: FIRST MESSAGE — smart intent detection + conversational response
    # -----------------------------------------------------------------------
    if request.phase is None or request.phase == "match":
        try:
            result = await smart_chat(request.message)
        except Exception as exc:
            logger.error("Smart chat failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI service error: {exc}",
            )

        # Non-algorithm intents (greeting, app_overview, algo_list, unrelated, general_chat)
        # → return Gemini's response directly, no algorithm card
        if result.intent != "algorithm_problem":
            return ChatResponse(
                phase="general_chat",
                session_id=session_id,
                message=result.message,
            )

        # Algorithm problem but no match found
        if not result.matched or not result.algo_id:
            return ChatResponse(
                phase="no_match",
                session_id=session_id,
                message=result.message,
            )

        # Algorithm match found — build the full structured card
        algo = ALGO_BY_ID.get(result.algo_id)
        if not algo:
            raise HTTPException(status_code=500, detail=f"Unknown algo_id '{result.algo_id}' returned by AI.")

        is_planned = algo.get("status") == "planned"
        if is_planned:
            return ChatResponse(
                phase="no_match",
                session_id=session_id,
                message=(
                    f"{result.message}\n\n"
                    f"However, **{algo['name']}** hasn't been implemented yet — it's on our roadmap.\n\n"
                    "Currently live: **Timetable Scheduling**, **Machine Scheduling**, "
                    "**Shift/Nurse Rostering**, **RCPSP**, **Vehicle Routing** (TSP/VRP/CVRP/VRPTW/PDP), "
                    "**Knapsack**, **Bin Packing**, and **Cutting Stock**."
                ),
                algo_id=result.algo_id,
                algo_details=algo,
            )

        # Create / reset session with default draft for this algo
        create_session(session_id, result.algo_id)
        capabilities_text = "\n".join(f"• {c}" for c in algo["capabilities"])
        constraints_text  = "\n".join(f"• {c}" for c in algo["constraints"])
        limitations_text  = "\n".join(f"• {lim}" for lim in algo["limitations"])

        reply = (
            f"{result.message}\n\n"
            f"**{algo['name']}** *(Confidence: {result.confidence})*\n\n"
            f"{algo['description']}\n\n"
            f"**What it can do:**\n{capabilities_text}\n\n"
            f"**Supported constraints:**\n{constraints_text}\n\n"
            f"**Objective:** {algo['objective']}\n\n"
            f"**Limitations:**\n{limitations_text}\n\n"
            "---\n"
            "Does this look right? Reply **\"yes\"** to proceed with inputs, "
            "or describe any changes you'd like to make."
        )

        return ChatResponse(
            phase="algo_found",
            session_id=session_id,
            algo_id=result.algo_id,
            algo_details=algo,
            message=reply,
        )

    # -----------------------------------------------------------------------
    # Phase: CONFIRM — user is satisfied, navigate to solver input page
    # -----------------------------------------------------------------------
    if request.phase == "confirm":
        algo_id = request.algo_id
        if not algo_id or algo_id not in ALGO_BY_ID:
            raise HTTPException(status_code=400, detail="Missing or unknown algo_id for confirm phase.")

        algo = ALGO_BY_ID[algo_id]

        # Return the effective (AI-patched) draft so the solve page can pre-fill
        session = get_session(session_id)
        effective_draft = session.draft if session else None

        return ChatResponse(
            phase="ready_to_solve",
            session_id=session_id,
            algo_id=algo_id,
            algo_details=algo,
            effective_draft=effective_draft,
            message=(
                f"Let's go! I'll take you to the **{algo['name']}** input form. "
                "Your AI-configured parameters are pre-filled and ready to solve."
            ),
        )

    # -----------------------------------------------------------------------
    # Phase: MODIFY — user wants to change constraints/variables
    # -----------------------------------------------------------------------
    if request.phase == "modify":
        algo_id = request.algo_id
        if not algo_id or algo_id not in ALGO_BY_ID:
            raise HTTPException(status_code=400, detail="Missing or unknown algo_id for modify phase.")

        # Retrieve or create session first so modification parsing can use current entities.
        session = get_or_create(session_id, algo_id)

        try:
            patch = await parse_modification(request.message, algo_id, session.draft)
        except Exception as exc:
            logger.error("Modification parsing failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI modification parsing error: {exc}",
            )

        # Apply patch deterministically
        try:
            new_draft, diff_entries = apply_patch(algo_id, session.draft, patch)
        except Exception as exc:
            logger.error("Patch apply failed: %s", exc)
            new_draft    = session.draft
            diff_entries = []

        update_draft(session_id, new_draft, patch.summary)

        algo = ALGO_BY_ID[algo_id]

        # Build friendly reply with inline diff
        reply = f"Got it! Here's what changed:\n\n**{patch.summary}**\n\n"
        if diff_entries:
            for entry in diff_entries[:10]:
                op_icon = {"add": "+", "remove": "−", "change": "→"}.get(entry["op"], "•")
                if entry["op"] == "add":
                    reply += f"  `{op_icon}` **{entry['field']}** → *{entry['to']}*\n"
                elif entry["op"] == "remove":
                    reply += f"  `{op_icon}` **{entry['field']}** ~~{entry['from']}~~ removed\n"
                else:
                    reply += f"  `{op_icon}` **{entry['field']}**: {entry['from']} → {entry['to']}\n"
            if len(diff_entries) > 10:
                reply += f"  … and {len(diff_entries) - 10} more change(s).\n"
        else:
            reply += "_(No recognisable changes were extracted — please rephrase your request.)_\n"

        reply += "\nDoes that look right? Reply **\"yes\"** to proceed or keep describing changes."

        return ChatResponse(
            phase="modified",
            session_id=session_id,
            algo_id=algo_id,
            algo_details=algo,
            modification={"summary": patch.summary},
            patch_diff=diff_entries,
            effective_draft=new_draft,
            message=reply,
        )

    raise HTTPException(status_code=400, detail=f"Unknown phase '{request.phase}'.")


# ===========================================================================
# POST /api/solve  — Structured solver (primary solve path)
# ===========================================================================

@router.post(
    "/solve",
    summary="Run a solver with structured inputs",
    status_code=status.HTTP_200_OK,
)
async def solve(request: SolveRequest):
    """
    Primary solve endpoint. Accepts structured JSON inputs (from the frontend
    dynamic form) and dispatches to the correct OR-Tools solver.

    Supported algo_id values: scheduling_jssp, scheduling_shift, scheduling_nurse,
    scheduling_timetable, scheduling_rcpsp (more coming).
    """
    algo_id = request.algo_id
    if algo_id not in ALGO_BY_ID and not algo_id.endswith("_substitute"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown algo_id '{algo_id}'. See GET /api/health for available algorithms.",
        )

    start_t = time.perf_counter()
    try:
        result = execute_solve(algo_id, request.inputs)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Solver error for algo_id=%s: %s", algo_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Solver error: {exc}",
        )

    elapsed = round(time.perf_counter() - start_t, 3)
    result["solve_time_seconds"] = elapsed
    return result


# ===========================================================================
# POST /api/solve/substitute  — Substitute teacher lookup
# ===========================================================================

@router.post(
    "/solve/substitute",
    summary="Find substitute teachers for an absent staff member",
    status_code=status.HTTP_200_OK,
)
async def find_substitutes(request: SubstituteRequest):
    """
    Given a solved timetable, absent teacher name, and absent day, returns
    a list of available substitute candidates per time slot.
    """
    from app.solvers.scheduling.timetable import find_substitutes as _find_subs
    return _find_subs(
        request.timetable_result,
        request.absent_teacher,
        request.absent_day,
        request.teachers_data,
    )


# ===========================================================================
# POST /api/optimize  — Legacy single-shot endpoint (kept for compatibility)
# ===========================================================================

@router.post(
    "/optimize",
    summary="[Legacy] Run single-shot optimization",
    status_code=status.HTTP_200_OK,
)
async def optimize(request: OptimizationRequest):
    """Legacy endpoint. For new integrations, use POST /api/solve."""
    pipeline_start = time.perf_counter()
    try:
        extraction_result = await extract_constraints(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    solver_result = execute_optimization(extraction_result)
    pipeline_time = round(time.perf_counter() - pipeline_start, 3)

    return {
        "domain":                extraction_result.domain.value,
        "constraints_extracted": len(extraction_result.constraints),
        "extraction":            extraction_result.model_dump(),
        "result":                solver_result,
        "pipeline_time_seconds": pipeline_time,
    }


# ===========================================================================
# GET /api/session/{session_id}  — Retrieve session draft for solve page
# ===========================================================================

@router.get(
    "/session/{session_id}",
    summary="Get AI-configured draft for solve page pre-fill",
    status_code=status.HTTP_200_OK,
)
async def get_session_draft(session_id: str):
    """
    Returns the current AI-patched form draft for a given session so the
    solve page can pre-fill its form fields.
    """
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    return {"algo_id": session.algo_id, "draft": session.draft}


# ===========================================================================
# GET /api/health
# ===========================================================================

@router.get("/health", summary="Health check", tags=["Health"])
async def health_check():
    """Returns 200 OK when the service is running."""
    return {
        "status":     "ok",
        "service":    "Neuro-Symbolic Optimization Engine",
        "algorithms": list(ALGO_BY_ID.keys()),
    }

