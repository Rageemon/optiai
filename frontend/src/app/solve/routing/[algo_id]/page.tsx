"use client";

/**
 * Routing Solve Page — /solve/routing/[algo_id]
 *
 * Renders interactive input forms for five OR-Tools routing algorithms:
 *   TSP, VRP, CVRP, VRP with Time Windows, and Pickup & Delivery Problem.
 * Displays rich route visualisation with per-vehicle route cards and SVG map.
 */

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useState, useCallback, useEffect, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft, Play, LoaderIcon, CheckCircle, AlertCircle,
  Plus, Trash2, Sparkles, ChevronDown, ChevronUp, Info,
  Clock, Truck, Package, Navigation, Route,
} from "lucide-react";
import { runSolver, getSessionDraft } from "@/lib/api";

// ============================================================================
// Algo metadata
// ============================================================================

const ALGO_META: Record<string, { name: string; description: string; color: string }> = {
  routing_tsp: {
    name:        "Travelling Salesperson Problem",
    description: "Find the shortest closed tour visiting all locations exactly once.",
    color:       "from-cyan-500 to-sky-600",
  },
  routing_vrp: {
    name:        "Vehicle Routing Problem",
    description: "Route a fleet of vehicles from a depot to serve all customers optimally.",
    color:       "from-teal-500 to-emerald-600",
  },
  routing_cvrp: {
    name:        "Capacitated VRP",
    description: "VRP where vehicles have limited carrying capacity per tour.",
    color:       "from-green-500 to-teal-600",
  },
  routing_vrptw: {
    name:        "VRP with Time Windows",
    description: "VRP where each customer must be visited within a time window.",
    color:       "from-blue-500 to-violet-600",
  },
  routing_pdp: {
    name:        "Pickup & Delivery Problem",
    description: "Route vehicles to pick up and deliver goods between paired locations.",
    color:       "from-violet-500 to-purple-600",
  },
};

// ============================================================================
// Shared UI helpers
// ============================================================================

function uid() { return Math.random().toString(36).slice(2, 8); }

function SectionCard({
  title, icon, children, collapsed,
}: {
  title:      string;
  icon:       ReactNode;
  children:   ReactNode;
  collapsed?: boolean;
}) {
  const [open, setOpen] = useState(!collapsed);
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-white/[0.03] transition-colors"
      >
        <span className="text-white/50">{icon}</span>
        <span className="text-sm font-medium text-white/80 flex-1">{title}</span>
        {open
          ? <ChevronUp   className="w-4 h-4 text-white/30" />
          : <ChevronDown className="w-4 h-4 text-white/30" />}
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-white/[0.05]">
          {children}
        </div>
      )}
    </div>
  );
}

function Field({ label, hint, children }: {
  label:    string;
  hint?:    string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-white/50 flex items-center gap-1">
        {label}
        {hint && (
          <span title={hint} className="cursor-help text-white/30">
            <Info className="w-3 h-3" />
          </span>
        )}
      </label>
      {children}
    </div>
  );
}

const inputCls   = "w-full bg-white/[0.05] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:border-teal-500/50 focus:bg-white/[0.07] transition-colors";
const btnSmall   = "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors";
const addBtnCls  = `${btnSmall} bg-white/[0.06] hover:bg-white/[0.1] text-white/60 hover:text-white border border-white/10`;
const removeBtnCls = `${btnSmall} bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20`;
const cellInputCls = "w-full h-8 bg-transparent border-0 text-center text-white text-xs focus:outline-none focus:bg-teal-500/10 rounded transition-colors";

// ============================================================================
// Matrix editor — inline NxN editable grid
// ============================================================================

function MatrixEditor({
  matrix, nodeNames, symmetry,
  onMatrixChange, onNodeNamesChange, onSymmetryChange,
}: {
  matrix:              number[][];
  nodeNames:           string[];
  symmetry:            boolean;
  onMatrixChange:      (m: number[][]) => void;
  onNodeNamesChange:   (names: string[]) => void;
  onSymmetryChange:    (s: boolean) => void;
}) {
  const n = matrix.length;

  const updateCell = (i: number, j: number, val: number) => {
    const next = matrix.map(row => [...row]);
    next[i][j] = val;
    if (symmetry) next[j][i] = val;
    onMatrixChange(next);
  };

  const addNode = () => {
    const n2 = n + 1;
    const next = matrix.map(row => [...row, 0]);
    next.push(new Array(n2).fill(0));
    onMatrixChange(next);
    onNodeNamesChange([...nodeNames, `Node ${n}`]);
  };

  const removeLastNode = () => {
    if (n <= 2) return;
    const next = matrix.slice(0, n - 1).map(row => row.slice(0, n - 1));
    onMatrixChange(next);
    onNodeNamesChange(nodeNames.slice(0, n - 1));
  };

  return (
    <div className="space-y-3 mt-3">
      {/* Controls row */}
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-xs text-white/50 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={symmetry}
            onChange={e => onSymmetryChange(e.target.checked)}
            className="accent-teal-500"
          />
          Symmetric — auto-mirror edits
        </label>
        <span className="text-xs text-white/20 ml-auto">{n} × {n}</span>
      </div>

      {/* Node name badges */}
      <div className="flex flex-wrap gap-1.5">
        {nodeNames.map((name, i) => (
          <input
            key={i}
            value={name}
            onChange={e => {
              const next = [...nodeNames];
              next[i] = e.target.value;
              onNodeNamesChange(next);
            }}
            title={`Label for node ${i}`}
            className="w-20 text-xs bg-white/[0.05] border border-white/10 rounded px-2 py-1 text-white/70 focus:outline-none focus:border-teal-500/40 transition-colors"
          />
        ))}
      </div>

      {/* Matrix grid */}
      <div className="overflow-x-auto rounded-lg border border-white/[0.07] bg-white/[0.02]">
        <table className="text-xs border-collapse min-w-full">
          <thead>
            <tr>
              <th className="w-8 min-w-[32px] bg-white/[0.03] border-b border-white/[0.07]" />
              {nodeNames.map((name, j) => (
                <th
                  key={j}
                  className="px-1.5 py-2 text-white/40 font-normal text-center min-w-[52px] max-w-[70px] bg-white/[0.02] border-b border-l border-white/[0.06] truncate"
                >
                  {name.length > 6 ? `${name.slice(0, 5)}…` : name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={i}>
                <td className="px-2 py-0.5 text-white/40 text-right text-[11px] whitespace-nowrap border-r border-white/[0.06] bg-white/[0.02]">
                  {nodeNames[i]?.length > 5 ? `${nodeNames[i].slice(0, 4)}…` : nodeNames[i]}
                </td>
                {row.map((val, j) => (
                  <td key={j} className="p-0.5 border-l border-b border-white/[0.04]">
                    {i === j ? (
                      <div className="w-full flex items-center justify-center h-8 text-white/15 rounded bg-white/[0.02] select-none">
                        —
                      </div>
                    ) : (
                      <input
                        type="number"
                        min={0}
                        value={val}
                        onChange={e => updateCell(i, j, Number(e.target.value))}
                        className={cellInputCls}
                      />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-2">
        <button onClick={addNode}       className={addBtnCls}><Plus   className="w-3 h-3"/> Add Node</button>
        {n > 2 && (
          <button onClick={removeLastNode} className={removeBtnCls}><Trash2 className="w-3 h-3"/> Remove Last</button>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// TSP form
// ============================================================================

function TspForm({ value, onChange }: { value: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void }) {
  const matrix    = (value.distance_matrix as number[][]) ?? [[0, 1], [1, 0]];
  const nodeNames = (value.node_names      as string[])   ?? ["Depot", "Node 1"];
  const symmetry  = (value._symmetry       as boolean)    ?? true;
  const set = (patch: object) => onChange({ ...value, ...patch });

  return (
    <div className="space-y-4 mt-3">
      <SectionCard title="Solver Settings" icon={<Navigation className="w-4 h-4"/>}>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Depot Node" hint="Start & end node index (0-based)">
            <input
              type="number" min={0} max={matrix.length - 1}
              value={(value.depot as number) ?? 0}
              onChange={e => set({ depot: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
          <Field label="Time Limit (s)">
            <input
              type="number" min={1} max={300}
              value={(value.time_limit_seconds as number) ?? 10}
              onChange={e => set({ time_limit_seconds: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
        </div>
      </SectionCard>

      <SectionCard title={`Distance Matrix (${matrix.length} nodes)`} icon={<Route className="w-4 h-4"/>}>
        <MatrixEditor
          matrix={matrix}
          nodeNames={nodeNames}
          symmetry={symmetry}
          onMatrixChange={m => set({ distance_matrix: m })}
          onNodeNamesChange={names => set({ node_names: names })}
          onSymmetryChange={s => set({ _symmetry: s })}
        />
      </SectionCard>
    </div>
  );
}

// ============================================================================
// VRP form
// ============================================================================

function VrpForm({ value, onChange }: { value: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void }) {
  const matrix    = (value.distance_matrix as number[][]) ?? [[0, 1], [1, 0]];
  const nodeNames = (value.node_names      as string[])   ?? ["Depot", "Node 1"];
  const symmetry  = (value._symmetry       as boolean)    ?? true;
  const set = (patch: object) => onChange({ ...value, ...patch });

  return (
    <div className="space-y-4 mt-3">
      <SectionCard title="Vehicle Fleet" icon={<Truck className="w-4 h-4"/>}>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Number of Vehicles">
            <input
              type="number" min={1} max={20}
              value={(value.num_vehicles as number) ?? 2}
              onChange={e => set({ num_vehicles: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
          <Field label="Depot Node">
            <input
              type="number" min={0} max={matrix.length - 1}
              value={(value.depot as number) ?? 0}
              onChange={e => set({ depot: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
          <Field label="Max Route Distance" hint="Per-vehicle cap; 0 = unlimited">
            <input
              type="number" min={0}
              value={(value.max_route_distance as number) ?? 0}
              onChange={e => set({ max_route_distance: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
          <Field label="Time Limit (s)">
            <input
              type="number" min={1} max={300}
              value={(value.time_limit_seconds as number) ?? 10}
              onChange={e => set({ time_limit_seconds: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
        </div>
      </SectionCard>

      <SectionCard title={`Distance Matrix (${matrix.length} nodes)`} icon={<Route className="w-4 h-4"/>}>
        <MatrixEditor
          matrix={matrix}
          nodeNames={nodeNames}
          symmetry={symmetry}
          onMatrixChange={m => set({ distance_matrix: m })}
          onNodeNamesChange={names => set({ node_names: names })}
          onSymmetryChange={s => set({ _symmetry: s })}
        />
      </SectionCard>
    </div>
  );
}

// ============================================================================
// CVRP form
// ============================================================================

function CvrpForm({ value, onChange }: { value: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void }) {
  const matrix      = (value.distance_matrix   as number[][]) ?? [[0, 1], [1, 0]];
  const nodeNames   = (value.node_names        as string[])   ?? ["Depot", "Node 1"];
  const symmetry    = (value._symmetry         as boolean)    ?? true;
  const demands     = (value.demands           as number[])   ?? new Array(matrix.length).fill(0);
  const numVehicles = (value.num_vehicles      as number)     ?? 2;
  const capacities  = (value.vehicle_capacities as number[])  ?? new Array(numVehicles).fill(15);
  const depot       = (value.depot             as number)     ?? 0;
  const set = (patch: object) => onChange({ ...value, ...patch });

  const handleMatrixChange = (m: number[][]) => {
    const newDemands = Array.from({ length: m.length }, (_, i) => demands[i] ?? 0);
    set({ distance_matrix: m, demands: newDemands });
  };

  const handleNumVehiclesChange = (n: number) => {
    const newCaps = Array.from({ length: n }, (_, i) => capacities[i] ?? 15);
    set({ num_vehicles: n, vehicle_capacities: newCaps });
  };

  return (
    <div className="space-y-4 mt-3">
      <SectionCard title="Vehicle Fleet" icon={<Truck className="w-4 h-4"/>}>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Number of Vehicles">
            <input
              type="number" min={1} max={20}
              value={numVehicles}
              onChange={e => handleNumVehiclesChange(Number(e.target.value))}
              className={inputCls}
            />
          </Field>
          <Field label="Depot Node">
            <input
              type="number" min={0} max={matrix.length - 1}
              value={depot}
              onChange={e => set({ depot: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
          <Field label="Time Limit (s)">
            <input
              type="number" min={1} max={300}
              value={(value.time_limit_seconds as number) ?? 10}
              onChange={e => set({ time_limit_seconds: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
        </div>
        <div className="mt-4">
          <p className="text-xs text-white/40 mb-2">Vehicle Capacities</p>
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: numVehicles }, (_, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <span className="text-xs text-white/30">V{i + 1}</span>
                <input
                  type="number" min={1}
                  value={capacities[i] ?? 15}
                  onChange={e => {
                    const next = [...capacities];
                    next[i] = Number(e.target.value);
                    set({ vehicle_capacities: next });
                  }}
                  className="w-16 h-8 bg-white/[0.05] border border-white/10 rounded px-2 text-xs text-white text-center focus:outline-none focus:border-teal-500/50 transition-colors"
                />
              </div>
            ))}
          </div>
        </div>
      </SectionCard>

      <SectionCard title={`Distance Matrix (${matrix.length} nodes)`} icon={<Route className="w-4 h-4"/>}>
        <MatrixEditor
          matrix={matrix}
          nodeNames={nodeNames}
          symmetry={symmetry}
          onMatrixChange={handleMatrixChange}
          onNodeNamesChange={names => set({ node_names: names })}
          onSymmetryChange={s => set({ _symmetry: s })}
        />
      </SectionCard>

      <SectionCard title="Node Demands" icon={<Package className="w-4 h-4"/>}>
        <p className="text-xs text-white/30 mt-3 mb-3">
          Units each node requires. Depot demand must be 0. Vehicle capacity must cover total demands per route.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {nodeNames.map((name, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-xs text-white/50 w-20 truncate">{name}</span>
              <input
                type="number" min={0}
                value={demands[i] ?? 0}
                onChange={e => {
                  const next = [...demands];
                  next[i] = Number(e.target.value);
                  set({ demands: next });
                }}
                disabled={i === depot}
                className={`${inputCls} w-24 text-center ${i === depot ? "opacity-40 cursor-not-allowed" : ""}`}
              />
              {i === depot && <span className="text-xs text-white/20">depot</span>}
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}

// ============================================================================
// VRPTW form
// ============================================================================

function VrptwForm({ value, onChange }: { value: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void }) {
  const matrix       = (value.time_matrix    as number[][])        ?? [[0, 1], [1, 0]];
  const nodeNames    = (value.node_names     as string[])          ?? ["Depot", "Node 1"];
  const symmetry     = (value._symmetry      as boolean)           ?? true;
  const timeWindows  = (value.time_windows   as [number, number][]) ?? matrix.map(() => [0, 200] as [number, number]);
  const serviceTimes = (value.service_times  as number[])          ?? new Array(matrix.length).fill(0);
  const set = (patch: object) => onChange({ ...value, ...patch });

  const handleMatrixChange = (m: number[][]) => {
    const newWindows  = Array.from({ length: m.length }, (_, i) => timeWindows[i]  ?? [0, 200]);
    const newServices = Array.from({ length: m.length }, (_, i) => serviceTimes[i] ?? 0);
    set({ time_matrix: m, time_windows: newWindows, service_times: newServices });
  };

  return (
    <div className="space-y-4 mt-3">
      <SectionCard title="Vehicle & Timing Settings" icon={<Truck className="w-4 h-4"/>}>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Number of Vehicles">
            <input
              type="number" min={1} max={20}
              value={(value.num_vehicles as number) ?? 2}
              onChange={e => set({ num_vehicles: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
          <Field label="Depot Node">
            <input
              type="number" min={0} max={matrix.length - 1}
              value={(value.depot as number) ?? 0}
              onChange={e => set({ depot: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
          <Field label="Max Waiting Time" hint="Max time a vehicle waits at a node before its window opens">
            <input
              type="number" min={0}
              value={(value.max_waiting_time as number) ?? 30}
              onChange={e => set({ max_waiting_time: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
          <Field label="Route Horizon" hint="Maximum total time per vehicle">
            <input
              type="number" min={1}
              value={(value.max_time_per_vehicle as number) ?? 200}
              onChange={e => set({ max_time_per_vehicle: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
          <Field label="Time Limit (s)">
            <input
              type="number" min={1} max={300}
              value={(value.time_limit_seconds as number) ?? 10}
              onChange={e => set({ time_limit_seconds: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
        </div>
      </SectionCard>

      <SectionCard title={`Travel-Time Matrix (${matrix.length} nodes)`} icon={<Route className="w-4 h-4"/>}>
        <MatrixEditor
          matrix={matrix}
          nodeNames={nodeNames}
          symmetry={symmetry}
          onMatrixChange={handleMatrixChange}
          onNodeNamesChange={names => set({ node_names: names })}
          onSymmetryChange={s => set({ _symmetry: s })}
        />
      </SectionCard>

      <SectionCard title="Time Windows & Service Times" icon={<Clock className="w-4 h-4"/>}>
        <div className="space-y-2 mt-3">
          <div className="grid grid-cols-[1fr_72px_72px_72px] gap-2 text-xs text-white/30 px-1 mb-1">
            <span>Node</span>
            <span className="text-center">Earliest</span>
            <span className="text-center">Latest</span>
            <span className="text-center">Service</span>
          </div>
          {nodeNames.map((name, i) => (
            <div key={i} className="grid grid-cols-[1fr_72px_72px_72px] gap-2 items-center">
              <span className="text-xs text-white/60 truncate pl-1">{name}</span>
              <input
                type="number" min={0}
                value={timeWindows[i]?.[0] ?? 0}
                onChange={e => {
                  const next = timeWindows.map(w => [...w] as [number, number]);
                  next[i][0] = Number(e.target.value);
                  set({ time_windows: next });
                }}
                className="h-8 bg-white/[0.05] border border-white/10 rounded px-1 text-xs text-white text-center focus:outline-none focus:border-teal-500/50 transition-colors"
              />
              <input
                type="number" min={0}
                value={timeWindows[i]?.[1] ?? 200}
                onChange={e => {
                  const next = timeWindows.map(w => [...w] as [number, number]);
                  next[i][1] = Number(e.target.value);
                  set({ time_windows: next });
                }}
                className="h-8 bg-white/[0.05] border border-white/10 rounded px-1 text-xs text-white text-center focus:outline-none focus:border-teal-500/50 transition-colors"
              />
              <input
                type="number" min={0}
                value={serviceTimes[i] ?? 0}
                onChange={e => {
                  const next = [...serviceTimes];
                  next[i] = Number(e.target.value);
                  set({ service_times: next });
                }}
                className="h-8 bg-white/[0.05] border border-white/10 rounded px-1 text-xs text-white text-center focus:outline-none focus:border-teal-500/50 transition-colors"
              />
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}

// ============================================================================
// PDP form
// ============================================================================

function PdpForm({ value, onChange }: { value: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void }) {
  const matrix      = (value.distance_matrix       as number[][])        ?? [[0, 1], [1, 0]];
  const nodeNames   = (value.node_names            as string[])          ?? ["Depot", "Node 1"];
  const symmetry    = (value._symmetry             as boolean)           ?? true;
  const demands     = (value.demands               as number[])          ?? new Array(matrix.length).fill(0);
  const numVehicles = (value.num_vehicles          as number)            ?? 2;
  const capacities  = (value.vehicle_capacities    as number[])          ?? new Array(numVehicles).fill(20);
  const pairs       = (value.pickup_delivery_pairs as [number, number][]) ?? [];
  const depot       = (value.depot                as number)            ?? 0;
  const set = (patch: object) => onChange({ ...value, ...patch });

  const handleMatrixChange = (m: number[][]) => {
    const newDemands = Array.from({ length: m.length }, (_, i) => demands[i] ?? 0);
    set({ distance_matrix: m, demands: newDemands });
  };

  const handleNumVehiclesChange = (n: number) => {
    const newCaps = Array.from({ length: n }, (_, i) => capacities[i] ?? 20);
    set({ num_vehicles: n, vehicle_capacities: newCaps });
  };

  const nonDepotNodes = nodeNames.map((_, i) => i).filter(i => i !== depot);

  const addPair = () => {
    const pickup   = nonDepotNodes[0] ?? 1;
    const delivery = nonDepotNodes[1] ?? 2;
    set({ pickup_delivery_pairs: [...pairs, [pickup, delivery]] });
  };

  return (
    <div className="space-y-4 mt-3">
      <SectionCard title="Vehicle Fleet" icon={<Truck className="w-4 h-4"/>}>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Number of Vehicles">
            <input
              type="number" min={1} max={20}
              value={numVehicles}
              onChange={e => handleNumVehiclesChange(Number(e.target.value))}
              className={inputCls}
            />
          </Field>
          <Field label="Depot Node">
            <input
              type="number" min={0} max={matrix.length - 1}
              value={depot}
              onChange={e => set({ depot: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
          <Field label="Time Limit (s)">
            <input
              type="number" min={1} max={300}
              value={(value.time_limit_seconds as number) ?? 10}
              onChange={e => set({ time_limit_seconds: Number(e.target.value) })}
              className={inputCls}
            />
          </Field>
        </div>
        <div className="mt-4">
          <p className="text-xs text-white/40 mb-2">Vehicle Capacities</p>
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: numVehicles }, (_, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <span className="text-xs text-white/30">V{i + 1}</span>
                <input
                  type="number" min={1}
                  value={capacities[i] ?? 20}
                  onChange={e => {
                    const next = [...capacities];
                    next[i] = Number(e.target.value);
                    set({ vehicle_capacities: next });
                  }}
                  className="w-16 h-8 bg-white/[0.05] border border-white/10 rounded px-2 text-xs text-white text-center focus:outline-none focus:border-teal-500/50 transition-colors"
                />
              </div>
            ))}
          </div>
        </div>
      </SectionCard>

      <SectionCard title={`Distance Matrix (${matrix.length} nodes)`} icon={<Route className="w-4 h-4"/>}>
        <MatrixEditor
          matrix={matrix}
          nodeNames={nodeNames}
          symmetry={symmetry}
          onMatrixChange={handleMatrixChange}
          onNodeNamesChange={names => set({ node_names: names })}
          onSymmetryChange={s => set({ _symmetry: s })}
        />
      </SectionCard>

      <SectionCard title="Node Demands" icon={<Package className="w-4 h-4"/>}>
        <p className="text-xs text-white/30 mt-3 mb-3">
          Positive = load picked up, Negative = load delivered, 0 = depot or pass-through.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {nodeNames.map((name, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-xs text-white/50 w-20 truncate">{name}</span>
              <input
                type="number"
                value={demands[i] ?? 0}
                onChange={e => {
                  const next = [...demands];
                  next[i] = Number(e.target.value);
                  set({ demands: next });
                }}
                disabled={i === depot}
                className={`${inputCls} w-24 text-center ${i === depot ? "opacity-40 cursor-not-allowed" : ""}`}
              />
              {i !== depot && demands[i] > 0 && <span className="text-[10px] text-emerald-400 font-medium">pickup</span>}
              {i !== depot && demands[i] < 0 && <span className="text-[10px] text-sky-400 font-medium">deliver</span>}
              {i === depot && <span className="text-[10px] text-white/20">depot</span>}
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title={`Pickup-Delivery Pairs (${pairs.length})`} icon={<Package className="w-4 h-4"/>}>
        <div className="space-y-3 mt-3">
          <p className="text-xs text-white/30">
            Each pair must be served by the same vehicle: it picks up at the first node and delivers to the second.
          </p>
          {pairs.map((pair, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <select
                value={pair[0]}
                onChange={e => {
                  const next = pairs.map(p => [...p] as [number, number]);
                  next[idx][0] = Number(e.target.value);
                  set({ pickup_delivery_pairs: next });
                }}
                className={`${inputCls} flex-1`}
              >
                {nodeNames.map((name, i) => i !== depot ? (
                  <option key={i} value={i}>{name} (node {i})</option>
                ) : null)}
              </select>
              <span className="text-white/30 text-xs shrink-0">→</span>
              <select
                value={pair[1]}
                onChange={e => {
                  const next = pairs.map(p => [...p] as [number, number]);
                  next[idx][1] = Number(e.target.value);
                  set({ pickup_delivery_pairs: next });
                }}
                className={`${inputCls} flex-1`}
              >
                {nodeNames.map((name, i) => i !== depot ? (
                  <option key={i} value={i}>{name} (node {i})</option>
                ) : null)}
              </select>
              <button
                onClick={() => set({ pickup_delivery_pairs: pairs.filter((_, i) => i !== idx) })}
                className={removeBtnCls}
              >
                <Trash2 className="w-3 h-3"/>
              </button>
            </div>
          ))}
          <button onClick={addPair} className={addBtnCls}><Plus className="w-3 h-3"/> Add Pair</button>
        </div>
      </SectionCard>
    </div>
  );
}

// ============================================================================
// Input transformers  (strip frontend-only keys before sending to backend)
// ============================================================================

function transformInputs(_algoId: string, raw: Record<string, unknown>): Record<string, unknown> {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { node_names: _nn, _symmetry: _sy, ...rest } = raw;
  return rest;
}

// ============================================================================
// Default starter data
// ============================================================================

const DEFAULT_VALUES: Record<string, Record<string, unknown>> = {
  routing_tsp: {
    depot: 0,
    time_limit_seconds: 10,
    _symmetry: true,
    node_names: ["Depot", "Alpha", "Beta", "Gamma", "Delta"],
    distance_matrix: [
      [0, 4, 8, 6, 7],
      [4, 0, 5, 3, 6],
      [8, 5, 0, 4, 3],
      [6, 3, 4, 0, 5],
      [7, 6, 3, 5, 0],
    ],
  },

  routing_vrp: {
    num_vehicles: 2,
    depot: 0,
    max_route_distance: 0,
    time_limit_seconds: 10,
    _symmetry: true,
    node_names: ["Depot", "Alpha", "Beta", "Gamma", "Delta", "Epsilon"],
    distance_matrix: [
      [0, 4, 8, 6, 7, 5],
      [4, 0, 5, 3, 6, 4],
      [8, 5, 0, 4, 3, 6],
      [6, 3, 4, 0, 5, 2],
      [7, 6, 3, 5, 0, 4],
      [5, 4, 6, 2, 4, 0],
    ],
  },

  routing_cvrp: {
    num_vehicles: 2,
    depot: 0,
    time_limit_seconds: 10,
    _symmetry: true,
    node_names: ["Depot", "Alpha", "Beta", "Gamma", "Delta", "Epsilon"],
    distance_matrix: [
      [0, 4, 8, 6, 7, 5],
      [4, 0, 5, 3, 6, 4],
      [8, 5, 0, 4, 3, 6],
      [6, 3, 4, 0, 5, 2],
      [7, 6, 3, 5, 0, 4],
      [5, 4, 6, 2, 4, 0],
    ],
    demands: [0, 4, 2, 6, 3, 5],
    vehicle_capacities: [11, 11],
  },

  routing_vrptw: {
    num_vehicles: 2,
    depot: 0,
    time_limit_seconds: 10,
    max_waiting_time: 30,
    max_time_per_vehicle: 200,
    _symmetry: true,
    node_names: ["Depot", "Alpha", "Beta", "Gamma", "Delta", "Epsilon"],
    time_matrix: [
      [0, 4, 8, 6, 7, 5],
      [4, 0, 5, 3, 6, 4],
      [8, 5, 0, 4, 3, 6],
      [6, 3, 4, 0, 5, 2],
      [7, 6, 3, 5, 0, 4],
      [5, 4, 6, 2, 4, 0],
    ],
    service_times: [0, 2, 2, 2, 2, 2],
    time_windows: [[0, 200], [5, 60], [10, 80], [20, 90], [30, 120], [40, 140]],
  },

  routing_pdp: {
    num_vehicles: 2,
    depot: 0,
    time_limit_seconds: 10,
    _symmetry: true,
    node_names: ["Depot", "P-Alpha", "D-Alpha", "P-Beta", "D-Beta", "P-Gamma"],
    distance_matrix: [
      [0, 4, 8, 6, 7, 5],
      [4, 0, 5, 3, 6, 4],
      [8, 5, 0, 4, 3, 6],
      [6, 3, 4, 0, 5, 2],
      [7, 6, 3, 5, 0, 4],
      [5, 4, 6, 2, 4, 0],
    ],
    demands: [0, 3, -3, 4, -4, 0],
    vehicle_capacities: [7, 7],
    pickup_delivery_pairs: [[1, 2], [3, 4]],
  },
};

// ============================================================================
// SVG radial route map
// ============================================================================

const VEHICLE_COLORS = [
  "#06b6d4",  // cyan
  "#10b981",  // emerald
  "#f59e0b",  // amber
  "#ef4444",  // red
  "#8b5cf6",  // violet
  "#ec4899",  // pink
];

type RouteStop = { node: number; load?: number; time?: number };
type RouteData = { vehicle_id: number; stops: RouteStop[]; distance: number };

function RouteMap({ routes, nodeNames, depot }: {
  routes:    RouteData[];
  nodeNames: string[];
  depot:     number;
}) {
  const n = nodeNames.length;
  if (n < 2) return null;

  const SIZE = 280;
  const CX = SIZE / 2;
  const CY = SIZE / 2;
  const R  = 95;

  // Place nodes around a circle; depot at the top (−90°)
  const angles  = nodeNames.map((_, i) => -Math.PI / 2 + (2 * Math.PI * i) / n);
  const nodePos = angles.map(a => ({ x: CX + R * Math.cos(a), y: CY + R * Math.sin(a) }));

  const activeRoutes = routes.filter(r => r.stops.length > 2);

  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="w-full max-w-[280px] mx-auto"
      aria-label="Route visualisation"
    >
      {/* Arrowhead marker defs */}
      <defs>
        {activeRoutes.map((_, ri) => {
          const col = VEHICLE_COLORS[ri % VEHICLE_COLORS.length];
          return (
            <marker
              key={ri}
              id={`arrowhead-${ri}`}
              markerWidth="6" markerHeight="6"
              refX="3" refY="3"
              orient="auto"
            >
              <path d="M0,0 L6,3 L0,6 Z" fill={col} fillOpacity={0.85} />
            </marker>
          );
        })}
      </defs>

      {/* Background grid circle */}
      <circle cx={CX} cy={CY} r={R} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth={1} />

      {/* Route arcs */}
      {activeRoutes.map((route, ri) => {
        const col = VEHICLE_COLORS[ri % VEHICLE_COLORS.length];
        const stops = route.stops.map(s => s.node);
        return stops.slice(0, -1).map((fromNode, si) => {
          const toNode = stops[si + 1];
          const p1 = nodePos[fromNode];
          const p2 = nodePos[toNode];
          if (!p1 || !p2) return null;

          const dx  = p2.x - p1.x;
          const dy  = p2.y - p1.y;
          const len = Math.sqrt(dx * dx + dy * dy) || 1;
          const ox  = (dx / len) * 8;
          const oy  = (dy / len) * 8;

          return (
            <line
              key={`${ri}-${si}`}
              x1={p1.x + ox} y1={p1.y + oy}
              x2={p2.x - ox} y2={p2.y - oy}
              stroke={col}
              strokeWidth={2}
              strokeOpacity={0.75}
              markerEnd={`url(#arrowhead-${ri})`}
            />
          );
        });
      })}

      {/* Node circles + labels */}
      {nodeNames.map((name, i) => {
        const { x, y } = nodePos[i];
        const isDepot  = i === depot;
        return (
          <g key={i} transform={`translate(${x},${y})`}>
            <circle
              r={isDepot ? 10 : 6}
              fill={isDepot ? "#78350f" : "#0f172a"}
              stroke={isDepot ? "#f59e0b" : "rgba(255,255,255,0.18)"}
              strokeWidth={isDepot ? 2.5 : 1.5}
            />
            {isDepot && (
              <text textAnchor="middle" dominantBaseline="central" fontSize="7" fontWeight="bold" fill="#fbbf24">
                D
              </text>
            )}
            <text
              textAnchor="middle"
              y={isDepot ? -16 : -11}
              fontSize="8.5"
              fill="rgba(255,255,255,0.55)"
              className="select-none"
            >
              {name.length > 7 ? `${name.slice(0, 6)}…` : name}
            </text>
          </g>
        );
      })}

      {/* Legend */}
      {activeRoutes.length > 0 && (
        <g transform="translate(6,6)">
          {activeRoutes.map((_, ri) => (
            <g key={ri} transform={`translate(0,${ri * 14})`}>
              <rect x={0} y={1} width={14} height={4} rx={2} fill={VEHICLE_COLORS[ri % VEHICLE_COLORS.length]} fillOpacity={0.85} />
              <text x={18} y={5} fontSize="8" fill="rgba(255,255,255,0.4)">Vehicle {ri + 1}</text>
            </g>
          ))}
        </g>
      )}
    </svg>
  );
}

// ============================================================================
// Route card — single vehicle result
// ============================================================================

function RouteCard({ route, nodeNames, color }: {
  route:     RouteData;
  nodeNames: string[];
  color:     string;
}) {
  const getName    = (idx: number) => nodeNames[idx] ?? `N${idx}`;
  const isActive   = route.stops.length > 2;
  const hasLoad    = route.stops.some(s => s.load !== undefined);
  const hasTime    = route.stops.some(s => s.time !== undefined);

  return (
    <div className={`rounded-xl border p-4 transition-colors ${
      isActive ? "border-white/[0.1] bg-white/[0.03]" : "border-white/[0.04] bg-white/[0.015] opacity-40"
    }`}>
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <div className="w-3 h-3 rounded-full shrink-0" style={{ background: color }} />
        <span className="text-sm font-semibold text-white/80">Vehicle {route.vehicle_id + 1}</span>
        {!isActive && <span className="text-xs text-white/25 italic ml-auto">not used</span>}
        {isActive && (
          <span className="text-xs text-white/40 ml-auto">
            distance&nbsp;<span className="text-white/70 font-medium tabular-nums">{route.distance}</span>
          </span>
        )}
      </div>

      {isActive && (
        <>
          {/* Stop sequence chips */}
          <div className="flex flex-wrap items-center gap-1 text-xs">
            {route.stops.map((stop, si) => {
              const isEndpoint = si === 0 || si === route.stops.length - 1;
              return (
                <span key={si} className="flex items-center gap-0.5">
                  <span className={`px-2 py-0.5 rounded-full border text-xs font-medium ${
                    isEndpoint
                      ? "bg-amber-500/20 border-amber-500/40 text-amber-300"
                      : "bg-white/[0.06] border-white/[0.1] text-white/70"
                  }`}>
                    {getName(stop.node)}
                  </span>
                  {si < route.stops.length - 1 && (
                    <span className="text-white/20 text-[10px]">›</span>
                  )}
                </span>
              );
            })}
          </div>

          {/* Per-stop metrics (load / arrival time) */}
          {(hasLoad || hasTime) && (
            <div className="mt-3 pt-3 border-t border-white/[0.05] space-y-1">
              <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 text-[10px] text-white/25 px-1 mb-0.5">
                <span>Stop</span>
                {hasLoad && <span>Load</span>}
                {hasTime && <span>Arrival</span>}
              </div>
              {route.stops.map((stop, si) => (
                <div key={si} className="grid grid-cols-[1fr_auto_auto] gap-x-4 text-xs items-center px-1">
                  <span className="text-white/50 truncate">{getName(stop.node)}</span>
                  {hasLoad && (
                    <span className="text-white/40 tabular-nums">
                      {stop.load ?? "—"}
                    </span>
                  )}
                  {hasTime && (
                    <span className="text-white/40 tabular-nums">
                      t={stop.time ?? "—"}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ============================================================================
// Unified routing result component
// ============================================================================

function RoutingResult({ result, formValues }: {
  result:     Record<string, unknown>;
  formValues: Record<string, unknown>;
}) {
  const routes    = (result.routes as RouteData[]) ?? [];
  const totalDist = result.total_distance as number | undefined;
  const totalTime = result.total_time     as number | undefined;
  const problem   = result.problem        as string;

  const nodeNames  = (formValues.node_names as string[]) ?? routes.flatMap(r => r.stops.map(s => s.node)).map(i => `Node ${i}`);
  const depot      = (formValues.depot      as number)   ?? 0;
  const isTimed    = problem === "vrptw";

  const activeRoutes   = routes.filter(r => r.stops.length > 2);
  const servedNodes    = new Set(activeRoutes.flatMap(r => r.stops.slice(1, -1).map(s => s.node))).size;
  const avgRouteDist   = activeRoutes.length > 0
    ? (routes.reduce((acc, r) => acc + r.distance, 0) / activeRoutes.length)
    : 0;

  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="flex flex-wrap gap-3">
        <div className="rounded-xl border border-teal-500/30 bg-teal-500/10 px-4 py-3">
          <p className="text-xs text-teal-400/70">{isTimed ? "Total Route Time" : "Total Distance"}</p>
          <p className="text-2xl font-bold text-teal-300 tabular-nums">
            {isTimed ? totalTime : totalDist}
            <span className="text-sm font-normal ml-1.5 text-teal-400/60">units</span>
          </p>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
          <p className="text-xs text-white/40">Vehicles used</p>
          <p className="text-xl font-bold text-white/80 tabular-nums">
            {activeRoutes.length}
            <span className="text-sm font-normal text-white/30 ml-1">/ {routes.length}</span>
          </p>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
          <p className="text-xs text-white/40">Nodes served</p>
          <p className="text-xl font-bold text-white/80 tabular-nums">{servedNodes}</p>
        </div>

        {activeRoutes.length > 0 && (
          <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
            <p className="text-xs text-white/40">Avg. route</p>
            <p className="text-xl font-bold text-white/80 tabular-nums">{avgRouteDist.toFixed(1)}</p>
          </div>
        )}
      </div>

      {/* Route map */}
      <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] px-4 pt-3 pb-4">
        <p className="text-xs text-white/35 mb-3">
          Route Map
          <span className="text-white/20 ml-2 text-[10px]">— nodes on circle, arrows show direction</span>
        </p>
        <RouteMap routes={routes} nodeNames={nodeNames} depot={depot} />
      </div>

      {/* Per-vehicle route cards */}
      <div className="space-y-3">
        <p className="text-xs text-white/30 uppercase tracking-wider">Vehicle Routes</p>
        {routes.map((route, ri) => (
          <RouteCard
            key={ri}
            route={route}
            nodeNames={nodeNames}
            color={VEHICLE_COLORS[ri % VEHICLE_COLORS.length]}
          />
        ))}
      </div>

      {/* Raw JSON */}
      <details className="text-xs text-white/25">
        <summary className="cursor-pointer hover:text-white/40 transition-colors">Raw JSON response</summary>
        <pre className="mt-2 overflow-auto text-[10px] text-white/20 max-h-56 rounded-lg border border-white/[0.05] bg-white/[0.02] p-3">
          {JSON.stringify(result, null, 2)}
        </pre>
      </details>
    </div>
  );
}

// ============================================================================
// Form dispatcher
// ============================================================================

function renderForm(
  algoId:   string,
  value:    Record<string, unknown>,
  onChange: (v: Record<string, unknown>) => void,
) {
  if (algoId === "routing_tsp")   return <TspForm   value={value} onChange={onChange} />;
  if (algoId === "routing_vrp")   return <VrpForm   value={value} onChange={onChange} />;
  if (algoId === "routing_cvrp")  return <CvrpForm  value={value} onChange={onChange} />;
  if (algoId === "routing_vrptw") return <VrptwForm value={value} onChange={onChange} />;
  if (algoId === "routing_pdp")   return <PdpForm   value={value} onChange={onChange} />;
  return null;
}

// ============================================================================
// Page component
// ============================================================================

export default function RoutingSolvePage() {
  const params       = useParams();
  const router       = useRouter();
  const searchParams = useSearchParams();

  const algoId = (params?.algo_id as string) ?? "";
  const meta   = ALGO_META[algoId];

  const [formValues,  setFormValues]  = useState<Record<string, unknown>>(DEFAULT_VALUES[algoId] ?? {});
  const [isLoading,   setIsLoading]   = useState(false);
  const [result,      setResult]      = useState<Record<string, unknown> | null>(null);
  const [error,       setError]       = useState<string | null>(null);
  const [aiPrefilled, setAiPrefilled] = useState(false);

  // Load AI-prefilled session draft when ?session= is present
  useEffect(() => {
    const sessionId = searchParams?.get("session");
    if (!sessionId) return;
    getSessionDraft(sessionId)
      .then(data => {
        if (data.draft && Object.keys(data.draft).length > 0) {
          setFormValues(data.draft as Record<string, unknown>);
          setAiPrefilled(true);
        }
      })
      .catch(err => console.warn("Could not load session draft:", err));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSolve = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setResult(null);
    try {
      const cleanInputs  = transformInputs(algoId, formValues);
      const payload      = { algo_id: algoId, inputs: cleanInputs };
      console.log("[RoutingSolvePage] Sending payload:", payload);
      const res = await runSolver(payload);
      if (res.error) throw new Error(res.error as string);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Solver failed. Check your inputs.");
    } finally {
      setIsLoading(false);
    }
  }, [algoId, formValues]);

  // Unknown algo fallback
  if (!meta) {
    return (
      <div className="min-h-screen bg-[#0a0a0b] text-white flex items-center justify-center p-8">
        <div className="text-center space-y-4">
          <p className="text-white/40 text-lg">
            Unknown routing algorithm: <code className="text-white/70">{algoId}</code>
          </p>
          <button
            onClick={() => router.push("/")}
            className="text-teal-400 hover:text-teal-300 text-sm transition-colors"
          >
            ← Back to chat
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0b] text-white">
      {/* ── Header ── */}
      <header className="sticky top-0 z-20 bg-black/60 backdrop-blur-xl border-b border-white/[0.05] px-4 py-3 flex items-center gap-3">
        <button
          onClick={() => router.push("/")}
          className="p-1.5 rounded-lg hover:bg-white/[0.06] text-white/40 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>

        <div className={`w-7 h-7 rounded-lg bg-gradient-to-br flex items-center justify-center ${meta.color}`}>
          <Navigation className="w-3.5 h-3.5 text-white" />
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white/90 truncate">{meta.name}</p>
          <p className="text-xs text-white/40 truncate">{meta.description}</p>
        </div>

        {aiPrefilled && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-teal-500/15 border border-teal-500/25 text-xs text-teal-300 shrink-0">
            <Sparkles className="w-3 h-3" />
            AI-configured
          </div>
        )}

        <button
          onClick={handleSolve}
          disabled={isLoading}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all bg-gradient-to-r text-white shrink-0 ${meta.color} ${isLoading ? "opacity-60 cursor-not-allowed" : "hover:scale-105 active:scale-100"}`}
        >
          {isLoading
            ? <><LoaderIcon className="w-4 h-4 animate-spin" />Solving…</>
            : <><Play className="w-4 h-4" />Solve</>}
        </button>
      </header>

      {/* ── Two-column layout ── */}
      <div className="max-w-6xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: input */}
        <div>
          <p className="text-xs text-white/30 uppercase tracking-wider mb-3">Input Configuration</p>
          {renderForm(algoId, formValues, setFormValues)}

          {/* JSON preview */}
          <details className="mt-4">
            <summary className="text-xs text-white/20 cursor-pointer hover:text-white/40 transition-colors">
              Preview JSON payload
            </summary>
            <pre className="mt-2 overflow-auto text-[10px] text-white/20 max-h-64 rounded-lg border border-white/[0.05] bg-white/[0.02] p-3">
              {JSON.stringify(transformInputs(algoId, formValues), null, 2)}
            </pre>
          </details>
        </div>

        {/* Right: results */}
        <div>
          <p className="text-xs text-white/30 uppercase tracking-wider mb-3">Results</p>

          {!result && !error && !isLoading && (
            <div className="flex flex-col items-center justify-center h-64 rounded-xl border border-dashed border-white/[0.08] text-white/20">
              <Navigation className="w-8 h-8 mb-3" />
              <p className="text-sm">Press Solve to run the optimizer</p>
              <p className="text-xs mt-1 text-white/15">OR-Tools Routing API · Guided Local Search</p>
            </div>
          )}

          {isLoading && (
            <div className="flex flex-col items-center justify-center h-64 rounded-xl border border-white/[0.08] bg-white/[0.02]">
              <LoaderIcon className="w-8 h-8 animate-spin text-teal-500 mb-3" />
              <p className="text-sm text-white/40">Running OR-Tools routing solver…</p>
            </div>
          )}

          {error && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 flex gap-3"
            >
              <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-red-300">Solver Error</p>
                <p className="text-xs text-red-400/80 mt-1">{error}</p>
              </div>
            </motion.div>
          )}

          {result && (
            <AnimatePresence>
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle className="w-4 h-4 text-emerald-400" />
                  <span className="text-sm font-medium text-emerald-300">Solution found</span>
                  <span className="text-xs text-white/25 ml-1">
                    ({(result.problem as string ?? algoId).toUpperCase()})
                  </span>
                </div>
                <RoutingResult result={result} formValues={formValues} />
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      </div>
    </div>
  );
}
