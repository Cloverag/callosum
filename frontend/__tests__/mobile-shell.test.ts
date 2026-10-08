/**
 * @jest-environment node
 *
 * The app shell must survive a 390px viewport.
 *
 * For as long as the sidebar has been `w-[248px]` it has been an unconditional
 * column, and on a phone that left ~142px for content which the shell's
 * `overflow-hidden` then CLIPPED — not scrolled. Headings truncated mid-word,
 * primary buttons fell off the right edge unreachable. A Playwright sweep of 39
 * route/viewport combos found it on every one; the fix (a drawer below `lg`, a
 * responsive `PageHeader`, two clipped content elements) cleared all 39.
 *
 * That sweep needs a real browser and a running server, so it is not this file.
 * This file guards the handful of classes the fix is MADE of, in the same idiom
 * as `tailwind-var-syntax.test.ts` and `motion-contract.test.ts`: assert the
 * invariant on the source, where a regression is caught before a screenshot.
 * If one of these fails, the shell has probably gone back to being unusable at
 * 390px even though CI is green — re-run the browser sweep before relaxing it.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

const SRC = join(__dirname, "..", "src");
const read = (rel: string) => readFileSync(join(SRC, rel), "utf8");

describe("the sidebar is a drawer below lg, a static rail at lg and up", () => {
  const sidebar = read("components/Sidebar.tsx");

  it("hides the static <aside> below lg", () => {
    // `hidden lg:flex` — the aside must not be an unconditional column again.
    const aside = /<aside[^>]*className={?["'`]([^"'`]+)["'`]/.exec(sidebar);
    expect(aside).not.toBeNull();
    expect(aside![1]).toMatch(/\bhidden\b/);
    expect(aside![1]).toMatch(/\blg:flex\b/);
  });

  it("renders the drawer on a real dialog primitive, scoped to below lg", () => {
    expect(sidebar).toMatch(/export function MobileNav\b/);
    expect(sidebar).toMatch(/@base-ui\/react\/dialog/);
    // Both the backdrop and the popup carry `lg:hidden` so a stale open state
    // cannot paint a drawer over the desktop layout.
    const lgHidden = sidebar.match(/lg:hidden/g) ?? [];
    expect(lgHidden.length).toBeGreaterThanOrEqual(2);
    // slide, not fade — the drawer enters from the left edge
    expect(sidebar).toMatch(/data-starting-style:-translate-x-full/);
    expect(sidebar).toMatch(/data-ending-style:-translate-x-full/);
  });

  it("labels the dialog and states aria-modal", () => {
    expect(sidebar).toMatch(/DialogPrimitive\.Title/);
    expect(sidebar).toMatch(/aria-modal="true"/);
  });
});

describe("the header carries the drawer trigger below lg", () => {
  const header = read("components/Header.tsx");

  it("has an lg:hidden hamburger wired to onMenuClick", () => {
    expect(header).toMatch(/onMenuClick\?: \(\) => void/);
    // one button, aria-labelled, hidden at lg
    const btn = /<button[\s\S]*?aria-label="Open navigation"[\s\S]*?className={?["'`]([^"'`]+)["'`]/.exec(header);
    expect(btn).not.toBeNull();
    expect(btn![1]).toMatch(/\blg:hidden\b/);
    expect(header).toMatch(/onClick={onMenuClick}/);
  });

  it("folds the identity block away below sm", () => {
    expect(header).toMatch(/hidden text-right leading-tight sm:block|hidden[^"'`]*sm:block/);
  });
});

describe("PageHeader stacks title and actions below lg", () => {
  const ph = read("components/ui/page-header.tsx");

  it("is flex-col by default and flex-row only at lg", () => {
    expect(ph).toMatch(/flex flex-col/);
    expect(ph).toMatch(/lg:flex-row/);
    // the old unconditional `flex items-start justify-between` must be gone
    expect(ph).not.toMatch(/className={cn\("flex items-start justify-between/);
  });

  it("lets the actions row wrap below lg", () => {
    const actions = /{actions &&[\s\S]*?className="([^"]+)"/.exec(ph);
    expect(actions).not.toBeNull();
    expect(actions![1]).toMatch(/\bflex-wrap\b/);
    expect(actions![1]).toMatch(/\blg:flex-nowrap\b/);
    expect(actions![1]).toMatch(/\blg:shrink-0\b/);
  });
});

describe("the shell closes the drawer on navigation and on resize past lg", () => {
  const shell = read("components/app-shell.tsx");

  it("closes on route change", () => {
    expect(shell).toMatch(/usePathname/);
    expect(shell).toMatch(/useEffect\(\s*\(\)\s*=>\s*{\s*setNavOpen\(false\);\s*},\s*\[pathname\]\)/);
  });

  it("closes when the viewport crosses to the static-sidebar breakpoint", () => {
    expect(shell).toMatch(/matchMedia\("\(min-width: 1024px\)"\)/);
    expect(shell).toMatch(/setNavOpen\(false\)/);
  });

  it("keeps children a passed-through prop, not an import", () => {
    // `children` must stay a Server Component: rendered output in, not part of
    // this client module's graph.
    expect(shell).toMatch(/children\s*}\s*:\s*{\s*children:\s*ReactNode\s*}/);
  });
});
