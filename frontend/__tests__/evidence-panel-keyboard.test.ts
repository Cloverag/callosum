/**
 * @jest-environment node
 *
 * Edge evidence is reachable by hover/tap and, for keyboard, through the
 * evidence panel — not by putting ~40 edges in the tab order (#211).
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

const SRC = readFileSync(
  join(__dirname, "../src/app/memory/knowledge-graph.tsx"),
  "utf8"
);

describe("edge evidence has a keyboard path (#211)", () => {
  it("keeps edges out of the tab order", () => {
    expect(SRC).toContain("edgesFocusable={false}");
  });

  it("tells keyboard users the panel is the path", () => {
    expect(SRC).toMatch(/Tab to an entity/);
    expect(SRC).toMatch(/this panel is the keyboard path/);
  });
});
