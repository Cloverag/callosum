/**
 * @jest-environment node
 *
 * Node rather than the suite's default jsdom: this file constructs `Response`
 * objects, which jsdom does not provide and every browser does. Nothing here
 * renders, so there is no DOM to want.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { isDemoValue } from "@/demo/mode";
import { demoResponse } from "@/demo/router";

/**
 * Demo mode must be structurally incapable of the `lib/api.ts` failure.
 *
 * That failure was not "mock data existed". It was that the mock lived inside
 * the error path — `if (res.ok) return await res.json(); ... return mockConflicts`
 * — so the trigger for showing invented data was the API breaking. `GET
 * /api/conflicts` then 500ed for four days while the dashboard reported "2 name
 * conflicts awaiting your review" as measured fact.
 *
 * Three properties keep that unreachable, and this file asserts each of them
 * against the source rather than against behaviour where behaviour cannot
 * distinguish them:
 *
 *   (b) demo mode turns on for exactly one env value and nothing else
 *   (c) there is no path from a failed request into fixture data
 *   (d) when it is on, the banner is on — by construction, not by coincidence
 *
 * Ungated tier: no Postgres, no network, no dev server.
 */

const SRC = join(__dirname, "..", "src");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return walk(path);
    return /\.tsx?$/.test(path) ? [path] : [];
  });
}

const ALL_SOURCES = walk(SRC);
const read = (rel: string) => readFileSync(join(SRC, rel), "utf8");

/** Comments describe the rule; they must not satisfy it. */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

describe("(b) the env gate is exact", () => {
  // `isDemoValue` and not `DEMO_ENABLED`: the constant is resolved once at
  // module load from whatever the environment held, so asserting on it would
  // measure the test runner's environment. The predicate is the rule.
  it("is on only for the string \"1\"", () => {
    expect(isDemoValue("1")).toBe(true);
  });

  it.each([undefined, "", "0", "true", "TRUE", "yes", "on", " 1", "1 ", "01", "2"])(
    "is off for %p",
    (value) => {
      expect(isDemoValue(value as string | undefined)).toBe(false);
    },
  );

  it("does not use a truthiness check, which would make \"0\" turn it on", () => {
    // The regression this guards is specific: `Boolean(process.env.X)` is true
    // for "0", so an operator disabling demo mode would enable it.
    expect(isDemoValue("0")).toBe(false);
  });
});

describe("(d) the banner and the interception are one decision", () => {
  it("names the env variable exactly once in the whole of src/", () => {
    const hits = ALL_SOURCES.filter((file) =>
      stripComments(readFileSync(file, "utf8")).includes("NEXT_PUBLIC_MERIDIAN_DEMO"),
    );
    // A second read is how a build serves fixtures with the banner off. There is
    // no legitimate second reader: everything imports `DEMO_ENABLED`.
    expect(hits.map((f) => f.slice(SRC.length + 1))).toEqual(["demo/mode.ts"]);
  });

  it("has the banner and the transport importing the same binding", () => {
    for (const file of ["demo/banner.tsx", "demo/transport.ts"]) {
      expect(stripComments(read(file))).toMatch(
        /import\s*\{\s*DEMO_ENABLED\s*\}\s*from\s*"\.\/mode"/,
      );
    }
  });

  it("mounts the banner in the root layout", () => {
    const layout = stripComments(read("app/layout.tsx"));
    expect(layout).toContain("<DemoBanner />");
    // Unconditionally: the component decides, so the layout cannot hold a second
    // condition that could drift from the first.
    expect(layout).not.toMatch(/DEMO|process\.env/);
  });

  it("renders a full-width bar rather than a badge, and says the data is fabricated", () => {
    const banner = read("demo/banner.tsx");
    expect(banner).toMatch(/DEMO MODE/);
    expect(banner).toMatch(/fabricated/);
    expect(banner).toMatch(/position: "sticky"|position: "fixed"/);
  });
});

describe("(c) there is no route from a failure into fixtures", () => {
  const seamSource = stripComments(read("demo/transport.ts"));
  const routerSource = stripComments(read("demo/router.ts"));

  it("never calls fetch or reacts to a response inside the fixture module", () => {
    // The router answers from fixtures and must have no way to observe the
    // network at all — not to call it, not to catch it, not to read a status.
    expect(routerSource).not.toMatch(/\bfetch\s*\(/);
    expect(routerSource).not.toMatch(/\bcatch\b/);
    expect(routerSource).not.toMatch(/\.ok\b/);
  });

  it("keeps the fixtures out of a build that has demo mode off", () => {
    // The router is reached through a dynamic import inside `if (DEMO_ENABLED)`,
    // so the bundler drops it when the constant inlines to false. A static
    // import here compiled the fabricated board into the production client
    // chunk of a non-demo build — found by grepping `.next/static/chunks`.
    expect(seamSource).toMatch(/import\("\.\/router"\)/);
    expect(seamSource).not.toMatch(/^import .*from "\.\/router"/m);
    expect(seamSource).not.toMatch(/from "\.\/fixtures/);
  });

  it("branches on the constant alone, with no try/catch around the real call", () => {
    const seam = seamSource.slice(seamSource.indexOf("export function transport"));
    expect(seam).toMatch(/if \(DEMO_ENABLED\)/);
    expect(seam).not.toMatch(/\btry\b|\bcatch\b/);
    // One `fetch` in the seam, on the non-demo branch, reached only when the
    // constant is false.
    expect(seam.match(/\bfetch\s*\(/g)).toHaveLength(1);
  });

  it("routes every fetch in src/ through the seam, so no module can add its own", () => {
    const callers = ALL_SOURCES.filter((file) => {
      if (file.endsWith(join("demo", "transport.ts"))) return false;
      return /(?<!\.)\bfetch\s*\(/.test(stripComments(readFileSync(file, "utf8")));
    });
    // If this list grows, a surface has acquired a request that demo mode does
    // not intercept — which in demo mode means a real network call from a page
    // whose other data is fabricated.
    expect(callers).toEqual([]);
  });

  it("keeps the fixtures out of every lib module except the seam", () => {
    const importers = ALL_SOURCES.filter((file) => {
      if (!file.includes(join("src", "lib"))) return false;
      return /from "@\/demo\//.test(stripComments(readFileSync(file, "utf8")));
    }).map((f) => f.slice(SRC.length + 1));
    // `http.ts` and `auth.ts` hold the only two fetch call sites in the app, so
    // they are the only two legitimate importers. A third would be a per-module
    // fallback — the shape that failed before.
    expect(importers.sort()).toEqual(["lib/auth.ts", "lib/http.ts"]);
  });

  it("answers an unrouted path with a visible failure, not an empty list", () => {
    const response = demoResponse("/api/no-such-collection", "GET", undefined);
    expect(response.ok).toBe(false);
    expect(response.status).toBe(500);
  });

  it("refuses writes rather than pretending to record them", () => {
    const response = demoResponse("/api/conflicts/x/approve", "POST", undefined);
    // The old mock returned `{ status: 'approved' }` here and the card animated
    // away, telling the operator a merge had been written to an append-only
    // graph that was never touched.
    expect(response.ok).toBe(false);
    expect(response.status).toBe(405);
  });
});
