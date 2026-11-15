import { GRAPH_EDGES, GRAPH_NODES } from "@/lib/graph";
import { insightsApi } from "@/lib/insights";

// These modules ship in the JavaScript bundle to every visitor, who has no
// clearance. A restricted row here is readable by anyone (#213 C2), whatever the
// page does with it at runtime.
describe("the client graph snapshot carries no restricted content", () => {
  it("has no restricted node or edge", () => {
    expect(GRAPH_NODES.filter((n) => n.restricted)).toEqual([]);
    expect(GRAPH_EDGES.filter((e) => e.restricted)).toEqual([]);
  });

  it("names no confidential document anywhere in the shipped data", async () => {
    const shipped = JSON.stringify([GRAPH_NODES, GRAPH_EDGES, await insightsApi.get()]);
    expect(shipped).not.toMatch(/CONFIDENTIAL|compensation/i);
  });
});
