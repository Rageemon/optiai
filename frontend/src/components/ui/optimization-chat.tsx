"use client";

/**
 * OptimizationChat
 * Full conversational pipeline wired to the FastAPI backend.
 *
 * State machine phases:
 *   idle        → user types first message
 *   loading     → waiting for backend
 *   no_match    → backend says no algorithm available
 *   algo_found  → backend found an algorithm, showing capabilities
 *   modified    → user requested changes, backend parsed them
 *   ready_to_solve → user confirmed, navigate to /solve/[algo_id]
 */

import { useState, useRef, useEffect, useTransition, useCallback, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  SendIcon, LoaderIcon, Paperclip, XIcon,
  CheckCircle, AlertCircle, RefreshCw, Sparkles,
  ChevronRight, ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { sendChatMessage, ChatResponse, AlgoDetails, PatchDiffEntry } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Role = "user" | "assistant" | "system";

interface Message {
  id: string;
  role: Role;
  content: string;        // raw markdown-ish text
  phase?: ChatResponse["phase"];
  algo_details?: AlgoDetails;
  modification?: Record<string, unknown>;
  patch_diff?: PatchDiffEntry[];
  effective_draft?: Record<string, unknown>;
}

interface ConversationState {
  session_id?: string;
  algo_id?: string;
  phase?: "match" | "confirm" | "modify" | null;
}

// ---------------------------------------------------------------------------
// Helper: auto-resize textarea hook
// ---------------------------------------------------------------------------

function useAutoResize(minH: number, maxH: number) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const adjust = useCallback((reset?: boolean) => {
    const el = ref.current;
    if (!el) return;
    el.style.height = `${minH}px`;
    if (!reset) el.style.height = `${Math.min(el.scrollHeight, maxH)}px`;
  }, [minH, maxH]);
  return { ref, adjust };
}

// ---------------------------------------------------------------------------
// Helper: render markdown-flavoured text as JSX (lightweight, no deps)
// ---------------------------------------------------------------------------

function MessageContent({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1.5">
      {lines.map((line, i) => {
        if (line.startsWith("**") && line.endsWith("**") && line.length > 4) {
          return <p key={i} className="font-semibold text-white/90">{line.slice(2, -2)}</p>;
        }
        if (line.startsWith("•") || line.startsWith("-")) {
          const content = line.replace(/^[•\-]\s*/, "");
          return (
            <p key={i} className="flex gap-2 text-white/70">
              <span className="text-violet-400 mt-0.5">›</span>
              <span dangerouslySetInnerHTML={{ __html: bold(content) }} />
            </p>
          );
        }
        if (line === "---") return <hr key={i} className="border-white/10 my-2" />;
        if (line.trim() === "") return <div key={i} className="h-1" />;
        return (
          <p key={i} className="text-white/80 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: bold(line) }} />
        );
      })}
    </div>
  );
}

// Bold inline **text**
function bold(s: string) {
  return s.replace(/\*\*(.+?)\*\*/g, '<strong class="text-white font-semibold">$1</strong>');
}

// ---------------------------------------------------------------------------
// Patch diff preview shown inside "modified" assistant bubbles
// ---------------------------------------------------------------------------

function PatchDiffPreview({ diff }: { diff: PatchDiffEntry[] }) {
  if (!diff.length) return null;
  return (
    <div className="mt-3 rounded-xl overflow-hidden border border-white/[0.08] text-xs">
      <div className="bg-white/[0.04] px-3 py-1.5 text-white/50 font-medium tracking-wide uppercase text-[10px]">
        Changes applied
      </div>
      <div className="divide-y divide-white/[0.05]">
        {diff.map((entry, i) => (
          <div
            key={i}
            className={cn(
              "flex items-start gap-2 px-3 py-2",
              entry.op === "add"    && "bg-emerald-500/5",
              entry.op === "remove" && "bg-red-500/5",
              entry.op === "change" && "bg-amber-500/5",
            )}
          >
            <span className={cn(
              "mt-0.5 font-bold shrink-0 w-4 text-center",
              entry.op === "add"    && "text-emerald-400",
              entry.op === "remove" && "text-red-400",
              entry.op === "change" && "text-amber-400",
            )}>
              {entry.op === "add" ? "+" : entry.op === "remove" ? "-" : "~"}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-white/45 mb-1 break-all">{entry.field}</div>
              {entry.op !== "add" && entry.from && (
                <div className="text-white/30 line-through break-all">{entry.from}</div>
              )}
              {entry.op !== "remove" && entry.to && (
                <div className="text-white/80 break-all">{entry.to}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Action buttons shown below assistant messages
// ---------------------------------------------------------------------------

function AlgoActions({
  phase,
  onConfirm,
  onModify,
}: {
  phase: ChatResponse["phase"];
  onConfirm: () => void;
  onModify: () => void;
}) {
  if (phase !== "algo_found" && phase !== "modified") return null;
  return (
    <motion.div
      className="flex gap-2 mt-3 flex-wrap"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
    >
      <button
        onClick={onConfirm}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium transition-colors"
      >
        <CheckCircle className="w-3.5 h-3.5" />
        Looks good — proceed
        <ChevronRight className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={onModify}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.06] hover:bg-white/[0.1] text-white/70 hover:text-white text-xs font-medium transition-colors border border-white/10"
      >
        <RefreshCw className="w-3.5 h-3.5" />
        I want to modify this
      </button>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function OptimizationChat() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi! I'm your optimization assistant.\n\n" +
        "Describe the problem you need to solve — for example:\n\n" +
        "• *\"I need to create a weekly timetable for 4 teachers across 5 days\"*\n" +
        "• *\"I need to find the shortest delivery route across 10 cities\"*\n" +
        "• *\"I have a backpack with 50kg limit and want to maximize value\"*\n" +
        "• *\"I need to cut steel rods to fulfill orders with minimal waste\"*\n\n" +
        "I'll find the right algorithm for you.",
    },
  ]);
  const [input, setInput]             = useState("");
  const [isLoading, setIsLoading]     = useState(false);
  const [convState, setConvState]     = useState<ConversationState>({});
  const [pendingAction, setPendingAction] = useState<"confirm" | "modify" | null>(null);

  const { ref: textareaRef, adjust } = useAutoResize(56, 200);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [, startTransition] = useTransition();

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Handle sending a message (from textarea or action buttons)
  const send = useCallback(async (
    text: string,
    overridePhase?: ConversationState["phase"],
    overrideAlgoId?: string,
  ) => {
    const userText = text.trim();
    if (!userText && !overridePhase) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: userText || (overridePhase === "confirm" ? "✓ Looks good — proceed" : ""),
    };

    setMessages(prev => [...prev, userMsg]);
    setInput("");
    adjust(true);
    setIsLoading(true);

    const phase = overridePhase ?? convState.phase ?? null;
    const algoId = overrideAlgoId ?? convState.algo_id;

    try {
      const res = await sendChatMessage({
        message: userText,
        session_id: convState.session_id,
        algo_id: algoId,
        phase: phase,
      });

      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: res.message,
        phase: res.phase,
        algo_details: res.algo_details,
        modification: res.modification as Record<string, unknown> | undefined,
        patch_diff: res.patch_diff,
        effective_draft: res.effective_draft,
      };

      setMessages(prev => [...prev, assistantMsg]);

      // Update conversation state
      // After algo_found or modified, keep phase="modify" so free-text typing
      // is treated as another modification (Confirm button always overrides with "confirm").
      setConvState({
        session_id: res.session_id ?? convState.session_id,
        algo_id: res.algo_id ?? algoId,
        phase: (res.phase === "algo_found" || res.phase === "modified") ? "modify" : null,
      });

            // If ready_to_solve, navigate to the correct sub-folder — include session for form pre-fill
      if (res.phase === 'ready_to_solve' && res.algo_id) {
        const sessionParam = res.session_id ? `?session=${res.session_id}` : '';
        let solveBase = `/solve/scheduling/${res.algo_id}`;
        if (res.algo_id.startsWith('routing_')) {
          solveBase = `/solve/routing/${res.algo_id}`;
        } else if (res.algo_id.startsWith('packing_')) {
          solveBase = `/solve/packing/${res.algo_id}`;
        } else if (res.algo_id.startsWith('map_routing_')) {
          solveBase = `/solve/map-routing/${res.algo_id}`;
        }
        setTimeout(() => router.push(`${solveBase}${sessionParam}`), 1800);
      }
    } catch (err) {
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "system",
        content: `Error: ${err instanceof Error ? err.message : "Something went wrong. Is the backend running?"}`,
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
      setPendingAction(null);
    }
  }, [convState, adjust, router]);

  const handleConfirm = useCallback(() => {
    setPendingAction("confirm");
    send("I'm satisfied with this algorithm. Let's proceed.", "confirm", convState.algo_id);
  }, [send, convState.algo_id]);

  const handleModify = useCallback(() => {
    // Add a prompt nudge so the user knows to describe changes
    const nudge: Message = {
      id: Date.now().toString(),
      role: "assistant",
      content:
        "Describe what you want to change in the current setup. For example: add more vehicles, change capacities, tighten time windows, or update distances.",
      phase: "modified",
    };
    setMessages(prev => [...prev, nudge]);
    setConvState(prev => ({ ...prev, phase: "modify" }));
    setPendingAction("modify");
  }, []);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const currentPhase = convState.phase;
      send(input, currentPhase ?? null);
    }
  };

  return (
    <div className="flex flex-col w-full min-h-screen bg-[#0a0a0b] text-white relative">
      {/* Ambient background glows */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-violet-500/8 rounded-full blur-[128px] animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-indigo-500/8 rounded-full blur-[128px] animate-pulse delay-700" />
      </div>

      {/* Header */}
      <header className="sticky top-0 z-20 backdrop-blur-xl bg-black/40 border-b border-white/[0.05] px-4 py-3 flex items-center gap-3">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
          <Sparkles className="w-3.5 h-3.5 text-white" />
        </div>
        <div>
          <p className="text-sm font-semibold text-white/90">Optimization Engine</p>
          <p className="text-xs text-white/40">Neuro-Symbolic · OR-Tools · Gemini AI</p>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4 max-w-3xl mx-auto w-full">
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
              className={cn(
                "flex gap-3",
                msg.role === "user" && "flex-row-reverse"
              )}
            >
              {/* Avatar */}
              {msg.role !== "user" && (
                <div className={cn(
                  "w-7 h-7 rounded-lg flex-shrink-0 flex items-center justify-center text-xs font-bold mt-0.5",
                  msg.role === "assistant"
                    ? "bg-gradient-to-br from-violet-500 to-indigo-600 text-white"
                    : "bg-red-500/20 border border-red-500/30 text-red-400"
                )}>
                  {msg.role === "assistant" ? "AI" : "!"}
                </div>
              )}

              {/* Bubble */}
              <div className={cn(
                "max-w-[80%] rounded-2xl px-4 py-3 text-sm",
                msg.role === "user"
                  ? "bg-white text-[#0a0a0b] font-medium ml-auto rounded-tr-sm"
                  : msg.role === "system"
                  ? "bg-red-500/10 border border-red-500/20 text-red-300 rounded-tl-sm"
                  : "bg-white/[0.04] border border-white/[0.06] rounded-tl-sm"
              )}>
                {msg.role === "user" ? (
                  <p>{msg.content}</p>
                ) : (
                  <>
                    <MessageContent text={msg.content} />
                    {msg.patch_diff && msg.patch_diff.length > 0 && (
                      <PatchDiffPreview diff={msg.patch_diff} />
                    )}
                    {msg.phase && (
                      <AlgoActions
                        phase={msg.phase}
                        onConfirm={handleConfirm}
                        onModify={handleModify}
                      />
                    )}
                  </>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Typing indicator */}
        <AnimatePresence>
          {isLoading && (
            <motion.div
              key="typing"
              className="flex gap-3"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
            >
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 flex-shrink-0 flex items-center justify-center text-xs font-bold">
                AI
              </div>
              <div className="bg-white/[0.04] border border-white/[0.06] rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-1.5">
                {[0, 1, 2].map((i) => (
                  <motion.div
                    key={i}
                    className="w-1.5 h-1.5 bg-violet-400 rounded-full"
                    animate={{ scale: [1, 1.4, 1], opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.2 }}
                  />
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="sticky bottom-0 z-10 px-4 pb-5 pt-3 bg-gradient-to-t from-[#0a0a0b] via-[#0a0a0b]/90 to-transparent">
        <div className="max-w-3xl mx-auto">
          {/* Modify-mode hint */}
          <AnimatePresence>
            {convState.phase === "modify" && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mb-2 flex items-center gap-2 text-xs text-violet-300/80 px-1"
              >
                <RefreshCw className="w-3 h-3" />
                <span>Modification mode — describe changes to the algorithm</span>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="relative backdrop-blur-xl bg-white/[0.03] rounded-2xl border border-white/[0.07] shadow-2xl">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => { setInput(e.target.value); adjust(); }}
              onKeyDown={handleKeyDown}
              placeholder={
                convState.phase === "modify"
                  ? "Describe your modifications…"
                  : "Describe the problem you need to solve…"
              }
              disabled={isLoading}
              rows={1}
              className={cn(
                "w-full resize-none bg-transparent text-white/90 placeholder:text-white/25",
                "px-4 pt-3.5 pb-3 text-sm focus:outline-none",
                "min-h-[56px] max-h-[200px]",
                "disabled:opacity-50"
              )}
              style={{ overflow: "hidden" }}
            />

            <div className="flex items-center justify-between px-3 pb-3 gap-2">
              <span className="text-xs text-white/25 pl-1">
                {convState.algo_id ? `Algorithm: ${convState.algo_id}` : "No algorithm selected yet"}
              </span>

              <button
                onClick={() => send(input, convState.phase ?? null)}
                disabled={isLoading || !input.trim()}
                className={cn(
                  "flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium transition-all",
                  input.trim() && !isLoading
                    ? "bg-white text-[#0a0a0b] hover:bg-white/90 shadow-lg shadow-white/10"
                    : "bg-white/[0.06] text-white/30 cursor-not-allowed"
                )}
              >
                {isLoading
                  ? <LoaderIcon className="w-4 h-4 animate-spin" />
                  : <SendIcon className="w-4 h-4" />
                }
                <span>{isLoading ? "Thinking…" : "Send"}</span>
              </button>
            </div>
          </div>

          <p className="text-center text-xs text-white/20 mt-2">
            Powered by Gemini AI + Google OR-Tools
          </p>
        </div>
      </div>
    </div>
  );
}
