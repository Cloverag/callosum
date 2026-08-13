/**
 * @jest-environment node
 *
 * The palette's contrast claims, made checkable.
 *
 * `DESIGN.md` and `rules.md` §4 state specific measured figures — "worst pairing in
 * the system is 5.54:1", "zero failures across 7 inks x 9 surfaces", "17.69:1 on
 * white". Until this file existed, nothing held them: the palette was *generated*
 * correctly and then documented, and any later token edit could silently falsify
 * the prose while every test stayed green.
 *
 * `rules.md` §2 calls a palette "exactly the kind of thing §2 means by a measured
 * claim". This is that measurement, run on every push, in the same idiom as
 * `test_no_raw_cypher.py` and `test_migration_immutability.py`: a documented
 * invariant becomes an enforced one.
 *
 * If a number here fails, do NOT relax the assertion to match the code. The
 * assertion is what the design doc promises a reader. Fix the token, or amend
 * DESIGN.md under a date and change the assertion in the same commit.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

const CSS = readFileSync(join(__dirname, "..", "src", "app", "globals.css"), "utf8");

// --------------------------------------------------------------------------
// Parsing
// --------------------------------------------------------------------------

/** Extract a `selector { ... }` body by brace matching, so nested rules cannot truncate it. */
function block(selector: string): string {
  const start = CSS.indexOf(selector);
  if (start === -1) throw new Error(`selector not found in globals.css: ${selector}`);
  const open = CSS.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < CSS.length; i++) {
    if (CSS[i] === "{") depth++;
    else if (CSS[i] === "}") {
      depth--;
      if (depth === 0) return CSS.slice(open + 1, i);
    }
  }
  throw new Error(`unbalanced braces after ${selector}`);
}

/** `--name: #hex` pairs. Several tokens share a line in this file, so the regex is global. */
function tokens(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;/g)) {
    out[m[1]] = m[2].toLowerCase();
  }
  return out;
}

/** `--name: rgba(r, g, b, a)` pairs — the washes and glass surfaces. */
function rgbaTokens(body: string): Record<string, [number, number, number, number]> {
  const out: Record<string, [number, number, number, number]> = {};
  for (const m of body.matchAll(/--([a-z0-9-]+)\s*:\s*rgba?\(([^)]*)\)\s*;/g)) {
    const parts = m[2].split(",").map((p) => Number(p.trim()));
    if (parts.length >= 3 && parts.every((n) => !Number.isNaN(n))) {
      out[m[1]] = [parts[0], parts[1], parts[2], parts[3] ?? 1];
    }
  }
  return out;
}

// --------------------------------------------------------------------------
// WCAG 2.2 relative luminance and contrast
// --------------------------------------------------------------------------

function rgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ];
}

function luminance([r, g, b]: [number, number, number]): number {
  const chan = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b);
}

function contrast(a: string | [number, number, number], b: string | [number, number, number]): number {
  const la = luminance(typeof a === "string" ? rgb(a) : a);
  const lb = luminance(typeof b === "string" ? rgb(b) : b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** Alpha-composite `over` (rgba) onto opaque `under` (hex). */
function composite(under: string, over: [number, number, number, number]): [number, number, number] {
  const [ur, ug, ub] = rgb(under);
  const [or_, og, ob, oa] = over;
  return [
    Math.round(or_ * oa + ur * (1 - oa)),
    Math.round(og * oa + ug * (1 - oa)),
    Math.round(ob * oa + ub * (1 - oa)),
  ];
}

const round2 = (n: number) => Math.round(n * 100) / 100;

// --------------------------------------------------------------------------
// The declared matrix — 7 inks x 9 surfaces, per DESIGN.md
// --------------------------------------------------------------------------

/**
 * `subtle-foreground` is deliberately absent: DESIGN.md scopes it to "large /
 * decorative only", so it answers to the 3:1 graphic floor, not the 4.5:1 body
 * floor. `memory-soft` is absent for the same reason (3.90:1, graphic only).
 * Adding either here would be testing a promise the design never made.
 */
const INKS = [
  "foreground",
  "muted-foreground",
  "accent-emphasis",
  "success-emphasis",
  "warning-emphasis",
  "danger-emphasis",
  "memory-emphasis",
] as const;

const SURFACE_TOKENS = [
  "surface",
  "surface-elevated",
  "surface-raised",
  "surface-alt",
  "surface-sunken",
  "accent-subtle",
  "success-subtle",
  "warning-subtle",
  "danger-subtle",
  "memory-subtle",
] as const;

/** DESIGN.md's floor for every ink on every surface it can occupy. */
const INK_FLOOR = 5.5;

const LIGHT = tokens(block(":root {"));
const DARK_MEDIA = tokens(block(':root:not([data-theme="light"])'));
const DARK_EXPLICIT = tokens(block(':root[data-theme="dark"]'));

function uniqueSurfaces(t: Record<string, string>): string[] {
  return [...new Set(SURFACE_TOKENS.map((s) => t[s]).filter(Boolean))];
}

function matrix(t: Record<string, string>) {
  const rows: { ink: string; surface: string; ratio: number }[] = [];
  for (const ink of INKS) {
    for (const surface of uniqueSurfaces(t)) {
      rows.push({ ink, surface, ratio: contrast(t[ink], surface) });
    }
  }
  return rows;
}

describe("palette — the light theme's declared figures", () => {
  it("declares nine unique surfaces, as DESIGN.md claims", () => {
    expect(uniqueSurfaces(LIGHT)).toHaveLength(9);
  });

  it("clears the 5.5:1 floor for all 7 inks on all 9 surfaces", () => {
    const failures = matrix(LIGHT)
      .filter((r) => r.ratio < INK_FLOOR)
      .map((r) => `${r.ink} on ${r.surface} = ${round2(r.ratio)}:1`);
    expect(failures).toEqual([]);
    expect(matrix(LIGHT)).toHaveLength(INKS.length * 9);
  });

  it("has a worst pairing of 5.54:1 — the figure DESIGN.md publishes", () => {
    const worst = Math.min(...matrix(LIGHT).map((r) => r.ratio));
    expect(round2(worst)).toBeCloseTo(5.54, 1);
  });

  it.each([
    ["foreground on white", "foreground", "#ffffff", 17.69],
    ["muted-foreground on white", "muted-foreground", "#ffffff", 7.6],
    ["accent-emphasis on white", "accent-emphasis", "#ffffff", 6.42],
    ["accent-emphasis on surface-sunken", "accent-emphasis", "#ebeff3", 5.55],
    ["memory-emphasis on white", "memory-emphasis", "#ffffff", 6.43],
  ])("matches the published figure: %s", (_label, ink, surface, expected) => {
    expect(round2(contrast(LIGHT[ink], surface))).toBeCloseTo(expected, 1);
  });

  it("keeps the two fills that carry a label above 4.5:1", () => {
    // accent takes a white label; amber is the one fill with a DARK label, because
    // an amber dark enough to hold white text has stopped reading as amber.
    expect(round2(contrast(LIGHT["accent"], LIGHT["accent-foreground"]))).toBeCloseTo(4.61, 1);
    expect(round2(contrast(LIGHT["warning"], LIGHT["warning-foreground"]))).toBeCloseTo(6.68, 1);
  });

  it("keeps memory-soft above the 3:1 graphic floor and below body-text use", () => {
    const ratio = contrast(LIGHT["memory-soft"], "#ffffff");
    expect(ratio).toBeGreaterThanOrEqual(3.0);
    expect(round2(ratio)).toBeCloseTo(3.9, 1);
  });
});

describe("palette — the dark theme's declared figures", () => {
  /**
   * DESIGN.md's dark paragraph makes two claims that cannot both hold: "each
   * coloured ink is solved for >=5.5:1" and "worst pairing 5.14:1", one sentence
   * apart. Measurement settles it — the 5.5 solve is true of the four BASE
   * surfaces, and the five `-subtle` washes sit lower, at 5.14 to 5.49.
   *
   * Nothing is inaccessible: every pairing clears the 4.5:1 AA floor that §6
   * actually mandates, which is why this went unnoticed. It is an over-claim, not
   * a defect — a figure true of one set of surfaces, generalised to all nine.
   * Asserted separately here so the distinction cannot quietly collapse again.
   * DESIGN.md is corrected to match in the same commit.
   */
  const BASE_SURFACES = ["surface", "surface-elevated", "surface-raised", "surface-alt"] as const;

  it("declares nine unique surfaces", () => {
    expect(uniqueSurfaces(DARK_EXPLICIT)).toHaveLength(9);
  });

  it("clears the WCAG 2.2 AA floor for all 7 inks on all 9 surfaces", () => {
    const failures = matrix(DARK_EXPLICIT)
      .filter((r) => r.ratio < 4.5)
      .map((r) => `${r.ink} on ${r.surface} = ${round2(r.ratio)}:1`);
    expect(failures).toEqual([]);
  });

  it("clears the 5.5:1 solve on the four base surfaces", () => {
    const bases = [...new Set(BASE_SURFACES.map((s) => DARK_EXPLICIT[s]))];
    const failures: string[] = [];
    for (const ink of INKS) {
      for (const surface of bases) {
        const ratio = contrast(DARK_EXPLICIT[ink], surface);
        if (ratio < INK_FLOOR) failures.push(`${ink} on ${surface} = ${round2(ratio)}:1`);
      }
    }
    expect(failures).toEqual([]);
  });

  it("keeps the -subtle washes in the 5.1-5.5 band they actually occupy", () => {
    const washes = ["accent-subtle", "success-subtle", "warning-subtle", "danger-subtle", "memory-subtle"];
    const ratios = INKS.flatMap((ink) => washes.map((w) => contrast(DARK_EXPLICIT[ink], DARK_EXPLICIT[w])));
    expect(Math.min(...ratios)).toBeGreaterThanOrEqual(5.1);
  });

  it("has a worst pairing of 5.14:1 — the figure DESIGN.md publishes", () => {
    const worst = Math.min(...matrix(DARK_EXPLICIT).map((r) => r.ratio));
    expect(round2(worst)).toBeCloseTo(5.14, 1);
  });
});

describe("palette — the two dark blocks cannot drift apart", () => {
  /**
   * Dark is declared twice on purpose: once under `prefers-color-scheme` for the
   * default "system" setting, once under `[data-theme="dark"]` so an explicit
   * toggle wins. They must stay identical — a token edited in one block and not
   * the other produces a theme that changes appearance depending on how the user
   * arrived at it, which no screenshot review would catch.
   */
  it("declares the same token set in both dark blocks", () => {
    expect(Object.keys(DARK_EXPLICIT).sort()).toEqual(Object.keys(DARK_MEDIA).sort());
  });

  it("declares the same value for every token in both dark blocks", () => {
    const drift = Object.keys(DARK_EXPLICIT)
      .filter((k) => DARK_EXPLICIT[k] !== DARK_MEDIA[k])
      .map((k) => `--${k}: ${DARK_MEDIA[k]} (media) vs ${DARK_EXPLICIT[k]} (data-theme)`);
    expect(drift).toEqual([]);
  });

  it("covers every token the light theme declares", () => {
    const missing = Object.keys(LIGHT).filter((k) => !(k in DARK_EXPLICIT));
    expect(missing).toEqual([]);
  });
});

describe("palette — the ambient wash does not spend the page ground's contrast", () => {
  /**
   * `body::before` paints two <=5% alpha radials over the page ground. Every figure
   * in DESIGN.md was computed against the *pure* surface token, so this checks the
   * composite that is actually on screen at the radial's centre — the strongest
   * point of the wash, before its falloff to transparent.
   */
  const LIGHT_RGBA = rgbaTokens(block(":root {"));
  const DARK_RGBA = rgbaTokens(block(':root[data-theme="dark"]'));

  it.each([
    ["light", LIGHT, LIGHT_RGBA],
    ["dark", DARK_EXPLICIT, DARK_RGBA],
  ])("keeps body inks above 4.5:1 on the washed ground (%s)", (_theme, t, washes) => {
    const ground = t["surface"];
    for (const wash of ["wash-a", "wash-b"]) {
      if (!washes[wash]) continue;
      const washed = composite(ground, washes[wash]);
      for (const ink of ["foreground", "muted-foreground"]) {
        expect(contrast(t[ink], washed)).toBeGreaterThanOrEqual(4.5);
      }
    }
  });
});

describe("gradients must be declared before they ship", () => {
  /**
   * The gradient ban was lifted 2026-08-13 (owner). What replaces it is a
   * register-and-measure rule: a gradient is a *range* of backgrounds, so a
   * contrast figure sampled at its midpoint always flatters it. Text over a
   * gradient is verified at the ramp's LIGHTEST point in light theme (its darkest
   * in dark), never its average.
   *
   * Every `gradient(` in globals.css must appear below. A new one fails this test
   * until its author states whether text sits on it, and proves the worst point.
   */
  const DECLARED: {
    match: string;
    carriesText: false | { textToken: string; lightestStop: string; floor: number };
    why: string;
  }[] = [
    {
      match: "radial-gradient(60rem 40rem at 12% -8%, var(--wash-a), transparent 60%)",
      carriesText: false,
      why: "body::before ambient ground wash, z-index -1, pointer-events none. No text is painted on it; page text sits on --surface above it, and that composite is asserted separately.",
    },
    {
      match: "radial-gradient(52rem 36rem at 92% 4%, var(--wash-b), transparent 62%)",
      carriesText: false,
      why: "the second ambient radial; same reasoning as wash-a.",
    },
  ];

  const found = [...CSS.matchAll(/[a-z-]*gradient\([^;]*?\)(?=[,;\s])/g)].map((m) => m[0].trim());

  it("has every gradient in globals.css registered here", () => {
    const unregistered = found.filter((g) => !DECLARED.some((d) => g.startsWith(d.match.slice(0, 40))));
    expect(unregistered).toEqual([]);
  });

  it("verifies text-bearing gradients at the ramp's worst point, not its midpoint", () => {
    const failures: string[] = [];
    for (const d of DECLARED) {
      if (d.carriesText === false) continue;
      const { textToken, lightestStop, floor } = d.carriesText;
      const ink = LIGHT[textToken] ?? textToken;
      const ratio = contrast(ink, lightestStop);
      if (ratio < floor) {
        failures.push(`${d.match}: ${textToken} on ${lightestStop} = ${round2(ratio)}:1, floor ${floor}`);
      }
    }
    expect(failures).toEqual([]);
  });
});
