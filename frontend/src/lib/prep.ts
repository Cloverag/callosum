import { isOpen, isOverdue, type Commitment } from "@/lib/commitments";
import type { Decision } from "@/lib/decisions";
import type { AgendaItem } from "@/lib/agenda";
import type { BoardPack } from "@/lib/packs";

/**
 * Meeting preparation, derived.
 *
 * ---------------------------------------------------------------------------
 * WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
 * ---------------------------------------------------------------------------
 * Nothing here is generated. Every suggestion below is a **query over state the
 * board already has**: a commitment that is open past its due date, a decision still
 * sitting at `proposed`, an agenda item carried from a meeting that has been. Each one
 * names the row it came from, so "why is this on the agenda?" is answerable by clicking
 * rather than by trusting.
 *
 * That is a deliberate rejection of the obvious alternative. A language model asked to
 * "suggest an agenda" would produce something more fluent and entirely unfalsifiable,
 * and `rules.md` §2 exists to stop exactly that: no AI output enters institutional
 * memory without a human approving it, and nothing is surfaced without the source that
 * proves it. A generated agenda has no source. A derived one is nothing but sources.
 *
 * The weaker-sounding claim is the stronger one. "The agenda assembles itself from what
 * is genuinely unresolved" can be checked. "The AI drafted your agenda" cannot.
 *
 * ---------------------------------------------------------------------------
 * WHY READINESS IS COUNTS AND NOT PERCENTAGES
 * ---------------------------------------------------------------------------
 * The prototype this follows shows Agenda 90%, Metrics 55%, Documents 70%,
 * Approvals 40%, and an overall 64%. Every one of those needs a denominator that does
 * not exist — there is no definition of a complete agenda, no metrics module, and no
 * total against which 40% of approvals could be measured. A percentage implies a
 * measurement; these would be decoration wearing a measurement's clothes, which is the
 * defect class this project has removed four times already.
 *
 * So readiness reports what is true and countable: how many agenda items exist, whether
 * a pack is published, how many commitments are overdue, how many decisions are still
 * open. A reader can act on those. They cannot act on 64%.
 */

/** Where a derived signal came from. The UI renders this; it is not decoration. */
export type PrepSource =
  | { kind: "commitment"; id: string; label: string }
  | { kind: "decision"; id: string; label: string }
  | { kind: "agenda_item"; id: string; label: string };

/**
 * The meeting `/prepare` is about: the earliest one not yet held.
 *
 * Extracted from the page because it was wrong there and inline logic cannot be
 * regression-tested. It sorted with `(a.scheduled_start ?? "").localeCompare(...)`,
 * and an empty string compares *below* every ISO timestamp — so an unscheduled draft
 * sorted **first** and the page prepared it in preference to a meeting with a real
 * date. The comment beside it asserted the opposite, which is how it passed review.
 *
 * Undated meetings sort last, explicitly: a meeting with no scheduled start cannot be
 * "next". Falls back to the first meeting of any status so a workspace whose meetings
 * are all completed still has something to show rather than an empty page.
 */
export function nextMeetingToPrepare<T extends { status: string; scheduled_start: string | null }>(
  meetings: T[],
): T | null {
  const upcoming = meetings
    .filter((m) => m.status === "draft" || m.status === "scheduled")
    .slice()
    .sort((a, b) => {
      if (!a.scheduled_start) return 1;
      if (!b.scheduled_start) return -1;
      return a.scheduled_start.localeCompare(b.scheduled_start);
    });

  return upcoming[0] ?? meetings[0] ?? null;
}

/**
 * Where a reader goes to check a derived claim against the record behind it, or `null`
 * when this product has nowhere to send them.
 *
 * `/commitments`, `/decisions` and `/packs` each render their rows with `id={x.id}` and
 * `scroll-mt-8`, so a fragment resolves to the record and scrolls it clear of the
 * header. Those are real destinations that exist today.
 *
 * **`agenda_item` returns `null` deliberately.** Agenda items are rendered inside the
 * calendar's meeting detail, not on a route that can resolve one by id, so there is no
 * honest link to give. The caller renders the id as text instead. Inventing
 * `/agenda#<id>` would produce a link that 404s — a worse failure than admitting the
 * product cannot yet resolve it, because the reader only discovers it by clicking.
 */
export function sourceHref(source: PrepSource): string | null {
  switch (source.kind) {
    case "commitment":
      return `/commitments#${source.id}`;
    case "decision":
      return `/decisions#${source.id}`;
    case "agenda_item":
      return null;
  }
}

/** One observation about the state of the board, with the row it was read from. */
export type PrepSignal = {
  id: string;
  /** Plain statement of fact. Never a recommendation the data cannot support. */
  statement: string;
  source: PrepSource;
  tone: "attention" | "critical" | "neutral";
};

/** A proposed agenda item, and the unfinished business that proposes it. */
export type AgendaSuggestion = {
  /** Stable across renders: derived from the source row, not a random id. */
  id: string;
  title: string;
  /** Why this is being suggested, in terms of the row it came from. */
  reason: string;
  source: PrepSource;
};

/** What is countably true about the meeting's preparation. */
export type PrepReadiness = {
  agendaItems: number;
  /** `null` when no pack exists at all, which is different from an empty one. */
  packItems: number | null;
  packPublished: boolean;
  overdueCommitments: number;
  openCommitments: number;
  openDecisions: number;
};

/**
 * Commitments that are open, most urgent first.
 *
 * Overdue before merely open, and within each group the earliest due date leads. A
 * commitment with no due date sorts last: it is unfinished but nothing about it is
 * late, and putting it above something three weeks overdue would misrepresent both.
 */
export function unresolvedCommitments(commitments: Commitment[], today: string): Commitment[] {
  return commitments
    .filter(isOpen)
    .slice()
    .sort((a, b) => {
      const aLate = isOverdue(a, today);
      const bLate = isOverdue(b, today);
      if (aLate !== bLate) return aLate ? -1 : 1;
      if (!a.due_date) return b.due_date ? 1 : 0;
      if (!b.due_date) return -1;
      return a.due_date.localeCompare(b.due_date);
    });
}

/** Decisions the board has not settled. `proposed` is the only genuinely open state. */
export function openDecisions(decisions: Decision[]): Decision[] {
  return decisions.filter((d) => d.status === "proposed");
}

/**
 * What the board has not finished, stated as fact.
 *
 * Each signal is one row. There is no summarising across rows — "revenue grew but burn
 * rose, so discuss hiring pace" is the kind of sentence that requires data this product
 * does not hold, and inventing the join is how the prototype ended up citing a Finance
 * Module that does not exist.
 */
export function prepSignals(
  commitments: Commitment[],
  decisions: Decision[],
  today: string,
): PrepSignal[] {
  const signals: PrepSignal[] = [];

  for (const c of unresolvedCommitments(commitments, today)) {
    const late = isOverdue(c, today);
    signals.push({
      id: `commitment:${c.id}`,
      statement: late
        ? `"${c.title}" was due ${c.due_date} and is still open.`
        : `"${c.title}" is still open.`,
      source: { kind: "commitment", id: c.id, label: "Commitment" },
      tone: late ? "critical" : "attention",
    });
  }

  for (const d of openDecisions(decisions)) {
    signals.push({
      id: `decision:${d.id}`,
      statement: `"${d.title}" is still proposed and has not been settled.`,
      source: { kind: "decision", id: d.id, label: "Decision" },
      tone: "attention",
    });
  }

  return signals;
}

/**
 * Agenda items proposed from unfinished business.
 *
 * Anything already on the agenda is excluded, matched on title, case- and
 * whitespace-insensitively. The domain has no link between an agenda item and the
 * commitment that produced it — `agenda_item` carries no foreign key to either
 * `commitment` or `decision` — so the title is the only join available. It is a weak
 * one, and stated as such here rather than presented as reliable: an item renamed after
 * being added will be suggested a second time.
 */
export function suggestAgenda(
  commitments: Commitment[],
  decisions: Decision[],
  existing: AgendaItem[],
  today: string,
): AgendaSuggestion[] {
  const normalise = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");
  const already = new Set(existing.map((item) => normalise(item.title)));
  const suggestions: AgendaSuggestion[] = [];

  for (const c of unresolvedCommitments(commitments, today)) {
    if (already.has(normalise(c.title))) continue;
    suggestions.push({
      id: `commitment:${c.id}`,
      title: c.title,
      reason: isOverdue(c, today)
        ? `Open commitment, past its due date of ${c.due_date}.`
        : "Open commitment, not yet complete.",
      source: { kind: "commitment", id: c.id, label: "Commitment" },
    });
  }

  for (const d of openDecisions(decisions)) {
    if (already.has(normalise(d.title))) continue;
    suggestions.push({
      id: `decision:${d.id}`,
      title: d.title,
      reason: "Proposed decision awaiting the board.",
      source: { kind: "decision", id: d.id, label: "Decision" },
    });
  }

  return suggestions;
}

/**
 * Countable preparation state.
 *
 * `packs` is every pack for the meeting; the newest published one decides
 * `packPublished`, because a superseded pack having once been published says nothing
 * about whether the board can currently read one.
 */
export function prepReadiness(
  agenda: AgendaItem[],
  packs: BoardPack[],
  commitments: Commitment[],
  decisions: Decision[],
  today: string,
): PrepReadiness {
  const open = unresolvedCommitments(commitments, today);
  // Item counts come from the pack the reader can actually see. They are already
  // clearance-filtered server-side, so this counts what survived for THIS caller and
  // never implies anything about what did not.
  //
  // Sorted here rather than trusting the caller's order. This took
  // `published[published.length - 1]`, which assumed ascending input — and
  // `list_packs` returns `ORDER BY version_no DESC`, so it selected the OLDEST
  // published pack and reported its item count as the current one. Sorting explicitly
  // makes the function correct whatever order it is handed, which a read-only
  // derivation should be.
  const published = packs
    .filter((p) => p.status === "published")
    .slice()
    .sort((a, b) => a.version_no - b.version_no);
  const newestPublished = published.length > 0 ? published[published.length - 1] : null;

  return {
    agendaItems: agenda.length,
    packItems: newestPublished ? newestPublished.items.length : null,
    packPublished: newestPublished !== null,
    overdueCommitments: open.filter((c) => isOverdue(c, today)).length,
    openCommitments: open.length,
    openDecisions: openDecisions(decisions).length,
  };
}
