"use client";

/**
 * Packing Solve Page — /solve/packing/[algo_id]
 *
 * Renders input forms for packing & knapsack algorithms:
 *   Knapsack, Bin Packing, Cutting Stock
 * Displays rich visualizations: item selection, bin assignments, cutting plans.
 */

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft, Play, LoaderIcon, CheckCircle, AlertCircle,
  Plus, Trash2, Sparkles, ChevronDown, ChevronUp, Info,
  Package, Box, Scissors, Scale, Grid3x3, Layers,
} from "lucide-react";
import { runSolver, getSessionDraft } from "@/lib/api";

// ============================================================================
// Algo metadata
// ============================================================================

const ALGO_META: Record<string, { name: string; description: string; color: string }> = {
  packing_knapsack: {
    name:        "Knapsack Problem",
    description: "Select items to maximize value within capacity constraints.",
    color:       "from-amber-500 to-orange-600",
  },
  packing_binpacking: {
    name:        "Bin Packing Problem",
    description: "Pack all items into minimum number of bins.",
    color:       "from-cyan-500 to-blue-600",
  },
  packing_cuttingstock: {
    name:        "Cutting Stock Problem",
    description: "Cut raw materials to fulfill orders with minimum waste.",
    color:       "from-green-500 to-emerald-600",
  },
};

// ============================================================================
// Shared UI helpers
// ============================================================================

function uid() { return Math.random().toString(36).slice(2, 8); }

function SectionCard({ title, icon, children, collapsed }: {
  title:     string;
  icon:      React.ReactNode;
  children:  React.ReactNode;
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
          ? <ChevronUp className="w-4 h-4 text-white/30" />
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

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-white/50 flex items-center gap-1">
        {label}
        {hint && (
          <span title={hint} className="cursor-help text-white/30"><Info className="w-3 h-3" /></span>
        )}
      </label>
      {children}
    </div>
  );
}

const inputCls = "w-full bg-white/[0.05] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:border-violet-500/50 focus:bg-white/[0.07] transition-colors";
const btnSmall = "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors";
const addBtnCls = `${btnSmall} bg-white/[0.06] hover:bg-white/[0.1] text-white/60 hover:text-white border border-white/10`;
const removeBtnCls = `${btnSmall} bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20`;

// ============================================================================
// Knapsack Form
// ============================================================================

type KnapsackItem = { _id: string; name: string; value: number; weight: number; quantity: number };

function KnapsackForm({
  value, onChange,
}: {
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}) {
  const items = (value.items as KnapsackItem[]) ?? [];
  const set = (patch: object) => onChange({ ...value, ...patch });

  const addItem = () => set({ items: [...items, { _id: uid(), name: `Item ${items.length+1}`, value: 100, weight: 10, quantity: 1 }] });
  const removeItem = (id: string) => set({ items: items.filter(i => i._id !== id) });
  const updateItem = (id: string, patch: Partial<KnapsackItem>) => set({ items: items.map(i => i._id === id ? { ...i, ...patch } : i) });

  return (
    <div className="space-y-4 mt-3">
      <SectionCard title="Configuration" icon={<Scale className="w-4 h-4"/>}>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Problem Type">
            <select value={(value.problem_type as string) ?? "0-1"} onChange={e=>set({problem_type:e.target.value})} className={inputCls}>
              <option value="0-1">0-1 Knapsack (take or leave)</option>
              <option value="bounded">Bounded (limited quantity)</option>
              <option value="unbounded">Unbounded (unlimited copies)</option>
              <option value="multiple">Multiple Knapsacks</option>
              <option value="multidimensional">Multi-dimensional</option>
            </select>
          </Field>
          <Field label="Capacity" hint="Maximum weight/size the knapsack can hold">
            <input type="number" min={1} value={(value.capacity as number) ?? 50} onChange={e=>set({capacity:Number(e.target.value)})} className={inputCls} />
          </Field>
          {(value.problem_type === "multiple") && (
            <Field label="Capacities (comma-sep)" hint="Capacities for each knapsack">
              <input
                value={(value.capacities as number[])?.join(",") ?? ""}
                onChange={e=>set({capacities:e.target.value.split(",").map(c=>parseInt(c.trim())).filter(c=>!isNaN(c))})}
                placeholder="50,40,30"
                className={inputCls}
              />
            </Field>
          )}
          <Field label="Time Limit (seconds)">
            <input type="number" min={1} value={(value.time_limit_seconds as number) ?? 30} onChange={e=>set({time_limit_seconds:Number(e.target.value)})} className={inputCls} />
          </Field>
        </div>
      </SectionCard>

      <SectionCard title={`Items (${items.length})`} icon={<Package className="w-4 h-4"/>}>
        <div className="space-y-2 mt-3">
          <div className="grid grid-cols-12 gap-2 text-xs text-white/40 font-medium px-1">
            <div className="col-span-4">Name</div>
            <div className="col-span-2">Value</div>
            <div className="col-span-2">Weight</div>
            <div className="col-span-2">Qty</div>
            <div className="col-span-2"></div>
          </div>
          {items.map(item => (
            <div key={item._id} className="grid grid-cols-12 gap-2 items-center">
              <input value={item.name} onChange={e=>updateItem(item._id,{name:e.target.value})} placeholder="Name" className={`${inputCls} col-span-4`} />
              <input type="number" min={0} value={item.value} onChange={e=>updateItem(item._id,{value:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
              <input type="number" min={1} value={item.weight} onChange={e=>updateItem(item._id,{weight:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
              <input type="number" min={1} value={item.quantity} onChange={e=>updateItem(item._id,{quantity:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
              <div className="col-span-2 flex justify-end">
                <button onClick={()=>removeItem(item._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
              </div>
            </div>
          ))}
          <button onClick={addItem} className={addBtnCls}><Plus className="w-3 h-3"/> Add Item</button>
        </div>
      </SectionCard>
    </div>
  );
}

// ============================================================================
// Bin Packing Form
// ============================================================================

type BinPackingItem = { _id: string; name: string; size: number; width: number; height: number; depth: number; quantity: number; can_rotate: boolean };
type BinType = { _id: string; name: string; capacity: number; cost: number; available: number };

function BinPackingForm({
  value, onChange,
}: {
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}) {
  const items = (value.items as BinPackingItem[]) ?? [];
  const binTypes = (value.bin_types as BinType[]) ?? [];
  const problemType = (value.problem_type as string) ?? "1d";
  const set = (patch: object) => onChange({ ...value, ...patch });

  const addItem = () => set({ items: [...items, { _id: uid(), name: `Box ${items.length+1}`, size: 20, width: 10, height: 10, depth: 10, quantity: 1, can_rotate: true }] });
  const removeItem = (id: string) => set({ items: items.filter(i => i._id !== id) });
  const updateItem = (id: string, patch: Partial<BinPackingItem>) => set({ items: items.map(i => i._id === id ? { ...i, ...patch } : i) });

  const addBinType = () => set({ bin_types: [...binTypes, { _id: uid(), name: `Bin Type ${binTypes.length+1}`, capacity: 100, cost: 1, available: 100 }] });
  const removeBinType = (id: string) => set({ bin_types: binTypes.filter(b => b._id !== id) });
  const updateBinType = (id: string, patch: Partial<BinType>) => set({ bin_types: binTypes.map(b => b._id === id ? { ...b, ...patch } : b) });

  const is1D = problemType === "1d" || problemType === "variable";
  const is2D = problemType === "2d";
  const is3D = problemType === "3d";

  return (
    <div className="space-y-4 mt-3">
      <SectionCard title="Configuration" icon={<Grid3x3 className="w-4 h-4"/>}>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Problem Type">
            <select value={problemType} onChange={e=>set({problem_type:e.target.value})} className={inputCls}>
              <option value="1d">1D Bin Packing (by size/weight)</option>
              <option value="2d">2D Bin Packing (rectangles)</option>
              <option value="3d">3D Bin Packing (boxes)</option>
              <option value="variable">Variable Bins (different sizes/costs)</option>
            </select>
          </Field>
          {is1D && (
            <Field label="Bin Capacity">
              <input type="number" min={1} value={(value.bin_capacity as number) ?? 100} onChange={e=>set({bin_capacity:Number(e.target.value)})} className={inputCls} />
            </Field>
          )}
          {is2D && (
            <>
              <Field label="Bin Width">
                <input type="number" min={1} value={(value.bin_width as number) ?? 100} onChange={e=>set({bin_width:Number(e.target.value)})} className={inputCls} />
              </Field>
              <Field label="Bin Height">
                <input type="number" min={1} value={(value.bin_height as number) ?? 100} onChange={e=>set({bin_height:Number(e.target.value)})} className={inputCls} />
              </Field>
            </>
          )}
          {is3D && (
            <>
              <Field label="Bin Width">
                <input type="number" min={1} value={(value.bin_width as number) ?? 100} onChange={e=>set({bin_width:Number(e.target.value)})} className={inputCls} />
              </Field>
              <Field label="Bin Height">
                <input type="number" min={1} value={(value.bin_height as number) ?? 100} onChange={e=>set({bin_height:Number(e.target.value)})} className={inputCls} />
              </Field>
              <Field label="Bin Depth">
                <input type="number" min={1} value={(value.bin_depth as number) ?? 100} onChange={e=>set({bin_depth:Number(e.target.value)})} className={inputCls} />
              </Field>
            </>
          )}
          <Field label="Time Limit (seconds)">
            <input type="number" min={1} value={(value.time_limit_seconds as number) ?? 60} onChange={e=>set({time_limit_seconds:Number(e.target.value)})} className={inputCls} />
          </Field>
        </div>
      </SectionCard>

      {problemType === "variable" && (
        <SectionCard title={`Bin Types (${binTypes.length})`} icon={<Box className="w-4 h-4"/>}>
          <div className="space-y-2 mt-3">
            <div className="grid grid-cols-12 gap-2 text-xs text-white/40 font-medium px-1">
              <div className="col-span-3">Name</div>
              <div className="col-span-2">Capacity</div>
              <div className="col-span-2">Cost</div>
              <div className="col-span-3">Available</div>
              <div className="col-span-2"></div>
            </div>
            {binTypes.map(bt => (
              <div key={bt._id} className="grid grid-cols-12 gap-2 items-center">
                <input value={bt.name} onChange={e=>updateBinType(bt._id,{name:e.target.value})} className={`${inputCls} col-span-3`} />
                <input type="number" min={1} value={bt.capacity} onChange={e=>updateBinType(bt._id,{capacity:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
                <input type="number" min={1} value={bt.cost} onChange={e=>updateBinType(bt._id,{cost:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
                <input type="number" min={1} value={bt.available} onChange={e=>updateBinType(bt._id,{available:Number(e.target.value)})} className={`${inputCls} col-span-3`} />
                <div className="col-span-2 flex justify-end">
                  <button onClick={()=>removeBinType(bt._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
                </div>
              </div>
            ))}
            <button onClick={addBinType} className={addBtnCls}><Plus className="w-3 h-3"/> Add Bin Type</button>
          </div>
        </SectionCard>
      )}

      <SectionCard title={`Items (${items.length})`} icon={<Package className="w-4 h-4"/>}>
        <div className="space-y-2 mt-3">
          {is1D && (
            <div className="grid grid-cols-12 gap-2 text-xs text-white/40 font-medium px-1">
              <div className="col-span-5">Name</div>
              <div className="col-span-3">Size</div>
              <div className="col-span-2">Qty</div>
              <div className="col-span-2"></div>
            </div>
          )}
          {is2D && (
            <div className="grid grid-cols-12 gap-2 text-xs text-white/40 font-medium px-1">
              <div className="col-span-3">Name</div>
              <div className="col-span-2">Width</div>
              <div className="col-span-2">Height</div>
              <div className="col-span-2">Qty</div>
              <div className="col-span-1">Rot</div>
              <div className="col-span-2"></div>
            </div>
          )}
          {is3D && (
            <div className="grid grid-cols-12 gap-2 text-xs text-white/40 font-medium px-1">
              <div className="col-span-2">Name</div>
              <div className="col-span-2">W</div>
              <div className="col-span-2">H</div>
              <div className="col-span-2">D</div>
              <div className="col-span-2">Qty</div>
              <div className="col-span-2"></div>
            </div>
          )}
          {items.map(item => (
            <div key={item._id} className="grid grid-cols-12 gap-2 items-center">
              {is1D && (
                <>
                  <input value={item.name} onChange={e=>updateItem(item._id,{name:e.target.value})} className={`${inputCls} col-span-5`} />
                  <input type="number" min={1} value={item.size} onChange={e=>updateItem(item._id,{size:Number(e.target.value)})} className={`${inputCls} col-span-3`} />
                  <input type="number" min={1} value={item.quantity} onChange={e=>updateItem(item._id,{quantity:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
                </>
              )}
              {is2D && (
                <>
                  <input value={item.name} onChange={e=>updateItem(item._id,{name:e.target.value})} className={`${inputCls} col-span-3`} />
                  <input type="number" min={1} value={item.width} onChange={e=>updateItem(item._id,{width:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
                  <input type="number" min={1} value={item.height} onChange={e=>updateItem(item._id,{height:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
                  <input type="number" min={1} value={item.quantity} onChange={e=>updateItem(item._id,{quantity:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
                  <label className="col-span-1 flex justify-center">
                    <input type="checkbox" checked={item.can_rotate} onChange={e=>updateItem(item._id,{can_rotate:e.target.checked})} className="accent-violet-500" />
                  </label>
                </>
              )}
              {is3D && (
                <>
                  <input value={item.name} onChange={e=>updateItem(item._id,{name:e.target.value})} className={`${inputCls} col-span-2`} />
                  <input type="number" min={1} value={item.width} onChange={e=>updateItem(item._id,{width:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
                  <input type="number" min={1} value={item.height} onChange={e=>updateItem(item._id,{height:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
                  <input type="number" min={1} value={item.depth} onChange={e=>updateItem(item._id,{depth:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
                  <input type="number" min={1} value={item.quantity} onChange={e=>updateItem(item._id,{quantity:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
                </>
              )}
              <div className="col-span-2 flex justify-end">
                <button onClick={()=>removeItem(item._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
              </div>
            </div>
          ))}
          <button onClick={addItem} className={addBtnCls}><Plus className="w-3 h-3"/> Add Item</button>
        </div>
      </SectionCard>
    </div>
  );
}

// ============================================================================
// Cutting Stock Form
// ============================================================================

type CuttingOrder = { _id: string; name: string; length: number; quantity: number };
type StockType = { _id: string; name: string; length: number; cost: number; available: number };

function CuttingStockForm({
  value, onChange,
}: {
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}) {
  const orders = (value.orders as CuttingOrder[]) ?? [];
  const stockTypes = (value.stock_types as StockType[]) ?? [];
  const problemType = (value.problem_type as string) ?? "1d";
  const set = (patch: object) => onChange({ ...value, ...patch });

  const addOrder = () => set({ orders: [...orders, { _id: uid(), name: `Piece ${orders.length+1}`, length: 25, quantity: 5 }] });
  const removeOrder = (id: string) => set({ orders: orders.filter(o => o._id !== id) });
  const updateOrder = (id: string, patch: Partial<CuttingOrder>) => set({ orders: orders.map(o => o._id === id ? { ...o, ...patch } : o) });

  const addStockType = () => set({ stock_types: [...stockTypes, { _id: uid(), name: `Stock ${stockTypes.length+1}`, length: 100, cost: 1, available: 100 }] });
  const removeStockType = (id: string) => set({ stock_types: stockTypes.filter(s => s._id !== id) });
  const updateStockType = (id: string, patch: Partial<StockType>) => set({ stock_types: stockTypes.map(s => s._id === id ? { ...s, ...patch } : s) });

  const isMultiStock = problemType === "multi-stock";

  return (
    <div className="space-y-4 mt-3">
      <SectionCard title="Configuration" icon={<Scissors className="w-4 h-4"/>}>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Problem Type">
            <select value={problemType} onChange={e=>set({problem_type:e.target.value})} className={inputCls}>
              <option value="1d">Single Stock Size</option>
              <option value="multi-stock">Multiple Stock Sizes</option>
            </select>
          </Field>
          {!isMultiStock && (
            <Field label="Stock Length" hint="Length of raw material">
              <input type="number" min={1} value={(value.stock_length as number) ?? 100} onChange={e=>set({stock_length:Number(e.target.value)})} className={inputCls} />
            </Field>
          )}
          <Field label="Time Limit (seconds)">
            <input type="number" min={1} value={(value.time_limit_seconds as number) ?? 60} onChange={e=>set({time_limit_seconds:Number(e.target.value)})} className={inputCls} />
          </Field>
        </div>
      </SectionCard>

      {isMultiStock && (
        <SectionCard title={`Stock Types (${stockTypes.length})`} icon={<Layers className="w-4 h-4"/>}>
          <div className="space-y-2 mt-3">
            <div className="grid grid-cols-12 gap-2 text-xs text-white/40 font-medium px-1">
              <div className="col-span-3">Name</div>
              <div className="col-span-2">Length</div>
              <div className="col-span-2">Cost</div>
              <div className="col-span-3">Available</div>
              <div className="col-span-2"></div>
            </div>
            {stockTypes.map(st => (
              <div key={st._id} className="grid grid-cols-12 gap-2 items-center">
                <input value={st.name} onChange={e=>updateStockType(st._id,{name:e.target.value})} className={`${inputCls} col-span-3`} />
                <input type="number" min={1} value={st.length} onChange={e=>updateStockType(st._id,{length:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
                <input type="number" min={1} value={st.cost} onChange={e=>updateStockType(st._id,{cost:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
                <input type="number" min={1} value={st.available} onChange={e=>updateStockType(st._id,{available:Number(e.target.value)})} className={`${inputCls} col-span-3`} />
                <div className="col-span-2 flex justify-end">
                  <button onClick={()=>removeStockType(st._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
                </div>
              </div>
            ))}
            <button onClick={addStockType} className={addBtnCls}><Plus className="w-3 h-3"/> Add Stock Type</button>
          </div>
        </SectionCard>
      )}

      <SectionCard title={`Orders (${orders.length})`} icon={<Package className="w-4 h-4"/>}>
        <div className="space-y-2 mt-3">
          <div className="grid grid-cols-12 gap-2 text-xs text-white/40 font-medium px-1">
            <div className="col-span-5">Piece Name</div>
            <div className="col-span-3">Length</div>
            <div className="col-span-2">Qty Needed</div>
            <div className="col-span-2"></div>
          </div>
          {orders.map(order => (
            <div key={order._id} className="grid grid-cols-12 gap-2 items-center">
              <input value={order.name} onChange={e=>updateOrder(order._id,{name:e.target.value})} className={`${inputCls} col-span-5`} />
              <input type="number" min={1} value={order.length} onChange={e=>updateOrder(order._id,{length:Number(e.target.value)})} className={`${inputCls} col-span-3`} />
              <input type="number" min={1} value={order.quantity} onChange={e=>updateOrder(order._id,{quantity:Number(e.target.value)})} className={`${inputCls} col-span-2`} />
              <div className="col-span-2 flex justify-end">
                <button onClick={()=>removeOrder(order._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
              </div>
            </div>
          ))}
          <button onClick={addOrder} className={addBtnCls}><Plus className="w-3 h-3"/> Add Order</button>
        </div>
      </SectionCard>
    </div>
  );
}

// ============================================================================
// Results Visualization Components
// ============================================================================

function KnapsackResult({ result }: { result: Record<string, unknown> }) {
  const selected = (result.selected_items as Array<{name:string; value:number; weight:number; quantity:number}>) ?? [];
  const notSelected = (result.items_not_selected as Array<{name:string; value:number; weight:number}>) ?? [];
  const usage = result.capacity_usage as {used:number; total:number; utilization_percent:number} | undefined;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
          <div className="text-2xl font-bold text-green-400">{result.total_value as number}</div>
          <div className="text-xs text-white/50">Total Value</div>
        </div>
        <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4">
          <div className="text-2xl font-bold text-blue-400">{result.total_weight as number}</div>
          <div className="text-xs text-white/50">Total Weight</div>
        </div>
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4">
          <div className="text-2xl font-bold text-amber-400">{usage?.utilization_percent}%</div>
          <div className="text-xs text-white/50">Capacity Used</div>
        </div>
      </div>

      <div className="rounded-lg border border-white/10 overflow-hidden">
        <div className="bg-green-500/10 px-4 py-2 border-b border-white/10">
          <span className="text-sm font-medium text-green-400">Selected Items ({selected.length})</span>
        </div>
        <div className="p-3 space-y-2">
          {selected.map((item, i) => (
            <div key={i} className="flex items-center justify-between text-sm bg-white/[0.03] rounded px-3 py-2">
              <span className="text-white/80">{item.name}</span>
              <span className="text-white/50">
                {item.quantity > 1 && <span className="text-violet-400">×{item.quantity} </span>}
                Value: {item.value} | Weight: {item.weight}
              </span>
            </div>
          ))}
        </div>
      </div>

      {notSelected.length > 0 && (
        <div className="rounded-lg border border-white/10 overflow-hidden">
          <div className="bg-red-500/10 px-4 py-2 border-b border-white/10">
            <span className="text-sm font-medium text-red-400">Not Selected ({notSelected.length})</span>
          </div>
          <div className="p-3 space-y-2">
            {notSelected.map((item, i) => (
              <div key={i} className="flex items-center justify-between text-sm bg-white/[0.03] rounded px-3 py-2">
                <span className="text-white/40">{item.name}</span>
                <span className="text-white/30">Value: {item.value} | Weight: {item.weight}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function BinPackingResult({ result }: { result: Record<string, unknown> }) {
  const bins = (result.bin_assignments as Array<{bin_id:number; bin_type?:string; items:Array<{name:string; size?:number}>; utilization_percent:number; total_size?:number; capacity?:number}>) ?? [];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4">
          <div className="text-2xl font-bold text-blue-400">{result.bins_used as number}</div>
          <div className="text-xs text-white/50">Bins Used</div>
        </div>
        <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
          <div className="text-2xl font-bold text-green-400">{result.total_items as number}</div>
          <div className="text-xs text-white/50">Items Packed</div>
        </div>
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4">
          <div className="text-2xl font-bold text-amber-400">{result.average_utilization as number}%</div>
          <div className="text-xs text-white/50">Avg Utilization</div>
        </div>
      </div>

      <div className="space-y-3">
        {bins.map((bin, i) => (
          <div key={i} className="rounded-lg border border-white/10 overflow-hidden">
            <div className="bg-cyan-500/10 px-4 py-2 border-b border-white/10 flex justify-between items-center">
              <span className="text-sm font-medium text-cyan-400">
                Bin {bin.bin_id + 1} {bin.bin_type && <span className="text-white/40">({bin.bin_type})</span>}
              </span>
              <span className="text-xs text-white/50">{bin.utilization_percent}% full</span>
            </div>
            <div className="p-3">
              <div className="h-2 bg-white/10 rounded-full overflow-hidden mb-3">
                <div className="h-full bg-cyan-500" style={{ width: `${bin.utilization_percent}%` }} />
              </div>
              <div className="flex flex-wrap gap-2">
                {bin.items.map((item, j) => (
                  <span key={j} className="px-2 py-1 bg-white/[0.05] rounded text-xs text-white/70">
                    {item.name} {item.size && <span className="text-white/40">({item.size})</span>}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CuttingStockResult({ result }: { result: Record<string, unknown> }) {
  const plan = (result.cutting_plan as Array<{stock_id:number; stock_type?:string; stock_length:number; cuts:Array<{name:string; length:number; count:number}>; waste:number; waste_percent:number}>) ?? [];
  const fulfillment = result.order_fulfillment as Record<string, {required:number; fulfilled:number}> | undefined;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4">
          <div className="text-2xl font-bold text-blue-400">{result.stocks_used as number}</div>
          <div className="text-xs text-white/50">Stocks Used</div>
        </div>
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
          <div className="text-2xl font-bold text-red-400">{result.total_waste as number}</div>
          <div className="text-xs text-white/50">Total Waste</div>
        </div>
        <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
          <div className="text-2xl font-bold text-green-400">{result.material_utilization as number}%</div>
          <div className="text-xs text-white/50">Material Utilization</div>
        </div>
        {result.total_cost !== undefined && (
          <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4">
            <div className="text-2xl font-bold text-amber-400">${result.total_cost as number}</div>
            <div className="text-xs text-white/50">Total Cost</div>
          </div>
        )}
      </div>

      {fulfillment && (
        <div className="rounded-lg border border-white/10 overflow-hidden">
          <div className="bg-violet-500/10 px-4 py-2 border-b border-white/10">
            <span className="text-sm font-medium text-violet-400">Order Fulfillment</span>
          </div>
          <div className="p-3 grid grid-cols-2 gap-2">
            {Object.entries(fulfillment).map(([name, status]) => (
              <div key={name} className="flex items-center justify-between text-sm bg-white/[0.03] rounded px-3 py-2">
                <span className="text-white/80">{name}</span>
                <span className={status.fulfilled >= status.required ? "text-green-400" : "text-red-400"}>
                  {status.fulfilled} / {status.required}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-3">
        {plan.map((stock, i) => (
          <div key={i} className="rounded-lg border border-white/10 overflow-hidden">
            <div className="bg-emerald-500/10 px-4 py-2 border-b border-white/10 flex justify-between items-center">
              <span className="text-sm font-medium text-emerald-400">
                Stock #{stock.stock_id + 1} {stock.stock_type && <span className="text-white/40">({stock.stock_type})</span>}
              </span>
              <span className="text-xs text-white/50">Length: {stock.stock_length} | Waste: {stock.waste} ({stock.waste_percent}%)</span>
            </div>
            <div className="p-3">
              {/* Visual cutting representation */}
              <div className="h-8 bg-white/10 rounded flex overflow-hidden mb-2">
                {stock.cuts.map((cut, j) => {
                  const widthPercent = (cut.length * cut.count / stock.stock_length) * 100;
                  const colors = ["bg-blue-500", "bg-green-500", "bg-amber-500", "bg-violet-500", "bg-pink-500"];
                  return (
                    <div
                      key={j}
                      className={`${colors[j % colors.length]} flex items-center justify-center text-xs text-white font-medium`}
                      style={{ width: `${widthPercent}%` }}
                      title={`${cut.name}: ${cut.length} × ${cut.count}`}
                    >
                      {widthPercent > 10 && `${cut.name}`}
                    </div>
                  );
                })}
                {stock.waste > 0 && (
                  <div
                    className="bg-red-500/30 flex items-center justify-center text-xs text-red-300"
                    style={{ width: `${(stock.waste / stock.stock_length) * 100}%` }}
                  >
                    {stock.waste_percent > 5 && "waste"}
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {stock.cuts.map((cut, j) => (
                  <span key={j} className="px-2 py-1 bg-white/[0.05] rounded text-xs text-white/70">
                    {cut.name}: {cut.length} × {cut.count}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// Main Page Component
// ============================================================================

export default function PackingSolvePage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const algoId = params.algo_id as string;

  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const meta = ALGO_META[algoId] ?? { name: "Unknown", description: "", color: "from-gray-500 to-gray-600" };

  // Load session draft or defaults
  useEffect(() => {
    const sessionId = searchParams.get("session");
    if (sessionId) {
      getSessionDraft(sessionId)
        .then(data => {
          if (data.draft) setFormData(data.draft);
        })
        .catch(() => {});
    }
  }, [searchParams]);

  // Set defaults based on algo
  useEffect(() => {
    if (Object.keys(formData).length === 0) {
      if (algoId === "packing_knapsack") {
        setFormData({
          problem_type: "0-1",
          capacity: 50,
          time_limit_seconds: 30,
          items: [
            { _id: uid(), name: "Laptop", value: 500, weight: 10, quantity: 1 },
            { _id: uid(), name: "Camera", value: 300, weight: 5, quantity: 1 },
            { _id: uid(), name: "Phone", value: 200, weight: 2, quantity: 1 },
            { _id: uid(), name: "Tablet", value: 250, weight: 8, quantity: 1 },
            { _id: uid(), name: "Headphones", value: 100, weight: 3, quantity: 1 },
          ],
        });
      } else if (algoId === "packing_binpacking") {
        setFormData({
          problem_type: "1d",
          bin_capacity: 100,
          time_limit_seconds: 60,
          items: [
            { _id: uid(), name: "Box A", size: 45, width: 10, height: 10, depth: 10, quantity: 2, can_rotate: true },
            { _id: uid(), name: "Box B", size: 35, width: 10, height: 10, depth: 10, quantity: 3, can_rotate: true },
            { _id: uid(), name: "Box C", size: 25, width: 10, height: 10, depth: 10, quantity: 4, can_rotate: true },
          ],
        });
      } else if (algoId === "packing_cuttingstock") {
        setFormData({
          problem_type: "1d",
          stock_length: 100,
          time_limit_seconds: 60,
          orders: [
            { _id: uid(), name: "Small Piece", length: 15, quantity: 10 },
            { _id: uid(), name: "Medium Piece", length: 25, quantity: 8 },
            { _id: uid(), name: "Large Piece", length: 40, quantity: 5 },
          ],
        });
      }
    }
  }, [algoId, formData]);

  const handleSolve = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await runSolver({ algo_id: algoId, inputs: formData });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Solver error");
    } finally {
      setLoading(false);
    }
  }, [algoId, formData]);

  const renderForm = () => {
    if (algoId === "packing_knapsack") {
      return <KnapsackForm value={formData} onChange={setFormData} />;
    }
    if (algoId === "packing_binpacking") {
      return <BinPackingForm value={formData} onChange={setFormData} />;
    }
    if (algoId === "packing_cuttingstock") {
      return <CuttingStockForm value={formData} onChange={setFormData} />;
    }
    return <div className="text-white/50 text-sm">Unknown algorithm</div>;
  };

  const renderResult = () => {
    if (!result) return null;
    if (algoId === "packing_knapsack") {
      return <KnapsackResult result={result} />;
    }
    if (algoId === "packing_binpacking") {
      return <BinPackingResult result={result} />;
    }
    if (algoId === "packing_cuttingstock") {
      return <CuttingStockResult result={result} />;
    }
    return <pre className="text-xs text-white/50 overflow-auto">{JSON.stringify(result, null, 2)}</pre>;
  };

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white">
      {/* Header */}
      <header className="border-b border-white/[0.08] bg-black/40 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center gap-4">
          <button onClick={() => router.push("/")} className="p-2 hover:bg-white/[0.05] rounded-lg transition-colors">
            <ArrowLeft className="w-5 h-5 text-white/60" />
          </button>
          <div className="flex-1">
            <h1 className={`text-xl font-semibold bg-gradient-to-r ${meta.color} bg-clip-text text-transparent`}>
              {meta.name}
            </h1>
            <p className="text-sm text-white/40">{meta.description}</p>
          </div>
          <button
            onClick={handleSolve}
            disabled={loading}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-medium transition-all ${
              loading
                ? "bg-white/10 text-white/40 cursor-not-allowed"
                : `bg-gradient-to-r ${meta.color} text-white hover:shadow-lg hover:shadow-violet-500/20`
            }`}
          >
            {loading ? (
              <>
                <LoaderIcon className="w-4 h-4 animate-spin" />
                Solving...
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                Solve
              </>
            )}
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Input Form */}
          <div>
            <h2 className="text-lg font-medium text-white/80 mb-4 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-violet-400" />
              Input Parameters
            </h2>
            {renderForm()}
          </div>

          {/* Results */}
          <div>
            <h2 className="text-lg font-medium text-white/80 mb-4 flex items-center gap-2">
              {result ? (
                result.status === "OPTIMAL" || result.status === "FEASIBLE" ? (
                  <CheckCircle className="w-5 h-5 text-green-400" />
                ) : (
                  <AlertCircle className="w-5 h-5 text-red-400" />
                )
              ) : (
                <Package className="w-5 h-5 text-white/40" />
              )}
              Results
            </h2>

            {error && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-4">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}

            {result ? (
              <div className="space-y-4">
                <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${
                  result.status === "OPTIMAL" ? "bg-green-500/10 text-green-400" :
                  result.status === "FEASIBLE" ? "bg-amber-500/10 text-amber-400" :
                  "bg-red-500/10 text-red-400"
                }`}>
                  {result.status as string}
                </div>
                {renderResult()}
              </div>
            ) : (
              <div className="bg-white/[0.02] border border-white/[0.06] rounded-xl p-8 text-center">
                <Package className="w-12 h-12 text-white/20 mx-auto mb-3" />
                <p className="text-white/40 text-sm">Configure parameters and click Solve to see results</p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
