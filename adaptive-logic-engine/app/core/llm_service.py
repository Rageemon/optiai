"""
Gemini LLM Service
Handles all communication with the Gemini API.

Key features
------------
* Multi-key rotation — up to 3 API keys loaded from .env.
  Keys are tried round-robin; on a 429 / quota error the next key is used
  automatically, giving ~3× the free-tier throughput.
* Fully async — never blocks the FastAPI event loop.
* Structured outputs — `response_schema` forces Pydantic-validated JSON.

Public functions
----------------
extract_constraints(request)  — legacy single-endpoint extraction
match_algorithm(user_message) — Phase 1: does any algo match the problem?
parse_modification(message, algo_id) — Phase 3: what changes does the user want?
"""

import os
import logging
import itertools
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError

from app.models.schemas import (
    AlgoMatchResult,
    SmartChatResult,
    LLMExtractionResult,
    OptimizationRequest,
)
from app.core.patch_applier import get_patch_class
from app.core.algo_context import get_algo_summary_for_llm, ALGO_BY_ID

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

logger = logging.getLogger(__name__)

MODEL_ID = "gemini-2.5-flash"

# Collect all non-empty keys; at least one must exist.
_raw_keys = [
    os.getenv("GEMINI_API_KEY",   ""),
    os.getenv("GEMINI_API_KEY_2", ""),
    os.getenv("GEMINI_API_KEY_3", ""),
]
_api_keys = [k.strip() for k in _raw_keys if k.strip() and k.strip() != "your_second_gemini_api_key_here" and k.strip() != "your_third_gemini_api_key_here"]

if not _api_keys:
    raise EnvironmentError(
        "No valid GEMINI_API_KEY found. Set at least GEMINI_API_KEY in .env."
    )

# One client per key — round-robin iterator
_clients = [genai.Client(api_key=k) for k in _api_keys]
_client_cycle = itertools.cycle(_clients)

logger.info("LLM service initialised with %d API key(s).", len(_api_keys))


# ---------------------------------------------------------------------------
# Internal: resilient call with key rotation
# ---------------------------------------------------------------------------

async def _call_gemini(
    prompt: str,
    response_schema,
    temperature: float = 0.1,
) -> object:
    """
    Attempt the Gemini call across all available keys.
    Rotates to the next key on 429 (quota) errors.
    Raises the last ClientError if all keys are exhausted.
    """
    last_error: Optional[ClientError] = None

    for _ in range(len(_api_keys)):
        client = next(_client_cycle)
        try:
            response = await client.aio.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    temperature=temperature,
                ),
            )
            return response
        except ClientError as exc:
            status_code = getattr(exc, "status_code", None) or (
                exc.args[0] if exc.args and isinstance(exc.args[0], int) else 0
            )
            if status_code == 429:
                logger.warning("Key quota hit (429) — rotating to next key.")
                last_error = exc
                continue
            raise  # Non-quota errors bubble up immediately

    raise last_error  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Public: Phase 1 — Problem matching
# ---------------------------------------------------------------------------

_MATCH_SYSTEM_PROMPT = """\
You are an algorithm-selection engine. Your job is to read a user's problem
description and select the single best-fitting algorithm from the list below.

{algo_summary}

Selection guide (read carefully before deciding)
------------------------------------------------
SCHEDULING_JSSP   → user mentions machines, production lines, manufacturing,
                    job sequences, flow shop, makespan, machine utilisation,
                    "tasks on machines", processing times, parallel machines.

SCHEDULING_SHIFT  → user mentions employees, workers, staff, shifts (morning/
                    evening/night), coverage, hours per week, rosters, days off.

SCHEDULING_NURSE  → same as shift but mentions nurses, doctors, head nurse,
                    skill levels, ICU, wards, or healthcare settings.

SCHEDULING_TIMETABLE → user mentions teachers, classes, students, lectures,
                    periods, subjects, rooms, timetable, school, university,
                    exam scheduling, class 1-A / 10-D style identifiers,
                    merged lectures, labs, sports fixtures, divisions.

SCHEDULING_RCPSP  → user mentions project, activities, tasks with dependencies,
                    critical path, resources like "workers" or "cranes", phases,
                    milestones, WBS, construction, software release schedule.

ROUTING_TSP       → single vehicle, one depot, visit all locations once and
                    return to start; shortest closed tour.

ROUTING_VRP       → multiple vehicles from one depot serving all locations.

ROUTING_CVRP      → VRP with demands + vehicle capacity limits.

ROUTING_VRPTW     → VRP with visit time windows and service times.

ROUTING_PDP       → pickup-delivery pairs where pickup must happen before drop
                    and both must be on same vehicle.

PACKING_KNAPSACK  → user mentions knapsack, budget constraint, limited capacity,
                    selecting items to maximize value/profit, ROI, investment
                    selection, choosing what to take/buy within a budget/weight
                    limit, "what should I pack", NOT needing to take everything.

PACKING_BINPACKING → user mentions bin packing, fitting everything into containers,
                    minimizing bins/containers/boxes needed, packing files onto
                    disks, loading trucks, pallet loading, "fit all items",
                    MUST pack everything (all items required).

PACKING_CUTTINGSTOCK → user mentions cutting stock, cutting raw materials, steel
                    rods, paper rolls, lumber, pipes, fulfilling orders by cutting,
                    minimizing waste/scrap, cutting patterns.

MAP_ROUTING_MULTIOBJECTIVE → user wants to find a real-world route on a map,
                    navigate from one place to another, find a route with specific
                    features (more restaurants, avoid highways, pass through parks,
                    scenic route), real street/road routing, geocoding addresses,
                    lat/lng navigation, "find me a path from X to Y", route with
                    POIs, restaurant route, map directions with preferences.

ASSIGNMENT        → user mentions cost matrix, agents to tasks, matching,
                    Hungarian algorithm, linear assignment, resource allocation
                    WITHOUT time component.

Instructions
------------
1. Analyse the problem. Use the selection guide to narrow down candidates.
2. Pick EXACTLY ONE algorithm. Do not hedge or list alternatives.
3. Set matched=true, algo_id to the chosen id, confidence to high/medium/low.
4. If nothing fits, set matched=false, algo_id=null.
5. Write one short, friendly reasoning sentence.
6. Respond ONLY with the JSON — no extra text.
"""


async def match_algorithm(user_message: str) -> AlgoMatchResult:
    """
    Ask Gemini whether any available algorithm can solve the user's problem.

    Returns
    -------
    AlgoMatchResult  — matched flag, algo_id, confidence, reasoning
    """
    algo_summary = get_algo_summary_for_llm()
    prompt = (
        _MATCH_SYSTEM_PROMPT.format(algo_summary=algo_summary)
        + f"\n\n--- USER PROBLEM ---\n{user_message}"
    )

    logger.info("Phase 1: matching problem to algorithms …")
    response = await _call_gemini(prompt, AlgoMatchResult, temperature=0.1)

    if response.parsed is not None:
        return response.parsed

    logger.warning("response.parsed None in match_algorithm — fallback to JSON parse.")
    return AlgoMatchResult.model_validate_json(response.text)


# ---------------------------------------------------------------------------
# Public: Smart conversational chat — handles ALL intent types
# ---------------------------------------------------------------------------

async def smart_chat(user_message: str) -> SmartChatResult:
    """
    One-shot intelligent chat handler that replaces the rigid match-only pipeline.

    Gemini detects the user's intent and generates an appropriate response:
      • algorithm_problem  — tries to match an algorithm; matched=true sets algo_id
      • app_overview       — explains what OptimAI does
      • algo_list          — lists available algorithms
      • greeting           — friendly welcome + capability summary
      • unrelated          — politely explains this is an optimisation tool
      • general_chat       — anything else, answered in context

    For algorithm_problem + matched=true the returned message is a 1-2 sentence
    intro; routes.py appends the full structured algorithm capabilities card.
    For every other intent the message is the complete response.
    """
    algo_summary = get_algo_summary_for_llm()

    # Build prompt with string concatenation — avoids .format() issues with
    # curly braces that may appear inside algo descriptions / JSON examples.
    prompt = (
        "You are the intelligent assistant for **OptimAI** — a web application that solves "
        "combinatorial optimization problems using AI-powered algorithm selection and "
        "OR-Tools CP-SAT solvers.\n\n"

        "## What OptimAI Does\n"
        "OptimAI helps users solve hard real-world optimization problems:\n"
        "1. The user describes their problem in plain language.\n"
        "2. You select the best algorithm from the library.\n"
        "3. The user fills in input data via a dynamic form.\n"
        "4. OR-Tools CP-SAT finds the optimal (or near-optimal) solution.\n\n"

        "## Available Algorithms\n"
        + algo_summary
        + "\n\n---\n\n"

        "## Your Behaviour\n"
        "Detect the user's intent from the list below, then respond accordingly.\n\n"

        "### INTENT: algorithm_problem\n"
        "The user is describing a combinatorial optimization problem they want to solve.\n"
        "- Check whether any algorithm above fits.\n"
        "- If YES → set intent='algorithm_problem', matched=true, algo_id=<id>, confidence=high/medium/low.\n"
        "  Write a short 1–2 sentence natural confirmation in `message` "
        "(e.g. 'That sounds like a classic Vehicle Routing problem — our CVRP solver handles "
        "exactly this!'). Keep it punchy; a full algorithm card will be shown automatically.\n"
        "- If NO → set intent='algorithm_problem', matched=false, algo_id=null.\n"
        "  In `message` briefly explain what makes the problem outside our scope and "
        "mention what kinds of problems OptimAI CAN solve.\n\n"

        "### INTENT: app_overview\n"
        "The user asks what OptimAI is, what it does, or how to use it.\n"
        "- Set intent='app_overview', matched=false.\n"
        "- Write a friendly, conversational 2–3 paragraph overview in `message`.\n\n"

        "### INTENT: algo_list\n"
        "The user asks which algorithms or how many algorithms are available.\n"
        "- Set intent='algo_list', matched=false.\n"
        "- In `message` list every available algorithm with a one-line description.\n\n"

        "### INTENT: greeting\n"
        "The user says hello, hi, hey, or opens with a friendly greeting.\n"
        "- Set intent='greeting', matched=false.\n"
        "- In `message` greet them warmly and briefly explain what you can help with.\n\n"

        "### INTENT: unrelated\n"
        "The user asks about something completely unrelated to optimization "
        "(e.g. recipes, general coding, history, weather, jokes).\n"
        "- Set intent='unrelated', matched=false.\n"
        "- In `message`: acknowledge their message naturally, explain you specialise in "
        "combinatorial optimisation, and invite them to describe an optimisation problem. "
        "Be warm and helpful, not dismissive.\n\n"

        "### INTENT: general_chat\n"
        "Anything else — vague follow-ups, meta questions, or unclear intent.\n"
        "- Set intent='general_chat', matched=false.\n"
        "- Respond naturally and helpfully in the context of OptimAI.\n\n"

        "---\n"
        "Tone: conversational and knowledgeable — like a helpful colleague, not a rigid bot.\n"
        "Respond ONLY with valid JSON matching the schema. No markdown fences, no extra text.\n\n"

        "--- USER MESSAGE ---\n"
        + user_message
    )

    logger.info("smart_chat: classifying intent and generating response …")
    response = await _call_gemini(prompt, SmartChatResult, temperature=0.3)

    if response.parsed is not None:
        return response.parsed

    logger.warning("response.parsed None in smart_chat — fallback to JSON parse.")
    return SmartChatResult.model_validate_json(response.text)


# ---------------------------------------------------------------------------
# Public: Phase 3 — Modification parsing (typed per-algo patch models)
# ---------------------------------------------------------------------------

def _build_entity_context(algo_id: str, draft: Optional[Dict[str, Any]]) -> str:
    """Build compact entity hints from current draft to improve NL grounding."""
    if not draft:
        return ""

    if algo_id == "scheduling_timetable":
        teacher_names = [t.get("name", "") for t in draft.get("teachers", []) if t.get("name")]
        class_ids = [c.get("id", "") for c in draft.get("classes", []) if c.get("id")]
        subject_names = [s.get("name", "") for s in draft.get("subjects", []) if s.get("name")]
        room_names = [r.get("name", "") for r in draft.get("rooms", []) if r.get("name")]
        return (
            "Known entities in current draft:\n"
            f"- Teachers: {', '.join(teacher_names) if teacher_names else '(none)'}\n"
            f"- Classes: {', '.join(class_ids) if class_ids else '(none)'}\n"
            f"- Subjects: {', '.join(subject_names) if subject_names else '(none)'}\n"
            f"- Rooms: {', '.join(room_names) if room_names else '(none)'}\n"
        )

    if algo_id == "map_routing_multiobjective":
        poi_prefs = draft.get("poi_preferences", {})
        poi_text = ", ".join(f"{k}={v}" for k, v in poi_prefs.items()) if poi_prefs else "(none)"
        return (
            "Current draft state:\n"
            f"- Start: {draft.get('start_address', '') or '(not set)'}\n"
            f"- End: {draft.get('end_address', '') or '(not set)'}\n"
            f"- POI preferences: {poi_text}\n"
            f"- Distance weight: {draft.get('distance_weight', 0.5)}\n"
            f"- Network type: {draft.get('network_type', 'drive')}\n"
            f"- Avoid highways: {draft.get('avoid_highways', False)}\n"
            "\nAvailable POI types: restaurant, cafe, park, museum, hospital, bar, pub, fast_food, "
            "supermarket, pharmacy, school, cinema, theatre, bank, fuel, parking, hotel.\n"
            "To set POI weights, use 'update_poi_weights' with a list of {poi_type, weight} entries.\n"
            "To replace ALL POI types at once, set 'clear_all_poi_weights' to true AND provide the new weights in 'update_poi_weights'.\n"
            "Example: to add restaurants and parks, use update_poi_weights: [{poi_type:'restaurant', weight:0.8}, {poi_type:'park', weight:0.6}]\n"
        )

    return ""


async def parse_modification(user_message: str, algo_id: str, current_draft: Optional[Dict[str, Any]] = None):
    """
    Parse the user's natural-language modification request into a typed patch
    object for the specified algorithm.

    Uses a fully-closed Pydantic schema (no Dict / additionalProperties) so
    the Gemini structured-output API accepts it without schema-validation errors.

    Parameters
    ----------
    user_message : str   — e.g. "Add Carol to teachers, remove the 9AM slot"
    algo_id      : str   — id of the algorithm being modified

    Returns
    -------
    A typed patch instance: JsspPatch | ShiftPatch | NursePatch |
                            TimetablePatch | RcpspPatch
    """
    algo = ALGO_BY_ID.get(algo_id)
    if algo is None:
        raise ValueError(f"Unknown algo_id '{algo_id}'")

    patch_class = get_patch_class(algo_id)

    algo_name = algo["name"]

    # NOTE: We intentionally do NOT use str.format() here — algo metadata
    # can contain curly braces (e.g. JSON examples in descriptions) which
    # would cause a KeyError inside .format().  f-strings with explicit
    # variable insertion are safe.
    raw_vars = algo.get("variables", {})
    if isinstance(raw_vars, dict):
        vars_text = "\n".join(f"  {k}: {v}" for k, v in raw_vars.items())
    elif isinstance(raw_vars, list):
        vars_text = "\n".join(f"  - {v}" for v in raw_vars)
    else:
        vars_text = str(raw_vars)

    algo_context = (
        "Variables available:\n"
        + vars_text
        + "\n\nSupported constraints:\n"
        + "\n".join(f"  - {c}" for c in algo.get("constraints", []))
        + f"\n\nObjective: {algo.get('objective', '')}"
    )

    entity_context = _build_entity_context(algo_id, current_draft)

    prompt = (
        f"You are a modification-parsing engine for the '{algo_name}' optimization algorithm.\n\n"
        f"Algorithm context:\n{algo_context}\n\n"
        + (f"{entity_context}\n" if entity_context else "")
        + "Instructions:\n"
        + "1. Read the user's modification request carefully.\n"
        + "2. Populate ONLY the schema fields that correspond to the requested changes.\n"
        + "   Leave all other list fields empty and all other optional scalars as null.\n"
        + "   If user asks to modify a subject that does not exist yet, include it in add_subjects.\n"
        + "3. The 'summary' field must be exactly ONE plain-English sentence describing what changed.\n"
        + "4. Respond ONLY with the JSON object matching the provided schema — no markdown, no prose.\n"
        + f"\n--- USER REQUEST ---\n{user_message}"
    )

    logger.info("Phase 3: parsing modification for algo '%s' using %s …", algo_id, patch_class.__name__)
    response = await _call_gemini(prompt, patch_class, temperature=0.1)

    if response.parsed is not None:
        return response.parsed

    logger.warning("response.parsed is None — falling back to model_validate_json")
    return patch_class.model_validate_json(response.text)


# ---------------------------------------------------------------------------
# Legacy: original extract_constraints (kept for /api/optimize endpoint)
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM_PROMPT = """\
You are a constraint-extraction engine for an optimization scheduler.
Your ONLY job is to analyse the user's text and produce a single JSON object
that strictly matches the schema provided to you.

Rules
-----
1. Classify the problem into exactly one domain: SCHEDULING, ROUTING, or ASSIGNMENT.
2. Extract every constraint. constraint_type must be one of:
   "unavailable", "required", "preferred".
   teacher = the person's name; day = full day name or null;
   time_slot = "9AM"/"12PM"/"3PM" or null.
3. If no constraints are found, return an empty list.
4. Do NOT invent constraints. Respond with valid JSON only.
"""


async def extract_constraints(request: OptimizationRequest) -> LLMExtractionResult:
    """Legacy extraction for the /api/optimize endpoint."""
    prompt = f"{_EXTRACT_SYSTEM_PROMPT}\n\n--- USER INPUT ---\n{request.text}"

    logger.info("Legacy extraction request …")
    response = await _call_gemini(prompt, LLMExtractionResult, temperature=0.1)

    if response.parsed is not None:
        return response.parsed

    try:
        return LLMExtractionResult.model_validate_json(response.text)
    except Exception as exc:
        raise ValueError(
            f"Gemini returned an unparseable response: {response.text!r}"
        ) from exc

