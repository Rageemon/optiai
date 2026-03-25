'use client';

/**
 * Map Routing Solve Page — /solve/map-routing/[algo_id]
 *
 * - Click map directly to set start then end (no "activate mode" needed)
 * - Addresses from AI prompt shown dynamically
 * - POI preferences hidden unless the AI explicitly sets them
 * - Glass morphism styling matching the routing page design system
 */

import dynamic from 'next/dynamic';
import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react';
import { useParams, useSearchParams, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowLeft, Play, LoaderIcon, CheckCircle, AlertCircle,
  Navigation, MapPin, Sparkles, ChevronDown, ChevronUp,
  Info, Car, Footprints, Bike, RotateCcw, Route,
  MousePointerClick,
} from 'lucide-react';
import { runSolver, getSessionDraft } from '@/lib/api';
import type { MapViewProps, PoiPoint } from './_map-view';
import { POI_COLORS } from './_map-view';

// Leaflet — browser-only
const MapView = dynamic<MapViewProps>(
  () => import('./_map-view'),
  {
    ssr: false,
    loading: () => (
      <div className="h-full flex items-center justify-center text-white/20 text-sm">
        <LoaderIcon className="w-5 h-5 animate-spin mr-2" />Loading map...
      </div>
    ),
  },
);

// ============================================================================
// Shared UI primitives (matching routing page design system)
// ============================================================================

function SectionCard({
  title, icon, children, defaultOpen = true, badge,
}: {
  title: string;
  icon: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  badge?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.03] overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-white/[0.03] transition-colors"
      >
        <span className="text-white/50">{icon}</span>
        <span className="text-sm font-medium text-white/80 flex-1">{title}</span>
        {badge}
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
  label: string; hint?: string; children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-white/50 flex items-center gap-1">
        {label}
        {hint && <span title={hint} className="cursor-help text-white/30"><Info className="w-3 h-3" /></span>}
      </label>
      {children}
    </div>
  );
}

const inputCls =
  "w-full bg-white/[0.05] border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:border-sky-500/50 focus:bg-white/[0.07] transition-colors";

// ============================================================================
// Types
// ============================================================================

type NetworkType = 'drive' | 'walk' | 'bike';

interface FormValues {
  start_address:      string;
  end_address:        string;
  start_lat:          number | null;
  start_lng:          number | null;
  end_lat:            number | null;
  end_lng:            number | null;
  poi_preferences:    Record<string, number>;
  distance_weight:    number;
  avoid_highways:     boolean;
  network_type:       NetworkType;
  search_radius_m:    number;
  time_limit_seconds: number;
}

const DEFAULT_FORM: FormValues = {
  start_address:      '',
  end_address:        '',
  start_lat:          null,
  start_lng:          null,
  end_lat:            null,
  end_lng:            null,
  poi_preferences:    {},
  distance_weight:    0.5,
  avoid_highways:     false,
  network_type:       'drive',
  search_radius_m:    100,
  time_limit_seconds: 30,
};

const NETWORK_META: Record<NetworkType, { icon: typeof Car; label: string }> = {
  drive: { icon: Car,        label: 'Drive' },
  walk:  { icon: Footprints, label: 'Walk' },
  bike:  { icon: Bike,       label: 'Bike' },
};

// ============================================================================
// Page
// ============================================================================

export default function MapRoutingPage() {
  const params       = useParams();
  const searchParams = useSearchParams();
  const router       = useRouter();
  const algoId       = (params?.algo_id as string) ?? '';

  const [form,         setForm]         = useState<FormValues>(DEFAULT_FORM);
  const [result,       setResult]       = useState<Record<string, unknown> | null>(null);
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState<string | null>(null);
  const [aiPrefilled,  setAiPrefilled]  = useState(false);
  // Track the "next click" target — always active, cycles: start → end → done
  const [nextClick,    setNextClick]    = useState<'start' | 'end' | 'done'>('start');

  // Track if we already loaded the draft (prevent double-load)
  const draftLoaded = useRef(false);

  // Load AI-prefilled session draft
  useEffect(() => {
    if (draftLoaded.current) return;
    const sid = searchParams?.get('session');
    if (!sid) return;
    draftLoaded.current = true;
    getSessionDraft(sid)
      .then(d => {
        if (d.draft && Object.keys(d.draft).length > 0) {
          const draft = d.draft as Partial<FormValues>;
          setForm(prev => ({ ...prev, ...draft }));
          setAiPrefilled(true);
          // If the draft has addresses, don't need map clicks for initial
          if (draft.start_address && draft.end_address) {
            setNextClick('done');
          } else if (draft.start_address || (draft.start_lat != null)) {
            setNextClick('end');
          }
        }
      })
      .catch(() => {});
  }, [searchParams]);

  const patch = useCallback(<K extends keyof FormValues>(key: K, val: FormValues[K]) =>
    setForm(prev => ({ ...prev, [key]: val })), []);

  // Map click — always active, cycles start → end → done
  const handleMapClick = useCallback((lat: number, lng: number) => {
    if (nextClick === 'start') {
      setForm(prev => ({ ...prev, start_lat: lat, start_lng: lng, start_address: '' }));
      setNextClick('end');
    } else if (nextClick === 'end') {
      setForm(prev => ({ ...prev, end_lat: lat, end_lng: lng, end_address: '' }));
      setNextClick('done');
    }
    // When 'done', clicks are ignored — user must clear a point to re-enable
  }, [nextClick]);

  // When a point is cleared, re-enable clicking for that point
  const clearStart = useCallback(() => {
    setForm(p => ({ ...p, start_lat: null, start_lng: null, start_address: '' }));
    setNextClick('start');
  }, []);

  const clearEnd = useCallback(() => {
    setForm(p => ({ ...p, end_lat: null, end_lng: null, end_address: '' }));
    setNextClick('end');
  }, []);

  const handleSolve = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await runSolver({ algo_id: algoId, inputs: form as unknown as Record<string, unknown> });
      if ((res as { error?: string }).error) throw new Error((res as { error: string }).error);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Solver failed — is the backend running?');
    } finally {
      setLoading(false);
    }
  }, [algoId, form]);

  // ── Derived display data ────────────────────────────────────────────────
  type RouteInfo = { coordinates: [number, number][]; total_distance_km: number; estimated_time_min: number; node_count: number };
  type AltInfo   = { coordinates: [number, number][]; total_distance_km: number; estimated_time_min: number; poi_count: number };
  type StatsInfo = { pois_found: number; optimized_route_pois: number; baseline_route_pois: number; distance_overhead_pct: number; weights_used: Record<string, number> };

  const routeData = result?.route             as RouteInfo | undefined;
  const altRoute  = result?.alternative_route as AltInfo | null | undefined;
  const stats     = result?.stats             as StatsInfo | undefined;
  const pois      = (result?.pois_along_route as PoiPoint[] | undefined) ?? [];
  const poiByType: Record<string, number> = {};
  for (const p of pois) poiByType[p.type] = (poiByType[p.type] ?? 0) + 1;

  const startPos: [number, number] | null =
    form.start_lat != null && form.start_lng != null ? [form.start_lat, form.start_lng] : null;
  const endPos: [number, number] | null =
    form.end_lat != null && form.end_lng != null ? [form.end_lat, form.end_lng] : null;

  // POI preferences — only show if AI has set any > 0
  const hasPoiPreferences = Object.values(form.poi_preferences).some(v => v > 0);

  // Whether both points are set (either by address or coords)
  const hasStart = startPos != null || form.start_address.trim() !== '';
  const hasEnd   = endPos   != null || form.end_address.trim()   !== '';
  const canSolve = hasStart && hasEnd;

  // Click-enabled: whenever we still need a point
  const clickEnabled = nextClick !== 'done';

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0a0a0b] text-white">

      {/* ── Header ── */}
      <header className="sticky top-0 z-20 bg-black/60 backdrop-blur-xl border-b border-white/[0.05] px-4 py-3 flex items-center gap-3">
        <button
          onClick={() => router.push('/')}
          className="p-1.5 rounded-lg hover:bg-white/[0.06] text-white/40 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>

        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-sky-500 to-blue-600 flex items-center justify-center">
          <Navigation className="w-3.5 h-3.5 text-white" />
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white/90 truncate">Multi-Objective Map Routing</p>
          <p className="text-xs text-white/40 truncate">
            {hasStart && hasEnd
              ? `${form.start_address || 'Map point'} → ${form.end_address || 'Map point'}`
              : 'Real-world routes on OpenStreetMap'}
          </p>
        </div>

        {aiPrefilled && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-sky-500/15 border border-sky-500/25 text-xs text-sky-300 shrink-0">
            <Sparkles className="w-3 h-3" />
            AI-configured
          </div>
        )}

        <button
          onClick={handleSolve}
          disabled={loading || !canSolve}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all bg-gradient-to-r from-sky-500 to-blue-600 text-white shrink-0 ${
            loading || !canSolve ? 'opacity-50 cursor-not-allowed' : 'hover:scale-105 active:scale-100'
          }`}
        >
          {loading
            ? <><LoaderIcon className="w-4 h-4 animate-spin" />Routing...</>
            : <><Play className="w-4 h-4" />Solve</>}
        </button>
      </header>

      {/* ── Two-column layout ── */}
      <div className="max-w-6xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* ═══════════ LEFT: Input ═══════════ */}
        <div>
          <p className="text-xs text-white/30 uppercase tracking-wider mb-3">Input Configuration</p>

          <div className="space-y-4">

            {/* Click-on-map status banner */}
            <AnimatePresence mode="wait">
              {clickEnabled ? (
                <motion.div
                  key="click-banner"
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  className="rounded-xl border border-sky-500/30 bg-sky-500/[0.08] p-3.5"
                >
                  <div className="flex items-center gap-3">
                    <div className="relative">
                      <MousePointerClick className="w-5 h-5 text-sky-400" />
                      <div className={`absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full animate-pulse ${
                        nextClick === 'start' ? 'bg-emerald-400' : 'bg-red-400'
                      }`} />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-white/90">
                        {nextClick === 'start'
                          ? 'Click the map to set your start point'
                          : 'Now click the map to set your destination'}
                      </p>
                      <p className="text-xs text-white/40 mt-0.5">
                        {nextClick === 'start'
                          ? 'Or enter an address below'
                          : 'First click placed your start — now pick the end'}
                      </p>
                    </div>
                  </div>
                </motion.div>
              ) : canSolve && !result ? (
                <motion.div
                  key="ready-banner"
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.06] p-3.5"
                >
                  <div className="flex items-center gap-3">
                    <CheckCircle className="w-5 h-5 text-emerald-400" />
                    <div>
                      <p className="text-sm font-medium text-white/90">Route ready</p>
                      <p className="text-xs text-white/40 mt-0.5">Both points set — press Solve to find the route</p>
                    </div>
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>

            {/* Route Points */}
            <SectionCard title="Route Points" icon={<MapPin className="w-4 h-4" />}>
              <div className="space-y-3 mt-3">
                {/* Start */}
                <Field label="Start" hint="Click the map or type an address">
                  {startPos ? (
                    <div className="flex items-center justify-between bg-white/[0.04] border border-emerald-500/20 rounded-lg px-3 py-2">
                      <div className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                        <span className="font-mono text-xs text-emerald-400">
                          {startPos[0].toFixed(5)}, {startPos[1].toFixed(5)}
                        </span>
                      </div>
                      <button
                        onClick={clearStart}
                        className="text-white/30 hover:text-white/70 transition-colors text-xs"
                      >
                        Clear
                      </button>
                    </div>
                  ) : (
                    <input
                      type="text"
                      value={form.start_address}
                      onChange={e => {
                        patch('start_address', e.target.value);
                        if (e.target.value.trim()) setNextClick(prev => prev === 'start' ? 'end' : prev);
                      }}
                      placeholder="e.g. Kurla Station, Mumbai"
                      className={inputCls}
                    />
                  )}
                </Field>

                {/* End */}
                <Field label="Destination" hint="Click the map or type an address">
                  {endPos ? (
                    <div className="flex items-center justify-between bg-white/[0.04] border border-red-500/20 rounded-lg px-3 py-2">
                      <div className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
                        <span className="font-mono text-xs text-red-400">
                          {endPos[0].toFixed(5)}, {endPos[1].toFixed(5)}
                        </span>
                      </div>
                      <button
                        onClick={clearEnd}
                        className="text-white/30 hover:text-white/70 transition-colors text-xs"
                      >
                        Clear
                      </button>
                    </div>
                  ) : (
                    <input
                      type="text"
                      value={form.end_address}
                      onChange={e => {
                        patch('end_address', e.target.value);
                        if (e.target.value.trim()) setNextClick('done');
                      }}
                      placeholder="e.g. Thane Station, Mumbai"
                      className={inputCls}
                    />
                  )}
                </Field>
              </div>
            </SectionCard>

            {/* Travel Mode */}
            <SectionCard title="Travel Mode" icon={<Car className="w-4 h-4" />}>
              <div className="grid grid-cols-3 gap-2 mt-3">
                {(Object.entries(NETWORK_META) as [NetworkType, typeof NETWORK_META['drive']][]).map(([mode, meta]) => {
                  const Icon = meta.icon;
                  const active = form.network_type === mode;
                  return (
                    <button
                      key={mode}
                      onClick={() => patch('network_type', mode)}
                      className={`flex items-center justify-center gap-2 py-2.5 rounded-lg border text-xs font-medium transition-all ${
                        active
                          ? 'bg-sky-500/20 border-sky-500/40 text-sky-300'
                          : 'bg-white/[0.03] border-white/[0.08] text-white/50 hover:text-white/70 hover:border-white/[0.15]'
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                      {meta.label}
                    </button>
                  );
                })}
              </div>
            </SectionCard>

            {/* POI Preferences — ONLY when AI has set them via modification */}
            {hasPoiPreferences && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                <SectionCard
                  title="POI Preferences"
                  icon={<Sparkles className="w-4 h-4" />}
                  badge={
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/25">
                      AI-set
                    </span>
                  }
                >
                  <div className="space-y-3 mt-3">
                    <p className="text-xs text-white/30">
                      Set by AI based on your conversation. The route will prefer roads near these POI types.
                    </p>
                    {Object.entries(form.poi_preferences)
                      .filter(([, v]) => v > 0)
                      .sort(([, a], [, b]) => b - a)
                      .map(([type, weight]) => (
                        <div key={type} className="flex items-center gap-3">
                          <div
                            className="w-3 h-3 rounded-full shrink-0"
                            style={{ background: POI_COLORS[type] ?? POI_COLORS.default }}
                          />
                          <span className="text-xs text-white/60 capitalize flex-1">{type}</span>
                          <div className="flex-1 max-w-[120px]">
                            <div className="h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full transition-all"
                                style={{
                                  width: `${weight * 100}%`,
                                  background: POI_COLORS[type] ?? POI_COLORS.default,
                                }}
                              />
                            </div>
                          </div>
                          <span className="text-xs text-white/40 font-mono w-8 text-right">{weight.toFixed(1)}</span>
                        </div>
                      ))}
                  </div>
                </SectionCard>
              </motion.div>
            )}

            {/* Advanced Options */}
            <SectionCard title="Advanced Options" icon={<Info className="w-4 h-4" />} defaultOpen={false}>
              <div className="space-y-4 mt-3">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.avoid_highways}
                    onChange={e => patch('avoid_highways', e.target.checked)}
                    className="accent-sky-500"
                  />
                  <div>
                    <span className="text-sm text-white/70">Avoid highways</span>
                    <p className="text-xs text-white/30">Exclude motorways and trunk roads</p>
                  </div>
                </label>

                <Field label="Distance Weight" hint="0 = scenic/POI-rich. 1 = strict shortest path.">
                  <div className="flex items-center gap-3">
                    <input
                      type="range" min={0} max={1} step={0.05}
                      value={form.distance_weight}
                      onChange={e => patch('distance_weight', parseFloat(e.target.value))}
                      className="flex-1 h-1.5 rounded-full accent-sky-500 cursor-pointer"
                    />
                    <span className="text-xs text-white/40 font-mono w-10 text-right">{form.distance_weight.toFixed(2)}</span>
                  </div>
                </Field>

                <Field label="POI Search Radius" hint="How close a POI must be to a road edge to count">
                  <div className="flex items-center gap-3">
                    <input
                      type="range" min={50} max={500} step={50}
                      value={form.search_radius_m}
                      onChange={e => patch('search_radius_m', parseInt(e.target.value))}
                      className="flex-1 h-1.5 rounded-full accent-sky-500 cursor-pointer"
                    />
                    <span className="text-xs text-white/40 font-mono w-12 text-right">{form.search_radius_m} m</span>
                  </div>
                </Field>

                <Field label="Solver Timeout">
                  <input
                    type="number" min={10} max={120}
                    value={form.time_limit_seconds}
                    onChange={e => patch('time_limit_seconds', parseInt(e.target.value))}
                    className={inputCls}
                  />
                  <p className="text-xs text-white/20 mt-1">
                    First solve downloads OSM data and may be slow. Subsequent solves use cache.
                  </p>
                </Field>
              </div>
            </SectionCard>

            {/* Reset */}
            <button
              onClick={() => { setForm(DEFAULT_FORM); setResult(null); setError(null); setNextClick('start'); }}
              className="w-full flex items-center justify-center gap-2 text-xs text-white/20 hover:text-white/50 py-2 transition-colors"
            >
              <RotateCcw className="w-3 h-3" /> Reset to defaults
            </button>

            {/* JSON preview */}
            <details className="mt-2">
              <summary className="text-xs text-white/20 cursor-pointer hover:text-white/40 transition-colors">
                Preview JSON payload
              </summary>
              <pre className="mt-2 overflow-auto text-[10px] text-white/20 max-h-64 rounded-lg border border-white/[0.05] bg-white/[0.02] p-3">
                {JSON.stringify(form, null, 2)}
              </pre>
            </details>
          </div>
        </div>

        {/* ═══════════ RIGHT: Map + Results ═══════════ */}
        <div>
          <p className="text-xs text-white/30 uppercase tracking-wider mb-3">Map & Results</p>

          <div className="space-y-4">

            {/* Map */}
            <div
              className={`rounded-xl border overflow-hidden transition-all ${
                clickEnabled
                  ? 'border-sky-500/40 shadow-[0_0_24px_rgba(56,189,248,0.1)]'
                  : 'border-white/[0.08]'
              }`}
              style={{ height: '480px' }}
            >
              <MapView
                startPos={startPos}
                endPos={endPos}
                routeCoords={routeData?.coordinates ?? []}
                altCoords={altRoute?.coordinates ?? []}
                pois={pois}
                clickEnabled={clickEnabled}
                onMapClick={handleMapClick}
              />
            </div>

            {/* Map legend */}
            <div className="flex flex-wrap gap-x-4 gap-y-1.5 px-1 text-[11px] text-white/30">
              <div className="flex items-center gap-1.5">
                <div className="w-5 h-[3px] rounded bg-blue-500" />
                <span>Optimised route</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-5 h-[2px] rounded"
                  style={{ background: 'repeating-linear-gradient(90deg,#94a3b8 0,#94a3b8 3px,transparent 3px,transparent 6px)' }} />
                <span>Shortest baseline</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                <span>Start</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
                <span>End</span>
              </div>
              {pois.length > 0 && Object.keys(poiByType).map(type => (
                <div key={type} className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full" style={{ background: POI_COLORS[type] ?? POI_COLORS.default }} />
                  <span className="capitalize">{type}</span>
                </div>
              ))}
            </div>

            {/* Error */}
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

            {/* Loading */}
            {loading && (
              <div className="flex flex-col items-center justify-center h-32 rounded-xl border border-white/[0.08] bg-white/[0.02]">
                <LoaderIcon className="w-6 h-6 animate-spin text-sky-500 mb-2" />
                <p className="text-sm text-white/40">Downloading road network & computing route...</p>
                <p className="text-xs text-white/20 mt-1">First solve may download OSM data</p>
              </div>
            )}

            {/* Empty state */}
            {!result && !loading && !error && (
              <div className="flex flex-col items-center justify-center h-48 rounded-xl border border-dashed border-white/[0.08] text-white/20">
                <Route className="w-8 h-8 mb-3" />
                <p className="text-sm">
                  {canSolve ? 'Ready — press Solve to find the route' : 'Pick your start and end on the map'}
                </p>
                <p className="text-xs mt-1 text-white/15">OpenStreetMap + NetworkX Dijkstra</p>
              </div>
            )}

            {/* Results */}
            {result && stats && routeData && (
              <AnimatePresence>
                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="space-y-4"
                >
                  {/* Status */}
                  <div className="flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                    <span className="text-sm font-medium text-emerald-300">Route found</span>
                    <span className="text-xs text-white/25 ml-1">{routeData.node_count} nodes</span>
                  </div>

                  {/* KPI cards */}
                  <div className="flex flex-wrap gap-3">
                    <div className="rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-3">
                      <p className="text-xs text-sky-400/70">Route Distance</p>
                      <p className="text-2xl font-bold text-sky-300 tabular-nums">
                        {routeData.total_distance_km.toFixed(2)}
                        <span className="text-sm font-normal ml-1.5 text-sky-400/60">km</span>
                      </p>
                    </div>

                    <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
                      <p className="text-xs text-white/40">Est. Time</p>
                      <p className="text-xl font-bold text-white/80 tabular-nums">
                        {Math.round(routeData.estimated_time_min)}
                        <span className="text-sm font-normal text-white/30 ml-1">min</span>
                      </p>
                    </div>

                    {stats.optimized_route_pois > 0 && (
                      <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.07] px-4 py-3">
                        <p className="text-xs text-emerald-400/70">POIs Along Route</p>
                        <p className="text-xl font-bold text-emerald-300 tabular-nums">{stats.optimized_route_pois}</p>
                      </div>
                    )}

                    {stats.distance_overhead_pct !== 0 && (
                      <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
                        <p className="text-xs text-white/40">Distance Overhead</p>
                        <p className={`text-xl font-bold tabular-nums ${
                          stats.distance_overhead_pct <= 10 ? 'text-emerald-300' :
                          stats.distance_overhead_pct <= 25 ? 'text-yellow-300' : 'text-red-300'
                        }`}>
                          {stats.distance_overhead_pct > 0 ? '+' : ''}{stats.distance_overhead_pct}%
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Route comparison */}
                  {altRoute && (
                    <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden">
                      <div className="px-4 py-3 border-b border-white/[0.05]">
                        <p className="text-xs text-white/40 font-medium uppercase tracking-wider">Route Comparison</p>
                      </div>
                      <div className="grid grid-cols-2 divide-x divide-white/[0.05]">
                        <div className="p-4 space-y-2">
                          <div className="flex items-center gap-2 mb-3">
                            <div className="w-4 h-[3px] bg-blue-500 rounded" />
                            <span className="text-xs font-medium text-sky-300">Optimised</span>
                          </div>
                          {[
                            ['Distance', `${routeData.total_distance_km.toFixed(2)} km`],
                            ['Est. time', `${Math.round(routeData.estimated_time_min)} min`],
                            ['POIs', String(stats.optimized_route_pois)],
                          ].map(([label, val]) => (
                            <div key={label} className="flex justify-between text-xs">
                              <span className="text-white/40">{label}</span>
                              <span className="text-white/70 font-mono">{val}</span>
                            </div>
                          ))}
                        </div>
                        <div className="p-4 space-y-2">
                          <div className="flex items-center gap-2 mb-3">
                            <div className="w-4 h-[2px] bg-white/30 rounded" />
                            <span className="text-xs font-medium text-white/50">Shortest</span>
                          </div>
                          {[
                            ['Distance', `${altRoute.total_distance_km.toFixed(2)} km`],
                            ['Est. time', `${Math.round(altRoute.estimated_time_min)} min`],
                            ['POIs', String(altRoute.poi_count)],
                          ].map(([label, val]) => (
                            <div key={label} className="flex justify-between text-xs">
                              <span className="text-white/40">{label}</span>
                              <span className="text-white/50 font-mono">{val}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* POI breakdown */}
                  {Object.keys(poiByType).length > 0 && (
                    <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                      <p className="text-xs text-white/35 mb-3">POIs along optimised route</p>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(poiByType).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
                          <span
                            key={type}
                            className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border"
                            style={{
                              background:  `${POI_COLORS[type] ?? '#64748b'}18`,
                              borderColor: `${POI_COLORS[type] ?? '#64748b'}50`,
                              color:        POI_COLORS[type] ?? '#94a3b8',
                            }}
                          >
                            <div className="w-2 h-2 rounded-full" style={{ background: POI_COLORS[type] ?? '#64748b' }} />
                            {count} {type}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Active weights */}
                  {stats.weights_used && (
                    <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                      <p className="text-xs text-white/35 mb-3">Active weights</p>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(stats.weights_used)
                          .filter(([, v]) => v > 0)
                          .map(([key, val]) => (
                            <span key={key} className="text-xs px-2.5 py-1 rounded-full bg-white/[0.05] border border-white/[0.1] text-white/50">
                              {key}: <span className="text-white/70 font-mono">{val.toFixed(2)}</span>
                            </span>
                          ))}
                      </div>
                    </div>
                  )}

                  {/* Raw JSON */}
                  <details className="text-xs text-white/25">
                    <summary className="cursor-pointer hover:text-white/40 transition-colors">Raw JSON response</summary>
                    <pre className="mt-2 overflow-auto text-[10px] text-white/20 max-h-56 rounded-lg border border-white/[0.05] bg-white/[0.02] p-3">
                      {JSON.stringify(result, null, 2)}
                    </pre>
                  </details>
                </motion.div>
              </AnimatePresence>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
