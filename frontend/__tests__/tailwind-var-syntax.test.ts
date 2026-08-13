/**
 * @jest-environment node
 *
 * Design tokens must be referenced in the spelling Tailwind v4 compiles.
 *
 * Found 2026-08-13, shipped for some time before that. Eighteen utilities across
 * ten files referenced a token as `rounded-[--radius-card]` /
 * `duration-[--duration-hover]` — the Tailwind **v3** spelling, in which a bare
 * `[--x]` was wrapped in `var()` for you. v4 replaced it with `rounded-(--x)`
 * and does NOT wrap the bracket form, so the compiled stylesheet contained:
 *
 *     border-radius: --radius-card;         <- not a length; declaration dropped
 *     transition-duration: --duration-hover; <- not a time;   declaration dropped
 *
 * Nothing errored. Tailwind emitted the class, the browser parsed the rule,
 * discarded the invalid declaration and moved on. The visible result was that
 * every surface using `rounded-(--radius-card)` — including the focal hero added
 * the same day — rendered with **square corners** against a design document that
 * specifies 16px, and six hover transitions silently fell back to the default
 * duration. A design system whose tokens do not reach the page is a document,
 * not a system.
 *
 * This is the class of defect that survives review: the source reads correctly,
 * the test suite is green, and only the compiled output or a screenshot shows it.
 * So it is asserted on the source, where it can be caught before either.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const SRC = join(__dirname, "..", "src");

function sources(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      if (entry === "node_modules") continue;
      sources(path, acc);
    } else if (/\.tsx?$/.test(entry)) {
      acc.push(path);
    }
  }
  return acc;
}

/**
 * `vendor/` is included deliberately, unlike in the motion contract. That rule is
 * about taste, which generated files cannot be held to; this one is about whether
 * the CSS is valid, which they can — and the registry already emits the v4 form
 * (`w-(--anchor-width)`, `origin-(--transform-origin)`), so it costs nothing.
 */
const SOURCES = sources(SRC);

describe("Tailwind v4 CSS-variable references", () => {
  it("finds source files to check", () => {
    expect(SOURCES.length).toBeGreaterThan(20);
  });

  it("uses `utility-(--token)` and never the v3 `utility-[--token]`", () => {
    const offenders: string[] = [];
    for (const path of SOURCES) {
      const src = readFileSync(path, "utf8");
      for (const m of src.matchAll(/[a-z][a-z-]*-\[--[a-z][a-z0-9-]*\]/g)) {
        offenders.push(`${path.slice(SRC.length + 1)}: ${m[0]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("still references the tokens it is supposed to reference", () => {
    /**
     * The bug had a tempting non-fix: delete the broken classes. Then the corners
     * would still be wrong and nothing would say so. These are the tokens the fix
     * restored; if a later change drops them, the design system has quietly lost
     * a consumer rather than gained a passing test.
     */
    const all = SOURCES.map((p) => readFileSync(p, "utf8")).join("\n");
    for (const token of ["--radius-card", "--radius-control", "--duration-hover", "--duration-state", "--ease-out-quart"]) {
      expect(all).toContain(`(${token})`);
    }
  });
});
