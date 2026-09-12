/**
 * @jest-environment node
 *
 * Restricted gold-graph evidence must not ship in the browser bundle (#213 C2).
 */

import { GRAPH_EDGES } from "@/lib/graph";

describe("the client gold-graph snapshot", () => {
  it("does not include restricted evidence quotes", () => {
    const leaked = GRAPH_EDGES.filter((e) => e.restricted && e.quote.trim() !== "");
    expect(leaked).toEqual([]);
  });
});
