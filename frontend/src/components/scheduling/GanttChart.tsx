"use client";
/**
 * GanttChart — SVG Gantt chart for Job Shop and RCPSP results.
 *
 * Props:
 *   rows     — array of { label: string; bars: { start, end, color?, tooltip? }[] }
 *   horizon  — max time unit (X axis)
 *   timeUnit — label for the X axis (default "t")
 */

import { useMemo } from "react";

export interface GanttBar {
  start:    number;
  end:      number;
  label?:   string;
  color?:   string;
  tooltip?: string;
}

export interface GanttRow {
  label: string;
  bars:  GanttBar[];
}

const PALETTE = [
  "#7c3aed", "#2563eb", "#059669", "#d97706", "#dc2626",
  "#7e22ce", "#0891b2", "#16a34a", "#ea580c", "#9333ea",
  "#0284c7", "#65a30d", "#b45309", "#e11d48", "#0d9488",
];

function colorForLabel(label: string, palette = PALETTE): string {
  let hash = 0;
  for (let i = 0; i < label.length; i++) hash = label.charCodeAt(i) + ((hash << 5) - hash);
  return palette[Math.abs(hash) % palette.length];
}

interface GanttChartProps {
  rows:       GanttRow[];
  horizon:    number;
  timeUnit?:  string;
  pixelsPerUnit?: number;
}

export function GanttChart({
  rows,
  horizon,
  timeUnit     = "t",
  pixelsPerUnit = 28,
}: GanttChartProps) {
  const ROW_H   = 36;
  const LABEL_W = 110;
  const PAD     = 16;
  const TICK    = 5; // tick every N units

  const chartW = horizon * pixelsPerUnit;
  const chartH = rows.length * ROW_H;
  const svgW   = chartW + LABEL_W + PAD * 2;
  const svgH   = chartH + 48; // extra for axis

  const ticks = useMemo(() => {
    const out = [];
    for (let t = 0; t <= horizon; t += TICK) out.push(t);
    if (horizon % TICK !== 0) out.push(horizon);
    return out;
  }, [horizon]);

  return (
    <div className="overflow-x-auto">
      <svg width={svgW} height={svgH} className="font-mono text-xs" aria-label="Gantt chart">
        {/* Row backgrounds */}
        {rows.map((_, i) => (
          <rect
            key={i}
            x={LABEL_W}
            y={i * ROW_H}
            width={chartW + PAD}
            height={ROW_H}
            fill={i % 2 === 0 ? "rgba(255,255,255,0.02)" : "transparent"}
          />
        ))}

        {/* Grid lines */}
        {ticks.map(t => (
          <line
            key={t}
            x1={LABEL_W + t * pixelsPerUnit}
            y1={0}
            x2={LABEL_W + t * pixelsPerUnit}
            y2={chartH}
            stroke="rgba(255,255,255,0.08)"
            strokeWidth={1}
          />
        ))}

        {/* Row labels */}
        {rows.map((row, i) => (
          <text
            key={i}
            x={LABEL_W - 8}
            y={i * ROW_H + ROW_H / 2 + 4}
            textAnchor="end"
            fill="rgba(255,255,255,0.55)"
            fontSize={11}
          >
            {row.label.length > 14 ? row.label.slice(0, 13) + "…" : row.label}
          </text>
        ))}

        {/* Bars */}
        {rows.map((row, i) =>
          row.bars.map((bar, j) => {
            const barX = LABEL_W + bar.start * pixelsPerUnit;
            const barW = Math.max(2, (bar.end - bar.start) * pixelsPerUnit - 2);
            const barY = i * ROW_H + 6;
            const barH = ROW_H - 12;
            const fill = bar.color ?? colorForLabel(bar.label ?? row.label);
            return (
              <g key={j}>
                <rect
                  x={barX} y={barY} width={barW} height={barH}
                  rx={3} fill={fill} opacity={0.85}
                />
                {barW > 30 && (
                  <text
                    x={barX + barW / 2} y={barY + barH / 2 + 4}
                    textAnchor="middle" fill="white" fontSize={10} fontWeight="600"
                  >
                    {bar.label ?? ""}
                  </text>
                )}
                <title>{bar.tooltip ?? `${bar.label ?? ""} [${bar.start}–${bar.end}]`}</title>
              </g>
            );
          })
        )}

        {/* X-axis ticks */}
        {ticks.map(t => (
          <g key={t}>
            <line
              x1={LABEL_W + t * pixelsPerUnit}
              y1={chartH}
              x2={LABEL_W + t * pixelsPerUnit}
              y2={chartH + 6}
              stroke="rgba(255,255,255,0.3)"
            />
            <text
              x={LABEL_W + t * pixelsPerUnit}
              y={chartH + 18}
              textAnchor="middle"
              fill="rgba(255,255,255,0.4)"
              fontSize={10}
            >
              {t}
            </text>
          </g>
        ))}

        {/* X-axis label */}
        <text
          x={LABEL_W + chartW / 2}
          y={chartH + 36}
          textAnchor="middle"
          fill="rgba(255,255,255,0.3)"
          fontSize={10}
        >
          {timeUnit}
        </text>
      </svg>
    </div>
  );
}

/**
 * Resource usage bar chart for RCPSP results.
 */
export function ResourceChart({
  usage,
  capacity,
  resource,
}: {
  usage:    number[];
  capacity: number;
  resource: string;
}) {
  const maxY  = Math.max(capacity, ...usage) || 1;
  const W     = 600;
  const H     = 120;
  const barW  = Math.max(2, Math.floor((W - 40) / Math.max(usage.length, 1)));

  return (
    <div>
      <p className="text-xs text-white/40 mb-1">{resource} usage over time (capacity = {capacity})</p>
      <svg width={W} height={H} className="overflow-visible">
        {/* Capacity line */}
        <line
          x1={40} y1={H - (capacity / maxY) * (H - 20) - 10}
          x2={W}  y2={H - (capacity / maxY) * (H - 20) - 10}
          stroke="#ef4444" strokeDasharray="4,2" strokeWidth={1}
        />
        {usage.map((u, t) => {
          const barH = Math.max(1, (u / maxY) * (H - 20));
          return (
            <rect
              key={t}
              x={40 + t * barW}
              y={H - barH - 10}
              width={barW - 1}
              height={barH}
              fill={u > capacity ? "#ef4444" : "#7c3aed"}
              opacity={0.7}
            />
          );
        })}
        {/* Y axis */}
        <text x={2} y={15} fill="rgba(255,255,255,0.3)" fontSize={9}>
          {maxY}
        </text>
        <text x={2} y={H - 10} fill="rgba(255,255,255,0.3)" fontSize={9}>
          0
        </text>
      </svg>
    </div>
  );
}
