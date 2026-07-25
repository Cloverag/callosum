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
  communities: number;
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
  approvedFacts: ApprovedFact[];
  decisions: Decision[];
  /** Weekly review throughput, oldest → newest. Feeds the sparkline. */
  reviewVelocity: number[];
  /** Institutional memory accumulating, week by week. Feeds the growth chart. */
  memoryGrowth: MemoryGrowthPoint[];
  pending: PendingActions;
};

/**
 * One weekly snapshot of the graph. Only APPROVED, evidence-backed records are
 * counted — quarantined extractions never appear here, so the curve is the
 * memory the board can actually rely on, not everything the extractor proposed.
 */
export type MemoryGrowthPoint = {
  date: string; // ISO
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
  memory: {
    verifiedPct: 100,
    pendingReview: 5,
    quarantined: 4,
    entities: 731,
    edges: 1277,
    communities: 53,
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
  // Ends on the real p1.0.4 graph snapshot (731 entities / 1277 edges) so the
  // demo reads true; earlier weeks are the corpus building up to it.
  memoryGrowth: [
    { date: "2026-06-01T00:00:00Z", entities: 214, edges: 289 },
    { date: "2026-06-08T00:00:00Z", entities: 298, edges: 431 },
    { date: "2026-06-15T00:00:00Z", entities: 367, edges: 562 },
    { date: "2026-06-22T00:00:00Z", entities: 441, edges: 704 },
    { date: "2026-06-29T00:00:00Z", entities: 528, edges: 871 },
    { date: "2026-07-06T00:00:00Z", entities: 602, edges: 1013 },
    { date: "2026-07-13T00:00:00Z", entities: 674, edges: 1158 },
    { date: "2026-07-20T00:00:00Z", entities: 731, edges: 1277 },
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
