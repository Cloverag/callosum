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
 * #157 enumerated four sites by hand. There were **eleven**, across six more files.
 * A hand-written list of the places a pattern appears is the same defect as a
 * hand-written list of endpoints, and it was wrong by nearly two thirds.
 *
 * ---------------------------------------------------------------------------
 * WHY THE PATTERN MATCHES ANY IDENTIFIER, AND WHY THERE IS AN ALLOWLIST
 * ---------------------------------------------------------------------------
 * The first version of this scan matched `/\berror\.message\b/` — bound to the
 * identifier `error`. Two live bypasses survived it, both binding the caught value as
 * `e`: `prepare/page.tsx` and `session-gate.tsx`, the latter in the same file as a site
 * that *was* converted. A guard against hand-picked lists, itself a hand-picked list
 * with one entry.
 *
 * Caught in review before merge. Recorded because it is the same shape as the three
 * defects above it — a method name, a router list, a file list — each fix correct about
 * the level above and reproducing the defect at its own.
 *
 * So: match `.message` on **any** identifier, and carry the legitimate cases in an
 * explicit allowlist with a reason written beside each. Narrowing the pattern until the
 * allowlist empties is exactly what failed; an allowlist of one, justified, is honest.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const SRC = join(__dirname, "..", "src");

/** The single sanctioned home for turning a server error into display text. */
const CHOKEPOINT = join("lib", "error-text.ts");

/** `.message` on ANY identifier — `error.message`, `e.message`, `apiError.message`. */
const ACCESS = /\b[A-Za-z_$][A-Za-z0-9_$]*\.message\b/;

/**
 * Legitimate `.message` accesses, each with the reason it is not a disclosure.
 *
 * Deliberately an allowlist rather than a cleverer pattern. Every narrowing of the
 * regex is a silent decision about what counts, and the last one cost two live
 * bypasses. An entry here is a decision someone can read and disagree with.
 */
const ALLOWED: Record<string, string> = {
  // `ApiError` parsing its OWN text to recover the version numbers out of a 409 detail.
  // Not a render: the string is already in the client's hands and goes to a number.
  "lib/http.ts": "ApiError reads its own message to extract conflict versions",
};

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

  it("has no `.message` access outside the chokepoint and the allowlist", () => {
    const offenders: string[] = [];
    for (const file of files) {
      const relative = file.slice(SRC.length + 1);
      if (file.endsWith(CHOKEPOINT) || relative in ALLOWED) continue;
      readFileSync(file, "utf8")
        .split("\n")
        .forEach((line, i) => {
          // Catches the rendered form `{error.message}`, the stored form
          // `setSaveError(e.message)`, and the ternary form `? e.message :` alike —
          // storing it is a render one tick later, and the identifier is not the point.
          if (ACCESS.test(line)) offenders.push(`${relative}:${i + 1}`);
        });
    }
    expect(offenders).toEqual([]);
  });

  it("every allowlist entry still exists and still matches", () => {
    // A stale entry excuses a file that no longer has the pattern — or worse, one that
    // was renamed, leaving the real site unguarded while the allowlist looks tidy.
    for (const relative of Object.keys(ALLOWED)) {
      const full = join(SRC, relative);
      expect(files).toContain(full);
      expect(ACCESS.test(readFileSync(full, "utf8"))).toBe(true);
    }
  });

  it("would catch the forms that escaped the first version of this scan", () => {
    // The previous self-test used `error.` in every example, so it confirmed the
    // framing it was written from and passed while two `e.message` bypasses were live.
    // These cases deliberately use identifiers the first author did NOT think of.
    for (const escaped of [
      "          : e.message",                                              // prepare/page.tsx
      "setError(x instanceof ApiError ? e.message : \"nope\");",             // session-gate.tsx
      "  const t = err.message;",
      "  return apiError.message;",
      "        <p>{error.message}</p>",
      "    setSaveError(error.message);",
    ]) {
      expect(ACCESS.test(escaped)).toBe(true);
    }
    for (const fine of ["    const message = error.code;", "  // a comment about messages", "  msg.length"]) {
      expect(ACCESS.test(fine)).toBe(false);
    }
  });
});
