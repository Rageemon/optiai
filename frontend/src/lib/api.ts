/**
 * Backend API client
 * All calls to the FastAPI adaptive-logic-engine go through here.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types (mirroring backend Pydantic models)
// ---------------------------------------------------------------------------

export interface ChatRequest {
  message: string;
  session_id?: string;
  algo_id?: string;
  phase?: "match" | "confirm" | "modify" | null;
}

export interface PatchDiffEntry {
  field: string;
  op: "add" | "remove" | "change";
  from: string;
  to: string;
}

export interface ChatResponse {
  phase: "no_match" | "algo_found" | "modified" | "ready_to_solve";
  message: string;
  algo_id?: string;
  algo_details?: AlgoDetails;
  modification?: AlgoModification;
  patch_diff?: PatchDiffEntry[];
  effective_draft?: Record<string, unknown>;
  session_id?: string;
}

export interface AlgoDetails {
  id: string;
  name: string;
  domain: string;
  description: string;
  capabilities: string[];
  variables: Record<string, string>;
  constraints: string[];
  objective: string;
  limitations: string[];
  input_schema: Record<string, unknown>;
  status?: string;
}

export interface AlgoModification {
  modified_constraints: Record<string, unknown>[];
  modified_variables: Record<string, unknown>;
  summary: string;
}

export interface SolveRequest {
  algo_id: string;
  inputs: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function sendChatMessage(req: ChatRequest): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function runSolver(req: SolveRequest): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/solve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }

  return res.json();
}

export async function getSessionDraft(
  sessionId: string,
): Promise<{ algo_id: string; draft: Record<string, unknown> }> {
  const res = await fetch(`${API_BASE}/api/session/${encodeURIComponent(sessionId)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function findSubstitutes(params: {
  timetable_result: Record<string, unknown>;
  absent_teacher:   string;
  absent_day:       string;
  teachers_data:    unknown[];
}): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/api/solve/substitute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}
