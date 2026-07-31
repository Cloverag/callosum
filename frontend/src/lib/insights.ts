// Dashboard insights.
//
// Audited tile by tile across three rounds (2026-07-26, 07-27, and CP-E 08-01). The
// rule this file now follows: a figure is either traceable to a file in this repo, or
// it is `null`. Nothing here is estimated, and nothing is a placeholder that reads as
// a measurement.
//
//   measured   — `memory` (gold graph), `quality` (eval/), `memoryGrowth` (GOLD_GROUPS)
//   derived    — `approvedFacts` (graph.ts, verbatim quotes)
//   not measured — `readiness`, `pending.*`, `reviewVelocity`, `pendingReview`,
//                  `quarantined`; all `null`, each with the reason recorded inline

import { GRAPH_EDGES } from "@/lib/graph";

export type MemoryHealth = {
  /** Share of graph edges with a located verbatim evidence quote. The thesis metric. */
  verifiedPct: number;
  /**
   * Facts awaiting human approval before they enter institutional memory.
   * Backed by `proposed_change WHERE status = 'pending'` (see `store.pending()`).
   *
   * `null` means NOT MEASURED, and the UI must say so rather than print a number.
   * It is deliberately not `0`: the graph on this dashboard is the deterministic
   * seeded gold graph, which never passed through extraction, so a `0` would
   * assert "the queue is empty" when the truth is "no queue was ever populated".
   */
  pendingReview: number | null;
  /**
   * Rejected-but-retained extractions (the extraction process is the dataset).
   * Backed by the `extraction_failure` table (see `store.failure_stats()`).
   * `null` for the same reason as `pendingReview` above.
   */
  quarantined: number | null;
  entities: number;
  edges: number;
  /** Distinct ontology relation types actually present in the graph. */
  relationTypes: number;
  /** Source documents ingested into the corpus. */
  documents: number;
};

/**
 * One measured evaluation metric. `value / total` is the raw count so the card can
 * show the fraction as well as the ratio — "17 / 21" is a more honest research
 * claim than "81%" alone, because it exposes how small the denominator is.
 */
export type QualityMetric = {
  id: string;
  label: string;
  value: number;
  total: number;
  /** What the number means, in board English. */
  hint: string;
};

/**
 * Graph quality, split by the SAME three-tier structure the eval harness uses
 * (see `docs/releases/meridian-p1.0.3.md`). The distinction is the point:
 * `verified` is deterministic and gated — it reruns identically with no cloud
 * LLM in the loop — while `observed` depends on a non-deterministic model and
 * is reported, never gated. Collapsing the two into one "health %" is precisely
 * the thing this panel exists to stop.
 */
export type GraphQuality = {
  /** Required tier — the p1.0.3 mechanism gate. Deterministic, no LLM. */
  verified: QualityMetric[];
  /** Observed tier — planner behaviour, LLM-dependent. */
  observed: QualityMetric[];
  /** Measured contribution of the grounding stage: same engine, grounding off vs on. */
  ablation: { off: number; on: number };
  /** Provenance so a reader can reproduce every number above. */
  source: { run: string; files: string[] };
};

/** A graph fact that cleared verification + human approval — shown with its evidence. */
/**
 * A board fact with the verbatim quote that evidences it.
 *
 * **Derived from `graph.ts`, never written by hand.** The five facts that used to sit
 * here as literals were checked against `data/demo/` during the CP-E audit and all
 * five quotes were fabricated — none appeared in any document — while two of the named
 * sources ("Investor Update — Sequoia", "Q3 Board Meeting") were not documents at all.
 *
 * That is the same defect found in the Ask Meridian citations and fixed there; this
 * surface was missed. It matters more than a wrong label: `rules.md` §2 says every
 * surfaced graph fact carries a machine-checked verbatim source quote, and a dashboard
 * printing invented quotes under the heading "Evidence, not summaries" breaks the one
 * claim the system exists to make.
 *
 * There is no `approvedAt`. The gold graph has no timestamps, so any date would be
 * invented — the same reason `memoryGrowth` is ordered by ingestion rather than time.
 */
export type ApprovedFact = {
  id: string;
  /** Plain-language statement of the fact. */
  statement: string;
  /** The verbatim source quote that grounds it (contiguous, single-speaker). */
  quote: string;
  /** Where the quote was located. */
  source: string; // ISO
};

/** Action counts that aren't derivable from the meetings/conflicts mocks. */
export type PendingActions = {
  /** `null` when not measured. A count that was never counted is not a zero. */
  decisionsToSign: number | null;
  docsToIngest: number | null;
};

// REMOVED 2026-07-28: `DecisionStatus` and `Decision` used to be declared here.
// They were invented — the status set was "approved" | "pending" | "proposed",
// and the domain has never had a "pending" decision, while "rejected",
// "superseded" and "deferred" were all missing. There were no stances at all.
//
// The real contract shipped in PR #22 (`meridian/decisions.py`, migration
// `0009_decision`, 20 integration tests). It now lives in `lib/decisions.ts`,
// mirrored field for field. Import from there.

/** Prep completeness for the next board meeting, 0–100 per track. */
export type BoardReadiness = {
  agenda: number;
  metrics: number;
  documents: number;
  approvals: number;
};

export type DashboardInsights = {
  /**
   * The narrative half of the operator's orientation line. Counts are NOT in
   * here — the dashboard derives those from live mock data and prepends them,
   * so the sentence cannot drift out of step with what the page shows.
   */
  dailyBrief: string;
  /** How ready the next board pack is, by track. */
  readiness: BoardReadiness | null;
  memory: MemoryHealth;
  quality: GraphQuality;
  approvedFacts: ApprovedFact[];
  /**
   * Weekly review throughput, oldest → newest. Feeds the sparkline.
   *
   * `null` = not measured. This is throughput of the *same* approval queue that
   * backs `memory.pendingReview`, so it cannot be real while that one is not,
   * and a weekly axis would additionally invent time the data does not have —
   * the mistake already corrected in `memoryGrowth` below.
   */
  reviewVelocity: number[] | null;
  /** Institutional memory accumulating, week by week. Feeds the growth chart. */
  memoryGrowth: MemoryGrowthPoint[];
  pending: PendingActions;
};

/**
 * The graph after each source document is ingested. Cumulative and de-duplicated:
 * a person named in three meetings is one entity, so the curve flattens where a
 * document mostly refers to things already known — which is the honest shape of
 * institutional memory, and more informative than a smooth upward line.
 *
 * NOT a time series. The x-axis is ingestion order, because that is the axis the
 * data actually has; inventing dates for it would be fabrication.
 */
export type MemoryGrowthPoint = {
  /** Source document, in ingestion order. */
  document: string;
  /** Short label for the axis. */
  label: string;
  edges: number;
  entities: number;
};

/**
 * Board facts, derived from the verified graph rather than authored.
 *
 * Takes the edges that record a board *action* — who approved what, what superseded
 * what, who owns what — and renders each with the quote `locate()` verified and the
 * document it came from. `graph.ts` is generated by `scripts/gen_graph_data.py` from
 * `GOLD_GROUPS`, so every quote here is text that exists in `data/demo/`.
 *
 * Restricted edges are excluded. This surface has no clearance context, and the safe
 * default when you cannot check is to show less.
 */
function deriveApprovedFacts(): ApprovedFact[] {
  const ACTIONS: Record<string, string> = {
    APPROVED: "approved",
    SUPERSEDES: "supersedes",
    OWNS: "owns",
  };

  return GRAPH_EDGES.filter((e) => !e.restricted && e.relation in ACTIONS)
    .slice(0, 5)
    .map((e) => ({
      id: e.id,
      statement: `${e.source} ${ACTIONS[e.relation]} ${e.target}.`,
      quote: e.quote,
      // The document the quote was located in, not a prettified meeting name. A
      // display label that does not match a filename is how "Board Meeting #14" and
      // "Q3 Board Meeting" ended up citing documents that do not exist.
      source: e.document,
    }));
}

const insights: DashboardInsights = {
  // CORRECTED 2026-07-27. Previously opened "3 meetings this week and 5 items
  // awaiting your review" — a hard-coded meeting count that no mock backed, and
  // a restatement of the invented `pendingReview: 5`. The counts now come from
  // the real mock data in `dashboard/page.tsx`; this field carries only the
  // narrative tail, which the gold graph does support (Sequoia leading the
  // Series B is an approved fact in `graph.ts`).
  dailyBrief: "Series B terms are still open ahead of the Q3 board meeting.",
  // AUDITED 2026-08-01 (CP-E). Was `{agenda: 90, metrics: 55, documents: 70,
  // approvals: 40}` — four percentages with no definition and no source, rendered
  // as "Board readiness 64%". Nothing in the system computes readiness, and no
  // definition of "Metrics 55%" exists to compute it from. There is no honest
  // number to substitute, so there is no number.
  //
  // To derive it later: each track needs a stated denominator first — agenda items
  // with a presenter, packs published against a scheduled meeting, decisions moved
  // out of `proposed`. Percentages without a denominator are a mood.
  readiness: null,
  // CORRECTED 2026-07-26. These previously read 731 entities / 1277 edges / 53
  // communities, which were the *graphify snapshot of this repository's source
  // code* at tag p1.0.2 — not institutional memory at all. Presenting repo
  // metadata as board memory is a correctness problem, not a cosmetic one.
  // The figures below are the real seeded gold graph from `data/demo/`
  // (counted from the GOLD_* tables in `src/callosum/evaluate.py`).
  memory: {
    verifiedPct: 100, // true by construction: verify() refuses an edge with no located quote
    // CORRECTED 2026-07-27. These previously read `pendingReview: 5` and
    // `quarantined: 4`, both labelled "demo value" in a comment nobody sees at
    // runtime — the dashboard printed them as measurements. They were the last
    // invented numbers on this page.
    //
    // There is no honest number to substitute. Both counts come from tables that
    // only an extraction run populates (`proposed_change`, `extraction_failure`),
    // and the graph shown here is the seeded gold graph, which bypasses
    // extraction entirely. `0` would be a claim, not a fact. The one recorded
    // live run (docs/findings.md, 2026-07-15) is prose, and self-inconsistent at
    // that — "57 + 36 proposed edges, 4 quarantined" alongside "93 edges
    // committed" — so it is not sound provenance either.
    //
    // Wire these at P3, from store.pending() and store.failure_stats().
    pendingReview: null,
    quarantined: null,
    entities: 38,
    edges: 40,
    relationTypes: 14,
    documents: 10, // documents seeded into the graph (GOLD_GROUPS); data/demo/ holds 16 files
  },
  // Every number here is measured, reproducible, and traceable to a file in the
  // repo. Nothing in this block is invented — that is the whole point of it.
  quality: {
    verified: [
      {
        id: "candidate",
        label: "Candidate recall",
        value: 22,
        total: 22,
        hint: "Questions whose gold entity appeared in the retrieved candidate set. A hard ceiling on everything downstream — the planner may only ground to names this stage surfaced.",
      },
      {
        id: "traversal",
        label: "Traversal",
        value: 21,
        total: 21,
        hint: "Given a correct starting entity, the graph returned every required edge. Measured on gold seeds, so it isolates the engine from the linking stage above it.",
      },
      {
        id: "rbac",
        label: "RBAC fail-closed",
        value: 1,
        total: 1,
        hint: "A caller below the required clearance was refused the restricted content, in SQL and in Cypher, before it ever reached the model.",
      },
    ],
    observed: [
      {
        id: "grounding",
        label: "Entity grounding",
        value: 17,
        total: 21,
        hint: "The planner mapped the question's wording to the right node — e.g. \"metered billing\" to \"Pricing Model B\". The Grounding Error Rate (19%) is simply the inverse of this number, not a separate measurement.",
      },
      {
        id: "precision",
        label: "Grounding precision",
        value: 1,
        total: 2,
        hint: "Questions with no referent in the graph at all, where the correct behaviour is to abstain. The known open weakness: the linker does not always refuse.",
      },
    ],
    ablation: { off: 38, on: 100 },
    source: {
      run: "2026-07-20",
      files: ["eval/mechanism.csv", "eval/results.md"],
    },
  },
  approvedFacts: deriveApprovedFacts(),
  // CORRECTED 2026-07-27. Was [4, 6, 3, 7, 5, 8, 6, 9] rendered under a
  // "last 8 weeks" caption: an invented series on an invented axis, measuring an
  // approval queue that has never been populated. See the type note above.
  reviewVelocity: null,
  // Every row below was computed from the real gold graph, not estimated:
  //   .venv/bin/python -c "from callosum.evaluate import GOLD_GROUPS; ..."
  // accumulating unique entities and unique (source, relation, target) triples
  // in GOLD_GROUPS order. Ends at 38 / 40, matching `memory` above.
  memoryGrowth: [
    { document: "board_meeting_12_transcript", label: "M12", entities: 7, edges: 6 },
    { document: "board_meeting_13_transcript", label: "M13", entities: 15, edges: 16 },
    { document: "board_meeting_14_transcript", label: "M14", entities: 25, edges: 28 },
    { document: "finance_fy27_forecast", label: "Finance", entities: 27, edges: 29 },
    { document: "sales_fy27_forecast", label: "Sales", entities: 29, edges: 30 },
    { document: "board_meeting_15_transcript", label: "M15", entities: 31, edges: 34 },
    { document: "board_meeting_16_transcript", label: "M16", entities: 34, edges: 37 },
    { document: "messy_board_followup_email", label: "Board email", entities: 35, edges: 38 },
    { document: "messy_audit_followup_email", label: "Audit email", entities: 37, edges: 39 },
    { document: "compensation_review_CONFIDENTIAL", label: "Comp review", entities: 38, edges: 40 },
  ],
  // AUDITED 2026-08-01 (CP-E). Was `{decisionsToSign: 2, docsToIngest: 1}`, printed
  // in the "Needs you" list as if counted.
  //
  // `decisionsToSign` is now genuinely derivable — `GET /api/decisions?meeting_id=`
  // went live in CP-C and `proposed` is the status that needs signing — but it takes
  // a meeting to scope it and the dashboard would have to fetch per meeting. Recorded
  // as #NNN rather than guessed at.
  //
  // `docsToIngest` has no source at all: ingestion is a CLI operation with no queue,
  // so nothing anywhere knows of a document waiting to be ingested.
  pending: {
    decisionsToSign: null,
    docsToIngest: null,
  },
};

const delay = (ms = 500) => new Promise((r) => setTimeout(r, ms));

export const insightsApi = {
  async get(): Promise<DashboardInsights> {
    await delay();
    return structuredClone(insights);
  },
};
