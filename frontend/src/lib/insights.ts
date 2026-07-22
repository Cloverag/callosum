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

export type DashboardInsights = {
  memory: MemoryHealth;
  approvedFacts: ApprovedFact[];
  /** Weekly review throughput, oldest → newest. Feeds the sparkline. */
  reviewVelocity: number[];
  pending: PendingActions;
};

const insights: DashboardInsights = {
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
  reviewVelocity: [4, 6, 3, 7, 5, 8, 6, 9],
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
