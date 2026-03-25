"use client";
/**
 * TimetableGrid — Visual weekly timetable for educational scheduling results.
 * 
 * Shows a class or teacher's timetable as a grid: columns = days, rows = time slots.
 * Color-coded by subject. Supports merged-lecture indicators.
 */

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";

const SUBJECT_COLORS = [
  "bg-violet-500/20 border-violet-500/40 text-violet-200",
  "bg-blue-500/20 border-blue-500/40 text-blue-200",
  "bg-emerald-500/20 border-emerald-500/40 text-emerald-200",
  "bg-amber-500/20 border-amber-500/40 text-amber-200",
  "bg-rose-500/20 border-rose-500/40 text-rose-200",
  "bg-cyan-500/20 border-cyan-500/40 text-cyan-200",
  "bg-fuchsia-500/20 border-fuchsia-500/40 text-fuchsia-200",
  "bg-lime-500/20 border-lime-500/40 text-lime-200",
  "bg-orange-500/20 border-orange-500/40 text-orange-200",
  "bg-teal-500/20 border-teal-500/40 text-teal-200",
];

function subjectColor(subject: string, allSubjects: string[]): string {
  const idx = allSubjects.indexOf(subject);
  return SUBJECT_COLORS[idx % SUBJECT_COLORS.length];
}

interface TimetableEntry {
  slot:        number;
  subject:     string;
  teacher?:    string;    // present in class view
  class_id?:   string;    // present in teacher view
  room?:       string | null;
  merged_with?: string[] | null;
}

interface TimetableGridProps {
  /** by_class or by_teacher — outer key is entity name, inner key is day name */
  data:        Record<string, Record<string, TimetableEntry[]>>;
  days:        string[];
  slotsPerDay: number;
  mode:        "class" | "teacher";
}

export function TimetableGrid({ data, days, slotsPerDay, mode }: TimetableGridProps) {
  const entityNames = Object.keys(data);
  const [selected, setSelected] = useState(entityNames[0] ?? "");

  const allSubjects = useMemo(() => {
    const set = new Set<string>();
    Object.values(data).forEach(dayMap =>
      Object.values(dayMap).forEach(entries =>
        entries.forEach(e => set.add(e.subject))
      )
    );
    return [...set].sort();
  }, [data]);

  const slots = Array.from({ length: slotsPerDay }, (_, i) => i);
  const schedule = data[selected] ?? {};

  // Build lookup: day → slot → entry
  const lookup: Record<string, Record<number, TimetableEntry>> = {};
  for (const day of days) {
    lookup[day] = {};
    for (const entry of schedule[day] ?? []) {
      lookup[day][entry.slot] = entry;
    }
  }

  return (
    <div className="space-y-4">
      {/* Entity selector */}
      <div className="flex flex-wrap gap-2">
        {entityNames.map(name => (
          <button
            key={name}
            onClick={() => setSelected(name)}
            className={cn(
              "px-3 py-1 rounded-lg text-xs font-medium border transition-colors",
              selected === name
                ? "bg-violet-600 border-violet-500 text-white"
                : "bg-white/[0.04] border-white/10 text-white/50 hover:text-white hover:bg-white/[0.08]"
            )}
          >
            {name}
          </button>
        ))}
      </div>

      {/* Subject legend */}
      <div className="flex flex-wrap gap-2">
        {allSubjects.map(s => (
          <span key={s} className={cn("text-xs px-2 py-0.5 rounded border", subjectColor(s, allSubjects))}>
            {s}
          </span>
        ))}
      </div>

      {/* Grid */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr>
              <th className="w-12 text-white/30 font-normal p-2 text-left">Slot</th>
              {days.map(day => (
                <th key={day} className="text-white/60 font-medium p-2 text-center min-w-[110px]">
                  {day}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slots.map(slot => (
              <tr key={slot} className="border-t border-white/[0.05]">
                <td className="text-white/30 p-2 font-mono">{slot + 1}</td>
                {days.map(day => {
                  const entry = lookup[day]?.[slot];
                  if (!entry) {
                    return (
                      <td key={day} className="p-1">
                        <div className="h-12 rounded border border-white/[0.05] bg-white/[0.01]" />
                      </td>
                    );
                  }
                  return (
                    <td key={day} className="p-1">
                      <div
                        className={cn(
                          "h-12 rounded border px-2 py-1 flex flex-col justify-center gap-0.5",
                          subjectColor(entry.subject, allSubjects)
                        )}
                      >
                        <p className="font-semibold leading-tight truncate">{entry.subject}</p>
                        <p className="text-[10px] opacity-70 truncate">
                          {mode === "class"
                            ? entry.teacher
                            : entry.class_id?.startsWith("[MERGED]")
                            ? entry.class_id
                            : entry.class_id}
                        </p>
                        {entry.room && (
                          <p className="text-[9px] opacity-50 truncate">{entry.room}</p>
                        )}
                        {entry.merged_with && entry.merged_with.length > 1 && (
                          <p className="text-[9px] opacity-60">⊕ merged</p>
                        )}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


/**
 * ShiftCalendar — Weekly shift schedule display for workforce scheduling.
 * Rows = employees, Columns = days, cells show shift name (color-coded).
 */
interface ShiftCalendarProps {
  schedule:  Record<string, Record<string, string | null>>;
  days:      string[];
  shifts:    string[];
  coverage?: Record<string, Record<string, { assigned: number; required: number }>>;
}

const SHIFT_COLORS: Record<string, string> = {};
const SHIFT_PALETTE = [
  "bg-violet-500/20 border-violet-500/40 text-violet-200",
  "bg-blue-500/20 border-blue-500/40 text-blue-200",
  "bg-emerald-500/20 border-emerald-500/40 text-emerald-200",
  "bg-amber-500/20 border-amber-500/40 text-amber-200",
  "bg-rose-500/20 border-rose-500/40 text-rose-200",
];

function shiftColor(shiftName: string, allShifts: string[]): string {
  const idx = allShifts.indexOf(shiftName);
  return SHIFT_PALETTE[idx % SHIFT_PALETTE.length];
}

export function ShiftCalendar({ schedule, days, shifts, coverage }: ShiftCalendarProps) {
  const employees = Object.keys(schedule);

  return (
    <div className="space-y-4 overflow-x-auto">
      {/* Legend */}
      <div className="flex flex-wrap gap-2">
        {shifts.map(s => (
          <span key={s} className={cn("text-xs px-2 py-0.5 rounded border", shiftColor(s, shifts))}>
            {s}
          </span>
        ))}
        <span className="text-xs px-2 py-0.5 rounded border border-white/10 text-white/30">
          — off
        </span>
      </div>

      {/* Schedule grid */}
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            <th className="text-white/40 font-normal p-2 text-left min-w-[100px]">Employee</th>
            {days.map(d => (
              <th key={d} className="text-white/60 p-2 text-center min-w-[80px]">{d}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {employees.map(emp => (
            <tr key={emp} className="border-t border-white/[0.05]">
              <td className="text-white/70 p-2 font-medium">{emp}</td>
              {days.map(day => {
                const shift = schedule[emp][day];
                return (
                  <td key={day} className="p-1">
                    {shift ? (
                      <div className={cn(
                        "rounded border px-2 py-1 text-center text-[11px] font-medium",
                        shiftColor(shift, shifts)
                      )}>
                        {shift}
                      </div>
                    ) : (
                      <div className="rounded border border-white/[0.05] px-2 py-1 text-center text-white/20 text-[11px]">
                        off
                      </div>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {/* Coverage check */}
      {coverage && (
        <div className="mt-4">
          <p className="text-xs text-white/40 mb-2">Coverage summary</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
            {Object.entries(coverage).map(([day, shiftCov]) =>
              Object.entries(shiftCov).map(([shift, { assigned, required }]) => {
                const ok = assigned >= required;
                return (
                  <div
                    key={`${day}-${shift}`}
                    className={cn(
                      "rounded-lg border px-3 py-2 text-xs",
                      ok
                        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                        : "border-red-500/30 bg-red-500/10 text-red-300"
                    )}
                  >
                    <p className="font-medium">{day} · {shift}</p>
                    <p className="opacity-70">{assigned}/{required} staff</p>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
