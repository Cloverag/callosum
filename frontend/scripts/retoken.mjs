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

const DEFAULT_TARGET = "src/components/vendor";
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
const target = args.find((a) => !a.startsWith("--")) ?? DEFAULT_TARGET;
const root = process.cwd();
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

const files = walk(absTarget);

if (files.length === 0) {
  console.log(
    `retoken: nothing to do — no components in ${target}.\n` +
      `         Install one first, e.g. npx shadcn@latest add @animate-ui/tooltip`
  );
  process.exit(0);
}

let changedFiles = 0;
let totalHits = 0;
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

  if (fileHits === 0) continue;

  changedFiles += 1;
  totalHits += fileHits;
  const rel = relative(root, file);
  console.log(`${checkOnly ? "would rewrite" : "rewrote"} ${rel} (${fileHits})`);
  if (!checkOnly) writeFileSync(file, after, "utf8");
}

if (totalHits === 0) {
  console.log(`retoken: ${files.length} file(s) scanned, already Meridian-clean.`);
  process.exit(0);
}

console.log("");
for (const rule of RULES) {
  const n = perRule.get(rule.to);
  if (n > 0) console.log(`  → ${rule.to.padEnd(20)} ${String(n).padStart(3)}   ${rule.why}`);
}
console.log(
  `\nretoken: ${totalHits} replacement(s) across ${changedFiles} file(s).`
);

process.exit(checkOnly ? 1 : 0);
