/**
 * @jest-environment node
 *
 * Signed-out visitors must reach /demo (sign-in) and /privacy (the notice).
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

const src = readFileSync(
  join(__dirname, "../src/components/session-gate.tsx"),
  "utf8",
);

describe("ungated routes", () => {
  it("includes the demo selector and the privacy notice", () => {
    expect(src).toMatch(/UNGATED_ROUTES = new Set\(\["\/demo", "\/privacy"\]\)/);
  });
});
