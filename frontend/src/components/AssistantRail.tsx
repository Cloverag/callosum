"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Sparkles, PanelRightClose, ArrowUp, BadgeCheck, Lock, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { assistantApi, type AssistantTurn } from "@/lib/assistant";
import { meetingsApi } from "@/lib/meetings";
import { decisionsApi, type Decision } from "@/lib/decisions";
import { documentsApi, type Document } from "@/lib/documents";
import { useSession } from "@/components/session-gate";

// Quick shortcuts map to questions the approved memory can actually answer —
// the rail never offers a prompt it would only abstain on.
const SHORTCUTS: { label: string; q: string }[] = [
  { label: "Pricing rationale", q: "Why did we reverse the Q3 pricing decision?" },
  { label: "Series B lead", q: "Who is leading the Series B?" },
  { label: "Hiring plan", q: "What did the board decide about hiring?" },
  { label: "Last meeting", q: "Summarize the last board meeting." },
];

/**
 * The opener.
 *
 * This used to read: *"Morning, Alex. The Q3 board meeting is in 13 days. I've drafted
 * 60% of the pack — I still need Q2 churn and the updated hiring plan before it's
 * ready."* Every clause of it was false. "Alex" was nobody's session — the signed-in
 * principal is whoever signed in. "13 days" contradicted the dashboard one panel away,
 * which computes the real figure from the meeting record. "60% of the pack" was a
 * measurement of nothing; no part of this product drafts a pack or could report progress
 * on one.
 *
 * It greets by the session's real name and claims nothing else. A proactive opener is
 * worth having, but not at the cost of the one sentence printed beneath the composer:
 * *"Every answer cites its source."*
 */
function greeting(name: string | undefined): string {
  const first = name?.trim().split(/\s+/)[0];
  return first
    ? `${first}, ask about any decision in approved memory. Every answer carries the sentence it came from — and says so plainly when there isn't one.`
    : "Ask about any decision in approved memory. Every answer carries the sentence it came from — and says so plainly when there isn't one.";
}

const STORAGE_KEY = "meridian.rail.collapsed";

export function AssistantRail() {
  const [collapsed, setCollapsed] = useState(false);
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [decisions, setDecisions] = useState<Decision[] | null>(null);
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const session = useSession();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();

  // Persist collapse across navigations/sessions.
  useEffect(() => {
    setCollapsed(localStorage.getItem(STORAGE_KEY) === "1");
  }, []);
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  // ⌘/Ctrl+J toggles the rail from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // `e.key` is typed as `string` but is genuinely absent on some keydown events —
      // browser autofill and IME composition both dispatch them — so the unguarded
      // `.toLowerCase()` threw a runtime TypeError from a global listener, on any page.
      // The type says this cannot happen; the browser disagrees.
      if (e.key?.toLowerCase() === "j" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setCollapsed((c) => !c);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    // Approved only: the rail surfaces settled positions, not live motions. The
    // filter runs server-side in the real API, so it is passed as an argument
    // here rather than applied after the fetch.
    // Meetings first — there is no workspace-wide decisions query. A failure here
    // leaves the rail's recent-decisions list empty rather than throwing; the rail is
    // an aside, and an error banner inside it would shout louder than the page.
    meetingsApi
      .list()
      .then((ms) => decisionsApi.listForMeetings(ms.map((m) => m.id), { status: "approved" }))
      .then((d) => setDecisions(d.slice(0, 3)))
      .catch(() => setDecisions([]));
  }, []);

  useEffect(() => {
    // Same reasoning as the decisions list above: the rail is an aside, so a failure
    // here shows nothing rather than an error banner that would shout louder than the
    // page it sits beside. `null` keeps the section hidden until the answer is known,
    // so an empty list is never rendered as though it were a measured "no documents".
    documentsApi
      .list()
      .then((d) => setDocuments(d.slice(0, 3)))
      .catch(() => setDocuments([]));
  }, []);

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

  // Collapsed: a slim rail with a single affordance to reopen.
  if (collapsed) {
    return (
      <div className="surface-glass-chrome hidden shrink-0 border-l border-border xl:flex xl:w-14 xl:flex-col xl:items-center xl:py-4">
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          aria-label="Open Meridian AI (Ctrl+J)"
          className="grid size-9 place-items-center rounded-[10px] bg-accent text-accent-foreground shadow-card transition-colors hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-elevated"
        >
          <Sparkles className="size-4" aria-hidden />
        </button>
      </div>
    );
  }

  return (
    <aside
      aria-label="Meridian AI"
      className="surface-glass-chrome hidden shrink-0 flex-col border-l border-border xl:flex xl:w-[368px]"
    >
      {/* Header */}
      <div className="flex h-16 items-center justify-between gap-2 border-b border-border px-4">
        <div className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-[10px] bg-accent text-accent-foreground shadow-card">
            <Sparkles className="size-4" aria-hidden />
          </span>
          <div className="leading-tight">
            <div className="text-sm font-semibold text-foreground">Meridian AI</div>
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <span className="size-1.5 rounded-full bg-success" aria-hidden />
              Always on · answers from approved memory
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          aria-label="Collapse Meridian AI (Ctrl+J)"
          className="grid size-8 place-items-center rounded-[10px] text-muted-foreground transition-colors hover:bg-surface-sunken hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <PanelRightClose className="size-4" aria-hidden />
        </button>
      </div>

      {/* Body */}
      <div ref={scrollRef} className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
        {turns.length === 0 ? (
          <>
            {/* Proactive greeting */}
            <div className="rounded-[14px] rounded-tl-md bg-surface-sunken px-3.5 py-3 text-sm leading-relaxed text-foreground">
              {greeting(session?.context.name)}
            </div>

            <RailSection label="Quick shortcuts">
              <div className="flex flex-wrap gap-1.5">
                {SHORTCUTS.map((s) => (
                  <button
                    key={s.label}
                    type="button"
                    onClick={() => ask(s.q)}
                    className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-raised px-2.5 py-1 text-[13px] text-muted-foreground shadow-card transition-colors hover:border-accent-border hover:text-accent-emphasis focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
                  >
                    <span className="size-1.5 rounded-full bg-accent" aria-hidden />
                    {s.label}
                  </button>
                ))}
              </div>
            </RailSection>

            <RailSection label="Recent decisions">
              <ul className="space-y-1.5">
                {(decisions ?? []).map((d) => (
                  <li
                    key={d.id}
                    className="rounded-[12px] border border-border bg-surface-raised px-3 py-2 shadow-card"
                  >
                    <p className="text-[13px] font-medium leading-snug text-foreground">{d.title}</p>
                    {/* The old mock carried a `meeting` display string. The real
                        contract has `meeting_id`, a reference — resolving it would
                        mean fetching meetings into the rail, and printing the raw
                        id would be worse than useless. Stance count says something
                        true and needs no join. */}
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {d.stances.length === 0
                        ? "No stances recorded"
                        : `${d.stances.length} ${d.stances.length === 1 ? "stance" : "stances"} on record`}
                    </p>
                  </li>
                ))}
              </ul>
            </RailSection>

            {/*
              Real documents, from `GET /api/documents`.

              This list was three hard-coded filenames — "Q2 Financial Model.pdf",
              "Board Meeting 13 — Minutes.pdf", "Pricing Model Comparison.xlsx". Two of
              the three exist nowhere in the corpus, under a panel whose own footer
              reads "Every answer cites its source". The July rewrite derived the
              assistant's *answers* from the graph and left these static panels behind.

              They are list items rather than buttons now: the buttons had no handler
              and a chevron that implied a document viewer this product does not have.

              Because the API filters by the caller's clearance, this list also shrinks
              for a lower-cleared principal — without announcing that it did, which is
              the same contract `/packs` keeps.
            */}
            {documents !== null && documents.length > 0 && (
              <RailSection label="Supporting documents">
                <ul className="space-y-0.5">
                  {documents.map((doc) => (
                    <li key={doc.id} className="flex items-center gap-2 px-2 py-1.5">
                      <FileText className="size-3.5 shrink-0 text-subtle-foreground" aria-hidden />
                      <span className="flex-1 truncate text-[13px] text-muted-foreground">{doc.title}</span>
                    </li>
                  ))}
                </ul>
              </RailSection>
            )}
          </>
        ) : (
          <AnimatePresence initial={false}>
            {turns.map((t) => (
              <Turn key={t.id} turn={t} reduce={!!reduce} />
            ))}
          </AnimatePresence>
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
        <div className="flex items-center gap-2 rounded-[12px] border border-border bg-surface-raised px-3 py-1.5 shadow-card transition-colors focus-within:border-accent">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask Meridian anything…"
            aria-label="Ask Meridian anything"
            className="h-8 flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
          />
          <button
            type="submit"
            disabled={!input.trim() || busy}
            aria-label="Send"
            className="grid size-7 shrink-0 place-items-center rounded-[9px] bg-accent text-accent-foreground transition-colors hover:bg-accent-hover disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            <ArrowUp className="size-4" aria-hidden />
          </button>
        </div>
        <p className="mt-1.5 px-1 text-[11px] text-subtle-foreground">
          Every answer cites its source. Withheld sources shown as a count.
        </p>
      </form>
    </aside>
  );
}

function RailSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">{label}</h3>
      {children}
    </section>
  );
}

function Turn({ turn, reduce }: { turn: AssistantTurn; reduce: boolean }) {
  return (
    <motion.div
      className="space-y-3"
      initial={reduce ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduce ? 0 : 0.2, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-[14px] rounded-br-md bg-accent px-3.5 py-2 text-sm text-accent-foreground">
          {turn.question}
        </p>
      </div>

      {turn.answer === null ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="size-1.5 animate-pulse rounded-full bg-accent" aria-hidden />
          Searching approved memory…
        </p>
      ) : (
        <div className="space-y-2.5">
          <p className={cn("text-sm leading-relaxed", turn.answer.abstained ? "text-muted-foreground" : "text-foreground")}>
            {turn.answer.answer}
          </p>

          {turn.answer.citations.map((c, i) => (
            <figure key={i} className="rounded-[12px] bg-surface-sunken px-3 py-2.5">
              <blockquote className="text-xs leading-relaxed text-muted-foreground">
                <span aria-hidden className="text-subtle-foreground">“</span>
                {c.quote}
                <span aria-hidden className="text-subtle-foreground">”</span>
              </blockquote>
              <figcaption className="mt-1.5 flex items-center gap-2 text-[11px]">
                <span className="truncate text-muted-foreground">{c.source}</span>
                <span className="text-border-strong" aria-hidden>·</span>
                <span className="inline-flex items-center gap-1 font-medium text-success-emphasis">
                  <BadgeCheck className="size-3" aria-hidden />
                  Verified
                </span>
              </figcaption>
            </figure>
          ))}

          {turn.answer.related.length > 0 && (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">Related</div>
              <ul className="mt-1.5 space-y-1">
                {turn.answer.related.map((r, i) => (
                  <li key={i} className="text-xs text-muted-foreground">— {r}</li>
                ))}
              </ul>
            </div>
          )}

          {turn.answer.withheld > 0 && (
            <p className="inline-flex items-center gap-1.5 rounded-[10px] bg-warning-subtle px-2.5 py-1.5 text-[11px] text-warning-emphasis">
              <Lock className="size-3" aria-hidden />
              {turn.answer.withheld} source withheld — insufficient clearance
            </p>
          )}
        </div>
      )}
    </motion.div>
  );
}
