// Mocked dashboard insights — the "institutional memory" signals and the
// pending-action counts the board home surfaces. Seeded with the real graph
// snapshot figures from the p1.0.3 build so the demo reads true. Swaps to real
// endpoints at P3 behind the same shape.

export type MemoryHealth = {
  /** Share of graph edges with a located verbatim evidence quote. The thesis metric. */
  verifiedPct: number;
  /** Facts awaiting human approval before they enter institutional memory. */
  pendingReview: number;
  /** Rejected-but-retained extractions (the extraction process is the dataset). */
  quarantined: number;
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
export type ApprovedFact = {
  id: string;
  /** Plain-language statement of the fact. */
  statement: string;
  /** The verbatim source quote that grounds it (contiguous, single-speaker). */
  quote: string;
  /** Where the quote was located. */
  source: string;
  approvedAt: string; // ISO
};

/** Action counts that aren't derivable from the meetings/conflicts mocks. */
export type PendingActions = {
  decisionsToSign: number;
  docsToIngest: number;
};

export type DecisionStatus = "approved" | "pending" | "proposed";

/** A governed board decision, sourced to the meeting where it was made. */
export type Decision = {
  id: string;
  title: string;
  status: DecisionStatus;
  meeting: string;
  date: string; // ISO
};

/** Prep completeness for the next board meeting, 0–100 per track. */
export type BoardReadiness = {
  agenda: number;
  metrics: number;
  documents: number;
  approvals: number;
};

export type DashboardInsights = {
  /** One-line, evidence-grounded orientation for the operator. */
  dailyBrief: string;
  /** How ready the next board pack is, by track. */
  readiness: BoardReadiness;
  memory: MemoryHealth;
  quality: GraphQuality;
  approvedFacts: ApprovedFact[];
  decisions: Decision[];
  /** Weekly review throughput, oldest → newest. Feeds the sparkline. */
  reviewVelocity: number[];
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

const insights: DashboardInsights = {
  dailyBrief:
    "3 meetings this week and 5 items awaiting your review. Series B terms are still open ahead of the Q3 board meeting.",
  readiness: {
    agenda: 90,
    metrics: 55,
    documents: 70,
    approvals: 40,
  },
  // CORRECTED 2026-07-26. These previously read 731 entities / 1277 edges / 53
  // communities, which were the *graphify snapshot of this repository's source
  // code* at tag p1.0.2 — not institutional memory at all. Presenting repo
  // metadata as board memory is a correctness problem, not a cosmetic one.
  // The figures below are the real seeded gold graph from `data/demo/`
  // (counted from the GOLD_* tables in `src/callosum/evaluate.py`).
  memory: {
    verifiedPct: 100, // true by construction: verify() refuses an edge with no located quote
    pendingReview: 5, // demo value — no approval queue is wired to the frontend yet
    quarantined: 4, // demo value — see docs/findings.md for real quarantine counts
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
  approvedFacts: [
    {
      id: "f-rev",
      statement: "The board reversed the Q3 pricing rejection.",
      quote: "On reflection we're moving ahead with usage-based pricing after all.",
      source: "Board Meeting 13",
      approvedAt: "2026-07-20T16:40:00Z",
    },
    {
      id: "f-sup",
      statement: "Pricing Model B supersedes the earlier flat-rate proposal.",
      quote: "Model B replaces the flat-rate structure we tabled last quarter.",
      source: "Board Meeting 13",
      approvedAt: "2026-07-20T16:41:00Z",
    },
    {
      id: "f-seq",
      statement: "Sequoia will lead the Series B round.",
      quote: "Sequoia has confirmed they'll lead the Series B at the proposed valuation.",
      source: "Investor Update — Sequoia",
      approvedAt: "2026-07-19T11:05:00Z",
    },
    {
      id: "f-fin",
      statement: "Priya Nair owns the revised FY27 forecast.",
      quote: "Priya will bring the revised FY27 forecast to the next cycle.",
      source: "Q3 Board Meeting",
      approvedAt: "2026-07-18T09:30:00Z",
    },
    {
      id: "f-hire",
      statement: "The board approved a six-person engineering hire.",
      quote: "We signed off on the six-engineer hiring plan for the half.",
      source: "Board Meeting #14",
      approvedAt: "2026-07-09T11:20:00Z",
    },
  ],
  decisions: [
    { id: "d-price", title: "Adopt usage-based pricing (Model B)", status: "approved", meeting: "Board Meeting 13", date: "2026-07-20T16:40:00Z" },
    { id: "d-seq", title: "Sequoia to lead the Series B round", status: "approved", meeting: "Investor Update — Sequoia", date: "2026-07-19T11:05:00Z" },
    { id: "d-terms", title: "Series B final terms", status: "pending", meeting: "Q3 Board Meeting", date: "2026-07-21T09:00:00Z" },
    { id: "d-hire", title: "Six-person engineering hire", status: "approved", meeting: "Board Meeting #14", date: "2026-07-09T11:20:00Z" },
    { id: "d-fcst", title: "Revise the FY27 forecast", status: "proposed", meeting: "Q3 Board Meeting", date: "2026-07-21T09:20:00Z" },
  ],
  reviewVelocity: [4, 6, 3, 7, 5, 8, 6, 9],
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
  pending: {
    decisionsToSign: 2,
    docsToIngest: 1,
  },
};

const delay = (ms = 500) => new Promise((r) => setTimeout(r, ms));

export const insightsApi = {
  async get(): Promise<DashboardInsights> {
    await delay();
    return structuredClone(insights);
  },
};
