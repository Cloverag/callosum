/**
 * @jest-environment node
 *
 * A server-supplied error string reaches the screen through ONE function (#157).
 *
 * ---------------------------------------------------------------------------
 * WHY A SOURCE SCAN AND NOT A COMPONENT TEST
 * ---------------------------------------------------------------------------
 * #151 fixed one surface that rendered `error.message` verbatim, and bound the fix with
 * a test scoped to that component. A component-scoped test binds one component, so the
 * invariant did not propagate — #157 found the same pattern live on four more surfaces
 * months later.
 *
 * Scanning the source is what makes it a *layer* rule instead of a habit. A surface
 * added next month joins by existing, exactly as `tests/test_p4_leak_sweep.py` walks the
 * OpenAPI schema rather than a list of endpoints.
 *
 * ---------------------------------------------------------------------------
 * WHAT THE CHOKEPOINT BUYS, SINCE IT SANITISES NOTHING
 * ---------------------------------------------------------------------------
 * Nothing is filtered here and nothing could be — the client cannot know which strings
 * are restricted. `meridian/api/errors.py` passes a domain exception's `str()` through
 * unless it has a fixed detail, and that is deliberate.
 *
 * What one function buys is that the policy is in one place. Today it renders the
 * server's words because they are useful; if that stops being safe, it is one edit
 * rather than nine, and this test is what keeps the count at one.
 *
 * ---------------------------------------------------------------------------
 * THE COUNT IS WHY THIS IS A TEST AND NOT A CODE REVIEW NOTE
 * ---------------------------------------------------------------------------
 * #157 enumerated four sites by hand. There were **nine**, across five more files —
 * `session-gate.tsx`, `resolutions/page.tsx`, `meeting-form.tsx` (twice) and
 * `field-state.ts`. A hand-written list of the places a pattern appears is the same
 * defect as a hand-written list of endpoints, and it was wrong here by more than half.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const SRC = join(__dirname, "..", "src");

/** The single sanctioned home for turning a server error into display text. */
const CHOKEPOINT = join("lib", "error-text.ts");

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if (/\.(ts|tsx)$/.test(entry)) out.push(full);
  }
  return out;
}

describe("a server error string reaches the screen through one function", () => {
  const files = sourceFiles(SRC);

  it("scans a source tree that actually exists", () => {
    // A scan over zero files passes every assertion below.
    expect(files.length).toBeGreaterThan(40);
    expect(files.some((f) => f.endsWith(CHOKEPOINT))).toBe(true);
  });

  it("has no direct `error.message` outside lib/error-text.ts", () => {
    const offenders: string[] = [];
    for (const file of files) {
      if (file.endsWith(CHOKEPOINT)) continue;
      const text = readFileSync(file, "utf8");
      text.split("\n").forEach((line, i) => {
        // `.message` on a caught ApiError. Matches the property access, so it catches
        // the rendered form `{error.message}` and the stored form
        // `setSaveError(error.message)` alike — the second is a render one tick later.
        if (/\berror\.message\b/.test(line)) {
          offenders.push(`${file.slice(SRC.length + 1)}:${i + 1}`);
        }
      });
    }
    expect(offenders).toEqual([]);
  });

  it("would fail if a surface reintroduced one", () => {
    // The scan is a regex over source text, so it is worth proving the regex matches
    // the shape it is meant to catch rather than trusting it to.
    const rendered = "        <p>{error.message}</p>";
    const stored = "    setSaveError(error.message);";
    const unrelated = "    const message = error.code;";
    expect(/\berror\.message\b/.test(rendered)).toBe(true);
    expect(/\berror\.message\b/.test(stored)).toBe(true);
    expect(/\berror\.message\b/.test(unrelated)).toBe(false);
  });
});
