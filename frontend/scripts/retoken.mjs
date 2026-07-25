#!/usr/bin/env node
/**
 * retoken — reconcile vendored shadcn-registry components with Meridian tokens.
 *
 * Most of shadcn's token vocabulary is bridged declaratively in
 * `src/app/shadcn-compat.css`. Two things cannot be:
 *
 *   1. `accent`. shadcn means "subtle hover surface"; Meridian means "ACTION
 *      blue". Meridian's meaning owns `--color-accent` (18 call sites), so the
 *      shadcn sense has to be rewritten out of vendored source instead.
 *   2. Radius utilities. Meridian's brief is controls 12px / cards 16px, but
 *      `rounded-md|lg` are already used at stock values by shipped components,
 *      so the scale can't be redefined globally — only rewritten locally here.
 *
 * Runs ONLY over the vendor directory. It must never touch `src/components/ui`
 * or any hand-authored Meridian component.
 *
 *   node scripts/retoken.mjs              # rewrite src/components/vendor
 *   node scripts/retoken.mjs --check      # report only, exit 1 if work remains
 *   node scripts/retoken.mjs path/to/dir  # explicit target
 */

import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

/**
 * Where registry output actually lands. shadcn routes each file by its declared
 * `type`, not by one alias, so a single directory is not enough:
 *   registry:ui        → the `ui` alias        → src/components/vendor
 *   registry:component → the `components` alias → src/components/<registry path>
 * Bklit's charts are `registry:component`, so they arrive outside vendor/.
 * Every root that exists is scanned; the rest are skipped silently.
 */
const DEFAULT_TARGETS = [
  "src/components/vendor",
  "src/components/charts",
  "src/components/animate-ui",
  "src/components/kokonutui",
  "src/charts",
];
const EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx"]);

/** Directories that hold hand-authored Meridian source. Never rewrite these. */
const PROTECTED = ["src/components/ui", "src/app", "src/lib"];

/**
 * Each rule matches a Tailwind class in isolation. The lookbehind/lookahead
 * pair is what keeps `bg-accent` from also eating `bg-accent-subtle` and
 * `bg-accent-hover`, which are legitimate Meridian tokens.
 */
const RULES = [
  {
    // shadcn hover/focus wash → Meridian's inset well tone.
    from: /(?<=^|[\s"'`:{])bg-accent(?![\w-])/g,
    to: "bg-surface-sunken",
    why: "shadcn `accent` is a hover surface; Meridian `accent` is ACTION blue",
  },
  {
    from: /(?<=^|[\s"'`:{])text-accent-foreground(?![\w-])/g,
    to: "text-foreground",
    why: "label on a hover wash is body text, not a label on blue",
  },
  {
    from: /(?<=^|[\s"'`:{])rounded-lg(?![\w-])/g,
    to: "rounded-[12px]",
    why: "Meridian control radius is 12px (DESIGN.md — Radius)",
  },
  {
    from: /(?<=^|[\s"'`:{])rounded-xl(?![\w-])/g,
    to: "rounded-[16px]",
    why: "Meridian card radius is 16px (DESIGN.md — Radius)",
  },
];

const args = process.argv.slice(2);
const checkOnly = args.includes("--check");
const explicit = args.filter((a) => !a.startsWith("--"));
const targets = explicit.length > 0 ? explicit : DEFAULT_TARGETS;
const root = process.cwd();

/**
 * The guard only applies to targets the caller named. The defaults are allowed
 * to sit under src/components/ (that is where shadcn puts things) — but an
 * explicit `retoken src/components/ui` must still be refused.
 */
if (explicit.length > 0) {
  for (const target of explicit) {
    const absTarget = resolve(root, target);
    for (const guard of PROTECTED) {
      const absGuard = resolve(root, guard);
      if (absTarget === absGuard || absTarget.startsWith(absGuard + "/")) {
        console.error(
          `refusing to rewrite ${target}: that is hand-authored Meridian source, ` +
            `not vendored registry output.`
        );
        process.exit(2);
      }
    }
  }
}

function walk(dir) {
  let out = [];
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const entry of entries) {
    if (entry === "node_modules" || entry.startsWith(".")) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out = out.concat(walk(full));
    } else if (EXTENSIONS.has(entry.slice(entry.lastIndexOf(".")))) {
      out.push(full);
    }
  }
  return out;
}

const files = targets.flatMap((t) => walk(resolve(root, t)));

/* ---------------------------------------------------------------------------
   Phase 2 — broken relative imports.

   Registries declare file paths against THEIR repo layout, and shadcn re-homes
   those files against OURS. When the two disagree in depth, relative imports
   between installed files break. Bklit is the live example: it ships
   `src/charts/*` and `src/components/shimmering-text.tsx` as siblings, so
   `../components/shimmering-text` is correct there — but shadcn puts the charts
   at `src/components/charts/`, where the same specifier overshoots into a
   `src/components/components/` that does not exist.

   This only ever touches imports that ALREADY fail to resolve (i.e. the build
   is broken anyway), and only rewrites when exactly one candidate file matches
   the basename. Ambiguous or unresolvable cases are reported, never guessed.
   --------------------------------------------------------------------------- */

const RESOLVE_EXTS = ["", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx"];
const IMPORT_RE = /(?<=from\s+["'])(\.[^"']+)(?=["'])/g;

function resolves(base) {
  return RESOLVE_EXTS.some((ext) => {
    try {
      return statSync(base + ext).isFile();
    } catch {
      return false;
    }
  });
}

/** basename (without extension) → absolute paths, across everything we scanned. */
const byBasename = new Map();
for (const file of files) {
  const stem = file.slice(file.lastIndexOf("/") + 1).replace(/\.(tsx?|jsx?)$/, "");
  if (!byBasename.has(stem)) byBasename.set(stem, []);
  byBasename.get(stem).push(file);
}
/* Registry deps can also land beside the vendor roots (Bklit drops
   shimmering-text straight into src/components/), so index that level too. */
for (const extraRoot of ["src/components", "src/lib", "src/hooks"]) {
  let entries = [];
  try {
    entries = readdirSync(resolve(root, extraRoot));
  } catch {
    continue;
  }
  for (const entry of entries) {
    if (!/\.(tsx?|jsx?)$/.test(entry)) continue;
    const full = join(resolve(root, extraRoot), entry);
    const stem = entry.replace(/\.(tsx?|jsx?)$/, "");
    if (!byBasename.has(stem)) byBasename.set(stem, []);
    if (!byBasename.get(stem).includes(full)) byBasename.get(stem).push(full);
  }
}

function repairImports(file, source) {
  const dir = file.slice(0, file.lastIndexOf("/"));
  const repairs = [];
  const out = source.replace(IMPORT_RE, (spec) => {
    if (resolves(resolve(dir, spec))) return spec;

    const stem = spec.slice(spec.lastIndexOf("/") + 1);
    const candidates = byBasename.get(stem) ?? [];
    if (candidates.length !== 1) {
      repairs.push({ spec, to: null, n: candidates.length });
      return spec;
    }

    let rel = relative(dir, candidates[0]).replace(/\.(tsx?|jsx?)$/, "");
    if (!rel.startsWith(".")) rel = "./" + rel;
    repairs.push({ spec, to: rel, n: 1 });
    return rel;
  });
  return { out, repairs };
}

if (files.length === 0) {
  console.log(
    `retoken: nothing to do — no vendored components found in:\n` +
      targets.map((t) => `           ${t}`).join("\n") +
      `\n         Install one first, e.g.\n` +
      `           npx shadcn@latest add @animate-ui/components-radix-tooltip`
  );
  process.exit(0);
}

let changedFiles = 0;
let totalHits = 0;
let importFixes = 0;
const importDetail = [];
const unresolvedImports = [];
const perRule = new Map(RULES.map((r) => [r.to, 0]));

for (const file of files) {
  const before = readFileSync(file, "utf8");
  let after = before;
  let fileHits = 0;

  for (const rule of RULES) {
    const hits = (after.match(rule.from) ?? []).length;
    if (hits === 0) continue;
    after = after.replace(rule.from, rule.to);
    fileHits += hits;

    perRule.set(rule.to, perRule.get(rule.to) + hits);
  }

  const { out, repairs } = repairImports(file, after);
  after = out;
  const fixed = repairs.filter((r) => r.to);
  const unresolved = repairs.filter((r) => !r.to);
  fileHits += fixed.length;
  importFixes += fixed.length;

  for (const r of unresolved) {
    unresolvedImports.push({ file, spec: r.spec, n: r.n });
  }
  for (const r of fixed) {
    importDetail.push({ file, from: r.spec, to: r.to });
  }

  if (fileHits === 0) continue;

  changedFiles += 1;
  totalHits += fileHits;
  const rel = relative(root, file);
  console.log(`${checkOnly ? "would rewrite" : "rewrote"} ${rel} (${fileHits})`);
  if (!checkOnly) writeFileSync(file, after, "utf8");
}

if (unresolvedImports.length > 0) {
  console.error("\nunresolved imports — fix these by hand:");
  for (const u of unresolvedImports) {
    const reason = u.n === 0 ? "no file with that name" : `${u.n} candidates, ambiguous`;
    console.error(`  ${relative(root, u.file)}\n    ${u.spec}  (${reason})`);
  }
}

if (totalHits === 0) {
  console.log(`retoken: ${files.length} file(s) scanned, already Meridian-clean.`);
  process.exit(unresolvedImports.length > 0 ? 1 : 0);
}

console.log("");
for (const rule of RULES) {
  const n = perRule.get(rule.to);
  if (n > 0) console.log(`  → ${rule.to.padEnd(20)} ${String(n).padStart(3)}   ${rule.why}`);
}
if (importFixes > 0) {
  console.log(
    `  → ${"import path".padEnd(20)} ${String(importFixes).padStart(3)}   ` +
      `registry layout re-homed by the shadcn CLI`
  );
  for (const d of importDetail) {
    console.log(`      ${relative(root, d.file)}: ${d.from} → ${d.to}`);
  }
}
console.log(
  `\nretoken: ${totalHits} replacement(s) across ${changedFiles} file(s).`
);

process.exit(checkOnly ? 1 : 0);
