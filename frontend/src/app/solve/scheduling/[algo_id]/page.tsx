"use client";

/**
 * Dynamic Solve Page — /solve/[algo_id]
 *
 * Renders a multi-section structured input form for each scheduling algorithm,
 * submits to POST /api/solve, and displays rich results (Gantt, timetable, etc.).
 */

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft, Play, LoaderIcon, CheckCircle, AlertCircle,
  Plus, Trash2, Sparkles, ChevronDown, ChevronUp, Info,
  Users, Clock, BookOpen, Building2, Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { runSolver, findSubstitutes, getSessionDraft } from "@/lib/api";
import { GanttChart, ResourceChart } from "@/components/scheduling/GanttChart";
import type { GanttRow } from "@/components/scheduling/GanttChart";
import { TimetableGrid, ShiftCalendar } from "@/components/scheduling/TimetableGrid";

// ============================================================================
// Algo metadata
// ============================================================================

const ALGO_META: Record<string, { name: string; description: string; color: string }> = {
  scheduling_jssp: {
    name:        "Job Shop & Machine Scheduling",
    description: "Schedule jobs on machines to minimise makespan or weighted tardiness.",
    color:       "from-orange-500 to-amber-600",
  },
  scheduling_shift: {
    name:        "Employee Shift Scheduling",
    description: "Assign employees to shifts satisfying coverage and rest requirements.",
    color:       "from-blue-500 to-cyan-600",
  },
  scheduling_nurse: {
    name:        "Nurse Rostering",
    description: "Skilled nurse rostering with shift-level qualification requirements.",
    color:       "from-pink-500 to-rose-600",
  },
  scheduling_timetable: {
    name:        "Educational Timetabling",
    description: "Generate a conflict-free school timetable with teachers, classes, and rooms.",
    color:       "from-violet-500 to-indigo-600",
  },
  scheduling_rcpsp: {
    name:        "Project Scheduling (RCPSP)",
    description: "Schedule project activities with precedence constraints and shared resources.",
    color:       "from-emerald-500 to-teal-600",
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
// Job Shop form
// ============================================================================

type TaskDef    = { _id: string; machine: string; duration: number };
type JobDef     = { _id: string; name: string; due_date: number|null; priority: number; tasks: TaskDef[] };
type MachineDef = { _id: string; name: string; count: number };

function JobShopForm({
  value, onChange,
}: {
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}) {
  const jobs     = (value.jobs     as JobDef[])     ?? [];
  const machines = (value.machines as MachineDef[]) ?? [];
  const set = (patch: object) => onChange({ ...value, ...patch });

  const addJob = () => set({ jobs: [...jobs, { _id: uid(), name: `Job-${jobs.length+1}`, due_date: null, priority: 1, tasks: [{ _id: uid(), machine: machines[0]?.name ?? "M1", duration: 3 }] }] });
  const removeJob = (id: string) => set({ jobs: jobs.filter(j => j._id !== id) });
  const updateJob = (id: string, patch: Partial<JobDef>) => set({ jobs: jobs.map(j => j._id === id ? { ...j, ...patch } : j) });
  const addTask = (jid: string) => updateJob(jid, { tasks: [...(jobs.find(j=>j._id===jid)?.tasks??[]), { _id: uid(), machine: machines[0]?.name ?? "M1", duration: 2 }] });
  const removeTask = (jid: string, tid: string) => updateJob(jid, { tasks: (jobs.find(j=>j._id===jid)?.tasks??[]).filter(t=>t._id!==tid) });
  const updateTask = (jid: string, tid: string, patch: Partial<TaskDef>) =>
    updateJob(jid, { tasks: (jobs.find(j=>j._id===jid)?.tasks??[]).map(t=>t._id===tid?{...t,...patch}:t) });
  const addMachine = () => set({ machines: [...machines, { _id: uid(), name: `M${machines.length+1}`, count: 1 }] });
  const removeMachine = (id: string) => set({ machines: machines.filter(m=>m._id!==id) });
  const updateMachine = (id: string, patch: Partial<MachineDef>) => set({ machines: machines.map(m=>m._id===id?{...m,...patch}:m) });

  return (
    <div className="space-y-4 mt-3">
      <SectionCard title="Configuration" icon={<Layers className="w-4 h-4"/>}>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Problem Type">
            <select value={(value.problem_type as string) ?? "jssp"} onChange={e=>set({problem_type:e.target.value})} className={inputCls}>
              <option value="jssp">Job Shop (JSSP)</option>
              <option value="fssp">Flow Shop (FSSP)</option>
              <option value="parallel">Parallel Machines</option>
            </select>
          </Field>
          <Field label="Objective">
            <select value={(value.objective as string) ?? "makespan"} onChange={e=>set({objective:e.target.value})} className={inputCls}>
              <option value="makespan">Minimise Makespan</option>
              <option value="weighted_tardiness">Minimise Weighted Tardiness</option>
            </select>
          </Field>
        </div>
      </SectionCard>

      <SectionCard title={`Machines (${machines.length})`} icon={<Building2 className="w-4 h-4"/>}>
        <div className="space-y-2 mt-3">
          {machines.map(m => (
            <div key={m._id} className="flex items-center gap-2">
              <input value={m.name} onChange={e=>updateMachine(m._id,{name:e.target.value})} placeholder="Name" className={`${inputCls} flex-1`} />
              <input type="number" min={1} value={m.count} onChange={e=>updateMachine(m._id,{count:Number(e.target.value)})} className={`${inputCls} w-20`} title="Copies" />
              <button onClick={()=>removeMachine(m._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
            </div>
          ))}
          <button onClick={addMachine} className={addBtnCls}><Plus className="w-3 h-3"/> Add Machine</button>
        </div>
      </SectionCard>

      <SectionCard title={`Jobs (${jobs.length})`} icon={<Layers className="w-4 h-4"/>}>
        <div className="space-y-4 mt-3">
          {jobs.map(job => (
            <div key={job._id} className="border border-white/[0.07] rounded-lg p-3 space-y-2">
              <div className="flex items-center gap-2">
                <input value={job.name} onChange={e=>updateJob(job._id,{name:e.target.value})} placeholder="Job name" className={`${inputCls} flex-1`} />
                <input type="number" min={1} value={job.priority} onChange={e=>updateJob(job._id,{priority:Number(e.target.value)})} placeholder="Priority" className={`${inputCls} w-20`} title="Weight" />
                <input type="number" value={job.due_date??""} onChange={e=>updateJob(job._id,{due_date:e.target.value?Number(e.target.value):null})} placeholder="Due" className={`${inputCls} w-20`} title="Due date" />
                <button onClick={()=>removeJob(job._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
              </div>
              <div className="pl-2 border-l border-white/[0.06] space-y-1.5">
                {job.tasks.map(task => (
                  <div key={task._id} className="flex items-center gap-2">
                    <span className="text-white/20 text-xs w-4">&rsaquo;</span>
                    <input value={task.machine} onChange={e=>updateTask(job._id,task._id,{machine:e.target.value})} placeholder="Machine" className={`${inputCls} flex-1`} />
                    <input type="number" min={1} value={task.duration} onChange={e=>updateTask(job._id,task._id,{duration:Number(e.target.value)})} className={`${inputCls} w-20`} title="Duration" />
                    <button onClick={()=>removeTask(job._id,task._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
                  </div>
                ))}
                <button onClick={()=>addTask(job._id)} className={`${addBtnCls} ml-6`}><Plus className="w-3 h-3"/> Add Task</button>
              </div>
            </div>
          ))}
          <button onClick={addJob} className={addBtnCls}><Plus className="w-3 h-3"/> Add Job</button>
        </div>
      </SectionCard>
    </div>
  );
}

// ============================================================================
// Shift Scheduling form (shared for scheduling_shift and scheduling_nurse)
// ============================================================================

type EmpDef   = { _id:string; name:string; skills:string; max_shifts_per_week:number; max_hours_per_week:number; min_hours_per_week:number; requested_days_off:string; preferred_shifts:string };
type ShiftDef = { _id:string; name:string; start_hour:number; end_hour:number; required_count:number; days:string };

function ShiftForm({
  value, onChange,
}: {
  value: Record<string,unknown>;
  onChange: (v:Record<string,unknown>) => void;
}) {
  const employees = (value.employees as EmpDef[]) ?? [];
  const shifts    = (value.shifts as ShiftDef[]) ?? [];
  const days      = (value.days as string[]) ?? ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
  const set = (patch: object) => onChange({ ...value, ...patch });

  const addEmp = () => set({ employees:[...employees, { _id:uid(), name:`Employee ${employees.length+1}`, skills:"", max_shifts_per_week:5, max_hours_per_week:40, min_hours_per_week:0, requested_days_off:"", preferred_shifts:"" }] });
  const removeEmp = (id:string) => set({ employees: employees.filter(e=>e._id!==id) });
  const updateEmp = (id:string, patch:Partial<EmpDef>) => set({ employees: employees.map(e=>e._id===id?{...e,...patch}:e) });

  const addShift = () => set({ shifts:[...shifts, { _id:uid(), name:`Shift ${shifts.length+1}`, start_hour:9, end_hour:17, required_count:2, days:"" }] });
  const removeShift = (id:string) => set({ shifts: shifts.filter(s=>s._id!==id) });
  const updateShift = (id:string, patch:Partial<ShiftDef>) => set({ shifts: shifts.map(s=>s._id===id?{...s,...patch}:s) });

  return (
    <div className="space-y-4 mt-3">
      <SectionCard title="Scheduling Horizon" icon={<Clock className="w-4 h-4"/>}>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Days (comma-separated)">
            <input value={days.join(",")} onChange={e=>set({days:e.target.value.split(",").map((d:string)=>d.trim())})} className={inputCls} />
          </Field>
          <Field label="Min rest hours between shifts">
            <input type="number" min={0} value={(value.min_rest_hours as number)??8} onChange={e=>set({min_rest_hours:Number(e.target.value)})} className={inputCls} />
          </Field>
          <Field label="Max consecutive working days">
            <input type="number" min={1} value={(value.max_consecutive_days as number)??5} onChange={e=>set({max_consecutive_days:Number(e.target.value)})} className={inputCls} />
          </Field>
        </div>
      </SectionCard>

      <SectionCard title={`Shifts (${shifts.length})`} icon={<Clock className="w-4 h-4"/>}>
        <div className="space-y-3 mt-3">
          {shifts.map(s => (
            <div key={s._id} className="border border-white/[0.07] rounded-lg p-3 grid grid-cols-2 gap-2">
              <Field label="Shift Name"><input value={s.name} onChange={e=>updateShift(s._id,{name:e.target.value})} className={inputCls}/></Field>
              <Field label="Required Staff"><input type="number" min={1} value={s.required_count} onChange={e=>updateShift(s._id,{required_count:Number(e.target.value)})} className={inputCls}/></Field>
              <Field label="Start Hour (0-23)"><input type="number" min={0} max={23} value={s.start_hour} onChange={e=>updateShift(s._id,{start_hour:Number(e.target.value)})} className={inputCls}/></Field>
              <Field label="End Hour"><input type="number" min={1} value={s.end_hour} onChange={e=>updateShift(s._id,{end_hour:Number(e.target.value)})} className={inputCls}/></Field>
              <div className="col-span-2 flex items-end gap-2">
                <div className="flex-1">
                  <Field label="Days (blank = all days)"><input value={s.days} onChange={e=>updateShift(s._id,{days:e.target.value})} placeholder="Mon,Tue,... (blank = all)" className={inputCls}/></Field>
                </div>
                <button onClick={()=>removeShift(s._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
              </div>
            </div>
          ))}
          <button onClick={addShift} className={addBtnCls}><Plus className="w-3 h-3"/> Add Shift</button>
        </div>
      </SectionCard>

      <SectionCard title={`Employees (${employees.length})`} icon={<Users className="w-4 h-4"/>}>
        <div className="space-y-3 mt-3">
          {employees.map(e => (
            <div key={e._id} className="border border-white/[0.07] rounded-lg p-3 grid grid-cols-2 gap-2">
              <Field label="Name"><input value={e.name} onChange={ev=>updateEmp(e._id,{name:ev.target.value})} className={inputCls}/></Field>
              <Field label="Max Shifts/Week"><input type="number" min={0} value={e.max_shifts_per_week} onChange={ev=>updateEmp(e._id,{max_shifts_per_week:Number(ev.target.value)})} className={inputCls}/></Field>
              <Field label="Max Hours/Week"><input type="number" min={0} value={e.max_hours_per_week} onChange={ev=>updateEmp(e._id,{max_hours_per_week:Number(ev.target.value)})} className={inputCls}/></Field>
              <Field label="Min Hours/Week"><input type="number" min={0} value={e.min_hours_per_week} onChange={ev=>updateEmp(e._id,{min_hours_per_week:Number(ev.target.value)})} className={inputCls}/></Field>
              <Field label="Skills (comma-sep)" hint="Used for nurse rostering skill coverage"><input value={e.skills} onChange={ev=>updateEmp(e._id,{skills:ev.target.value})} placeholder="cashier,manager" className={inputCls}/></Field>
              <Field label="Preferred Shifts (comma-sep)"><input value={e.preferred_shifts} onChange={ev=>updateEmp(e._id,{preferred_shifts:ev.target.value})} placeholder="Morning,Evening" className={inputCls}/></Field>
              <div className="col-span-2 flex items-end gap-2">
                <div className="flex-1">
                  <Field label="Requested Days Off (comma-sep)"><input value={e.requested_days_off} onChange={ev=>updateEmp(e._id,{requested_days_off:ev.target.value})} placeholder="Sun,Sat" className={inputCls}/></Field>
                </div>
                <button onClick={()=>removeEmp(e._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
              </div>
            </div>
          ))}
          <button onClick={addEmp} className={addBtnCls}><Plus className="w-3 h-3"/> Add Employee</button>
        </div>
      </SectionCard>
    </div>
  );
}

// ============================================================================
// Timetable form
// ============================================================================

type TeacherDef = { _id:string; name:string; subjects:string; max_periods_per_week:number; unavailable:string };
type ClassDef   = { _id:string; id:string; strength:number };
type SubjectDef = { _id:string; name:string; periods_per_week_per_class:number; consecutive:boolean; mergeable_groups:string };
type RoomDef    = { _id:string; name:string; capacity:number };

function TimetableForm({
  value, onChange,
}: {
  value: Record<string,unknown>;
  onChange: (v:Record<string,unknown>) => void;
}) {
  const teachers = (value.teachers as TeacherDef[]) ?? [];
  const classes  = (value.classes  as ClassDef[])   ?? [];
  const subjects = (value.subjects as SubjectDef[]) ?? [];
  const rooms    = (value.rooms    as RoomDef[])    ?? [];
  const timeCfg  = (value.time_config as { days: string[]; slots_per_day: number }) ?? { days:["Mon","Tue","Wed","Thu","Fri"], slots_per_day: 8 };
  const set = (patch: object) => onChange({ ...value, ...patch });

  const addTeacher = () => set({ teachers:[...teachers, { _id:uid(), name:`Teacher ${teachers.length+1}`, subjects:"", max_periods_per_week:20, unavailable:"" }] });
  const removeTeacher = (id:string) => set({ teachers: teachers.filter(t=>t._id!==id) });
  const updateTeacher = (id:string, patch:Partial<TeacherDef>) => set({ teachers: teachers.map(t=>t._id===id?{...t,...patch}:t) });

  const addClass = () => set({ classes:[...classes, { _id:uid(), id:`${classes.length+1}-A`, strength:35 }] });
  const removeClass = (id:string) => set({ classes: classes.filter(c=>c._id!==id) });
  const updateClass = (id:string, patch:Partial<ClassDef>) => set({ classes: classes.map(c=>c._id===id?{...c,...patch}:c) });

  const addSubject = () => set({ subjects:[...subjects, { _id:uid(), name:`Subject ${subjects.length+1}`, periods_per_week_per_class:4, consecutive:false, mergeable_groups:"" }] });
  const removeSubject = (id:string) => set({ subjects: subjects.filter(s=>s._id!==id) });
  const updateSubject = (id:string, patch:Partial<SubjectDef>) => set({ subjects: subjects.map(s=>s._id===id?{...s,...patch}:s) });

  const addRoom = () => set({ rooms:[...rooms, { _id:uid(), name:`Room ${rooms.length+1}`, capacity:40 }] });
  const removeRoom = (id:string) => set({ rooms: rooms.filter(r=>r._id!==id) });
  const updateRoom = (id:string, patch:Partial<RoomDef>) => set({ rooms: rooms.map(r=>r._id===id?{...r,...patch}:r) });

  return (
    <div className="space-y-4 mt-3">
      <SectionCard title="Time Configuration" icon={<Clock className="w-4 h-4"/>}>
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Days (comma-separated)">
            <input value={timeCfg.days.join(",")} onChange={e=>set({time_config:{...timeCfg,days:e.target.value.split(",").map((d:string)=>d.trim())}})} className={inputCls}/>
          </Field>
          <Field label="Periods per Day">
            <input type="number" min={1} max={20} value={timeCfg.slots_per_day} onChange={e=>set({time_config:{...timeCfg,slots_per_day:Number(e.target.value)}})} className={inputCls}/>
          </Field>
        </div>
      </SectionCard>

      <SectionCard title={`Teachers (${teachers.length})`} icon={<Users className="w-4 h-4"/>}>
        <div className="space-y-3 mt-3">
          {teachers.map(t => (
            <div key={t._id} className="border border-white/[0.07] rounded-lg p-3 grid grid-cols-2 gap-2">
              <Field label="Name"><input value={t.name} onChange={e=>updateTeacher(t._id,{name:e.target.value})} className={inputCls}/></Field>
              <Field label="Max Periods/Week"><input type="number" min={1} value={t.max_periods_per_week} onChange={e=>updateTeacher(t._id,{max_periods_per_week:Number(e.target.value)})} className={inputCls}/></Field>
              <Field label="Subjects (comma-sep)" hint="Subjects the teacher is qualified to teach">
                <input value={t.subjects} onChange={e=>updateTeacher(t._id,{subjects:e.target.value})} placeholder="Math,Physics" className={inputCls}/>
              </Field>
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <Field label="Unavailable slots (Day:Period,...)" hint="e.g. Monday:0,Friday:7 (0-indexed periods)">
                    <input value={t.unavailable} onChange={e=>updateTeacher(t._id,{unavailable:e.target.value})} placeholder="Monday:0,Friday:7" className={inputCls}/>
                  </Field>
                </div>
                <button onClick={()=>removeTeacher(t._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
              </div>
            </div>
          ))}
          <button onClick={addTeacher} className={addBtnCls}><Plus className="w-3 h-3"/> Add Teacher</button>
        </div>
      </SectionCard>

      <SectionCard title={`Classes (${classes.length})`} icon={<BookOpen className="w-4 h-4"/>}>
        <div className="space-y-2 mt-3">
          {classes.map(c => (
            <div key={c._id} className="flex items-center gap-2">
              <input value={c.id} onChange={e=>updateClass(c._id,{id:e.target.value})} placeholder="e.g. 10-A" className={`${inputCls} flex-1`}/>
              <input type="number" min={1} value={c.strength} onChange={e=>updateClass(c._id,{strength:Number(e.target.value)})} placeholder="Students" className={`${inputCls} w-28`} title="Number of students"/>
              <button onClick={()=>removeClass(c._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
            </div>
          ))}
          <button onClick={addClass} className={addBtnCls}><Plus className="w-3 h-3"/> Add Class</button>
        </div>
      </SectionCard>

      <SectionCard title={`Subjects (${subjects.length})`} icon={<BookOpen className="w-4 h-4"/>}>
        <div className="space-y-3 mt-3">
          {subjects.map(s => (
            <div key={s._id} className="border border-white/[0.07] rounded-lg p-3 grid grid-cols-2 gap-2">
              <Field label="Subject Name"><input value={s.name} onChange={e=>updateSubject(s._id,{name:e.target.value})} className={inputCls}/></Field>
              <Field label="Periods/Week/Class"><input type="number" min={1} value={s.periods_per_week_per_class} onChange={e=>updateSubject(s._id,{periods_per_week_per_class:Number(e.target.value)})} className={inputCls}/></Field>
              <div className="flex items-center gap-3 pt-1 col-span-2">
                <label className="flex items-center gap-2 text-xs text-white/50 cursor-pointer">
                  <input type="checkbox" checked={s.consecutive} onChange={e=>updateSubject(s._id,{consecutive:e.target.checked})} className="accent-violet-500"/>
                  Consecutive periods (labs / double periods)
                </label>
              </div>
              <div className="col-span-2 flex items-end gap-2">
                <div className="flex-1">
                  <Field label="Merge groups (pipe | separates groups, comma separates classes)" hint="e.g. 10-A,10-B | 10-C,10-D">
                    <input value={s.mergeable_groups} onChange={e=>updateSubject(s._id,{mergeable_groups:e.target.value})} placeholder="10-A,10-B | 10-C,10-D" className={inputCls}/>
                  </Field>
                </div>
                <button onClick={()=>removeSubject(s._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
              </div>
            </div>
          ))}
          <button onClick={addSubject} className={addBtnCls}><Plus className="w-3 h-3"/> Add Subject</button>
        </div>
      </SectionCard>

      <SectionCard title={`Rooms (${rooms.length})`} icon={<Building2 className="w-4 h-4"/>} collapsed>
        <div className="space-y-2 mt-3">
          {rooms.map(r => (
            <div key={r._id} className="flex items-center gap-2">
              <input value={r.name} onChange={e=>updateRoom(r._id,{name:e.target.value})} placeholder="Room name" className={`${inputCls} flex-1`}/>
              <input type="number" min={1} value={r.capacity} onChange={e=>updateRoom(r._id,{capacity:Number(e.target.value)})} placeholder="Capacity" className={`${inputCls} w-24`}/>
              <button onClick={()=>removeRoom(r._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
            </div>
          ))}
          <button onClick={addRoom} className={addBtnCls}><Plus className="w-3 h-3"/> Add Room</button>
        </div>
      </SectionCard>
    </div>
  );
}

// ============================================================================
// RCPSP form
// ============================================================================

type ActivityDef = { _id:string; name:string; duration:number; predecessors:string; resources:string };
type ResourceDef = { _id:string; name:string; capacity:number };

function RcpspForm({
  value, onChange,
}: {
  value: Record<string,unknown>;
  onChange: (v:Record<string,unknown>) => void;
}) {
  const activities = (value.activities as ActivityDef[]) ?? [];
  const resources  = (value.resources  as ResourceDef[]) ?? [];
  const set = (patch: object) => onChange({ ...value, ...patch });

  const addActivity = () => set({ activities:[...activities, { _id:uid(), name:`Task ${activities.length+1}`, duration:3, predecessors:"", resources:"" }] });
  const removeActivity = (id:string) => set({ activities: activities.filter(a=>a._id!==id) });
  const updateActivity = (id:string, patch:Partial<ActivityDef>) => set({ activities: activities.map(a=>a._id===id?{...a,...patch}:a) });

  const addResource = () => set({ resources:[...resources, { _id:uid(), name:`Resource ${resources.length+1}`, capacity:5 }] });
  const removeResource = (id:string) => set({ resources: resources.filter(r=>r._id!==id) });
  const updateResource = (id:string, patch:Partial<ResourceDef>) => set({ resources: resources.map(r=>r._id===id?{...r,...patch}:r) });

  return (
    <div className="space-y-4 mt-3">
      <SectionCard title={`Resources (${resources.length})`} icon={<Layers className="w-4 h-4"/>}>
        <div className="space-y-2 mt-3">
          {resources.map(r => (
            <div key={r._id} className="flex items-center gap-2">
              <input value={r.name} onChange={e=>updateResource(r._id,{name:e.target.value})} placeholder="Resource name" className={`${inputCls} flex-1`}/>
              <input type="number" min={1} value={r.capacity} onChange={e=>updateResource(r._id,{capacity:Number(e.target.value)})} className={`${inputCls} w-24`} title="Max simultaneous units"/>
              <button onClick={()=>removeResource(r._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
            </div>
          ))}
          <button onClick={addResource} className={addBtnCls}><Plus className="w-3 h-3"/> Add Resource</button>
        </div>
      </SectionCard>

      <SectionCard title={`Activities (${activities.length})`} icon={<Layers className="w-4 h-4"/>}>
        <div className="space-y-3 mt-3">
          {activities.map(a => (
            <div key={a._id} className="border border-white/[0.07] rounded-lg p-3 grid grid-cols-2 gap-2">
              <Field label="Activity Name"><input value={a.name} onChange={e=>updateActivity(a._id,{name:e.target.value})} className={inputCls}/></Field>
              <Field label="Duration"><input type="number" min={1} value={a.duration} onChange={e=>updateActivity(a._id,{duration:Number(e.target.value)})} className={inputCls}/></Field>
              <Field label="Predecessors (comma-sep names)" hint="Activities that must finish before this one starts">
                <input value={a.predecessors} onChange={e=>updateActivity(a._id,{predecessors:e.target.value})} placeholder="Task 1, Task 2" className={inputCls}/>
              </Field>
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <Field label="Resource demands (name:units,...)" hint="e.g. Workers:3,Cranes:1">
                    <input value={a.resources} onChange={e=>updateActivity(a._id,{resources:e.target.value})} placeholder="Workers:3,Cranes:1" className={inputCls}/>
                  </Field>
                </div>
                <button onClick={()=>removeActivity(a._id)} className={removeBtnCls}><Trash2 className="w-3 h-3"/></button>
              </div>
            </div>
          ))}
          <button onClick={addActivity} className={addBtnCls}><Plus className="w-3 h-3"/> Add Activity</button>
        </div>
      </SectionCard>

      <div className="text-xs text-white/30 px-1 flex items-center gap-2">
        <span>Time unit:</span>
        <input
          value={(value.time_unit as string) ?? "days"}
          onChange={e => set({ time_unit: e.target.value })}
          className="bg-transparent border-b border-white/20 text-white/50 w-16 px-1 focus:outline-none"
        />
      </div>
    </div>
  );
}

// ============================================================================
// Input transformers (UI form objects -> clean backend JSON)
// ============================================================================

function transformJobShop(raw: Record<string, unknown>): Record<string, unknown> {
  const jobs = ((raw.jobs as JobDef[]) ?? []).map(j => ({
    name:     j.name,
    priority: j.priority,
    due_date: j.due_date,
    tasks:    (j.tasks ?? []).map(t => ({ machine: t.machine, duration: t.duration })),
  }));
  const machines = ((raw.machines as MachineDef[]) ?? []).map(m => ({ name: m.name, count: m.count }));
  return { ...raw, jobs, machines };
}

function transformShift(raw: Record<string, unknown>): Record<string, unknown> {
  const employees = ((raw.employees as EmpDef[]) ?? []).map(e => ({
    name:               e.name,
    skills:             e.skills ? e.skills.split(",").map((s:string) => s.trim()).filter(Boolean) : [],
    max_shifts_per_week: e.max_shifts_per_week,
    max_hours_per_week:  e.max_hours_per_week,
    min_hours_per_week:  e.min_hours_per_week,
    requested_days_off: e.requested_days_off ? e.requested_days_off.split(",").map((s:string) => s.trim()).filter(Boolean) : [],
    preferred_shifts:   e.preferred_shifts   ? e.preferred_shifts.split(",").map((s:string) => s.trim()).filter(Boolean) : [],
  }));
  const shifts = ((raw.shifts as ShiftDef[]) ?? []).map(s => ({
    name:           s.name,
    start_hour:     s.start_hour,
    end_hour:       s.end_hour,
    required_count: s.required_count,
    days:           s.days ? s.days.split(",").map((d:string) => d.trim()).filter(Boolean) : (raw.days as string[]) ?? [],
  }));
  return { ...raw, employees, shifts };
}

function transformTimetable(raw: Record<string, unknown>): Record<string, unknown> {
  const teachers = ((raw.teachers as TeacherDef[]) ?? []).map(t => ({
    name:                 t.name,
    subjects:             t.subjects ? t.subjects.split(",").map((s:string) => s.trim()).filter(Boolean) : [],
    max_periods_per_week: t.max_periods_per_week,
    unavailable: (t.unavailable ?? "").split(",").flatMap((token: string) => {
      token = token.trim();
      if (!token) return [];
      const [day, slotStr] = token.split(":");
      const slot = parseInt(slotStr, 10);
      return isNaN(slot) ? [] : [{ day: day.trim(), slot }];
    }),
  }));
  const classes = ((raw.classes as ClassDef[]) ?? []).map(c => ({ id: c.id, strength: c.strength }));
  const subjects = ((raw.subjects as SubjectDef[]) ?? []).map(s => ({
    name:                       s.name,
    periods_per_week_per_class: s.periods_per_week_per_class,
    consecutive:                s.consecutive,
    mergeable_groups: s.mergeable_groups
      ? s.mergeable_groups.split("|").map((grp: string) =>
          grp.split(",").map((c: string) => c.trim()).filter(Boolean)
        ).filter((g: string[]) => g.length > 1)
      : [],
  }));
  const rooms = ((raw.rooms as RoomDef[]) ?? []).map(r => ({ name: r.name, capacity: r.capacity }));
  return { ...raw, teachers, classes, subjects, rooms };
}

function transformRcpsp(raw: Record<string, unknown>): Record<string, unknown> {
  const activities = ((raw.activities as ActivityDef[]) ?? []).map(a => ({
    name:         a.name,
    duration:     a.duration,
    predecessors: a.predecessors ? a.predecessors.split(",").map((p:string) => p.trim()).filter(Boolean) : [],
    resources:    Object.fromEntries(
      (a.resources ?? "").split(",")
        .map((token:string) => token.trim().split(":"))
        .filter((parts:string[]) => parts.length === 2 && parts[1])
        .map((parts:string[]) => [parts[0].trim(), parseInt(parts[1], 10)])
    ),
  }));
  const resources = ((raw.resources as ResourceDef[]) ?? []).map(r => ({ name: r.name, capacity: r.capacity }));
  return { ...raw, activities, resources };
}

function transformInputs(algoId: string, raw: Record<string, unknown>): Record<string, unknown> {
  if (algoId === "scheduling_jssp")                                   return transformJobShop(raw);
  if (algoId === "scheduling_shift" || algoId === "scheduling_nurse") return transformShift(raw);
  if (algoId === "scheduling_timetable")                              return transformTimetable(raw);
  if (algoId === "scheduling_rcpsp")                                  return transformRcpsp(raw);
  return raw;
}

// ============================================================================
// Default starter data (easy demo values per algo)
// ============================================================================

const DEFAULT_VALUES: Record<string, Record<string, unknown>> = {
  scheduling_jssp: {
    problem_type: "jssp",
    objective: "makespan",
    machines: [
      { _id: "m1", name: "Machine A", count: 1 },
      { _id: "m2", name: "Machine B", count: 1 },
      { _id: "m3", name: "Machine C", count: 1 },
    ],
    jobs: [
      { _id: "j1", name: "Job 1", due_date: null, priority: 1,
        tasks: [{ _id:"t1", machine:"Machine A", duration:3 }, { _id:"t2", machine:"Machine B", duration:2 }, { _id:"t3", machine:"Machine C", duration:2 }] },
      { _id: "j2", name: "Job 2", due_date: null, priority: 1,
        tasks: [{ _id:"t4", machine:"Machine B", duration:3 }, { _id:"t5", machine:"Machine A", duration:2 }, { _id:"t6", machine:"Machine C", duration:4 }] },
      { _id: "j3", name: "Job 3", due_date: null, priority: 1,
        tasks: [{ _id:"t7", machine:"Machine C", duration:2 }, { _id:"t8", machine:"Machine A", duration:3 }, { _id:"t9", machine:"Machine B", duration:3 }] },
    ],
  },

  scheduling_shift: {
    days: ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
    min_rest_hours: 8,
    max_consecutive_days: 5,
    shifts: [
      { _id:"s1", name:"Morning", start_hour:6,  end_hour:14, required_count:2, days:"" },
      { _id:"s2", name:"Evening", start_hour:14, end_hour:22, required_count:2, days:"" },
      { _id:"s3", name:"Night",   start_hour:22, end_hour:30, required_count:1, days:"" },
    ],
    employees: [
      { _id:"e1", name:"Alice",  skills:"", max_shifts_per_week:5, max_hours_per_week:40, min_hours_per_week:20, requested_days_off:"Sun", preferred_shifts:"Morning" },
      { _id:"e2", name:"Bob",    skills:"", max_shifts_per_week:5, max_hours_per_week:40, min_hours_per_week:20, requested_days_off:"Sat", preferred_shifts:"Evening" },
      { _id:"e3", name:"Carol",  skills:"", max_shifts_per_week:5, max_hours_per_week:40, min_hours_per_week:20, requested_days_off:"", preferred_shifts:"" },
      { _id:"e4", name:"David",  skills:"", max_shifts_per_week:4, max_hours_per_week:32, min_hours_per_week:0,  requested_days_off:"Sun,Sat", preferred_shifts:"Night" },
      { _id:"e5", name:"Eve",    skills:"", max_shifts_per_week:5, max_hours_per_week:40, min_hours_per_week:20, requested_days_off:"", preferred_shifts:"Morning" },
    ],
  },

  scheduling_nurse: {
    days: ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
    min_rest_hours: 10,
    max_consecutive_days: 4,
    shifts: [
      { _id:"s1", name:"Day",   start_hour:7,  end_hour:19, required_count:4, days:""},
      { _id:"s2", name:"Night", start_hour:19, end_hour:31, required_count:2, days:""},
    ],
    employees: [
      { _id:"e1", name:"Nurse Alice",  skills:"head_nurse",  max_shifts_per_week:5, max_hours_per_week:48, min_hours_per_week:36, requested_days_off:"", preferred_shifts:"Day" },
      { _id:"e2", name:"Nurse Bob",    skills:"trainee",     max_shifts_per_week:5, max_hours_per_week:48, min_hours_per_week:36, requested_days_off:"", preferred_shifts:"" },
      { _id:"e3", name:"Nurse Carol",  skills:"trainee",     max_shifts_per_week:5, max_hours_per_week:48, min_hours_per_week:36, requested_days_off:"", preferred_shifts:"Day" },
      { _id:"e4", name:"Nurse David",  skills:"specialist",  max_shifts_per_week:5, max_hours_per_week:48, min_hours_per_week:36, requested_days_off:"Sat,Sun", preferred_shifts:"" },
      { _id:"e5", name:"Nurse Eve",    skills:"head_nurse",  max_shifts_per_week:4, max_hours_per_week:40, min_hours_per_week:24, requested_days_off:"", preferred_shifts:"Night" },
    ],
  },

  scheduling_timetable: {
    time_config: { days:["Monday","Tuesday","Wednesday","Thursday","Friday"], slots_per_day: 8 },
    teachers: [
      { _id:"t1", name:"Alice",  subjects:"Math,Physics",      max_periods_per_week:20, unavailable:"" },
      { _id:"t2", name:"Bob",    subjects:"Chemistry,Biology", max_periods_per_week:18, unavailable:"Monday:0" },
      { _id:"t3", name:"Carol",  subjects:"English,History",   max_periods_per_week:16, unavailable:"" },
      { _id:"t4", name:"David",  subjects:"Math,Computer",     max_periods_per_week:20, unavailable:"Friday:7" },
      { _id:"t5", name:"Eve",    subjects:"Physics,Chemistry", max_periods_per_week:18, unavailable:"" },
    ],
    classes: [
      { _id:"c1", id:"10-A", strength:38 },
      { _id:"c2", id:"10-B", strength:35 },
      { _id:"c3", id:"9-A",  strength:40 },
    ],
    subjects: [
      { _id:"s1", name:"Math",      periods_per_week_per_class:5, consecutive:false, mergeable_groups:"" },
      { _id:"s2", name:"Physics",   periods_per_week_per_class:4, consecutive:false, mergeable_groups:"10-A,10-B" },
      { _id:"s3", name:"Chemistry", periods_per_week_per_class:3, consecutive:true,  mergeable_groups:"" },
      { _id:"s4", name:"English",   periods_per_week_per_class:4, consecutive:false, mergeable_groups:"" },
    ],
    rooms: [
      { _id:"r1", name:"Room 101", capacity:45 },
      { _id:"r2", name:"Room 102", capacity:45 },
      { _id:"r3", name:"Lab 1",    capacity:40 },
      { _id:"r4", name:"Hall",     capacity:80 },
    ],
  },

  scheduling_rcpsp: {
    time_unit: "days",
    resources: [
      { _id:"r1", name:"Workers", capacity:8 },
      { _id:"r2", name:"Cranes",  capacity:2 },
    ],
    activities: [
      { _id:"a1", name:"Foundation",    duration:5, predecessors:"",                    resources:"Workers:4,Cranes:1" },
      { _id:"a2", name:"Framing",       duration:8, predecessors:"Foundation",           resources:"Workers:6,Cranes:2" },
      { _id:"a3", name:"Electrical",    duration:4, predecessors:"Framing",              resources:"Workers:3,Cranes:0" },
      { _id:"a4", name:"Plumbing",      duration:5, predecessors:"Framing",              resources:"Workers:4,Cranes:0" },
      { _id:"a5", name:"HVAC",          duration:3, predecessors:"Framing",              resources:"Workers:2,Cranes:1" },
      { _id:"a6", name:"Dry Wall",      duration:6, predecessors:"Electrical,Plumbing", resources:"Workers:5,Cranes:0" },
      { _id:"a7", name:"Paint & Floor", duration:4, predecessors:"Dry Wall",             resources:"Workers:4,Cranes:0" },
      { _id:"a8", name:"Final Inspect", duration:2, predecessors:"Paint & Floor,HVAC",   resources:"Workers:2,Cranes:0" },
    ],
  },
};

// ============================================================================
// Result display components
// ============================================================================

function JobShopResult({ result }: { result: Record<string, unknown> }) {
  const timelines   = (result.machine_timelines   as Record<string, Array<{ job: string; start: number; end: number }>>) ?? {};
  const utilization = (result.machine_utilization as Record<string, number>) ?? {};
  const makespan    = result.makespan as number;

  const rows: GanttRow[] = Object.entries(timelines).map(([machine, slots]) => ({
    label: machine,
    bars: slots.map(s => ({
      start:   s.start,
      end:     s.end,
      label:   s.job,
      tooltip: `${s.job} on ${machine}: [${s.start} to ${s.end}]`,
    })),
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-4">
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
          <p className="text-xs text-emerald-400/70">Makespan</p>
          <p className="text-2xl font-bold text-emerald-300">{makespan} <span className="text-sm font-normal">time units</span></p>
        </div>
        {Object.entries(utilization).map(([m, u]) => (
          <div key={m} className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
            <p className="text-xs text-white/40">{m} utilisation</p>
            <p className="text-xl font-bold text-white/80">{(u * 100).toFixed(0)}%</p>
          </div>
        ))}
      </div>
      <div>
        <p className="text-xs text-white/40 mb-2">Machine Gantt Chart</p>
        <GanttChart rows={rows} horizon={makespan} timeUnit="time units" />
      </div>
      <details className="text-xs text-white/30">
        <summary className="cursor-pointer">Raw JSON</summary>
        <pre className="mt-2 overflow-auto text-[10px] text-white/20 max-h-48">{JSON.stringify(result, null, 2)}</pre>
      </details>
    </div>
  );
}

function ShiftResult({ result }: { result: Record<string, unknown> }) {
  const schedule    = (result.schedule       as Record<string, Record<string, string | null>>) ?? {};
  const coverage    = (result.daily_coverage as Record<string, Record<string, { assigned: number; required: number }>>) ?? {};
  const empHours    = (result.employee_hours as Record<string, number>) ?? {};
  const coverageMet = (result.statistics as Record<string,unknown>)?.coverage_met;

  const days   = Object.keys((schedule[Object.keys(schedule)[0]] ?? {}));
  const shifts = Array.from(new Set(
    Object.values(schedule).flatMap(dmap => Object.values(dmap).filter((v): v is string => v !== null))
  ));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-4">
        <div className={`rounded-xl border px-4 py-3 ${coverageMet ? "border-emerald-500/30 bg-emerald-500/10" : "border-red-500/30 bg-red-500/10"}`}>
          <p className={`text-xs ${coverageMet ? "text-emerald-300" : "text-red-300"}`}>
            {coverageMet ? "All shifts covered" : "Coverage gaps detected"}
          </p>
        </div>
        {Object.entries(empHours).map(([e, h]) => (
          <div key={e} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
            <p className="text-xs text-white/40">{e}</p>
            <p className="text-sm font-semibold text-white/80">{Number(h).toFixed(1)}h</p>
          </div>
        ))}
      </div>
      <ShiftCalendar schedule={schedule} days={days} shifts={shifts} coverage={coverage} />
      <details className="text-xs text-white/30">
        <summary className="cursor-pointer">Raw JSON</summary>
        <pre className="mt-2 overflow-auto text-[10px] text-white/20 max-h-48">{JSON.stringify(result, null, 2)}</pre>
      </details>
    </div>
  );
}

function TimetableResult({
  result,
  formValues,
}: {
  result:     Record<string, unknown>;
  formValues: Record<string, unknown>;
}) {
  const byClass   = (result.by_class   as Record<string, Record<string, unknown[]>>) ?? {};
  const byTeacher = (result.by_teacher as Record<string, Record<string, unknown[]>>) ?? {};
  const stats     = result.statistics as Record<string,unknown>;
  const [view, setView] = useState<"class" | "teacher">("class");

  type UncoveredItem = { class_id: string; subject: string; scheduled: number; required: number };
  const uncovered = (stats?.uncovered as UncoveredItem[]) ?? [];
  const timeCfg = (formValues.time_config as { days: string[]; slots_per_day: number }) ?? { days:[], slots_per_day: 8 };

  // Substitute finder
  const [subTeacher, setSubTeacher] = useState("");
  const [subDay,     setSubDay]     = useState("");
  const [subResult,  setSubResult]  = useState<Record<string, unknown> | null>(null);
  const [subLoading, setSubLoading] = useState(false);
  const [subError,   setSubError]   = useState<string | null>(null);

  const findSubs = async () => {
    if (!subTeacher || !subDay) return;
    setSubLoading(true);
    setSubError(null);
    try {
      const res = await findSubstitutes({
        timetable_result: result,
        absent_teacher:   subTeacher,
        absent_day:       subDay,
        teachers_data:    (transformTimetable(formValues).teachers as unknown[]) ?? [],
      });
      setSubResult(res);
    } catch (err) {
      setSubError(err instanceof Error ? err.message : "Error finding substitutes");
    } finally {
      setSubLoading(false);
    }
  };

  type TimetableEntry = {
    slot: number; subject: string; teacher?: string; class_id?: string;
    room?: string | null; merged_with?: string[] | null;
  };

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="flex flex-wrap gap-3">
        <div className={`rounded-xl border px-4 py-2 text-sm ${stats?.coverage_met ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : "border-red-500/30 bg-red-500/10 text-red-300"}`}>
          {stats?.coverage_met ? "All subjects covered" : `${uncovered.length} coverage gap(s) detected`}
        </div>
        {uncovered.slice(0,5).map((u, i) => (
          <div key={i} className="text-xs rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-300 px-3 py-1">
            {u.class_id} / {u.subject}: {u.scheduled}/{u.required}
          </div>
        ))}
      </div>

      {/* View toggle */}
      <div className="flex gap-2">
        {(["class", "teacher"] as const).map(v => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`${btnSmall} border ${view === v ? "bg-violet-600 border-violet-500 text-white" : "bg-white/[0.04] border-white/10 text-white/50"}`}
          >
            {v === "class" ? "Class View" : "Teacher View"}
          </button>
        ))}
      </div>

      <TimetableGrid
        data={(view === "class" ? byClass : byTeacher) as Record<string, Record<string, TimetableEntry[]>>}
        days={timeCfg.days}
        slotsPerDay={timeCfg.slots_per_day}
        mode={view}
      />

      {/* Substitute finder */}
      <div className="border border-white/[0.08] rounded-xl p-4 space-y-3">
        <p className="text-sm font-medium text-white/70">Find Substitute Teacher</p>
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Absent Teacher">
            <select value={subTeacher} onChange={e=>setSubTeacher(e.target.value)} className={`${inputCls} w-44`}>
              <option value="">-- select --</option>
              {Object.keys(byTeacher).map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Absent Day">
            <select value={subDay} onChange={e=>setSubDay(e.target.value)} className={`${inputCls} w-36`}>
              <option value="">-- select --</option>
              {timeCfg.days.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </Field>
          <button
            onClick={findSubs}
            disabled={!subTeacher || !subDay || subLoading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium disabled:opacity-40 transition-colors"
          >
            {subLoading ? <LoaderIcon className="w-3.5 h-3.5 animate-spin"/> : <Users className="w-3.5 h-3.5"/>}
            Find Subs
          </button>
        </div>
        {subError && <p className="text-xs text-red-400">{subError}</p>}
        {subResult && (() => {
          const sug = (subResult.suggestions as Record<string, { class_id: string; subject: string; candidates: string[] }>) ?? {};
          return (
            <div className="space-y-2 pt-1">
              {Object.entries(sug).map(([slot, s]) => (
                <div key={slot} className="text-xs border border-white/[0.07] rounded-lg px-3 py-2">
                  <span className="text-white/50">Period {Number(slot)+1} &middot; {s.class_id} &middot; {s.subject}: </span>
                  {s.candidates.length > 0
                    ? s.candidates.map(c => (
                      <span key={c} className="inline-block bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 rounded px-1.5 py-0.5 mr-1">{c}</span>
                    ))
                    : <span className="text-red-400">No available substitute</span>
                  }
                </div>
              ))}
            </div>
          );
        })()}
      </div>

      <details className="text-xs text-white/30">
        <summary className="cursor-pointer">Raw JSON</summary>
        <pre className="mt-2 overflow-auto text-[10px] text-white/20 max-h-48">{JSON.stringify(result, null, 2)}</pre>
      </details>
    </div>
  );
}

function RcpspResult({ result }: { result: Record<string, unknown> }) {
  type ActivityResult = { activity: string; start: number; finish: number; duration: number };

  const schedule         = (result.schedule         as ActivityResult[]) ?? [];
  const makespan         = result.makespan as number;
  const criticalPath     = (result.critical_path     as string[]) ?? [];
  const resourceUsage    = (result.resource_usage    as Record<string, number[]>) ?? {};
  const resourceCapacity = (result.resource_capacity as Record<string, number>) ?? {};

  const rows: GanttRow[] = schedule.map(a => ({
    label: a.activity,
    bars: [{
      start:   a.start,
      end:     a.finish,
      label:   a.activity,
      color:   criticalPath.includes(a.activity) ? "#ef4444" : undefined,
      tooltip: `${a.activity}: ${a.start} to ${a.finish} (${a.duration} ${result.time_unit ?? "units"})`,
    }],
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-4">
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
          <p className="text-xs text-emerald-400/70">Project Duration</p>
          <p className="text-2xl font-bold text-emerald-300">{makespan} <span className="text-sm font-normal">{result.time_unit as string ?? "units"}</span></p>
        </div>
        {criticalPath.length > 0 && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3">
            <p className="text-xs text-red-400/70">Critical Path</p>
            <p className="text-sm font-semibold text-red-300">{criticalPath.join(" → ")}</p>
          </div>
        )}
      </div>

      <div>
        <p className="text-xs text-white/40 mb-2">Project Gantt <span className="text-white/20 ml-2">(red = critical)</span></p>
        <GanttChart rows={rows} horizon={makespan} timeUnit={result.time_unit as string ?? "days"} pixelsPerUnit={32} />
      </div>

      {Object.entries(resourceUsage).map(([res, usage]) => (
        <ResourceChart key={res} resource={res} usage={usage} capacity={resourceCapacity[res] ?? 0} />
      ))}

      <details className="text-xs text-white/30">
        <summary className="cursor-pointer">Raw JSON</summary>
        <pre className="mt-2 overflow-auto text-[10px] text-white/20 max-h-48">{JSON.stringify(result, null, 2)}</pre>
      </details>
    </div>
  );
}

// ============================================================================
// Main page component
// ============================================================================

export default function SolvePage() {
  const params       = useParams();
  const router       = useRouter();
  const searchParams = useSearchParams();
  const algoId  = (params?.algo_id as string) ?? "";
  const meta    = ALGO_META[algoId];

  const [formValues,  setFormValues]  = useState<Record<string, unknown>>(DEFAULT_VALUES[algoId] ?? {});
  const [isLoading,   setIsLoading]   = useState(false);
  const [result,      setResult]      = useState<Record<string, unknown> | null>(null);
  const [error,       setError]       = useState<string | null>(null);
  const [aiPrefilled, setAiPrefilled] = useState(false);

  // Pre-fill form with AI-configured draft when arrive from chat with ?session= param
  useEffect(() => {
    const sessionId = searchParams?.get("session");
    if (!sessionId) return;
    getSessionDraft(sessionId)
      .then((data) => {
        if (data.draft && Object.keys(data.draft).length > 0) {
          setFormValues(data.draft as Record<string, unknown>);
          setAiPrefilled(true);
        }
      })
      .catch((err) => {
        console.warn("Could not load session draft:", err);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSolve = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setResult(null);
    try {
      const cleanInputs = transformInputs(algoId, formValues);
      const solverPayload = { algo_id: algoId, inputs: cleanInputs };
      console.log("[SolvePage] Sending payload to backend:", solverPayload);
      const res = await runSolver(solverPayload);
      if (res.error) throw new Error(res.error as string);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Solver failed. Check your inputs.");
    } finally {
      setIsLoading(false);
    }
  }, [algoId, formValues]);

  if (!meta) {
    return (
      <div className="min-h-screen bg-[#0a0a0b] text-white flex items-center justify-center p-8">
        <div className="text-center space-y-4">
          <p className="text-white/50 text-lg">Unknown algorithm: <code>{algoId}</code></p>
          <button onClick={() => router.push("/")} className="text-violet-400 hover:text-violet-300 text-sm transition-colors">
            &larr; Back to chat
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0b] text-white">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-black/60 backdrop-blur-xl border-b border-white/[0.05] px-4 py-3 flex items-center gap-3">
        <button onClick={() => router.push("/")} className="p-1.5 rounded-lg hover:bg-white/[0.06] text-white/40 hover:text-white transition-colors">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className={`w-7 h-7 rounded-lg bg-gradient-to-br flex items-center justify-center ${meta.color}`}>
          <Sparkles className="w-3.5 h-3.5 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white/90 truncate">{meta.name}</p>
          <p className="text-xs text-white/40 truncate">{meta.description}</p>
        </div>
        {aiPrefilled && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-violet-500/15 border border-violet-500/25 text-xs text-violet-300">
            <Sparkles className="w-3 h-3" />
            AI-configured
          </div>
        )}
        <button
          onClick={handleSolve}
          disabled={isLoading}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all bg-gradient-to-r text-white ${meta.color} ${isLoading ? "opacity-60 cursor-not-allowed" : "hover:scale-105"}`}
        >
          {isLoading
            ? <><LoaderIcon className="w-4 h-4 animate-spin" /> Solving&hellip;</>
            : <><Play className="w-4 h-4" /> Solve</>}
        </button>
      </header>

      <div className="max-w-5xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Input panel */}
        <div>
          <p className="text-xs text-white/30 uppercase tracking-wider mb-3">Input Configuration</p>
          {algoId === "scheduling_jssp" && (
            <JobShopForm value={formValues} onChange={setFormValues} />
          )}
          {(algoId === "scheduling_shift" || algoId === "scheduling_nurse") && (
            <ShiftForm value={formValues} onChange={setFormValues} />
          )}
          {algoId === "scheduling_timetable" && (
            <TimetableForm value={formValues} onChange={setFormValues} />
          )}
          {algoId === "scheduling_rcpsp" && (
            <RcpspForm value={formValues} onChange={setFormValues} />
          )}
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

        {/* Result panel */}
        <div>
          <p className="text-xs text-white/30 uppercase tracking-wider mb-3">Results</p>

          {!result && !error && !isLoading && (
            <div className="flex flex-col items-center justify-center h-64 rounded-xl border border-dashed border-white/[0.08] text-white/20">
              <Play className="w-8 h-8 mb-2" />
              <p className="text-sm">Press Solve to run the optimizer</p>
            </div>
          )}

          {isLoading && (
            <div className="flex flex-col items-center justify-center h-64 rounded-xl border border-white/[0.08] bg-white/[0.02]">
              <LoaderIcon className="w-8 h-8 animate-spin text-violet-500 mb-3" />
              <p className="text-sm text-white/40">Running OR-Tools solver&hellip;</p>
            </div>
          )}

          {error && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 flex gap-3"
            >
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-red-300">Solver Error</p>
                <p className="text-xs text-red-400/80 mt-1">{error}</p>
              </div>
            </motion.div>
          )}

          {result && (
            <AnimatePresence>
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle className="w-4 h-4 text-emerald-400" />
                  <span className="text-sm font-medium text-emerald-300">
                    Solution found
                  </span>
                </div>
                {algoId === "scheduling_jssp" && <JobShopResult result={result} />}
                {(algoId === "scheduling_shift" || algoId === "scheduling_nurse") && (
                  <ShiftResult result={result} />
                )}
                {algoId === "scheduling_timetable" && (
                  <TimetableResult result={result} formValues={formValues} />
                )}
                {algoId === "scheduling_rcpsp" && <RcpspResult result={result} />}
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      </div>
    </div>
  );
}
