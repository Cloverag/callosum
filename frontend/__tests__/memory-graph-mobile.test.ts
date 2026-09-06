/**
 * @jest-environment node
 *
 * The knowledge graph has to survive a pane that changes size and a reader with
 * no pointer.
 *
 * `useForceLayout` fires `refit` exactly once, when the simulation first
 * settles. Every later size change — the mobile nav drawer opening over the
 * pane, a phone rotating — then leaves the graph framed for the old size, with
 * no gesture that corrects it. And `fitView` on a pane under 640px clamps near
 * `minZoom`, where 38 boxes at 168px wide render too small to read (~0.4
 * measured). And the edge readout was hover-only, so on touch the edges showed
 * as forty grey lines.
 *
 * Same source-parse idiom as `mobile-shell.test.ts` — a browser sweep proves
 * the behaviour, this keeps the mechanism from being deleted while CI stays
 * green.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

const kg = readFileSync(
  join(__dirname, "..", "src", "app", "memory", "knowledge-graph.tsx"),
  "utf8",
);

describe("the graph re-frames when its pane resizes", () => {
  it("observes the container and calls refit, debounced", () => {
    expect(kg).toMatch(/new ResizeObserver\(/);
    expect(kg).toMatch(/ro\.observe\(el\)/);
    // debounced — a clearTimeout/setTimeout pair around refit, not a bare call
    expect(kg).toMatch(/clearTimeout\(t\);\s*\n\s*t = setTimeout\(refit,/);
    // and the observer is torn down
    expect(kg).toMatch(/ro\.disconnect\(\)/);
  });
});

describe("the zoom floor is higher on a narrow pane", () => {
  it("tracks pane width and raises minZoom below 640px", () => {
    expect(kg).toMatch(/setNarrowPane\(entry\.contentRect\.width < 640\)/);
    expect(kg).toMatch(/minZoom={narrowPane \? 0\.5 : 0\.3}/);
  });
});

describe("the edge readout is reachable without a pointer", () => {
  it("toggles the readout on edge tap and dismisses on pane tap", () => {
    expect(kg).toMatch(/onEdgeClick={\(_, edge\) =>\s*setHovered\(\(h\) => \(h === edge\.id \? null : edge\.id\)\)/);
    // the pane click handler clears the readout too (touch has no mouse-leave)
    expect(kg).toMatch(/onPaneClick={\(\) => {[\s\S]*?setHovered\(null\);[\s\S]*?}}/);
  });

  it("gives the readout a visible dismiss control", () => {
    expect(kg).toMatch(/aria-label="Dismiss"/);
    expect(kg).toMatch(/onClick={\(\) => setHovered\(null\)}/);
    // the panel body stays pointer-events-none; only the button opts back in
    expect(kg).toMatch(/pointer-events-none relative/);
    expect(kg).toMatch(/pointer-events-auto absolute/);
  });
});
