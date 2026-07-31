/**
 * The dashboard states only what the repository can evidence (CP-E audit).
 *
 * Three rounds of data-honesty work have gone through `insights.ts`: the dashboard
 * once showed this repository's own source-code graph as institutional memory, then an
 * invented health percentage, then an approval queue that had never been populated.
 * This is the fourth finding and the worst of them.
 *
 * **All five `approvedFacts` quotes were fabricated.** Checked against `data/demo/`
 * during CP-E: not one appeared in any document, and two of the named sources
 * ("Investor Update — Sequoia", "Q3 Board Meeting") were not documents at all. They
 * rendered under the heading "Evidence, not summaries — each with its source quote".
 *
 * That breaks the claim the whole system exists to make. `rules.md` §2: every surfaced
 * graph fact carries a machine-checked verbatim source quote. A hand-written quote is
 * the exact thing `locate()` refuses to let into the graph.
 *
 * These tests do not check prose. They check that each figure is either derived from
 * something in the repo or explicitly `null`.
 */

import { insightsApi } from "../src/lib/insights";
import { GRAPH_EDGES } from "../src/lib/graph";

describe("approved facts are derived, not authored", () => {
  it("quotes every fact from the verified graph", async () => {
    const { approvedFacts } = await insightsApi.get();
    const realQuotes = new Set(GRAPH_EDGES.map((e) => e.quote));

    expect(approvedFacts.length).toBeGreaterThan(0);
    for (const fact of approvedFacts) {
      // If this fails, someone has hand-written a quote again. `graph.ts` is
      // generated from GOLD_GROUPS, so its quotes are text that exists in data/demo/.
      expect(realQuotes.has(fact.quote)).toBe(true);
    }
  });

  it("cites the document the quote was located in", async () => {
    const { approvedFacts } = await insightsApi.get();
    const realDocuments = new Set(GRAPH_EDGES.map((e) => e.document));

    for (const fact of approvedFacts) {
      // A display label that does not match a document is how "Q3 Board Meeting"
      // ended up citing a file that does not exist.
      expect(realDocuments.has(fact.source)).toBe(true);
    }
  });

  it("never surfaces a restricted edge", async () => {
    const { approvedFacts } = await insightsApi.get();
    const restricted = new Set(GRAPH_EDGES.filter((e) => e.restricted).map((e) => e.quote));

    for (const fact of approvedFacts) {
      expect(restricted.has(fact.quote)).toBe(false);
    }
  });
});

describe("unmeasured figures are null, not zero and not invented", () => {
  it("reports no board readiness, because nothing computes one", async () => {
    // Was {agenda: 90, metrics: 55, documents: 70, approvals: 40} — four percentages
    // with no definition. There is no denominator anywhere for "Metrics 55%".
    const { readiness } = await insightsApi.get();
    expect(readiness).toBeNull();
  });

  it("reports no pending counts", async () => {
    const { pending } = await insightsApi.get();
    expect(pending.decisionsToSign).toBeNull();
    expect(pending.docsToIngest).toBeNull();
  });

  it("keeps the earlier nulls null", async () => {
    // Regression cover for rounds two and three. These have been corrected once;
    // a helpful zero substituted later would be the same defect returning.
    const insights = await insightsApi.get();
    expect(insights.memory.pendingReview).toBeNull();
    expect(insights.memory.quarantined).toBeNull();
    expect(insights.reviewVelocity).toBeNull();
  });
});

describe("the figures that ARE measured stay traceable", () => {
  it("reports the seeded gold graph, not this repository's source code", async () => {
    // 38 entities / 40 edges / 14 relation types / 10 documents, counted from
    // GOLD_GROUPS. The dashboard once showed 731/1277/53 — the graphify snapshot of
    // this repo's own code at tag p1.0.2.
    const { memory } = await insightsApi.get();
    expect(memory.entities).toBe(38);
    expect(memory.edges).toBe(40);
    expect(memory.relationTypes).toBe(14);
  });

  it("ends memory growth exactly where the totals say", async () => {
    const { memory, memoryGrowth } = await insightsApi.get();
    const last = memoryGrowth[memoryGrowth.length - 1];
    // The growth chart and the totals card are on the same screen. They once
    // disagreed by a factor of twenty-five.
    expect(last.entities).toBe(memory.entities);
    expect(last.edges).toBe(memory.edges);
  });
});
