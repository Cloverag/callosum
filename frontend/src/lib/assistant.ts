// "Ask Meridian" — the product thesis made conversational.
//
// REWRITTEN 2026-07-26. This module used to carry hand-written answers with
// hand-written quotes. Checked against the real graph, EVERY quote it cited was
// fabricated and three of its four sources did not exist — on the one feature
// whose stated premise is "I only answer from approved, source-backed memory".
// An examiner asking "show me where that quote came from" would have found
// nothing.
//
// Now every answer is DERIVED from `graph.ts`, which is itself generated from
// the research corpus. A citation cannot be invented here because there is
// nowhere to invent one from.
//
// The shape deliberately mirrors the real pipeline in `src/callosum/retrieve.py`:
//
//   ground(question)  → match the question's wording to real node names
//   traverse(entity)  → collect the edges touching it
//   filter(clearance) → drop what the caller may not see, and COUNT it
//   render            → answer + verbatim citations, or abstain
//
// It is not a language model and does not pretend to be one. It is a small
// deterministic retriever over verified memory, which is the honest thing for a
// mock to be — and it fails the same way the real system does: by abstaining.

import { GRAPH_EDGES, GRAPH_NODES, type GraphEdgeData } from "./graph";

export type Citation = {
  /** Verbatim source quote grounding the answer (contiguous, single-speaker). */
  quote: string;
  source: string;
};

export type AssistantAnswer = {
  answer: string;
  citations: Citation[];
  /** Related approved facts the operator might follow. */
  related: string[];
  /** Sources excluded by clearance before the answer was assembled (count only). */
  withheld: number;
  /** True when no verified answer exists — the assistant abstains rather than guess. */
  abstained?: boolean;
};

export type AssistantTurn = {
  id: string;
  question: string;
  answer: AssistantAnswer | null; // null while thinking
};

/** Only prompts the graph can actually answer. Offering one it cannot would be
 *  a promise the evidence does not keep. */
export const SUGGESTED_PROMPTS = [
  "Why did we reject Pricing Model B?",
  "Who reversed the pricing decision?",
  "Who is Rajesh Kumar?",
  "What came out of Board Meeting 14?",
];

/* -------------------------------------------------------------------------- */
/* Grounding — deterministic, no embeddings, exactly like retrieve.ground()     */
/* -------------------------------------------------------------------------- */

const STOP = new Set([
  "the", "a", "an", "and", "or", "but", "did", "do", "does", "we", "our", "us",
  "what", "who", "why", "when", "where", "how", "was", "were", "is", "are",
  "about", "for", "from", "with", "to", "of", "on", "in", "it", "that", "this",
  "board", "decide", "decided", "decision", "say", "said", "tell", "me",
]);

function tokens(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter((t) => t.length > 1 && !STOP.has(t));
}

/**
 * Map the question's wording onto real node names.
 *
 * Scored by how much of the NODE's name the question covers, so "Pricing Model
 * B" beats "Pricing" — the same bias toward specific matches the real linker
 * has. Returns nothing when the question shares no vocabulary with the graph,
 * which is what makes abstention possible rather than decorative.
 */
function ground(question: string): string[] {
  const qt = new Set(tokens(question));
  if (qt.size === 0) return [];

  const scored = GRAPH_NODES.map((n) => {
    const nt = tokens(n.label);
    if (nt.length === 0) return { id: n.id, score: 0 };
    const hits = nt.filter((t) => qt.has(t)).length;
    // Fraction of the node's own name that the question matched.
    return { id: n.id, score: hits / nt.length, hits };
  }).filter((s) => s.score > 0 && (s.hits ?? 0) > 0);

  if (scored.length === 0) return [];
  const best = Math.max(...scored.map((s) => s.score));
  // Only full-strength matches. A partial one is the linker's failure mode, and
  // abstaining beats grounding to the wrong node.
  return scored.filter((s) => s.score === best && best >= 0.5).map((s) => s.id);
}

/* -------------------------------------------------------------------------- */
/* Rendering                                                                    */
/* -------------------------------------------------------------------------- */

const RELATION_PHRASE: Record<string, string> = {
  APPROVED: "approved",
  OPPOSED: "opposed",
  SUPPORTED: "supported",
  REQUESTED: "requested",
  SUPERSEDES: "supersedes",
  MADE_IN: "was made in",
  ABOUT: "concerns",
  OWNS: "owns",
  ATTENDED: "attended",
  REPORTED_IN: "was reported in",
  DERIVED_FROM: "was derived from",
  PRESENTED_AT: "was presented at",
  WORKS_AT: "works at",
  ALIAS_OF: "is the same person as",
};

function sentenceFor(e: GraphEdgeData): string {
  return `${e.source} ${RELATION_PHRASE[e.relation] ?? e.relation.toLowerCase()} ${e.target}.`;
}

const ABSTENTION: AssistantAnswer = {
  answer:
    "I don't have a verified answer for that. I only answer from approved, source-backed board memory — I won't guess.",
  citations: [],
  related: [],
  withheld: 0,
  abstained: true,
};

const delay = (ms = 700) => new Promise((r) => setTimeout(r, ms));

export const assistantApi = {
  /**
   * `canSeeRestricted` mirrors the caller's clearance. Restricted edges are
   * dropped BEFORE the answer is assembled and reported as a count — the same
   * ordering the backend enforces, where filtering after retrieval would mean
   * the text had already been loaded.
   */
  async ask(question: string, canSeeRestricted = true): Promise<AssistantAnswer> {
    await delay();

    const seeds = ground(question);
    if (seeds.length === 0) return structuredClone(ABSTENTION);

    const touching = GRAPH_EDGES.filter(
      (e) => seeds.includes(e.source) || seeds.includes(e.target)
    );
    const visible = canSeeRestricted ? touching : touching.filter((e) => !e.restricted);
    const withheld = touching.length - visible.length;

    if (visible.length === 0) {
      return {
        ...structuredClone(ABSTENTION),
        answer:
          withheld > 0
            ? "Everything I hold on that sits above your clearance. I can tell you it exists, but not what it says."
            : ABSTENTION.answer,
        withheld,
      };
    }

    // Lead with the edges a board actually asks about; keep the rest as context.
    const RANK = ["APPROVED", "SUPERSEDES", "OPPOSED", "SUPPORTED", "REQUESTED", "ABOUT", "MADE_IN"];
    const ranked = [...visible].sort(
      (a, b) =>
        (RANK.indexOf(a.relation) + 1 || 99) - (RANK.indexOf(b.relation) + 1 || 99)
    );

    // Lead with the facts, not with a match report. The count goes last, where
    // it reads as provenance rather than as the answer.
    const lead = ranked.slice(0, 3).map(sentenceFor).join(" ");
    const rest = ranked.length - Math.min(3, ranked.length);

    return {
      answer:
        lead +
        (rest > 0
          ? ` ${rest} further verified relationship${rest === 1 ? "" : "s"} are recorded.`
          : ""),
      // Citations are the edges' own quotes. There is no other source of them.
      citations: ranked
        .filter((e) => e.quote)
        .slice(0, 4)
        .map((e) => ({ quote: e.quote, source: e.document })),
      related: ranked.slice(3, 6).map(sentenceFor),
      withheld,
    };
  },
};
