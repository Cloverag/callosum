"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Sparkles, X, ArrowUp, BadgeCheck, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import { assistantApi, SUGGESTED_PROMPTS, type AssistantTurn } from "@/lib/assistant";

export function AskMeridian() {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();

  // ⌘/Ctrl+J toggles the assistant from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "j" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: reduce ? "auto" : "smooth" });
  }, [turns, reduce]);

  async function ask(q: string) {
    const question = q.trim();
    if (!question || busy) return;
    const id = crypto.randomUUID();
    setTurns((t) => [...t, { id, question, answer: null }]);
    setInput("");
    setBusy(true);
    const answer = await assistantApi.ask(question);
    setTurns((t) => t.map((x) => (x.id === id ? { ...x, answer } : x)));
    setBusy(false);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Ask Meridian"
        className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border bg-surface-raised px-2.5 text-sm text-muted-foreground transition-colors duration-150 hover:border-border-strong hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-elevated"
      >
        <Sparkles className="size-4 text-accent-emphasis" aria-hidden />
        <span className="hidden sm:inline">Ask Meridian</span>
        <kbd className="ml-0.5 hidden rounded border border-border px-1 text-[10px] tabular-nums text-subtle-foreground md:inline">⌘J</kbd>
      </button>

      <AnimatePresence>
        {open && (
          <div className="fixed inset-0 z-50">
            <motion.div
              className="absolute inset-0 bg-black/40 backdrop-blur-[1px]"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: reduce ? 0 : 0.15 }}
              onClick={() => setOpen(false)}
            />
            <motion.aside
              role="dialog"
              aria-modal="true"
              aria-label="Ask Meridian"
              className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col border-l border-border bg-surface-elevated shadow-2xl"
              initial={{ x: reduce ? 0 : "100%" }}
              animate={{ x: 0 }}
              exit={{ x: reduce ? 0 : "100%" }}
              transition={reduce ? { duration: 0 } : { duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
              onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
            >
              {/* Header */}
              <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
                <div className="flex items-center gap-2">
                  <Sparkles className="size-4 text-accent-emphasis" aria-hidden />
                  <div>
                    <h2 className="text-sm font-medium text-foreground">Ask Meridian</h2>
                    <p className="text-[11px] text-muted-foreground">Answers from approved board memory only.</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close"
                  className="grid size-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-surface-raised hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
                >
                  <X className="size-4" aria-hidden />
                </button>
              </div>

              {/* Conversation */}
              <div ref={scrollRef} className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
                {turns.length === 0 ? (
                  <div>
                    <p className="text-sm text-muted-foreground">
                      Ask about decisions, meetings, or people. Every answer cites its source quote; anything you
                      aren&apos;t cleared to see is withheld.
                    </p>
                    <div className="mt-4 text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">
                      Suggested
                    </div>
                    <div className="mt-2 flex flex-col gap-2">
                      {SUGGESTED_PROMPTS.map((p) => (
                        <button
                          key={p}
                          type="button"
                          onClick={() => ask(p)}
                          className="rounded-lg border border-border bg-surface-raised px-3 py-2 text-left text-sm text-foreground transition-colors hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
                        >
                          {p}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  turns.map((t) => <Turn key={t.id} turn={t} />)
                )}
              </div>

              {/* Composer */}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  ask(input);
                }}
                className="border-t border-border p-3"
              >
                <div className="flex items-end gap-2 rounded-lg border border-border bg-surface-raised px-3 py-2 focus-within:border-accent">
                  <input
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Ask Meridian…"
                    aria-label="Ask Meridian"
                    className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={!input.trim() || busy}
                    aria-label="Send"
                    className="grid size-7 shrink-0 place-items-center rounded-md bg-accent text-accent-foreground transition-opacity hover:opacity-90 disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
                  >
                    <ArrowUp className="size-4" aria-hidden />
                  </button>
                </div>
              </form>
            </motion.aside>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}

function Turn({ turn }: { turn: AssistantTurn }) {
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-surface-raised px-3.5 py-2 text-sm text-foreground">
          {turn.question}
        </p>
      </div>

      {turn.answer === null ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="size-1.5 animate-pulse rounded-full bg-accent-emphasis" aria-hidden />
          Searching approved memory…
        </p>
      ) : (
        <div className="space-y-3">
          <p className={cn("text-sm leading-relaxed", turn.answer.abstained ? "text-muted-foreground" : "text-foreground")}>
            {turn.answer.answer}
          </p>

          {turn.answer.citations.map((c, i) => (
            <div key={i} className="rounded-lg bg-surface-sunken px-3 py-2.5">
              <p className="text-xs leading-relaxed text-muted-foreground">
                <span aria-hidden className="text-subtle-foreground">“</span>
                {c.quote}
                <span aria-hidden className="text-subtle-foreground">”</span>
              </p>
              <div className="mt-1.5 flex items-center gap-2 text-[11px]">
                <span className="truncate text-muted-foreground">{c.source}</span>
                <span className="text-border-strong" aria-hidden>·</span>
                <span className="inline-flex items-center gap-1 font-medium text-success-emphasis">
                  <BadgeCheck className="size-3" aria-hidden />
                  Verified
                </span>
              </div>
            </div>
          ))}

          {turn.answer.related.length > 0 && (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">
                Related knowledge
              </div>
              <ul className="mt-1.5 space-y-1">
                {turn.answer.related.map((r, i) => (
                  <li key={i} className="text-xs text-muted-foreground">— {r}</li>
                ))}
              </ul>
            </div>
          )}

          {turn.answer.withheld > 0 && (
            <p className="inline-flex items-center gap-1.5 rounded-md bg-surface-sunken px-2.5 py-1.5 text-[11px] text-muted-foreground">
              <Lock className="size-3 text-warning-emphasis" aria-hidden />
              {turn.answer.withheld} source withheld — insufficient clearance
            </p>
          )}
        </div>
      )}
    </div>
  );
}
